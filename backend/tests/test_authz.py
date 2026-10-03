"""TeamMember+utilizasyon=403, admin=200, talep giris yapana acik."""

from __future__ import annotations

import secrets

from fastapi.testclient import TestClient

from app.main import create_app


def _client(monkeypatch, role: str) -> TestClient:
    monkeypatch.setenv("TAMLIFE_ENV", "test")
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", "user-" + role)
    monkeypatch.setenv("TAMLIFE_LOCAL_PASSWORD", secrets.token_urlsafe(18))
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", role)
    client = TestClient(create_app())
    token = client.get("/api/v1/csrf").json()
    del token
    csrf = client.cookies.get("tamlife_csrf")
    response = client.post(
        "/api/v1/session",
        json={
            "username": "user-" + role,
            "password": __import__("os").environ["TAMLIFE_LOCAL_PASSWORD"],
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    return client


def test_role_gates(monkeypatch) -> None:
    anon = TestClient(create_app())
    assert anon.get("/api/v1/modules/talep").status_code == 401
    member = _client(monkeypatch, "TeamMember")
    assert member.get("/api/v1/modules/utilizasyon").status_code == 403
    assert member.get("/api/v1/modules/talep").status_code == 200
    admin = _client(monkeypatch, "admin")
    assert admin.get("/api/v1/modules/utilizasyon").status_code == 200
    assert admin.get("/api/v1/modules/talep").status_code == 200
