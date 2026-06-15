"""Testa conexão SIGMA e lista gestores ativos (sem expor senhas)."""
import os
import sys

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    from backend.config import settings
    from backend.services import sigma_auth

    if not sigma_auth.sigma_configured():
        print("SIGMA não configurado (SIGMA_POSTGRES_PASSWORD ou SIGMA_DATABASE_URL)")
        return 1
    try:
        conn = psycopg.connect(
            settings.sigma_database_dsn, row_factory=dict_row, connect_timeout=10
        )
        try:
            rows = conn.execute(
                """
                SELECT username, email_institucional, tipo_usuario
                FROM usuarios.usuario
                WHERE UPPER(tipo_usuario) = 'GESTOR' AND ativo = true
                ORDER BY username
                LIMIT 10
                """
            ).fetchall()
        finally:
            conn.close()
        print(f"Conexão OK — {len(rows)} gestor(es) ativo(s) (amostra):")
        for r in rows:
            print(f"  - {r['username']} ({r.get('email_institucional') or 'sem email'})")
        return 0
    except Exception as exc:
        print(f"Falha: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
