import time

import pytest

from app import session as sess
from app.config import get_settings
from tests.conftest import login_ok

PROTECTED = (
    "/api/v1/session/me",
    "/api/v1/modules",
    "/api/v1/home",
    "/api/v1/yonetim/ozet",
    "/api/v1/tampon/kaynaklar",
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


def test_oturum_mutlak_omur_siniri_yok(client, monkeypatch):
    """2026-10-21: etkin kullanici saat kac olursa olsun atilmaz; tek kapanma nedeni bosta sure."""
    login_ok(client)
    real = time.monotonic
    ileri = [0.0]
    monkeypatch.setattr(sess, "_now", lambda: real() + ileri[0])
    for _ in range(30):  # 30 x 29 dk = ~14,5 saat; her adimda istek oturumu tazeler
        ileri[0] += 29 * 60
        assert client.get("/api/v1/session/me").status_code == 200


def test_bosta_arka_plan_istegi_oturumu_uzatmaz(client, monkeypatch):
    """Arayuz bosta (>= 120 sn hareketsiz) iken yoklama istegi oturumu tazelemez; etkin istek tazeler."""
    login_ok(client)
    real = time.monotonic
    ileri = [0.0]
    monkeypatch.setattr(sess, "_now", lambda: real() + ileri[0])
    dk = 60.0
    ileri[0] += 20 * dk
    assert client.get("/api/v1/session/me", headers={"X-Son-Hareket-Sn": "1500"}).status_code == 200  # bosta yoklama: tazelemez
    ileri[0] += 11 * dk  # girisin 31. dakikasi: son GERCEK hareketten bu yana > 30 dk
    assert client.get("/api/v1/session/me").status_code == 401
    login_ok(client)
    ileri[0] += 20 * dk
    assert client.get("/api/v1/session/me", headers={"X-Son-Hareket-Sn": "5"}).status_code == 200  # etkin istek: tazeler
    ileri[0] += 20 * dk
    assert client.get("/api/v1/session/me").status_code == 200


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
    assert "talep" in keys and not keys & {"utilizasyon", "roller"}  # Yonetim alani (utilizasyon, roller) yalniz admin
    for yol in ("/api/v1/modules/utilizasyon", "/api/v1/modules/roller"):
        assert client.get(yol).status_code == 403, yol
    for path in ("/api/v1/yonetim/ozet", "/api/v1/tampon/kaynaklar", "/api/v1/roller", "/api/v1/skor/agac"):
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
    assert {"musteri", "utilizasyon", "yonetim"} <= ids
    assert not ids & {"roller", "admin", "integrations", "veri"}  # admin icin tek giris: Yonetim (sekiz bolum); eski kimlikler yok
    yonetim = next(i for i in data["navigation"] if i["id"] == "yonetim")
    assert [c["id"] for c in yonetim["children"]] == [
        f"yonetim/{b}" for b in ("durum", "utilizasyon", "tampon", "kurum", "veritabani", "roller", "arizalar", "gunlukler")
    ]
    assert yonetim["group"] == "admin"
    assert data["idle_timeout_minutes"] == get_settings().session_idle_minutes
    assert "topoloji" not in ids  # menude gorunmez
    client.post("/api/v1/session/logout", headers={"X-CSRF-Token": client.cookies.get("tamlife_csrf")})
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    login_ok(client)
    ids = {item["id"] for item in client.get("/api/v1/session/me").json()["data"]["navigation"]}
    assert "talep" in ids and "musteri" in ids
    assert not ids & {"utilizasyon", "roller", "admin", "integrations", "veri", "yonetim"}  # yonetim sayfalari yalniz admin


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


def test_kurum_baglantilari_yonetimde_sir_sizdirmaz(client, monkeypatch):
    login_ok(client)
    monkeypatch.setenv("ORACLE_REPORTDB_ENABLED", "true")
    monkeypatch.setenv("ORACLE_REPORTDB_HOST", "gizli-host.example")
    monkeypatch.setenv("ORACLE_REPORTDB_PASSWORD", "cok-gizli-parola")
    kaynaklar = client.get("/api/v1/tampon/kaynaklar")
    ozet = client.get("/api/v1/yonetim/ozet")
    for r in (kaynaklar, ozet):
        assert r.status_code == 200
        assert "gizli-host.example" not in r.text and "cok-gizli-parola" not in r.text
    row = next(k for k in kaynaklar.json()["data"] if k["anahtar"] == "oracle_reportdb")
    assert row["yapilandirma"] == "eksik" and "ORACLE_REPORTDB_SERVICE_NAME" in row["eksik"]  # PORT bossa 1521 (uretim kurali)
    assert "ORACLE_REPORTDB_HOST" not in row["eksik"]  # dolu olan anahtarin adi bile yok sayilir
    kontrol = next(k for k in ozet.json()["data"]["saglik"]["kontroller"] if k["id"] == "entegrasyon")
    assert kontrol["durum"] == "uyari"  # yarim yapilandirma uyari verir


def test_db_erisilemezken_giris_bloklanmaz_ve_hata_kodlanir(client, monkeypatch):
    import socket

    from fastapi.testclient import TestClient

    try:
        socket.create_connection(("127.0.0.1", 5432), timeout=0.5).close()
        pytest.skip("bu makinede 5432 dinleniyor")
    except OSError:
        pass
    monkeypatch.setenv("TAMLIFE_DATABASE_URL", "postgresql+psycopg://kullanici:gizli-sifre@127.0.0.1:5432/x")
    istemci = TestClient(client.app, base_url="http://testserver", raise_server_exceptions=False)
    basla = time.monotonic()
    login_ok(istemci)  # giris veritabani gerektirmez; denetim olayi kuyruga alinir, istek beklemez
    assert time.monotonic() - basla < 15
    r = istemci.get("/api/v1/yonetim/ozet")  # veritabani gerektiren uc: ham metin degil kod + kayit no
    assert r.status_code == 500 and r.json()["hata_kodu"] == "TL-DB-01" and len(r.json()["kayit_no"]) == 32
    assert "gizli-sifre" not in r.text and "kullanici" not in r.text
