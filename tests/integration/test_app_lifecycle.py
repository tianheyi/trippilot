"""App factory assembly, startup validation and lifespan wiring."""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from trippilot import __version__
from trippilot.core.config import AppEnv, LogFormat, LogLevel, Settings
from trippilot.core.exceptions import ConfigurationError
from trippilot.core.runtime import Runtime
from trippilot.main import create_app


def test_factory_returns_a_configured_application(settings: Settings) -> None:
    app = create_app(settings)

    assert isinstance(app, FastAPI)
    assert app.title == "TripPilot"
    assert app.version == __version__

    runtime = app.state.runtime
    assert isinstance(runtime, Runtime)
    assert runtime.settings is settings


def test_factory_rejects_a_self_contradictory_configuration() -> None:
    """A bad deployment must fail at boot, not at the first request."""
    broken = Settings(app_env=AppEnv.PRODUCTION, debug=True, _env_file=None)

    with pytest.raises(ConfigurationError):
        create_app(broken)


def test_logging_is_configured_before_the_app_is_returned() -> None:
    create_app(Settings(log_level=LogLevel.DEBUG, log_format=LogFormat.JSON, _env_file=None))

    assert logging.getLogger().level == logging.DEBUG
    assert len(logging.getLogger().handlers) == 1


def test_lifespan_runs_startup_and_shutdown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Assert on stdout rather than caplog: configure_logging replaces the root
    handlers, which is exactly the behaviour under test."""
    app = create_app(Settings(log_level=LogLevel.INFO, log_format=LogFormat.JSON, _env_file=None))

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

    output = capsys.readouterr().out
    assert "application starting" in output
    assert "application stopping" in output


def test_no_database_engine_is_created_at_startup(settings: Settings) -> None:
    """Storage is not wired up yet; the app must not pretend otherwise."""
    app = create_app(settings)

    with TestClient(app):
        assert not hasattr(app.state, "db_engine")
        assert not hasattr(app.state, "session_factory")


def test_runtime_is_available_without_running_the_lifespan(settings: Settings) -> None:
    """Routes must work for a server that has not emitted startup yet."""
    app = create_app(settings)

    assert app.state.runtime.uptime_seconds >= 0
