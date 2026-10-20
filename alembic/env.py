"""Alembic environment: DATABASE_URL from the environment, models metadata."""

import os
from logging.config import fileConfig
from typing import Any

from sqlalchemy import engine_from_config, pool

# Import models so Base.metadata sees every table.
import app.db.events  # noqa: F401
import app.db.models  # noqa: F401
from alembic import context
from app.db.base import Base
from app.settings import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata: Any = Base.metadata


def database_url() -> str:
    """DATABASE_URL wins (tests point it at a throwaway schema); settings
    supply the local compose default."""
    return os.environ.get("DATABASE_URL") or settings.database_url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration: dict[str, Any] = dict(config.get_section(config.config_ini_section, {}) or {})
    configuration["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
