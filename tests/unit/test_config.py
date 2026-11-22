"""Configuration loading, validation and fail-fast behaviour."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from trippilot.core.config import (
    AppEnv,
    LogFormat,
    LogLevel,
    Settings,
    environment_variable_name,
    get_settings,
)
from trippilot.core.exceptions import ConfigurationError


def make_settings(**overrides: Any) -> Settings:
    """Build settings isolated from any developer ``.env`` file.

    ``overrides`` is deliberately ``Any``: several tests feed values that are
    invalid *by design* to prove they are rejected, which a precise type would
    forbid at check time.
    """
    return Settings(_env_file=None, **overrides)


def test_defaults_target_local_development() -> None:
    settings = make_settings()

    assert settings.app_name == "TripPilot"
    assert settings.app_env is AppEnv.LOCAL
    assert settings.debug is False
    assert settings.log_level is LogLevel.INFO
    assert settings.log_format is LogFormat.CONSOLE
    assert settings.trace_header == "X-Trace-Id"
    # No storage is wired up at this stage, so an unset DSN is valid.
    assert settings.database_url is None


def test_values_are_read_from_prefixed_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRIPPILOT_APP_ENV", "staging")
    monkeypatch.setenv("TRIPPILOT_LOG_FORMAT", "json")
    monkeypatch.setenv("TRIPPILOT_DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/trippilot")

    settings = make_settings()

    assert settings.app_env is AppEnv.STAGING
    assert settings.log_format is LogFormat.JSON
    assert settings.database_url == "postgresql+asyncpg://u:p@db:5432/trippilot"


def test_unprefixed_environment_variables_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stray APP_ENV in the shell must not silently reconfigure the service."""
    monkeypatch.setenv("APP_ENV", "production")

    assert make_settings().app_env is AppEnv.LOCAL


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        make_settings(app_env="prod")

    message = str(excinfo.value)
    assert "app_env" in message
    assert "'local', 'staging' or 'production'" in message


def test_a_bad_value_from_the_environment_names_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator sees TRIPPILOT_APP_ENV, not the internal field name."""
    monkeypatch.setenv("TRIPPILOT_APP_ENV", "prod")
    get_settings.cache_clear()

    try:
        with pytest.raises(ConfigurationError) as excinfo:
            get_settings()
    finally:
        get_settings.cache_clear()

    assert "TRIPPILOT_APP_ENV" in str(excinfo.value)


def test_environment_variable_name_is_derived_from_the_field() -> None:
    assert environment_variable_name("database_url") == "TRIPPILOT_DATABASE_URL"
    assert environment_variable_name("log_level") == "TRIPPILOT_LOG_LEVEL"


def test_log_level_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRIPPILOT_LOG_LEVEL", "debug")

    assert make_settings().log_level is LogLevel.DEBUG


def test_unknown_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(log_level="chatty")


def test_blank_trace_header_is_rejected_at_construction() -> None:
    with pytest.raises(ValidationError):
        make_settings(trace_header="")


def test_valid_configuration_passes_startup_check() -> None:
    make_settings().check_startup_requirements()


def test_production_with_debug_enabled_fails_startup() -> None:
    settings = make_settings(app_env=AppEnv.PRODUCTION, debug=True)

    with pytest.raises(ConfigurationError) as excinfo:
        settings.check_startup_requirements()

    assert "TRIPPILOT_DEBUG" in str(excinfo.value)


def test_non_postgres_dsn_fails_startup() -> None:
    settings = make_settings(database_url="mysql://u:p@localhost:3306/trippilot")

    with pytest.raises(ConfigurationError) as excinfo:
        settings.check_startup_requirements()

    assert "PostgreSQL" in str(excinfo.value)
    # The DSN may contain credentials, so only the scheme is reported.
    assert "u:p" not in str(excinfo.value)


def test_startup_check_reports_every_problem_at_once() -> None:
    """One restart should surface every misconfiguration, not just the first."""
    settings = make_settings(
        app_env=AppEnv.PRODUCTION,
        debug=True,
        database_url="sqlite:///./trippilot.db",
    )

    with pytest.raises(ConfigurationError) as excinfo:
        settings.check_startup_requirements()

    details = excinfo.value.details
    assert isinstance(details, dict)
    assert len(details["problems"]) == 2


def test_api_key_is_never_rendered_in_plain_text() -> None:
    settings = make_settings(llm_api_key="sk-do-not-log-me")

    assert "sk-do-not-log-me" not in repr(settings)
    assert "sk-do-not-log-me" not in str(settings)
    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == "sk-do-not-log-me"


def test_get_settings_returns_a_cached_singleton() -> None:
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()
