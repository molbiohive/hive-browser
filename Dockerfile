FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install dependencies first (for better caching)
COPY pyproject.toml .
RUN uv venv && uv pip install -r pyproject.toml

# Copy application code
COPY . .

# Activate virtual environment
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Run the application directly
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
