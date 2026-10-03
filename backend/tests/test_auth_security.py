import time

import pytest

from app import session as sess
from app.config import get_settings
from tests.conftest import login_ok

PROTECTED = (
    "/api/v1/session/me",
    "/api/v1/modules",
    "/api/v1/home",
    "/api/v1/summary",
    "/api/v1/schema",
    "/api/v1/sources",
    "/api/v1/admin",
    "/api/v1/directory",
)


def test_anonymous_blocked(client):
    for path in PROTECTED:
        assert client.get(path).status_code == 401, path


def test_wrong_credentials_generic_401(client):
    for body in ({"username": "admin", "password": "x"}, {"username": "yok", "password": "x"}):
        r = client.post("/api/v1/session/login", json=body)
        assert r.status_code == 401 and r.json() == {"detail": "Giris reddedildi"}


def test_login_cookie_flags_and_no_token_in_body(client):
    r = client.post("/api/v1/session/login", json={"username": "admin", "password": "test-parola-1"})
    assert r.status_code == 200
    head = [h.lower() for h in r.headers.get_list("set-cookie")]
    sid = next(h for h in head if h.startswith("tamlife_session="))
    assert "httponly" in sid and "samesite=strict" in sid
    csrf = next(h for h in head if h.startswith("tamlife_csrf="))
    assert "httponly" not in csrf
    token = client.cookies.get("tamlife_session")
    assert token and token not in r.text


def test_input_limits(client):
    assert client.post("/api/v1/session/login", json={"username": "a" * 65, "password": "x"}).status_code == 422
    assert client.post("/api/v1/session/login", json={"username": "a", "password": "x" * 257}).status_code == 422
    assert client.post("/api/v1/session/login", json={"username": "", "password": "x"}).status_code == 422


