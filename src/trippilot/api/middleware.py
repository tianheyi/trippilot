"""Trace-id middleware.

Written as a raw ASGI middleware rather than a ``BaseHTTPMiddleware`` subclass:
contextvars are read by the logging formatter several frames deeper, and raw
ASGI keeps the propagation semantics obvious.

What it does, per HTTP request:

1. Reuses an inbound trace header when present (so a trace continues across
   services), otherwise mints one.
2. Binds it to the contextvar that :mod:`trippilot.core.logging` reads.
3. Mirrors it onto ``scope["state"]`` so exception handlers -- which run after
   this middleware has already reset the contextvar -- can still report it.
4. Echoes it back as a response header.
"""

from __future__ import annotations

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from trippilot.core.logging import bind_trace_id, new_trace_id, reset_trace_id

_MAX_TRACE_ID_LENGTH = 128


class TraceIdMiddleware:
    """Bind a trace id for the duration of one request."""

    def __init__(self, app: ASGIApp, *, header_name: str = "X-Trace-Id") -> None:
        self.app = app
        self.header_name = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        trace_id = self._resolve_trace_id(scope)
        scope.setdefault("state", {})["trace_id"] = trace_id

        async def send_with_trace_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                # Exception handlers set this header themselves; do not duplicate.
                if self.header_name.lower() not in headers:
                    headers.append(self.header_name, trace_id)
            await send(message)

        token = bind_trace_id(trace_id)
        try:
            await self.app(scope, receive, send_with_trace_header)
        finally:
            reset_trace_id(token)

    def _resolve_trace_id(self, scope: Scope) -> str:
        """Trust an inbound header, but bound its length.

        Unsanitised caller input ends up in every log line and response header,
        so an oversized value is replaced rather than propagated.
        """
        inbound = Headers(scope=scope).get(self.header_name)
        if inbound and 0 < len(inbound) <= _MAX_TRACE_ID_LENGTH:
            return inbound
        return new_trace_id()
