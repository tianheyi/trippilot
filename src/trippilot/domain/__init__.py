"""Travel domain models and business rules.

This layer must not import FastAPI, LangGraph, SQLAlchemy or any HTTP/provider
concern (AGENTS.md 4.1). Pydantic is permitted: it is the validation library
the project standardises on, not a web framework.
"""
