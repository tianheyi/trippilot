"""Application services: the use-case layer between HTTP and the agent.

Not implemented yet. This package exists so that the first business use case has
a defined home; it stays a docstring until then (AGENTS.md §3).

Responsibility (AGENTS.md §4.2)
    Orchestrate use cases -- start a conversation, continue one, generate an
    itinerary, confirm one. Call the agent and supply its runtime context.
    Coordinate domain rules with business-data access. Own user permission
    checks, transaction boundaries and application-level exceptions. Translate
    the result into what ``api/`` needs to serialise.

Forbidden here
    * Binding a concrete database SDK or model-provider SDK.
    * Re-implementing LangGraph's node/edge traversal -- that lives in ``agent/``.
    * Taking HTTP framework objects as core business parameters.

Dependency direction (AGENTS.md §5): ``api/`` -> ``services/`` -> ``agent/``,
plus ``domain/`` and repository abstractions from ``domain/ports/``.
"""
