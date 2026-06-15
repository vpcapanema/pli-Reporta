"""Aplica migrações Alembic de forma idempotente e segura no deploy.

Lida com três cenários:
1. Banco novo (sem tabelas)           -> upgrade head (cria tudo).
2. Banco já versionado (alembic)      -> upgrade head (aplica o que faltar).
3. Banco legado (tabelas sem alembic) -> stamp head + upgrade head (adota o
   schema atual sem recriar, depois aplica migrações futuras).

Uso:
    python scripts/db_migrate.py
"""
from __future__ import annotations
# pylint: disable=import-error  # imports do backend resolvidos via sys.path.insert abaixo
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

from backend.config import settings  # noqa: E402
from backend.database import engine  # noqa: E402

APP_TABLES = {"reports", "clusters", "moderation_policy", "audit_log"}


def main() -> int:
    cfg = Config(str(ROOT / "alembic.ini"))

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    print(f"[db_migrate] banco: {settings.database_url.split('@')[-1]}")
    print(f"[db_migrate] tabelas existentes: {sorted(tables) or 'nenhuma'}")

    if "alembic_version" not in tables and (tables & APP_TABLES):
        print("[db_migrate] schema legado detectado -> stamp head")
        command.stamp(cfg, "head")

    print("[db_migrate] upgrade head")
    command.upgrade(cfg, "head")
    print("[db_migrate] concluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
