#!/usr/bin/env python3
"""Instala extensões PostgreSQL necessárias (PostGIS).

Uso:
    python scripts/enable_postgis.py

Requer DATABASE_URL apontando para PostgreSQL com permissão CREATE EXTENSION.
A migração Alembic f1a2b3c4d5e7 também executa CREATE EXTENSION IF NOT EXISTS postgis.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from backend.config import settings  # noqa: E402
from backend.database import engine  # noqa: E402

EXTENSIONS = ("postgis",)


def main() -> int:
    if settings.database_url.startswith("sqlite"):
        print("[enable_postgis] SQLite — PostGIS não se aplica.")
        return 0

    print(f"[enable_postgis] banco: {settings.database_url.rsplit('@', maxsplit=1)[-1]}")
    try:
        with engine.begin() as conn:
            for ext in EXTENSIONS:
                conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
                ver = conn.execute(text("SELECT PostGIS_Version()")).scalar_one_or_none()
                print(f"  OK  {ext}" + (f" ({ver})" if ver else ""))
    except Exception as exc:  # noqa: BLE001
        err = str(exc).lower()
        if "permission denied" in err or "insufficientprivilege" in err:
            print(
                "  AVISO: usuário do app não pode CREATE EXTENSION.\n"
                "  Peça ao DBA (superuser) no banco pli_reporta:\n"
                "    CREATE EXTENSION IF NOT EXISTS postgis;\n"
                "  Depois rode: python scripts/db_migrate.py"
            )
            return 1
        raise
    print("[enable_postgis] concluído. Rode: python scripts/db_migrate.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
