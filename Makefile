# Hive Browser — Development & Deployment

.PHONY: setup-dev \
        dev back-dev front-dev static \
        docker-init docker-build docker-up docker-down docker-update docker-logs \
        test lint check-deps check-backend check-frontend check-all clean

SHELL := /bin/bash

DB_USER ?= hive
DB_NAME ?= hive
DB_PASS ?= hive

# ── Setup ─────────────────────────────────────────────────

setup-dev:
	uv sync --group dev
	cd frontend && bun install
	@mkdir -p data/{blast,chats,tools}
	@if [ ! -f config/config.local.yaml ]; then \
		cp config/config.example.yaml config/config.local.yaml; \
		echo "Created config/config.local.yaml"; \
	else \
		echo "config/config.local.yaml already exists, skipping"; \
	fi
	@createuser -s $(DB_USER) 2>/dev/null || true
	@psql -U $(DB_USER) -c "ALTER USER $(DB_USER) WITH PASSWORD '$(DB_PASS)';" 2>/dev/null || true
	@createdb -U $(DB_USER) $(DB_NAME) 2>/dev/null || true
	@psql -U $(DB_USER) -d $(DB_NAME) -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" 2>/dev/null || true
	@echo "Database ready: $(DB_NAME)"
	HIVE_CONFIG=config/config.local.yaml uv run alembic upgrade head

# ── Dev ───────────────────────────────────────────────────

dev:
	@trap 'kill 0' EXIT; \
	HIVE_CONFIG=config/config.local.yaml uv run uvicorn hive.main:app \
		--reload --host 127.0.0.1 --port 8080 & \
	cd frontend && bun run dev & \
	wait

back-dev:
	HIVE_CONFIG=config/config.local.yaml uv run uvicorn hive.main:app \
		--reload --host 127.0.0.1 --port 8080

front-dev:
	cd frontend && bun run dev

static:
	cd frontend && bun install && bun run build
	rm -rf static && cp -r frontend/build static

# ── Docker ────────────────────────────────────────────────

docker-init:
	@if [ ! -f config/config.docker.yaml ]; then \
		cp config/config.example.yaml config/config.docker.yaml; \
		echo "Created config/config.docker.yaml"; \
	else \
		echo "config/config.docker.yaml already exists, skipping"; \
	fi
	@if [ ! -f .env ]; then \
		PG_PASS=$$(openssl rand -base64 24 | tr -d '/+=' | head -c 32) && \
		printf 'POSTGRES_USER=hive\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=hive\nHIVE_PORT=8080\nHIVE_DATA_ROOT=~/.hive\nHIVE_WATCHER_ROOT=~/sequences\n' "$$PG_PASS" > .env && \
		echo ".env created — edit HIVE_DATA_ROOT and HIVE_WATCHER_ROOT before starting"; \
	else \
		echo ".env already exists, skipping"; \
	fi

docker-build:
	docker compose build

docker-up: docker-init
	docker compose up -d

docker-down:
	docker compose down

docker-update:
	docker compose build
	docker compose up -d

docker-logs:
	docker compose logs -f hive

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
