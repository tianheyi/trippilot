"""Inward-facing interfaces the domain and application layers depend on.

Not implemented yet. The first occupant will be ``trip_repository.py``, defining
a ``TripRepository`` Protocol, once a persistable domain model exists. See the
worked example in AGENTS.md §6.

Why the abstraction lives here rather than next to its implementation
    Dependency inversion: ``services/`` depends on the Protocol defined here,
    and ``infrastructure/persistence/`` provides the concrete class. That keeps
    the inner layers free of any database SDK and lets tests substitute an
    in-memory implementation without touching production code.

This package must not import FastAPI, LangGraph, SQLAlchemy, a model-provider
SDK, or a web framework (AGENTS.md §4.5).
"""
