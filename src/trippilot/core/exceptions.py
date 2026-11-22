"""Application error taxonomy and the HTTP mapping for it.

Rules (see AGENTS.md):
  * Business code raises :class:`AppError` subclasses, never ``HTTPException``.
    ``HTTPException`` couples ``domain/`` to FastAPI, which the layering rules
    forbid.
  * Every error carries a stable machine-readable ``code`` that clients and
    evals can assert on. The human-readable ``message`` is allowed to change.
  * ``details`` must never contain secrets, credentials or full raw user input.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for every error TripPilot raises deliberately."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


class ConfigurationError(AppError):
    """Raised at startup when configuration is missing or self-contradictory.

    Failing fast here is intentional: the process should refuse to boot rather
    than serve traffic with a half-configured dependency (AGENTS.md 4.4).
    """

    code = "CONFIGURATION_ERROR"
    http_status = 500


class DomainError(AppError):
    """Base class for business-rule violations. Pure: imports no framework."""

    code = "DOMAIN_ERROR"
    http_status = 422


class NotFoundError(AppError):
    """A requested resource does not exist."""

    code = "NOT_FOUND"
    http_status = 404


class UpstreamError(AppError):
    """An external tool or provider failed after its retry budget was spent."""

    code = "UPSTREAM_ERROR"
    http_status = 502
