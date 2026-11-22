# End-to-end tests

Empty on purpose.

An end-to-end test here means: one request in, one complete trip plan out,
across HTTP → agent workflow → tools → persistence. None of those layers exist
yet, so any test placed here today would assert against stubs and prove
nothing about the system.

The `e2e` pytest marker is already registered (`pyproject.toml`) and CI runs
`pytest -m "not e2e"` for the fast gate, so the first real end-to-end test only
needs to be marked and given a Compose-backed database. See
docs/quality/test-strategy.md for the intended boundary between integration and
end-to-end coverage.
