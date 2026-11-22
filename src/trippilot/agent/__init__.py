"""Agent orchestration: the decision flow and its state transitions.

Not implemented yet. This package holds only this docstring until the workflow
lands (AGENTS.md §3). The shape it will take, per AGENTS.md §4.3:

    graph.py      builds and compiles the LangGraph -- nodes, edges,
                  conditional routing, interrupt points
    state.py      the graph state's fields, types and update conventions
    nodes/        intent detection, slot extraction, itinerary planning,
                  tool-result summarisation, confirmation
    prompts/      system and task prompts, version-controlled together
    policies.py   routing, termination and retry policies -- testable ones

Requirements that bind the implementation
    * Nodes stay single-purpose so each can be tested on its own.
    * Nodes must not import ``api/``.
    * Nodes must not create global database connections or model clients;
      side effects go through a tool or an explicitly injected dependency.
    * Do not pile the logic into ``graph.py``.

State (AGENTS.md §7) is split three ways, and the distinction is load-bearing:

    graph execution state      -> state.py, workflow progress only
    conversation persistence   -> LangGraph Checkpointer, keyed by thread_id
    business data              -> domain models via a repository

Never put connection objects, HTTP requests, client instances or secrets into
graph state. A Checkpointer is not a business database, and a ``thread_id``
locates a conversation -- it is not an identity credential.

Planned flow (one graph, not a multi-agent system -- see ADR-0006)::

    parse_request -> check_slots -> [clarify] -> gather_context -> plan -> respond
"""
