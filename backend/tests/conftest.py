"""Test ortami: yerel admin ve her test icin ayri gecici SQLite veritabani."""

from __future__ import annotations

import os

os.environ["TAMLIFE_ENV"] = "test"
os.environ["TAMLIFE_LOCAL_USER"] = "admin"
os.environ["TAMLIFE_LOCAL_PASSWORD"] = "test-parola-1"
os.environ["TAMLIFE_LOCAL_ROLE"] = "admin"

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.deps import dispose_engines, engine
from app.main import create_app
from app.models import Base
from app.security import limiter
from app.session import reset_for_tests
from app.yonetim.kalici_yazici import yazici


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("TAMLIFE_DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("TAMLIFE_LOG_DIR", str(tmp_path / "log"))  # testler repo icine gunluk/yedek yazmasin
    monkeypatch.setenv("TAMLIFE_BACKUP_DIR", str(tmp_path / "yedek"))
    dispose_engines()
    Base.metadata.create_all(engine())
    limiter.reset()
    reset_for_tests()
    yazici.sifirla()
    with TestClient(create_app(), base_url="http://testserver") as c:
        yield c
    dispose_engines()


def login_ok(c: TestClient) -> dict[str, str]:
    r = c.post("/api/v1/session/login", json={"username": "admin", "password": "test-parola-1"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": c.cookies.get("tamlife_csrf") or ""}
