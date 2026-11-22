"""Structured logging: trace-id propagation and record shape.

Records are collected through an in-memory stream attached directly to the
logger under test, rather than through ``capsys``. pytest's capture fixtures
activate *after* a logger fixture has already been constructed, so a handler
built in a fixture would bind the pre-capture ``sys.stdout`` and silently
capture nothing.
"""

from __future__ import annotations

import io
import json
import logging
import sys
from typing import Any

import pytest

from trippilot.core.config import LogFormat, Settings
from trippilot.core.logging import (
    ConsoleFormatter,
    JsonFormatter,
    bind_trace_id,
    configure_logging,
    get_logger,
    get_trace_id,
    new_trace_id,
    reset_trace_id,
)


class RecordingLogger:
    """A logger whose output is readable directly, with no capture involved."""

    def __init__(
        self, name: str, formatter: logging.Formatter, *, level: int = logging.DEBUG
    ) -> None:
        self.stream = io.StringIO()
        self.logger = logging.getLogger(name)
        self.logger.handlers.clear()
        # Keep these records out of the root logger, which other tests touch.
        self.logger.propagate = False

        handler = logging.StreamHandler(self.stream)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(level)

    @property
    def output(self) -> str:
        return self.stream.getvalue()

    @property
    def lines(self) -> list[str]:
        return [line for line in self.output.splitlines() if line]

    def last_json(self) -> dict[str, Any]:
        parsed = json.loads(self.lines[-1])
        assert isinstance(parsed, dict)
        return parsed


@pytest.fixture
def json_log() -> RecordingLogger:
    return RecordingLogger(
        "trippilot.tests.json", JsonFormatter(service="TripPilot", environment="local")
    )


@pytest.fixture
def console_log() -> RecordingLogger:
    return RecordingLogger("trippilot.tests.console", ConsoleFormatter(), level=logging.INFO)


class TestTraceIdContext:
    def test_no_trace_id_outside_a_bound_context(self) -> None:
        assert get_trace_id() is None

    def test_binding_and_resetting_restores_the_previous_value(self) -> None:
        token = bind_trace_id("abc123")
        assert get_trace_id() == "abc123"

        reset_trace_id(token)
        assert get_trace_id() is None

    def test_generated_ids_are_unique(self) -> None:
        assert new_trace_id() != new_trace_id()


class TestJsonFormatter:
    def test_record_carries_the_trace_id_and_extras(self, json_log: RecordingLogger) -> None:
        token = bind_trace_id("trace-under-test")
        try:
            json_log.logger.info("trip parsed", extra={"destination": "长沙", "days": 3})
        finally:
            reset_trace_id(token)

        record = json_log.last_json()

        assert record["message"] == "trip parsed"
        assert record["level"] == "INFO"
        assert record["logger"] == "trippilot.tests.json"
        assert record["traceId"] == "trace-under-test"
        assert record["service"] == "TripPilot"
        assert record["environment"] == "local"
        assert record["context"] == {"destination": "长沙", "days": 3}

    def test_unbound_request_renders_a_null_trace_id(self, json_log: RecordingLogger) -> None:
        json_log.logger.info("startup")

        assert json_log.last_json()["traceId"] is None

    def test_non_ascii_is_not_escaped(self, json_log: RecordingLogger) -> None:
        json_log.logger.info("目的地解析完成")

        assert "目的地解析完成" in json_log.output

    def test_exception_records_include_the_traceback(self, json_log: RecordingLogger) -> None:
        try:
            raise ValueError("upstream exploded")
        except ValueError:
            json_log.logger.exception("tool call failed")

        assert "upstream exploded" in str(json_log.last_json()["exception"])

    def test_unserialisable_extras_do_not_break_the_log_line(
        self, json_log: RecordingLogger
    ) -> None:
        json_log.logger.info("odd payload", extra={"when": object()})

        assert isinstance(json_log.last_json()["context"], dict)

    def test_records_without_extras_omit_the_context_key(self, json_log: RecordingLogger) -> None:
        json_log.logger.info("plain")

        assert "context" not in json_log.last_json()


class TestConsoleFormatter:
    def test_line_includes_level_logger_and_trace_id(self, console_log: RecordingLogger) -> None:
        token = bind_trace_id("console-trace")
        try:
            console_log.logger.warning("careful", extra={"destination": "长沙"})
        finally:
            reset_trace_id(token)

        output = console_log.output
        assert "WARNING" in output
        assert "trippilot.tests.console" in output
        assert "[trace=console-trace]" in output
        assert "destination='长沙'" in output

    def test_missing_trace_id_renders_a_placeholder(self, console_log: RecordingLogger) -> None:
        console_log.logger.info("no request context")

        assert "[trace=-]" in console_log.output

    def test_exception_is_appended_to_the_line(self, console_log: RecordingLogger) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            console_log.logger.exception("failed")

        assert "ValueError: boom" in console_log.output


class TestConfigureLogging:
    def test_installs_exactly_one_root_handler(self) -> None:
        configure_logging(Settings(log_format=LogFormat.JSON, _env_file=None))
        configure_logging(Settings(log_format=LogFormat.JSON, _env_file=None))

        assert len(logging.getLogger().handlers) == 1

    def test_root_level_follows_the_settings(self) -> None:
        configure_logging(Settings(log_level="WARNING", _env_file=None))

        assert logging.getLogger().level == logging.WARNING

    def test_handler_writes_to_stdout_so_container_logs_are_captured(self) -> None:
        configure_logging(Settings(_env_file=None))

        handler = logging.getLogger().handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream is sys.stdout

    def test_uvicorn_loggers_propagate_to_the_root_handler(self) -> None:
        configure_logging(Settings(_env_file=None))

        uvicorn_logger = logging.getLogger("uvicorn.error")
        assert uvicorn_logger.propagate is True
        assert uvicorn_logger.handlers == []

    def test_get_logger_returns_a_namespaced_logger(self) -> None:
        assert get_logger("trippilot.some.module").name == "trippilot.some.module"
