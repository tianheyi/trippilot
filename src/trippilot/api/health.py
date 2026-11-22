"""Liveness and readiness probes.

``/health`` answers "is this process alive?" and nothing else. It must stay
cheap and dependency-free, because an orchestrator restarts the container when
it fails.

``/ready`` answers "can this process serve traffic right now?" and reports the
real state of each known dependency. It never reports a dependency as healthy
on the basis of configuration alone -- see ``_dependency_statuses``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Response, status

from trippilot.api.dependencies import RuntimeDep, current_trace_id
from trippilot.core.config import Settings
from trippilot.schemas.common import (
    ApiResponse,
    DependencyState,
    DependencyStatus,
    HealthPayload,
    HealthStatus,
    ReadinessPayload,
    ReadinessStatus,
)

router = APIRouter(tags=["health"])

#: Name of the dependency reported by /ready today. Extending /ready means
#: adding entries here; nothing else needs to change.
_DATABASE = "database"


def _dependency_statuses(settings: Settings) -> list[DependencyStatus]:
    """Report each dependency's *actual* state.

    The database is reported as ``not_configured`` unconditionally. That is the
    truthful answer: no engine is created and no connection is opened at this
    stage of the project, so there is nothing to probe. It is deliberately not
    reported as ``ok``, and it is marked ``required=False`` because the API can
    serve every endpoint it currently exposes without storage. Both values flip
    when the first repository lands.
    """
    if settings.database_url is None:
        database_detail = (
            "No database is wired up yet: TRIPPILOT_DATABASE_URL is unset and "
            "infrastructure/persistence/ has no implementation."
        )
    else:
        database_detail = (
            "TRIPPILOT_DATABASE_URL is set but no connection is opened yet; "
            "this reports configuration presence, not connectivity."
        )

    return [
        DependencyStatus(
            name=_DATABASE,
            state=DependencyState.NOT_CONFIGURED,
            required=False,
            detail=database_detail,
        )
    ]


@router.get(
    "/health",
    response_model=ApiResponse[HealthPayload],
    summary="Liveness probe",
    description="Returns 200 whenever the process is running. Performs no I/O.",
)
async def health(runtime: RuntimeDep) -> ApiResponse[HealthPayload]:
    return ApiResponse[HealthPayload](
        code="OK",
        message="service is alive",
        data=HealthPayload(
            status=HealthStatus.OK,
            service=runtime.settings.app_name,
            version=runtime.version,
            environment=runtime.settings.app_env.value,
            uptime_seconds=runtime.uptime_seconds,
        ),
        trace_id=current_trace_id(),
    )


@router.get(
    "/ready",
    response_model=ApiResponse[ReadinessPayload],
    summary="Readiness probe",
    description=(
        "Returns 200 when every *required* dependency is available, otherwise 503. "
        "Dependency states are reported individually and are never assumed."
    ),
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "A required dependency is unavailable."
        }
    },
)
async def readiness(runtime: RuntimeDep, response: Response) -> ApiResponse[ReadinessPayload]:
    dependencies = _dependency_statuses(runtime.settings)
    is_ready = all(
        dependency.state is DependencyState.OK for dependency in dependencies if dependency.required
    )

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ApiResponse[ReadinessPayload](
        code="READY" if is_ready else "NOT_READY",
        message="service is ready" if is_ready else "a required dependency is unavailable",
        data=ReadinessPayload(
            status=ReadinessStatus.READY if is_ready else ReadinessStatus.NOT_READY,
            service=runtime.settings.app_name,
            version=runtime.version,
            environment=runtime.settings.app_env.value,
            checked_at=datetime.now(UTC),
            dependencies=dependencies,
        ),
        trace_id=current_trace_id(),
    )
