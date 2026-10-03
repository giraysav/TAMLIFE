"""Test ortami: yerel admin, veritabani gerekmez."""

from __future__ import annotations

import os

os.environ["TAMLIFE_ENV"] = "test"
os.environ["TAMLIFE_LOCAL_USER"] = "admin"
os.environ["TAMLIFE_LOCAL_PASSWORD"] = "test-parola-1"
os.environ["TAMLIFE_LOCAL_ROLE"] = "admin"

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security import limiter
from app.session import reset_for_tests


@pytest.fixture
def client() -> Iterator[TestClient]:
    limiter.reset()
    reset_for_tests()
    with TestClient(create_app(), base_url="http://testserver") as c:
        yield c


def login_ok(c: TestClient) -> dict[str, str]:
    r = c.post("/api/v1/session/login", json={"username": "admin", "password": "test-parola-1"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": c.cookies.get("tamlife_csrf") or ""}
