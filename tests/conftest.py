"""Shared fixtures.

Two deliberate choices:

* Settings are constructed explicitly with ``_env_file=None`` so a developer's
  local ``.env`` can never change the outcome of a test.
* HTTP tests go through the real ASGI app via ``httpx.ASGITransport``. Nothing
  is mocked at the transport layer, so routing, middleware and exception
  handlers are all exercised.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from trippilot.core.config import AppEnv, LogFormat, LogLevel, Settings
from trippilot.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Quiet, local-environment settings, isolated from the real environment."""
    return Settings(
        app_env=AppEnv.LOCAL,
        debug=False,
        log_level=LogLevel.WARNING,
        log_format=LogFormat.JSON,
        _env_file=None,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async client over the ASGI app.

    ``raise_app_exceptions=False`` so the unhandled-error test observes the
    mapped 500 response instead of the propagating exception; every other test
    asserts a status code, which would fail loudly anyway.
    """
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest.fixture
async def dsn_client() -> AsyncIterator[AsyncClient]:
    """Client for an app built with a database DSN configured.

    Exists so /ready's "configured but not connected" branch is covered without
    pretending a connection was made.
    """
    app = create_app(
        Settings(
            database_url="postgresql+asyncpg://trippilot:trippilot@localhost:5432/trippilot",
            log_level=LogLevel.WARNING,
            _env_file=None,
        )
    )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest.fixture
def sync_client(app: FastAPI) -> Iterator[TestClient]:
    """Sync client used only where the lifespan must actually run."""
    with TestClient(app) as test_client:
        yield test_client
