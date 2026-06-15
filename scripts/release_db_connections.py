"""Libera conexoes ociosas do usuario atual no PostgreSQL (dev/restart)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import settings  # noqa: E402


def main() -> int:
    url = settings.database_url
    if url.startswith("sqlite"):
        print("[pli-reporta] SQLite — nada a liberar.")
        return 0

    try:
        import psycopg
    except ImportError:
        print("[pli-reporta] psycopg nao instalado — pulando liberacao de conexoes.")
        return 0

    dsn = url
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://"):
        if dsn.startswith(prefix):
            dsn = "postgresql://" + dsn[len(prefix):]
            break

    terminated = 0
    try:
        conn = psycopg.connect(dsn, connect_timeout=8)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE usename = current_user
                      AND pid <> pg_backend_pid()
                      AND datname = current_database()
                    """
                )
                terminated = sum(1 for row in cur.fetchall() if row[0])
            conn.commit()
        finally:
            conn.close()
        print(f"[pli-reporta] Conexoes encerradas: {terminated}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[pli-reporta] AVISO: nao foi possivel liberar conexoes ({exc})")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
