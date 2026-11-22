"""Infrastructure: concrete adapters for external technology.

Not implemented yet, and this package deliberately stops at ``__init__.py``.
Subpackages are created when there is something to put in them (AGENTS.md §3):

    infrastructure/llm/            model-provider adapters
    infrastructure/persistence/    database connections and repository impls
    infrastructure/search/         map, weather and POI API clients
    infrastructure/observability/  tracing, metrics, cost accounting

Responsibility (AGENTS.md §4.8)
    Keep concrete SDKs confined here. Expose capability upward through small,
    stable interfaces that implement the abstractions the inner layers define.
    Own timeouts, rate limiting, retries and error translation for outbound
    calls.

Forbidden here
    Business process orchestration. This layer implements; it does not decide.

Dependency direction (AGENTS.md §5): ``infrastructure/`` implements interfaces
defined by ``domain/ports/``. The inner layers never import back into it --
concrete implementations are constructed in ``main.py`` and injected.
"""
