"""Wire format shared by every HTTP endpoint.

These models are the API contract, not the domain model. They may evolve
independently of ``domain/``: a field can be renamed here without touching
business rules, and a domain concept can be exposed in two different shapes.

JSON is camelCase (``traceId``, ``checkedAt``) because the future frontend is
React + TypeScript, where camelCase is idiomatic. Python code keeps
snake_case; :class:`CamelModel` bridges the two.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base for every request/response model.

    ``populate_by_name`` lets tests and internal callers construct these with
    snake_case field names while the wire format stays camelCase.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class ApiResponse[DataT](CamelModel):
    """Success envelope returned by every endpoint.

    A single envelope shape means the TypeScript client needs one generic type
    and one error path, rather than per-endpoint special cases.
    """

    code: str = Field(default="OK", description="Stable machine-readable outcome code.")
    message: str = Field(default="ok", description="Human-readable summary.")
    data: DataT | None = Field(default=None, description="Endpoint-specific payload.")
    trace_id: str = Field(description="Correlation id; also returned as a response header.")


class ErrorResponse(CamelModel):
    """Error envelope. ``code`` is the stable part; ``message`` may change."""

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable explanation, safe to display.")
    details: object | None = Field(
        default=None, description="Optional structured context. Never contains secrets."
    )
    trace_id: str = Field(description="Correlation id; also returned as a response header.")


class HealthStatus(StrEnum):
    """Liveness answer for the process itself."""

    OK = "ok"


class ReadinessStatus(StrEnum):
    """Whether the service can currently serve traffic."""

    READY = "ready"
    NOT_READY = "not_ready"


class DependencyState(StrEnum):
    """Per-dependency status reported by ``/ready``.

    ``NOT_CONFIGURED`` is deliberately distinct from ``DOWN``: it states that
    the dependency is not wired up yet, which is the honest answer for the
    database today, rather than claiming a check passed.
    """

    OK = "ok"
    NOT_CONFIGURED = "not_configured"
    DEGRADED = "degraded"
    DOWN = "down"


class DependencyStatus(CamelModel):
    """Status of one downstream dependency."""

    name: str = Field(description="Dependency identifier, e.g. 'database'.")
    state: DependencyState = Field(description="Observed state of the dependency.")
    required: bool = Field(
        description="When true, a non-ok state makes the whole service not ready."
    )
    detail: str | None = Field(default=None, description="Why the state is what it is.")


class HealthPayload(CamelModel):
    """Body of ``GET /health``. Proves the process is alive; nothing more."""

    status: HealthStatus = Field(default=HealthStatus.OK)
    service: str
    version: str
    environment: str
    uptime_seconds: float = Field(ge=0, description="Seconds since application startup.")


class ReadinessPayload(CamelModel):
    """Body of ``GET /ready``. Reports real dependency state, never assumed."""

    status: ReadinessStatus
    service: str
    version: str
    environment: str
    checked_at: datetime = Field(description="UTC timestamp of this check.")
    dependencies: list[DependencyStatus] = Field(
        description="One entry per dependency the service knows about."
    )
