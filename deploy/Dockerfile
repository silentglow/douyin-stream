# ==========================================
# Stage 1: Build Frontend (React + Vite + TS)
# ==========================================
FROM node:20-slim AS frontend-builder
WORKDIR /frontend

# Copy dependency files first for layer caching
COPY frontend/package*.json ./
RUN npm ci

# Copy frontend source files and build
COPY frontend/ ./
RUN npm run build

# ==========================================
# Stage 2: Final Service Image (Python + ffmpeg)
# ==========================================
FROM python:3.11-slim AS base
WORKDIR /app

# Install system dependencies (ffmpeg is required for video/audio processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy package metadata and source before uv sync because the project itself is installed.
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN uv sync --frozen --no-dev

RUN mkdir -p config/transcribe
COPY config/config.yaml.example config/auth_rules.yaml config/
COPY config/transcribe/.env.example config/transcribe/accounts.example.json config/transcribe/
RUN cp config/config.yaml.example config/config.yaml

# Copy built frontend assets from Stage 1
COPY --from=frontend-builder /frontend/dist/ /app/frontend/dist/

# Create persistent storage directories
RUN mkdir -p /app/data /app/logs /app/transcripts /app/downloads

# Define configuration environment variables
ENV FRONTEND_DIST_DIR=/app/frontend/dist
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "media_tools.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
