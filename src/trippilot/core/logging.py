"""Structured logging with a request-scoped trace id.

There is exactly one way to log in this codebase::

    from trippilot.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("trip parsed", extra={"destination": "长沙", "days": 3})

Two output formats are supported. ``console`` is for humans reading a terminal;
``json`` is one object per line and is what production and CI should use.

The trace id lives in a :mod:`contextvars` variable rather than being threaded
through call signatures, so code several layers down (domain helpers, tools,
future LangGraph nodes) can log a correlated line without receiving it as an
argument. Inbound ``X-Trace-Id`` headers are honoured, so a trace survives
across service boundaries; this is the hook a real tracing backend
(OpenTelemetry, LangSmith, ...) will attach to later -- see
``src/trippilot/infrastructure/observability/``.

Never pass secrets, credentials or full raw user input as ``extra`` values.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from trippilot.core.config import LogFormat, Settings

_trace_id_var: ContextVar[str | None] = ContextVar("trippilot_trace_id", default=None)

#: Attributes present on every LogRecord; anything outside this set was passed
#: by the caller via ``extra=`` and is worth serialising.
_RESERVED_ATTRS: frozenset[str] = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "taskName"}


def new_trace_id() -> str:
    """Generate a fresh trace id (32 hex chars, no dashes)."""
    return uuid4().hex


def get_trace_id() -> str | None:
    """Return the trace id bound to the current context, if any."""
    return _trace_id_var.get()


def bind_trace_id(trace_id: str) -> Token[str | None]:
    """Bind *trace_id* to the current context. Pass the result to reset it."""
    return _trace_id_var.set(trace_id)


def reset_trace_id(token: Token[str | None]) -> None:
    """Undo a previous :func:`bind_trace_id`."""
    _trace_id_var.reset(token)


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in record.__dict__.items() if k not in _RESERVED_ATTRS}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the trace id and any ``extra`` fields."""

    def __init__(self, *, service: str, environment: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self._service,
            "environment": self._environment,
            "traceId": get_trace_id(),
        }
        extras = _extras(record)
        if extras:
            payload["context"] = extras
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # default=str keeps an unexpected value type from killing the log line.
        return json.dumps(payload, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """Compact single-line format for local development."""

    def format(self, record: logging.LogRecord) -> str:
        trace_id = get_trace_id() or "-"
        line = (
            f"{datetime.fromtimestamp(record.created, tz=UTC).isoformat()} "
            f"{record.levelname:<8} {record.name} [trace={trace_id}] "
            f"{record.getMessage()}"
        )
        extras = _extras(record)
        if extras:
            line += " " + " ".join(f"{k}={v!r}" for k, v in extras.items())
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(settings: Settings) -> None:
    """Install the root handler. Safe to call repeatedly (tests call it a lot).

    Uvicorn installs its own handlers; we clear them and let its loggers
    propagate to the root handler so that framework lines get the same format
    and trace id as application lines.
    """
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format is LogFormat.JSON:
        handler.setFormatter(
            JsonFormatter(service=settings.app_name, environment=settings.app_env.value)
        )
    else:
        handler.setFormatter(ConsoleFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(settings.log_level.value)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger. Use ``get_logger(__name__)`` at module scope."""
    return logging.getLogger(name)