def test_lockout_after_failures_blocks_even_correct_password(client):
    for _ in range(get_settings().login_max_attempts):
        assert client.post("/api/v1/session/login", json={"username": "admin", "password": "x"}).status_code == 401
    r = client.post("/api/v1/session/login", json={"username": "admin", "password": "test-parola-1"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_csrf_required_on_logout_and_session_survives(client):
    hdr = login_ok(client)
    assert client.post("/api/v1/session/logout").status_code == 403
    assert client.get("/api/v1/session/me").status_code == 200
    assert client.post("/api/v1/session/logout", headers={"X-CSRF-Token": "yanlis"}).status_code == 403
    assert client.post("/api/v1/session/logout", headers=hdr).status_code == 200
    assert client.get("/api/v1/session/me").status_code == 401


def test_foreign_origin_rejected(client):
    r = client.post(
        "/api/v1/session/login",
        json={"username": "admin", "password": "test-parola-1"},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403


def test_relogin_rotates_token(client):
    login_ok(client)
    old = client.cookies.get("tamlife_session")
    login_ok(client)
    assert client.cookies.get("tamlife_session") != old
    client.cookies.set("tamlife_session", old)
    assert client.get("/api/v1/session/me").status_code == 401


def test_idle_expiry(client, monkeypatch):
    login_ok(client)
    real = time.monotonic
    monkeypatch.setattr(sess, "_now", lambda: real() + get_settings().session_idle_minutes * 60 + 5)
    assert client.get("/api/v1/session/me").status_code == 401


def test_security_headers(client):
    r = client.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "no-store" in r.headers["cache-control"]


def test_unknown_host_rejected(client):
    assert client.get("/api/v1/health", headers={"Host": "evil.example"}).status_code == 400


def test_local_user_disabled_outside_dev(monkeypatch, client):
    monkeypatch.setenv("TAMLIFE_ENV", "production")
    r = client.post("/api/v1/session/login", json={"username": "admin", "password": "test-parola-1"})
    assert r.status_code == 401


def test_team_member_sees_only_allowed(monkeypatch, client):
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    login_ok(client)
    keys = {m["key"] for m in client.get("/api/v1/modules").json()["data"]}
    assert "utilizasyon" not in keys and "roller" not in keys and "talep" in keys
    assert client.get("/api/v1/modules/utilizasyon").status_code == 403
    for path in ("/api/v1/admin", "/api/v1/sources", "/api/v1/directory"):
        assert client.get(path).status_code == 403, path


@pytest.mark.parametrize("path", ["/docs", "/openapi.json"])
def test_docs_hidden_in_production(monkeypatch, path):
    monkeypatch.setenv("TAMLIFE_ENV", "production")
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        assert c.get(path).status_code == 404


def test_me_returns_navigation_by_role(client, monkeypatch):
    login_ok(client)
    data = client.get("/api/v1/session/me").json()["data"]
    ids = {item["id"] for item in data["navigation"]}
    assert {"musteri", "utilizasyon", "roller", "admin", "integrations", "veri"} <= ids
    assert data["idle_timeout_minutes"] == get_settings().session_idle_minutes
    assert "topoloji" not in ids  # menude gorunmez
    client.post("/api/v1/session/logout", headers={"X-CSRF-Token": client.cookies.get("tamlife_csrf")})
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    login_ok(client)
    ids = {item["id"] for item in client.get("/api/v1/session/me").json()["data"]["navigation"]}
    assert "talep" in ids and "musteri" in ids
    assert not ids & {"utilizasyon", "roller", "admin", "integrations", "veri"}


def test_forwarded_for_only_from_trusted_proxy(client, monkeypatch):
    from starlette.requests import Request

    from app.security import client_ip

    def req(peer, xff):
        scope = {"type": "http", "headers": [(b"x-forwarded-for", xff.encode())], "client": (peer, 1)}
        return Request(scope)

    assert client_ip(req("10.0.0.9", "1.2.3.4")) == "10.0.0.9"  # guvenilir degil: yoksayilir
    monkeypatch.setenv("TAMLIFE_TRUSTED_PROXIES", "10.0.0.9")
    assert client_ip(req("10.0.0.9", "1.2.3.4, 10.0.0.9")) == "1.2.3.4"
    assert client_ip(req("8.8.8.8", "1.2.3.4")) == "8.8.8.8"  # baska esten gelen basliga guvenilmez


def test_integrations_admin_only_and_no_values(client, monkeypatch):
    assert client.get("/api/v1/integrations").status_code == 401
    login_ok(client)
    monkeypatch.setenv("ORACLE_REPORTDB_ENABLED", "true")
    monkeypatch.setenv("ORACLE_REPORTDB_HOST", "gizli-host.example")
    monkeypatch.setenv("ORACLE_REPORTDB_PASSWORD", "cok-gizli-parola")
    r = client.get("/api/v1/integrations")
    assert r.status_code == 200
    assert "gizli-host.example" not in r.text and "cok-gizli-parola" not in r.text
    row = next(i for i in r.json()["data"]["items"] if i["id"] == "oracle_reportdb")
    assert row["state"] == "incomplete" and "ORACLE_REPORTDB_PORT" in row["missing"]
    assert "ORACLE_REPORTDB_HOST" not in row["missing"]


def _tablolar(d):
    assert [t["name"] for t in d["tables"]] == [
        "veri_setleri", "ham_bloklar", "kurallar", "metrikler", "uygulama_gunlugu", "ingest_batch", "ingest_record",
    ]
    for t in d["tables"]:
        assert t["rows"] is None or t["exists"] is True  # var olmayan tabloya satir uydurulmaz


def test_veri_durumu_admin_only(client):
    assert client.get("/api/v1/veri").status_code == 401


def test_veri_durumu_sqlite_postgres_degil_ve_sir_yok(client, monkeypatch, tmp_path):
    monkeypatch.setenv("TAMLIFE_DATABASE_URL", f"sqlite:///{(tmp_path / 'v.db').as_posix()}")
    login_ok(client)
    r = client.get("/api/v1/veri")
    d = r.json()["data"]
    _tablolar(d)
    assert d["engine"] == "sqlite" and d["postgres"] is False and d["postgres_ready"] is False
    assert "PostgreSQL bagli degil" in d["note"]
    assert all(t["exists"] is False and t["rows"] is None for t in d["tables"])
    assert "://" not in r.text and str(tmp_path) not in r.text


def test_veri_durumu_postgres_ulasilamiyor(client, monkeypatch):
    import socket

    try:
        socket.create_connection(("127.0.0.1", 5432), timeout=0.5).close()
        pytest.skip("bu makinede 5432 dinleniyor")
    except OSError:
        pass
    monkeypatch.setenv("TAMLIFE_DATABASE_URL", "postgresql+psycopg://kullanici:gizli-sifre@127.0.0.1:5432/x")
    login_ok(client)
    r = client.get("/api/v1/veri")
    d = r.json()["data"]
    _tablolar(d)
    assert d["engine"] == "postgresql" and d["postgres_ready"] is False and "baglanilamadi" in d["note"]
    assert "gizli-sifre" not in r.text and "kullanici" not in r.text


def test_contract_covers_catalog_and_owners_match():
    from app.catalog import MODULES
    from app.contract import CONTRACT_DATA

    ids = {m.key for m in MODULES}
    assert ids <= set(CONTRACT_DATA) and set(CONTRACT_DATA) - ids == {"veri"}
    for m in MODULES:
        own = CONTRACT_DATA[m.key]["sahip_tablolar"]
        assert own == ([m.table] if m.table else []), m.key
    for key, c in CONTRACT_DATA.items():
        assert set(c["baska_modul_tablolari"]) == set(c["kullanilan_tablolar"]) - set(c["sahip_tablolar"]), key
        for f in c["fonksiyonlar"]:
            assert isinstance(f["ad"], str) and isinstance(f["girdi"], tuple)
