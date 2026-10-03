"""Alembic ortam. Veri tasimaz, gizli dosya okumaz."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.data.base import Base

import app.core.audit  # noqa: F401

target_metadata = Base.metadata

DEFAULT_DATABASE_URL = "postgresql+psycopg://localhost:5432/tamlife"


def _database_url() -> str:
    """Env wins over the passwordless ini default. An explicit test URL still wins."""
    configured = context.config.get_main_option("sqlalchemy.url")
    env_url = os.environ.get("TAMLIFE_DATABASE_URL")
    if configured and configured != DEFAULT_DATABASE_URL:
        return configured
    if env_url:
        return env_url
    return configured or DEFAULT_DATABASE_URL




def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = context.config.get_section(context.config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
