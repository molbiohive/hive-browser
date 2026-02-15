FROM python:3.11-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ncbi-blast+ \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ncbi-blast+ \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src/ ./src/
COPY zerg_config.yaml ./
COPY frontend/build/ ./static/
COPY alembic/ ./alembic/
COPY alembic.ini ./

RUN mkdir -p /var/zerg/chats

EXPOSE 8080

CMD ["uvicorn", "zerg.main:app", "--host", "0.0.0.0", "--port", "8080"]
