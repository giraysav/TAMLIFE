"""Set-Cookie bayraklari. Govdede token yok."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.session import SessionUser
from app.main import create_app


def _user() -> SessionUser:
    return SessionUser(id=1, username="probe", role="admin", is_admin=True, is_active=True)


def _client(monkeypatch, secure: str) -> TestClient:
    monkeypatch.setenv("TAMLIFE_ENV", "test")
    monkeypatch.setenv("TAMLIFE_COOKIE_SECURE", secure)
    monkeypatch.setattr("app.core.session.authenticate", lambda username, password, settings: _user())
    base = "https://testserver" if secure == "true" else "http://testserver"
    return TestClient(create_app(), base_url=base)


def _login(client: TestClient):
    issued = client.get("/api/v1/csrf")
    assert issued.status_code == 200
    token = client.cookies.get("tamlife_csrf")
    assert token
    assert token not in issued.text
    return client.post(
        "/api/v1/session",
        json={"username": "probe", "password": "not-a-stored-secret"},
        headers={"X-CSRF-Token": token},
    )


def test_cookie_secure_lax_httponly(monkeypatch) -> None:
    client = _client(monkeypatch, "true")
    denied = client.post("/api/v1/session", json={"username": "probe", "password": "not-a-stored-secret"})
    assert denied.status_code == 403
    response = _login(client)
    assert response.status_code == 200
    session = [item for item in response.headers.get_list("set-cookie") if item.lower().startswith("tamlife_session=")]
    assert len(session) == 1
    header = session[0].lower()
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "secure" in header
    value = session[0].split(";", 1)[0].split("=", 1)[1]
    assert value not in response.text
    assert "password" not in response.text.lower()


def test_secure_flag_off_when_setting_false(monkeypatch) -> None:
    client = _client(monkeypatch, "false")
    response = _login(client)
    assert response.status_code == 200
    header = [item for item in response.headers.get_list("set-cookie") if item.lower().startswith("tamlife_session=")][0]
    lowered = header.lower()
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert "secure" not in lowered
