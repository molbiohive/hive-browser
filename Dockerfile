# Stage 1 — frontend
FROM oven/bun:1 AS frontend
WORKDIR /app
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/src ./src
COPY frontend/static ./static
COPY frontend/svelte.config.js frontend/vite.config.ts ./
RUN bun run build

# Stage 2 — Python deps
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS deps
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
RUN uv sync --no-dev --frozen

# Stage 3 — runtime
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    ncbi-blast+ curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=deps /app/.venv /app/.venv
COPY --from=frontend /app/build /app/static
COPY src/ /app/src/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1
ENTRYPOINT ["/app/docker/entrypoint.sh"]
