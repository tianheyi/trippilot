"""Aggregate HTTP router.

Operational endpoints (``/health``, ``/ready``) are mounted at the root, which
is where orchestrators and load balancers expect them. Business endpoints will
mount under a versioned prefix (``/api/v1/...``) once they exist; the prefix is
not defined here yet because an empty router would be dead code. See
docs/architecture/overview.md.
"""

from __future__ import annotations

from fastapi import APIRouter

from trippilot.api import health

api_router = APIRouter()
api_router.include_router(health.router)

__all__ = ["api_router"]
