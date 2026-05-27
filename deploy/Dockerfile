FROM python:3.11-slim AS base
WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ src/
COPY config/ config/

# Create data directory
RUN mkdir -p /app/data /app/logs /app/transcripts

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "media_tools.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
