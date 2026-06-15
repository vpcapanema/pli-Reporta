"""Camada de persistência. SQLAlchemy 2.x, sessão por request."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


_engine_kwargs: dict = {"future": True}
if settings.database_url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Postgres (possivelmente via túnel SSH): valida a conexão antes de usar e
    # recicla conexões ociosas, evitando erros de socket quando o túnel oscila.
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_recycle"] = 1800

engine = create_engine(settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _sqlite_add_column_if_missing(conn, table: str, column: str, ddl: str) -> None:
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if table not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns(table)}
    if column not in cols:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def _migrate_schema() -> None:
    """Migrações leves para SQLite (ADD COLUMN)."""
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        _sqlite_add_column_if_missing(
            conn, "reports", "interaction_type",
            "interaction_type VARCHAR(24) DEFAULT 'evento_trafego' NOT NULL",
        )
        _sqlite_add_column_if_missing(
            conn, "clusters", "resolve_votes",
            "resolve_votes INTEGER DEFAULT 0 NOT NULL",
        )
        _sqlite_add_column_if_missing(
            conn, "moderation_policy", "category_overrides_json",
            "category_overrides_json TEXT",
        )
        _sqlite_add_column_if_missing(
            conn, "moderation_policy", "veracity_weights_json",
            "veracity_weights_json TEXT",
        )
        _sqlite_add_column_if_missing(
            conn, "moderation_policy", "highway_factors_json",
            "highway_factors_json TEXT",
        )


def init_db() -> None:
    """Prepara o banco.

    - SQLite (dev/test): cria tabelas via metadata + migrações leves.
    - Postgres (produção): o schema é gerido pelo Alembic (scripts/db_migrate.py
      roda no deploy); aqui apenas garantimos a política padrão.
    """
    import importlib

    importlib.import_module(".models", __package__)

    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
        _migrate_schema()

    with SessionLocal() as db:
        from .services.moderation_policy import ensure_default_policy

        ensure_default_policy(db)


def get_session() -> Iterator[Session]:
    """Dependency FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Sessão para scripts e tarefas em background."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
