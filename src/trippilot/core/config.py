"""Runtime configuration.

Every tunable value enters the process here. No other module reads
``os.environ`` directly -- that is what makes the "no scattered API keys, model
names or DSNs" rule from AGENTS.md 4.4 reviewable by grep.

Environment variables are prefixed with ``TRIPPILOT_`` (e.g.
``TRIPPILOT_LOG_LEVEL``). A local ``.env`` file is read when present; it is
git-ignored, and ``.env.example`` documents the expected keys.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from trippilot.core.exceptions import ConfigurationError

_POSTGRES_SCHEMES = ("postgresql://", "postgresql+asyncpg://")


class AppEnv(StrEnum):
    """Deployment environment. Drives how strict startup validation is."""

    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(StrEnum):
    """``json`` for machines (production/CI), ``console`` for humans (local)."""

    JSON = "json"
    CONSOLE = "console"


class Settings(BaseSettings):
    """Application settings, validated at construction time."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TRIPPILOT_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "TripPilot"
    app_env: AppEnv = AppEnv.LOCAL
    debug: bool = False

    log_level: LogLevel = LogLevel.INFO
    log_format: LogFormat = LogFormat.CONSOLE

    # Request header carrying the correlation id. Inbound values are honoured
    # so a trace survives across services; absent ones are generated.
    trace_header: str = Field(default="X-Trace-Id", min_length=1)

    # Optional today: SQLAlchemy is a declared dependency but the application
    # does not open a connection yet, so this may legitimately be unset. It
    # becomes required once repositories/ get their first real implementation.
    database_url: str | None = None

    # --- Reserved for the LLM layer, deliberately unconsumed for now ---------
    # Declared here so that model/provider configuration has exactly one home
    # when the agent lands, and so the SecretStr convention is established
    # before real keys exist. Nothing reads these fields yet.
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        """Accept ``debug`` as well as ``DEBUG`` so .env files are forgiving."""
        return value.upper() if isinstance(value, str) else value

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    @property
    def is_local(self) -> bool:
        return self.app_env is AppEnv.LOCAL

    def check_startup_requirements(self) -> None:
        """Fail fast on configuration that is present but self-contradictory.

        Pydantic already rejects malformed values (an unknown ``APP_ENV`` is a
        validation error at construction). What it cannot express is
        cross-field intent, which is what this method covers. Every problem is
        collected before raising so the operator sees the whole list at once
        instead of fixing them one restart at a time.
        """
        problems: list[str] = []

        if self.is_production and self.debug:
            problems.append("TRIPPILOT_DEBUG must be false when TRIPPILOT_APP_ENV=production")

        if self.database_url is not None and not self.database_url.startswith(_POSTGRES_SCHEMES):
            problems.append(
                "TRIPPILOT_DATABASE_URL must be a PostgreSQL DSN starting with "
                f"one of {_POSTGRES_SCHEMES!r}; got {self.database_url.split(':', 1)[0]!r}"
            )

        if not self.trace_header.strip():
            problems.append("TRIPPILOT_TRACE_HEADER must not be blank")

        if problems:
            raise ConfigurationError(
                "Invalid TripPilot configuration:\n  - " + "\n  - ".join(problems),
                details={"problems": problems},
            )


def environment_variable_name(field_name: str) -> str:
    """Map a settings field name to the environment variable that feeds it."""
    return f"{Settings.model_config['env_prefix']}{field_name}".upper()


def _describe(exc: ValidationError) -> str:
    """Turn a Pydantic error into an operator-facing message.

    Pydantic reports the *field* (``app_env``). An operator staring at a
    container that will not boot needs the *variable* (``TRIPPILOT_APP_ENV``),
    so each error is rewritten in those terms.
    """
    lines: list[str] = []
    for error in exc.errors():
        location = error.get("loc") or ("<unknown>",)
        variable = environment_variable_name(str(location[0]))
        lines.append(f"{variable}: {error.get('msg', 'invalid value')}")
    return "Invalid TripPilot configuration:\n  - " + "\n  - ".join(lines)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so that import-time callers and request-time callers agree. Tests
    that need different values should either construct ``Settings(...)``
    directly or call ``get_settings.cache_clear()``.

    Raises :class:`ConfigurationError` naming the offending environment
    variables, so a misconfigured deployment reports what to fix rather than a
    raw validation dump.
    """
    try:
        return Settings()
    except ValidationError as exc:
        raise ConfigurationError(_describe(exc), details={"problems": exc.errors()}) from exc
