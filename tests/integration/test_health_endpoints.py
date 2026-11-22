"""HTTP contract of the operational endpoints, exercised through the real app."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from trippilot import __version__

TRACE_HEADER = "X-Trace-Id"


@pytest.fixture
def app_with_probe_routes(app: FastAPI) -> FastAPI:
    """Attach throwaway routes so error mapping can be tested.

    The application deliberately ships no route that fails, so the failure
    paths are provoked from here instead of by weakening production code.
    """

    def explode() -> None:
        raise RuntimeError("database password hunter2 leaked")

    def echo_count(count: int) -> dict[str, int]:
        return {"count": count}

    app.add_api_route("/_probe/explode", explode, methods=["GET"], include_in_schema=False)
    app.add_api_route("/_probe/echo", echo_count, methods=["GET"], include_in_schema=False)
    return app


class TestHealth:
    async def test_returns_ok_with_a_stable_envelope(self, client: AsyncClient) -> None:
        response = await client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == "OK"
        assert body["data"]["status"] == "ok"
        assert body["data"]["service"] == "TripPilot"
        assert body["data"]["version"] == __version__
        assert body["data"]["environment"] == "local"
        assert body["data"]["uptimeSeconds"] >= 0

    async def test_body_trace_id_matches_the_response_header(self, client: AsyncClient) -> None:
        response = await client.get("/health")

        assert response.json()["traceId"] == response.headers[TRACE_HEADER]
        assert response.headers[TRACE_HEADER]

    async def test_liveness_does_not_depend_on_the_database(self, client: AsyncClient) -> None:
        """A liveness probe must keep succeeding while storage is unavailable."""
        response = await client.get("/health")

        assert response.status_code == 200


class TestReady:
    async def test_is_ready_because_nothing_required_is_missing(self, client: AsyncClient) -> None:
        response = await client.get("/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == "READY"
        assert body["data"]["status"] == "ready"

    async def test_reports_the_database_as_not_configured_rather_than_ok(
        self, client: AsyncClient
    ) -> None:
        """The honest answer: no connection exists, so no check can have passed."""
        response = await client.get("/ready")

        dependencies = response.json()["data"]["dependencies"]
        assert len(dependencies) == 1

        database = dependencies[0]
        assert database["name"] == "database"
        assert database["state"] == "not_configured"
        assert database["required"] is False
        assert "No database is wired up yet" in database["detail"]

    async def test_reports_configuration_presence_when_a_dsn_is_set(
        self, dsn_client: AsyncClient
    ) -> None:
        """A configured DSN is still not a verified connection, and says so."""
        response = await dsn_client.get("/ready")

        database = response.json()["data"]["dependencies"][0]
        assert database["state"] == "not_configured"
        assert "not connectivity" in database["detail"]

    async def test_checked_at_is_a_utc_timestamp(self, client: AsyncClient) -> None:
        response = await client.get("/ready")

        assert response.json()["data"]["checkedAt"].endswith("Z")


class TestTracePropagation:
    async def test_inbound_trace_id_is_reused(self, client: AsyncClient) -> None:
        response = await client.get("/health", headers={TRACE_HEADER: "caller-supplied-id"})

        assert response.headers[TRACE_HEADER] == "caller-supplied-id"
        assert response.json()["traceId"] == "caller-supplied-id"

    async def test_an_oversized_inbound_trace_id_is_replaced(self, client: AsyncClient) -> None:
        """Caller input lands in every log line, so its size is bounded."""
        response = await client.get("/health", headers={TRACE_HEADER: "x" * 500})

        assert response.headers[TRACE_HEADER] != "x" * 500
        assert len(response.headers[TRACE_HEADER]) == 32

    async def test_each_request_without_a_header_gets_a_distinct_id(
        self, client: AsyncClient
    ) -> None:
        first = await client.get("/health")
        second = await client.get("/health")

        assert first.headers[TRACE_HEADER] != second.headers[TRACE_HEADER]


class TestErrorEnvelope:
    async def test_unknown_route_uses_the_error_envelope(self, client: AsyncClient) -> None:
        response = await client.get("/does-not-exist")

        assert response.status_code == 404
        body = response.json()
        assert body["code"] == "NOT_FOUND"
        assert body["traceId"] == response.headers[TRACE_HEADER]
        assert "detail" not in body  # no bare FastAPI body may leak through

    async def test_validation_failure_is_reported_without_echoing_input(
        self, client: AsyncClient, app_with_probe_routes: FastAPI
    ) -> None:
        response = await client.get("/_probe/echo", params={"count": "not-a-number"})

        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert body["details"][0]["loc"] == ["query", "count"]
        assert "not-a-number" not in response.text

    async def test_unhandled_exception_is_mapped_to_an_opaque_500(
        self, client: AsyncClient, app_with_probe_routes: FastAPI
    ) -> None:
        response = await client.get("/_probe/explode")

        assert response.status_code == 500
        body = response.json()
        assert body["code"] == "INTERNAL_ERROR"
        assert body["message"] == "Internal server error."
        # The internal message and any traceback must not reach the client.
        assert "hunter2" not in response.text
        assert "RuntimeError" not in response.text
        # ...but the trace id still links the client report to the server log.
        assert body["traceId"]
        assert response.headers[TRACE_HEADER] == body["traceId"]


class TestSchema:
    async def test_openapi_document_describes_both_probes(self, client: AsyncClient) -> None:
        document = (await client.get("/openapi.json")).json()

        assert document["info"]["title"] == "TripPilot"
        assert "/health" in document["paths"]
        assert "/ready" in document["paths"]

    async def test_probe_routes_are_absent_from_the_published_schema(
        self, client: AsyncClient, app_with_probe_routes: FastAPI
    ) -> None:
        document = (await client.get("/openapi.json")).json()

        assert not [path for path in document["paths"] if path.startswith("/_probe")]
