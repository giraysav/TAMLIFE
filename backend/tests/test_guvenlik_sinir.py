"""Sinir zorlayan guvenlik testleri: tum uclarda kimliksiz/CSRF'siz erisim, oturum yeniden dogrulama, kaba kuvvet sinirlayici
atlatma, X-Forwarded-For sahteciligi, Host/Origin enjeksiyonu, yol gezinme, SQL enjeksiyonu kaliplari, govde siniri."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import update
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.db import engine
from app.models import AppUser, Customer
from app.security import LoginLimiter, client_ip
from tests.conftest import login_ok

ACIK = {("POST", "/api/v1/session/login"), ("POST", "/api/v1/session/logout"), ("GET", "/api/v1/health")}
GUVENSIZ = {"POST", "PUT", "PATCH", "DELETE"}


def _uclar(app) -> list[tuple[str, str]]:
    sonuc: list[tuple[str, str]] = []

    def gez(rotalar, on: str = "") -> None:
        for r in rotalar:
            ic = getattr(r, "router", None) or getattr(r, "original_router", None)
            if ic is not None and not isinstance(r, APIRoute):
                gez(ic.routes, on + getattr(r, "prefix", ""))
            elif isinstance(r, APIRoute):
                yol = re.sub(r"\{[^}]+\}", "1", on + r.path)
                sonuc.extend((y, yol) for y in r.methods)

    gez(app.routes)
    return sorted(set(sonuc))


def _giris(client, monkeypatch, ad: str, rol: str) -> dict[str, str]:
    client.post("/api/v1/session/logout", headers={"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""})
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", ad)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    r = client.post("/api/v1/session/login", json={"username": ad, "password": "test-parola-1"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""}


def test_uc_listesi_bos_degil(client):
    assert len(_uclar(client.app)) > 140


def test_kimliksiz_hicbir_uc_veri_dondurmez(client):
    for yontem, yol in _uclar(client.app):
        if (yontem, yol) in ACIK:
            continue
        r = client.request(yontem, yol, json={})
        assert r.status_code in {401, 403}, (yontem, yol, r.status_code)
        assert "success" not in r.text, (yontem, yol)


def test_csrf_basligi_olmadan_hicbir_yazma_ucu_calismaz(client):
    login_ok(client)
    for yontem, yol in _uclar(client.app):
        if yontem not in GUVENSIZ or (yontem, yol) in ACIK:
            continue
        for baslik in ({}, {"X-CSRF-Token": "sahte"}, {"X-CSRF-Token": client.cookies.get("tamlife_session") or ""}):
            r = client.request(yontem, yol, json={}, headers=baslik)
            assert r.status_code == 403 and "CSRF" in r.text, (yontem, yol, r.status_code)


def test_teammember_yonetim_ve_yazma_uclarinda_403(client, monkeypatch):
    hdr = _giris(client, monkeypatch, "uye", "TeamMember")
    for yontem, yol in _uclar(client.app):
        if yol.startswith(("/api/v1/yonetim", "/api/v1/tampon", "/api/v1/roller")) or (yol.startswith("/api/v1/skor") and yol != "/api/v1/skor/talepler"):
            r = client.request(yontem, yol, json={}, headers=hdr)
            assert r.status_code == 403, (yontem, yol, r.status_code)


@pytest.mark.parametrize(
    "degisiklik",
    [{"active": False}, {"role": "admin"}, {"role": "TeamMngr"}, {"username": "baska_ad"}],
    ids=["pasif", "rol-yukseltme", "rol-degisimi", "hesap-yok"],
)
def test_hesap_baska_surecte_degisirse_oturum_duser(client, monkeypatch, degisiklik):
    _giris(client, monkeypatch, "uye", "TeamMember")
    assert client.get("/api/v1/session/me").status_code == 200
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", "baskasi")  # hesap artik yalniz veritabaninda (AD/yerel acil hesap gibi)
    with Session(engine()) as db:
        db.execute(update(AppUser).where(AppUser.username == "uye").values(**degisiklik))
        db.commit()
    assert client.get("/api/v1/session/me").status_code == 401
    assert client.get("/api/v1/musteri").status_code == 401
    with Session(engine()) as db:
        db.execute(update(AppUser).values(active=True, role="TeamMember", username="uye"))
        db.commit()
    assert client.get("/api/v1/session/me").status_code == 401  # oturum sunucuda silindi, geri gelmez


def test_sinirlayici_toplu_isimle_sifirlanamaz(monkeypatch):
    monkeypatch.setenv("TAMLIFE_LOGIN_MAX_ATTEMPTS", "3")
    s = LoginLimiter()
    for _ in range(3):
        s.failed("10.1.1.1", "admin")
    assert s.retry_after("10.1.1.1", "admin") > 0
    for i in range(LoginLimiter.AZAMI_ANAHTAR + 50):
        s.failed(f"10.2.{i // 250}.{i % 250}", f"rastgele{i}")
    assert s.retry_after("10.1.1.1", "admin") > 0


def test_sinirlayici_suresi_gecen_kayitlari_atar(monkeypatch):
    s = LoginLimiter()
    zaman = [1000.0]
    monkeypatch.setattr("app.security.time.monotonic", lambda: zaman[0])
    for i in range(LoginLimiter.AZAMI_ANAHTAR):
        s.failed(f"10.3.{i // 250}.{i % 250}", f"k{i}")
    zaman[0] += 10_000
    s.failed("10.9.9.9", "son")
    assert len(s._fails) <= 2 and not s._locked



def test_ortak_ip_baska_kullanicinin_girisini_kilitlemez(monkeypatch):
    monkeypatch.setenv("TAMLIFE_LOGIN_MAX_ATTEMPTS", "5")
    s = LoginLimiter()
    for i in range(19):
        for _ in range(5):
            s.failed("10.5.5.5", f"citrix{i}")
        assert s.retry_after("10.5.5.5", f"citrix{i}") > 0
    assert s.retry_after("10.5.5.5", "masum") == 0
    for _ in range(5):
        s.failed("10.5.5.5", "citrix19")
    assert s.retry_after("10.5.5.5", "masum") > 0


def test_sahte_x_forwarded_for_kilitlemeyi_atlatamaz(client):
    for i in range(5):
        client.post("/api/v1/session/login", json={"username": "admin", "password": "x"}, headers={"X-Forwarded-For": f"1.1.1.{i}"})
    r = client.post("/api/v1/session/login", json={"username": "admin", "password": "test-parola-1"}, headers={"X-Forwarded-For": "9.9.9.9"})
    assert r.status_code == 429


def test_guvenilir_vekilde_sagdan_ilk_guvenilmeyen_adres(monkeypatch):
    monkeypatch.setenv("TAMLIFE_TRUSTED_PROXIES", "127.0.0.1")

    def istek(xff: str) -> Request:
        return Request({"type": "http", "headers": [(b"x-forwarded-for", xff.encode())], "client": ("127.0.0.1", 1)})

    assert client_ip(istek("6.6.6.6, 10.0.0.5")) == "10.0.0.5"  # istemcinin basa yazdigi sahte adres secilmez
    assert client_ip(istek("10.0.0.5")) == "10.0.0.5"
    assert client_ip(istek("127.0.0.1")) == "127.0.0.1"
    assert client_ip(istek("")) == "127.0.0.1"


@pytest.mark.parametrize("host", ["evil.example", "tamlife.evil.example", "127.0.0.1.evil", "localhost:8117@evil"])
def test_izinsiz_host_reddedilir(client, host):
    assert client.get("/api/v1/health", headers={"Host": host}).status_code == 400


@pytest.mark.parametrize("origin", ["null", "https://evil.example", "http://testserver.evil", "file://"])
def test_yabanci_origin_yazmada_reddedilir(client, origin):
    hdr = login_ok(client)
    r = client.post("/api/v1/session/logout", headers={**hdr, "Origin": origin})
    assert r.status_code == 403 and r.json()["detail"] == "Kaynak reddedildi"


def test_sahte_oturum_cerezi_401(client):
    login_ok(client)
    client.cookies.set("tamlife_session", "A" * 43)
    assert client.get("/api/v1/session/me").status_code == 401


@pytest.mark.parametrize("yol", ["/..%2fgizli.txt", "/%2e%2e/gizli.txt", "/..%5cgizli.txt", "/assets/..%2f..%2fgizli.txt", "/%2e%2e%2f%2e%2e%2fgizli.txt"])
def test_arayuz_yol_gezinme(client, monkeypatch, tmp_path: Path, yol):
    from fastapi.testclient import TestClient

    from app.main import create_app

    kok = tmp_path / "dist"
    (kok / "assets").mkdir(parents=True)
    (kok / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "gizli.txt").write_text("SIR", encoding="utf-8")
    monkeypatch.setenv("TAMLIFE_STATIC_DIR", str(kok))
    with TestClient(create_app(), base_url="http://testserver") as c:
        r = c.get(yol)
        assert "SIR" not in r.text and r.status_code in {400, 404}, (yol, r.status_code)


@pytest.mark.parametrize(
    "yuk",
    ["' OR '1'='1", "%' OR 1=1 --", "%", "_", "\\", "'; DROP TABLE customer; --", "\" OR \"\"=\"", "Alfa' UNION SELECT username FROM app_user --"],
)
def test_arama_parametresinde_sql_enjeksiyonu(client, monkeypatch, yuk):
    _giris(client, monkeypatch, "uye", "TeamMember")
    with Session(engine()) as db:
        db.add(Customer(external_key="X1", name="Gizli Musteri", owner_id=None))
        db.commit()
    r = client.get("/api/v1/musteri", params={"q": yuk})
    assert r.status_code == 200 and r.json()["data"]["total"] == 0
    _giris(client, monkeypatch, "admin", "admin")
    r = client.get("/api/v1/musteri", params={"q": yuk})
    assert r.status_code == 200 and r.json()["data"]["total"] == 0
    assert client.get("/api/v1/yonetim/gunlukler", params={"q": yuk, "kullanici": yuk, "olay": yuk}).status_code == 200
    with Session(engine()) as db:
        assert db.get(Customer, 1) is not None


@pytest.mark.parametrize("kimlik", ["0", "-1", "2147483648", "99999999999999999999999", "1e3", "1;DROP"])
def test_kimlik_sinir_disi_422_ya_da_404(client, kimlik):
    login_ok(client)
    assert client.get(f"/api/v1/musteri/{kimlik}").status_code in {404, 422}


def test_chunked_govde_siniri_bildirilen_boyutsuz_da_413(client):
    hdr = login_ok(client)

    def parcalar():
        for _ in range(12):
            yield b"x" * (1024 * 1024)

    r = client.put("/api/v1/topoloji/analiz", content=parcalar(), headers=hdr)
    assert r.status_code == 413


def test_yalan_content_length_govdeyi_kesmez(client):
    hdr = login_ok(client)
    r = client.put("/api/v1/topoloji/analiz", content=b"x" * (11 * 1024 * 1024), headers={**hdr, "Content-Length": "10"})
    assert r.status_code in {400, 413}


def test_hata_govdesi_ic_ayrinti_sizdirmaz(client, monkeypatch):
    from fastapi.testclient import TestClient

    c = TestClient(client.app, base_url="http://testserver", raise_server_exceptions=False)
    hdr = login_ok(c)

    def patla(*_a, **_k):
        raise RuntimeError("C:\\gizli\\yol sqlite:///var/dev.db parola=xyz")

    monkeypatch.setattr("app.oturum_api.kullanicilar.profil_guncelle", patla)
    r = c.put("/api/v1/session/profile", json={"phone": "1"}, headers=hdr)
    assert r.status_code == 500
    assert "gizli" not in r.text and "dev.db" not in r.text and "xyz" not in r.text and "kayit_no" in r.text
