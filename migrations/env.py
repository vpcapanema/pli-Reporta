"""Ambiente de execução do Alembic.

A URL do banco vem de `backend.config.settings.database_url`, garantindo uma
única fonte de verdade (a mesma usada pela aplicação). O metadata-alvo é o
`Base.metadata` da aplicação, com todos os modelos importados.
"""
# pylint: disable=no-member
# (alembic.context tem membros injetados em runtime — falso-positivo do Pylint)
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importa a aplicação para registrar os modelos no metadata.
from backend import models  # noqa: F401  pylint: disable=unused-import
from backend.config import settings
from backend.database import Base

config = context.config

# Injeta a URL real do banco (env/.env) na configuração do Alembic.
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _is_sqlite() -> bool:
    return settings.database_url.startswith("sqlite")


def run_migrations_offline() -> None:
    """Executa migrações em modo 'offline' (gera SQL sem conectar)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_is_sqlite(),
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Executa migrações conectando ao banco."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_is_sqlite(),
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
