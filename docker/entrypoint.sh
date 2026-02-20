#!/bin/bash
set -e

# Ensure data directories exist
mkdir -p /data/chats /data/blast /data/tools

# Run database migrations
alembic upgrade head

# Start server
exec uvicorn zerg.main:app --host 0.0.0.0 --port 8080
