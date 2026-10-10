"""Alembic environment. Schema only. Does not read secret files."""

from __future__ import annotations

import os

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.config import env_dosyasi_yukle
from app.models import Base

env_dosyasi_yukle()  # backend/.env: TAMLIFE_DATABASE_URL orada olabilir (ortami ezmez)

target_metadata = Base.metadata

DEFAULT_DATABASE_URL = "postgresql+psycopg://localhost:5432/tamlife"


def _database_url() -> str:
    configured = context.config.get_main_option("sqlalchemy.url")
    env_url = os.environ.get("TAMLIFE_DATABASE_URL")
    if configured and configured != DEFAULT_DATABASE_URL:
        return configured
    if env_url:
        return env_url
    return configured or DEFAULT_DATABASE_URL


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = context.config.get_section(context.config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
