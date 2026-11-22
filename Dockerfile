# syntax=docker/dockerfile:1

# ---- Build stage -----------------------------------------------------------
# Dependencies are installed from the lock file in their own layer, before the
# source is copied, so editing application code does not reinstall them.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    uv sync --frozen --no-install-project --no-dev

# The project files must be COPYed, not bind-mounted: the mounts above exist
# only for the duration of that one RUN, and the second sync needs them on disk.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# --no-editable installs a real wheel, so the runtime image needs no source tree.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


# ---- Runtime stage ---------------------------------------------------------
FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Run unprivileged. The uid/gid are fixed so volume permissions stay stable.
RUN groupadd --system --gid 1000 trippilot \
    && useradd --system --uid 1000 --gid trippilot --no-create-home trippilot

WORKDIR /app

COPY --from=builder --chown=trippilot:trippilot /app/.venv /app/.venv
COPY --chown=trippilot:trippilot pyproject.toml uv.lock README.md ./

USER trippilot

EXPOSE 8000

# Uses the stdlib rather than curl: the slim image has no HTTP client, and
# adding one just for a probe is not worth the attack surface.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "trippilot.main:app", "--host", "0.0.0.0", "--port", "8000"]
