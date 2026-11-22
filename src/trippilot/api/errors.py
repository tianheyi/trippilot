"""FastAPI exception handlers producing the uniform error envelope.

These live in ``api/`` rather than ``core/`` because they translate into HTTP
concepts; ``core/exceptions.py`` stays framework-free.

Guarantees, asserted by tests:

* Every error the client sees is the :class:`~trippilot.schemas.common.ErrorResponse`
  shape -- no bare FastAPI ``{"detail": ...}`` bodies leak out.
* The trace id is always present, in the body and in the response header, even
  for unhandled exceptions (read from ``request.state``, since the middleware
  has already reset the contextvar by then).
* Unexpected exceptions never leak a traceback or internal message.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from trippilot.core.exceptions import AppError
from trippilot.core.logging import get_logger
from trippilot.schemas.common import ErrorResponse

logger = get_logger(__name__)

#: Fallback codes for framework-raised errors that carry only a status code.
_STATUS_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_ERROR",
    502: "UPSTREAM_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def _trace_id(request: Request) -> str:
    """Trace id for a request, readable even after the contextvar is reset."""
    from_state = getattr(request.state, "trace_id", None)
    if isinstance(from_state, str) and from_state:
        return from_state
    return ""


def _trace_header(request: Request) -> dict[str, str]:
    """Response header carrying the trace id, when the app is configured."""
    runtime = getattr(request.app.state, "runtime", None)
    header_name = getattr(getattr(runtime, "settings", None), "trace_header", "X-Trace-Id")
    return {str(header_name): _trace_id(request)}


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        code=code,
        message=message,
        details=details,
        trace_id=_trace_id(request),
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(by_alias=True, mode="json"),
        headers=_trace_header(request),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the handlers. Called once by the app factory."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "application error",
            extra={"errorCode": exc.code, "path": request.url.path},
        )
        return _error_response(
            request,
            status_code=exc.http_status,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Only loc/msg/type are echoed. The offending input is deliberately
        # omitted: it is caller-supplied text that would otherwise be copied
        # into client-visible payloads and log lines verbatim.
        details = [
            {
                "loc": list(error.get("loc", ())),
                "msg": error.get("msg", ""),
                "type": error.get("type", ""),
            }
            for error in exc.errors()
        ]
        logger.info(
            "request validation failed",
            extra={"path": request.url.path, "errorCount": len(details)},
        )
        return _error_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request payload failed validation.",
            details=details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error_response(
            request,
            status_code=exc.status_code,
            code=_STATUS_CODES.get(exc.status_code, "HTTP_ERROR"),
            message=str(exc.detail),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Logged in full for operators; the client gets a fixed message.
        logger.exception(
            "unhandled exception",
            extra={"path": request.url.path, "exceptionType": type(exc).__name__},
        )
        return _error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="Internal server error.",
        )
