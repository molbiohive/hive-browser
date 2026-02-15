# Zerg Browser — Development & Deployment
# Usage:
#   make setup       — install Postgres, BLAST+, Python deps, create DB
#   make dev         — run server with config.local
#   make prod        — run server with config.prod
#   make test        — run test suite
#   make migrate     — run Alembic migrations
#   make clean       — remove build artifacts

.PHONY: setup setup-db setup-blast setup-deps setup-dirs migrate dev prod test lint clean mklocal mkprod

SHELL := /bin/bash

DB_USER   ?= zerg
DB_NAME   ?= zerg
DB_PASS   ?= zerg

# ── Setup ──────────────────────────────────────────────────

setup: setup-deps setup-db setup-blast setup-dirs migrate
	@echo "Setup complete. Run 'make dev' to start."

setup-deps:
	uv sync --group dev

setup-db:
	@echo "Installing PostgreSQL..."
	brew install postgresql@16 || true
	brew services start postgresql@16 || true
	@sleep 2
	@echo "Creating database user and database..."
	createuser -s $(DB_USER) 2>/dev/null || true
	psql -U $(DB_USER) -c "ALTER USER $(DB_USER) WITH PASSWORD '$(DB_PASS)';" 2>/dev/null || true
	createdb -U $(DB_USER) $(DB_NAME) 2>/dev/null || true
	psql -U $(DB_USER) -d $(DB_NAME) -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" 2>/dev/null || true
	@echo "Database ready: $(DB_NAME)"

setup-blast:
	@echo "Installing BLAST+..."
	brew install blast || true
	@echo "BLAST+ ready: $$(blastn -version 2>/dev/null | head -1)"

setup-dirs:
	mkdir -p ~/.zerg/blast ~/.zerg/chats

# ── Config ─────────────────────────────────────────────────

mklocal:
	cp config/config.example.yaml config/config.local.yaml
	@echo "Created config/config.local.yaml — edit as needed."

mkprod:
	cp config/config.example.yaml config/config.prod.yaml
	@echo "Created config/config.prod.yaml — edit as needed."

# ── Database ───────────────────────────────────────────────

migrate:
	ZERG_CONFIG=config/config.local.yaml uv run alembic upgrade head

# ── Run ────────────────────────────────────────────────────

dev:
	ZERG_CONFIG=config/config.local.yaml uv run uvicorn zerg.main:app \
		--reload --host 127.0.0.1 --port 8080

prod:
	ZERG_CONFIG=config/config.prod.yaml uv run uvicorn zerg.main:app \
		--host 0.0.0.0 --port 8080 --workers 2

# ── Test ───────────────────────────────────────────────────

test:
	uv run pytest -v

lint:
	uv run ruff check src/ tests/

# ── Clean ──────────────────────────────────────────────────

clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
