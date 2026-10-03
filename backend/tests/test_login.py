"""Dogru parola 200, yanlis 401, gercek LDAP cagrisi 0."""

from __future__ import annotations

import secrets

import ldap3
from fastapi.testclient import TestClient

from app.adapters.ad_fake import directory
from app.main import create_app


def _csrf(client: TestClient) -> str:
    issued = client.get("/api/v1/csrf")
    assert issued.status_code == 200
    token = client.cookies.get("tamlife_csrf")
    assert token
    return token


def test_local_login_and_no_ldap(monkeypatch) -> None:
    username = "local-" + secrets.token_hex(4)
    password = secrets.token_urlsafe(18)
    monkeypatch.setenv("TAMLIFE_ENV", "test")
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", username)
    monkeypatch.setenv("TAMLIFE_LOCAL_PASSWORD", password)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "admin")
    ldap_calls = {"n": 0}

    def banned(*_args, **_kwargs):
        ldap_calls["n"] += 1
        raise AssertionError("real ldap")

    monkeypatch.setattr(ldap3, "Connection", banned)
    monkeypatch.setattr(ldap3, "Server", banned)
    directory.lookups = 0
    directory.ldap_calls = 0
    client = TestClient(create_app())
    token = _csrf(client)
    ok = client.post(
        "/api/v1/session",
        json={"username": username, "password": password},
        headers={"X-CSRF-Token": token},
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["role"] == "admin"
    assert password not in ok.text
    bad = client.post(
        "/api/v1/session",
        json={"username": username, "password": password + "x"},
        headers={"X-CSRF-Token": token},
    )
    assert bad.status_code == 401
    assert password not in bad.text
    unknown = client.post(
        "/api/v1/session",
        json={"username": username + "-nope", "password": password},
        headers={"X-CSRF-Token": token},
    )
    assert unknown.status_code == 401
    assert directory.lookups == 1
    assert directory.ldap_calls == 0
    assert ldap_calls["n"] == 0
