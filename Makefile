# TripPilot development tasks.
#
# `make` on its own lists every target. CI runs the same commands as `make
# check` and `make test`, so a green local run means a green pipeline.

.DEFAULT_GOAL := help
.PHONY: help install lock run run-reload test test-e2e cov lint format format-check typecheck check ci up down logs ps clean

UV ?= uv
IMAGE ?= trippilot
PORT ?= 8000

help: ## List available targets
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- Setup ------------------------------------------------------------------

install: ## Install every dependency from the lock file, including dev tools
	$(UV) sync --all-groups

lock: ## Re-resolve dependencies and update uv.lock
	$(UV) lock

# --- Run --------------------------------------------------------------------

run: ## Run the API against the local environment (.env), port $(PORT)
	$(UV) run uvicorn trippilot.main:app --host 0.0.0.0 --port $(PORT)

run-reload: ## Run the API with autoreload for development
	$(UV) run uvicorn trippilot.main:app --reload --host 0.0.0.0 --port $(PORT)

up: ## Start the Compose stack (api + postgres) in the background
	docker compose up --build --detach

down: ## Stop the Compose stack (V=1 also deletes the database volume)
	docker compose down $(if $(V),--volumes,)

logs: ## Follow the API logs from the Compose stack
	docker compose logs --follow api

ps: ## Show Compose service status
	docker compose ps

# --- Quality gates ----------------------------------------------------------

test: ## Run the test suite
	$(UV) run pytest

test-e2e: ## Run only the end-to-end tests
	$(UV) run pytest -m e2e

cov: ## Run tests with a coverage report
	$(UV) run pytest --cov --cov-report=term-missing

lint: ## Check code with Ruff
	$(UV) run ruff check .

format: ## Auto-format code with Ruff
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

format-check: ## Verify formatting without changing files
	$(UV) run ruff format --check .

typecheck: ## Type-check with mypy
	$(UV) run mypy

check: lint format-check typecheck ## Run every static check (no tests)

ci: check cov ## Exactly what the CI workflow runs

# --- Housekeeping -----------------------------------------------------------

clean: ## Remove caches and build artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
