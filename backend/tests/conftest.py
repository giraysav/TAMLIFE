"""Pytest ortakligi. Uretim veritabanina yazmaz."""

from __future__ import annotations

import os

# Panel default is PostgreSQL. Tests do not start a server and do not use that default.
os.environ.setdefault("TAMLIFE_DATABASE_URL", "sqlite:///./var/tamlife.db")


from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    application = create_app()
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def _sema() -> None:
    """Tek sema kaynagi Alembic: testler tablolari revizyonlardan kurar."""
    from pathlib import Path

    from alembic.config import Config

    from alembic import command

    ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    command.upgrade(Config(str(ini)), "head")
