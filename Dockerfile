# Multi-stage Dockerfile for VisionCaster Python Backend & Celery Worker
FROM python:3.12-slim AS base

# Install system dependencies: ffmpeg (for video remuxing/processing) & curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv from official dist
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Environment settings
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=0 \
    PATH="/workspace/.venv/bin:$PATH"

WORKDIR /workspace

# Install Python dependencies first for caching
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-cache

# Copy application source and alembic configuration
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini
COPY .env.example ./.env

# Create data directories
RUN mkdir -p /workspace/data/downloads

EXPOSE 3001

# Default command: run migrations and start FastAPI server
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 3001"]
