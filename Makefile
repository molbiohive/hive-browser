# Zerg Browser — Development & Deployment

.PHONY: check setup setup-deps setup-db setup-blast setup-dirs setup-llm \
        migrate dev dev-frontend build-frontend prod \
        test lint clean mklocal mkprod

SHELL := /bin/bash

DB_USER      ?= zerg
DB_NAME      ?= zerg
DB_PASS      ?= zerg
LLM_MODEL    ?= qwen2.5:3b

OS       := $(shell uname -s)
IS_UBUNTU := $(shell grep -qi ubuntu /etc/os-release 2>/dev/null && echo 1 || echo 0)

# ── System check ──────────────────────────────────────────

define check_bin
	@command -v $(1) >/dev/null 2>&1 \
		&& printf "  %-12s %s\n" "$(1)" "$$($(1) $(2) 2>/dev/null | head -1)" \
		|| printf "  %-12s MISSING\n" "$(1)"
endef

check:
	@echo "System dependencies:"
	$(call check_bin,uv,--version)
	$(call check_bin,bun,--version)
	$(call check_bin,psql,--version)
	$(call check_bin,blastn,-version)
	$(call check_bin,ollama,--version)

# ── Setup ──────────────────────────────────────────────────

setup: setup-deps setup-db setup-blast setup-dirs setup-llm migrate
	@echo "Setup complete. Run 'make dev' to start."

setup-deps:
	uv sync --group dev
	cd frontend && bun install

setup-db:
ifeq ($(OS),Darwin)
	@brew list postgresql@16 >/dev/null 2>&1 || brew install postgresql@16
	@brew services start postgresql@16 || true
	@sleep 2
else ifeq ($(IS_UBUNTU),1)
	@dpkg -s postgresql >/dev/null 2>&1 || (sudo apt-get update && sudo apt-get install -y postgresql postgresql-contrib)
	@sudo systemctl start postgresql || true
else
	@command -v psql >/dev/null 2>&1 || { echo "Install PostgreSQL: https://www.postgresql.org/download/"; exit 1; }
endif
	@createuser -s $(DB_USER) 2>/dev/null || true
	@psql -U $(DB_USER) -c "ALTER USER $(DB_USER) WITH PASSWORD '$(DB_PASS)';" 2>/dev/null || true
	@createdb -U $(DB_USER) $(DB_NAME) 2>/dev/null || true
	@psql -U $(DB_USER) -d $(DB_NAME) -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" 2>/dev/null || true
	@echo "Database ready: $(DB_NAME)"

setup-blast:
ifeq ($(OS),Darwin)
	@brew list blast >/dev/null 2>&1 || brew install blast
else ifeq ($(IS_UBUNTU),1)
	@dpkg -s ncbi-blast+ >/dev/null 2>&1 || (sudo apt-get update && sudo apt-get install -y ncbi-blast+)
else
	@command -v blastn >/dev/null 2>&1 || { echo "Install BLAST+: https://blast.ncbi.nlm.nih.gov/doc/blast-help/downloadblastdata.html"; exit 1; }
endif
	@echo "BLAST+ ready: $$(blastn -version 2>/dev/null | head -1)"

setup-llm:
ifeq ($(OS),Darwin)
	@brew list ollama >/dev/null 2>&1 || brew install ollama
else
	@command -v ollama >/dev/null 2>&1 || { echo "Install Ollama: https://ollama.com/download"; exit 1; }
endif
	@ollama pull $(LLM_MODEL)

setup-dirs:
	@mkdir -p ~/.zerg/blast ~/.zerg/chats

# ── Config ─────────────────────────────────────────────────

mklocal:
	@cp config/config.example.yaml config/config.local.yaml
	@echo "Created config/config.local.yaml"

mkprod:
	@cp config/config.example.yaml config/config.prod.yaml
	@echo "Created config/config.prod.yaml"

# ── Database ───────────────────────────────────────────────

migrate:
	ZERG_CONFIG=config/config.local.yaml uv run alembic upgrade head

# ── Run ────────────────────────────────────────────────────

dev:
	ZERG_CONFIG=config/config.local.yaml uv run uvicorn zerg.main:app \
		--reload --host 127.0.0.1 --port 8080

dev-frontend:
	cd frontend && bun run dev

build-frontend:
	cd frontend && bun install && bun run build
	rm -rf static && cp -r frontend/build static

prod: build-frontend
	ZERG_CONFIG=config/config.prod.yaml uv run uvicorn zerg.main:app \
		--host 0.0.0.0 --port 8080 --workers 2

# ── Test ───────────────────────────────────────────────────

test:
	uv run pytest -v

lint:
	uv run ruff check src/ tests/

# ── Clean ──────────────────────────────────────────────────

clean:
	rm -rf dist/ build/ static/ *.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
