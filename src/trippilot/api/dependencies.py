"""FastAPI dependency accessors.

These are the only sanctioned ways for a route to reach process state. Routes
must not poke at ``request.app.state`` directly by string key.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from trippilot.core.logging import get_trace_id
from trippilot.core.runtime import Runtime


def get_runtime(request: Request) -> Runtime:
    """Return the runtime created by :func:`trippilot.main.create_app`.

    Raises ``RuntimeError`` rather than a domain error: reaching this with no
    runtime means the app was assembled incorrectly, which is a programming
    error, not a client-facing condition.
    """
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, Runtime):
        raise RuntimeError(
            "Runtime is not initialised on app.state. Build the ASGI app via "
            "trippilot.main.create_app()."
        )
    return runtime


#: Annotated alias so route signatures stay short and typed.
RuntimeDep = Annotated[Runtime, Depends(get_runtime)]


def current_trace_id() -> str:
    """Trace id for the in-flight request.

    Bound by ``TraceIdMiddleware``, so it is non-empty for any request that
    reached a route. The empty-string fallback only applies to code calling a
    route function directly, outside the ASGI stack.
    """
    return get_trace_id() or ""
