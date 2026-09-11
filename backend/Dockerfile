FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps (for pypdf, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps from pyproject.toml (single source of truth — no drift)
COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install $(python -c "import tomllib; print(' '.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))")

# uv (provides uvx for MCP `uvx`-based servers)
RUN pip install "uv>=0.4"

# Copy app
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Create dirs
RUN mkdir -p /app/data/uploads /app/data/skills /app/logs /app/data/workspace

EXPOSE 8000

# Run migrations + start server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]