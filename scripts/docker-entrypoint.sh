#!/bin/sh
set -e

PORT="${PORT:-8080}"

echo "[pli-reporta] aplicando migrações..."
python scripts/db_migrate.py

echo "[pli-reporta] subindo uvicorn em 0.0.0.0:${PORT}"
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT}" --workers 1
