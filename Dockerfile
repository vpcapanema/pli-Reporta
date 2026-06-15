# syntax=docker/dockerfile:1
# PLI Reporta — imagem de produção (FastAPI + PWA + PostGIS)
#
# Build:  docker build -t pli-reporta-app:latest .
# VM:      docker compose -f docker-compose.vm.yml up -d
# URL VM:  http://pli-reporta.56-125-163-194.sslip.io
# Teste:   powershell -File scripts/docker-test.ps1

FROM python:3.11-slim-bookworm AS base

LABEL maintainer="PLI Reporta"
LABEL description="Reportes viários colaborativos — API, PWA e gestão"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8090 \
    PYTHONPATH=/app

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && pip install --prefer-binary -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY backend ./backend
COPY frontend ./frontend
COPY scripts ./scripts
COPY data/camadas-do-sistema ./data/camadas-do-sistema

RUN python scripts/generate_icons.py \
    && mkdir -p backend/storage/photos \
    && groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /usr/sbin/nologin --create-home appuser \
    && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/healthz" || exit 1

CMD ["sh", "-c", "python scripts/db_migrate.py && exec python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8090} --workers 1"]
