"""Application factory and ASGI entry point.

Run locally with::

    uv run uvicorn trippilot.main:app --reload

The factory pattern (rather than a module-level singleton only) is what lets
tests build an app with explicit settings, and what will let the app be
constructed per-worker later without re-reading the environment.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from trippilot import __version__
from trippilot.api.errors import register_exception_handlers
from trippilot.api.middleware import TraceIdMiddleware
from trippilot.api.router import api_router
from trippilot.core.config import Settings, get_settings
from trippilot.core.logging import configure_logging, get_logger
from trippilot.core.runtime import Runtime

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hooks.

    Deliberately does not open a database connection: nothing uses storage yet,
    and creating a pool the code never reads would be theatre. This is where the
    engine, the checkpointer and the provider clients get created and disposed
    once they exist.
    """
    runtime: Runtime = app.state.runtime
    logger.info(
        "application starting",
        extra={
            "version": runtime.version,
            "environment": runtime.settings.app_env.value,
            "logFormat": runtime.settings.log_format.value,
        },
    )
    try:
        yield
    finally:
        logger.info("application stopping", extra={"uptimeSeconds": runtime.uptime_seconds})


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fully configured application.

    Raises :class:`~trippilot.core.exceptions.ConfigurationError` before the app is
    returned if the configuration is self-contradictory, so a bad deployment
    fails at boot instead of at the first request.
    """
    settings = settings or get_settings()
    settings.check_startup_requirements()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="AI travel planning agent for domestic (China) trips.",
        description=(
            "This service currently exposes operational endpoints only. "
            "Trip planning endpoints are not implemented yet."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    app.state.runtime = Runtime(
        settings=settings,
        version=__version__,
        started_at=datetime.now(UTC),
    )

    # Added before the exception handlers run, so routes and handlers can both
    # rely on the trace id being bound.
    app.add_middleware(TraceIdMiddleware, header_name=settings.trace_header)
    register_exception_handlers(app)
    app.include_router(api_router)

    return app


#: Module-level ASGI target for ``uvicorn trippilot.main:app``.
app = create_app()
