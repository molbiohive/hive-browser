# Zerg Browser — Development & Deployment

.PHONY: setup deps config db migrate \
        back-dev front-dev static prod \
        test lint check-deps check-backend check-frontend check-all clean

SHELL := /bin/bash

DB_USER ?= zerg
DB_NAME ?= zerg
DB_PASS ?= zerg

# ── Aggregate ─────────────────────────────────────────────

setup: deps config db migrate

# ── Setup ─────────────────────────────────────────────────

deps:
	uv sync --group dev
	cd frontend && bun install

config:
	@mkdir -p ~/.zerg/blast ~/.zerg/chats ~/.zerg/tools
	@if [ ! -f config/config.local.yaml ]; then \
		cp config/config.example.yaml config/config.local.yaml; \
		echo "Created config/config.local.yaml"; \
	else \
		echo "config/config.local.yaml already exists, skipping"; \
	fi
	@if [ ! -f config/config.prod.yaml ]; then \
		cp config/config.example.yaml config/config.prod.yaml; \
		echo "Created config/config.prod.yaml"; \
	else \
		echo "config/config.prod.yaml already exists, skipping"; \
	fi

db:
	@createuser -s $(DB_USER) 2>/dev/null || true
	@psql -U $(DB_USER) -c "ALTER USER $(DB_USER) WITH PASSWORD '$(DB_PASS)';" 2>/dev/null || true
	@createdb -U $(DB_USER) $(DB_NAME) 2>/dev/null || true
	@psql -U $(DB_USER) -d $(DB_NAME) -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" 2>/dev/null || true
	@echo "Database ready: $(DB_NAME)"

migrate:
	ZERG_CONFIG=config/config.local.yaml uv run alembic upgrade head

# ── Dev ───────────────────────────────────────────────────

back-dev:
	ZERG_CONFIG=config/config.local.yaml uv run uvicorn zerg.main:app \
		--reload --host 127.0.0.1 --port 8080

front-dev:
	cd frontend && bun run dev

static:
	cd frontend && bun install && bun run build
	rm -rf static && cp -r frontend/build static

prod: static
	ZERG_CONFIG=config/config.prod.yaml uv run uvicorn zerg.main:app \
		--host 0.0.0.0 --port 8080 --workers 2

# ── Quality ───────────────────────────────────────────────

define check_bin
	@command -v $(1) >/dev/null 2>&1 \
		&& printf "  %-12s %s\n" "$(1)" "$$($(1) $(2) 2>/dev/null | head -1)" \
		|| printf "  %-12s MISSING\n" "$(1)"
endef

test:
	uv run pytest -v

lint:
	uv run ruff check src/ tests/

check-deps:
	@echo "System dependencies:"
	$(call check_bin,uv,--version)
	$(call check_bin,bun,--version)
	$(call check_bin,psql,--version)
	$(call check_bin,blastn,-version)
	$(call check_bin,ollama,--version)

check-backend: lint test

check-frontend:
	cd frontend && bun run build

check-all: check-deps check-backend check-frontend

# ── Clean ─────────────────────────────────────────────────

clean:
	rm -rf dist/ build/ static/ *.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
