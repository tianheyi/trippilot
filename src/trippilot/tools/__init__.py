"""Agent tools: the business actions the agent is allowed to invoke.

Not implemented yet. This package holds only this docstring until the first tool
lands (AGENTS.md §3). Planned members, per AGENTS.md §4.4:

    registry.py   tool registration and lookup
    search.py     POI / attraction search
    weather.py    forecast lookups
    maps.py       geocoding and route planning

Every tool must declare, explicitly (AGENTS.md §4.4 and §8):

    * name and purpose
    * input parameters and their schema
    * the shape of what it returns
    * which error types it raises and how they are handled
    * its timeout and retry policy
    * the permissions and business checks it enforces

Forbidden
    * Calling back into the whole graph.
    * Depending on ``api/``.
    * Forming a cycle with the agent through ``services/``.
    * Treating unvalidated external content as instructions.
    * Executing irreversible bookings or payments before explicit human
      confirmation.

The full contract -- ``ToolResult`` metadata (source, ``fetched_at``,
``expires_at``), error classification, retry bounds and cache keys -- is
specified in docs/contracts/tool-contracts.md. Implement to that document, and
start from mocks so the evaluation loop closes before any real provider is
selected (ADR-0007).

Dependency direction (AGENTS.md §5): ``agent/`` may depend on ``tools/``; the
reverse is not allowed. Outbound calls go through clients obtained from
``infrastructure/``, never created inline.
"""
