"""Provisiona o banco do PLI Reporta no mesmo PostgreSQL do SIGMA.

Cria (de forma idempotente):
  - role/usuário dedicado (LOGIN) — isolado do SIGMA;
  - banco `pli_reporta` com esse usuário como dono;
  - privilégios mínimos.

Requer uma conexão de ADMINISTRADOR do PostgreSQL (superuser ou role com
CREATEDB + CREATEROLE). As credenciais de admin vêm de variáveis de ambiente
ou argumentos de linha de comando — nunca ficam no repositório.

Exemplos
--------
Via túnel SSH (porta local 15433 -> VM:5433):

    python scripts/sigma-tunnel.ps1            # abre o túnel (PowerShell)
    set PGADMIN_HOST=127.0.0.1
    set PGADMIN_PORT=15433
    set PGADMIN_USER=postgres
    set PGADMIN_PASSWORD=********
    set PLI_DB_PASSWORD=senha-forte-do-pli
    python scripts/provision_pli_db.py

Rodando diretamente na VM:

    PGADMIN_HOST=127.0.0.1 PGADMIN_PORT=5433 PGADMIN_USER=postgres \
    PGADMIN_PASSWORD=*** PLI_DB_PASSWORD=*** python scripts/provision_pli_db.py
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg
from psycopg import sql


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Provisiona o banco do PLI Reporta.")
    p.add_argument("--admin-host", default=_env("PGADMIN_HOST", "127.0.0.1"))
    p.add_argument("--admin-port", type=int, default=int(_env("PGADMIN_PORT", "15433")))
    p.add_argument("--admin-user", default=_env("PGADMIN_USER", "postgres"))
    p.add_argument("--admin-password", default=_env("PGADMIN_PASSWORD"))
    p.add_argument("--admin-db", default=_env("PGADMIN_DB", "postgres"))
    p.add_argument("--db-name", default=_env("PLI_DB_NAME", "pli_reporta"))
    p.add_argument("--db-user", default=_env("PLI_DB_USER", "pli_user"))
    p.add_argument("--db-password", default=_env("PLI_DB_PASSWORD"))
    p.add_argument("--sslmode", default=_env("PGADMIN_SSLMODE", "disable"))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.admin_password:
        print("ERRO: defina PGADMIN_PASSWORD (senha do admin do PostgreSQL).")
        return 2
    if not args.db_password:
        print("ERRO: defina PLI_DB_PASSWORD (senha do usuário do PLI Reporta).")
        return 2

    dsn = (
        f"host={args.admin_host} port={args.admin_port} dbname={args.admin_db} "
        f"user={args.admin_user} password={args.admin_password} sslmode={args.sslmode}"
    )
    print(f"[provision] conectando admin em {args.admin_host}:{args.admin_port} ...")
    try:
        conn = psycopg.connect(dsn, connect_timeout=10, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[provision] falha ao conectar como admin: {exc}")
        return 1

    try:
        with conn.cursor() as cur:
            # 1) Role/usuário dedicado
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (args.db_user,))
            if cur.fetchone():
                print(f"[provision] role '{args.db_user}' já existe — atualizando senha.")
                cur.execute(
                    sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                        sql.Identifier(args.db_user), sql.Literal(args.db_password)
                    )
                )
            else:
                print(f"[provision] criando role '{args.db_user}'.")
                cur.execute(
                    sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(
                        sql.Identifier(args.db_user), sql.Literal(args.db_password)
                    )
                )

            # 2) Banco com o usuário como dono
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (args.db_name,))
            if cur.fetchone():
                print(f"[provision] banco '{args.db_name}' já existe.")
            else:
                print(f"[provision] criando banco '{args.db_name}' (owner={args.db_user}).")
                cur.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8'").format(
                        sql.Identifier(args.db_name), sql.Identifier(args.db_user)
                    )
                )

            # 3) Privilégios
            cur.execute(
                sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {} TO {}").format(
                    sql.Identifier(args.db_name), sql.Identifier(args.db_user)
                )
            )
    finally:
        conn.close()

    # 4) Garante privilégios no schema public dentro do novo banco
    db_dsn = (
        f"host={args.admin_host} port={args.admin_port} dbname={args.db_name} "
        f"user={args.admin_user} password={args.admin_password} sslmode={args.sslmode}"
    )
    try:
        # pylint: disable=not-context-manager
        with psycopg.connect(db_dsn, connect_timeout=10, autocommit=True) as conn2:
            with conn2.cursor() as cur:
                cur.execute(
                    sql.SQL("GRANT ALL ON SCHEMA public TO {}").format(
                        sql.Identifier(args.db_user)
                    )
                )
                cur.execute(
                    sql.SQL("ALTER SCHEMA public OWNER TO {}").format(
                        sql.Identifier(args.db_user)
                    )
                )
    except Exception as exc:  # noqa: BLE001
        print(f"[provision] aviso: não foi possível ajustar schema public: {exc}")

    print("\n[provision] concluído. Configure o DATABASE_URL da aplicação:")
    print(
        f"  DATABASE_URL=postgresql+psycopg://{args.db_user}:***@"
        f"{args.admin_host}:{args.admin_port}/{args.db_name}"
    )
    print("Depois rode as migrações: python scripts/db_migrate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
