"""Process-lifetime runtime state.

Lives in ``core`` (not ``api``) because both the app factory and the HTTP layer
need it, and ``core`` must stay importable without FastAPI. Holding settings in
one immutable value object -- rather than reaching into ``app.state`` by string
key from every route -- keeps access typed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from trippilot.core.config import Settings


@dataclass(frozen=True, slots=True)
class Runtime:
    """Immutable per-process state, created once by :func:`trippilot.main.create_app`."""

    settings: Settings
    version: str
    started_at: datetime

    @property
    def uptime_seconds(self) -> float:
        return (datetime.now(UTC) - self.started_at).total_seconds()
