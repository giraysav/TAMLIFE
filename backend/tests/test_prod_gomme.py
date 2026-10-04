"""Uretim paneli (Flask) arkasinda /admin/dev altinda calisma: SSO, cerez yolu, arayuz sunumu."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.session import reset_for_tests

SIR = "s" * 40
YONETICI = {"X-TAM-User": "ayse.yilmaz", "X-TAM-Role": "admin", "X-TAM-Proxy-Secret": SIR}


def _cerez(c: TestClient) -> dict[str, str]:
    """Tarayici /admin/dev altinda istek atar; testte yol on eki yok, bu yuzden cerezi elle ekleriz."""
    return {"Cookie": f"tamlife_session={c.cookies.get('tamlife_session')}; tamlife_csrf={c.cookies.get('tamlife_csrf')}"}


@pytest.fixture
def sso(client, monkeypatch):
    monkeypatch.setenv("TAMLIFE_SSO_SECRET", SIR)
    monkeypatch.setenv("TAMLIFE_BASE_PATH", "/admin/dev")
    reset_for_tests()
    with TestClient(create_app(), base_url="http://testserver", client=("127.0.0.1", 50000)) as c:
        yield c


def test_sso_acar_oturumu_ve_cerez_yolunu_kisitlar(sso):
    r = sso.post("/api/v1/session/sso", headers=YONETICI)
    assert r.status_code == 200 and r.json()["data"] == {"username": "ayse.yilmaz", "role": "admin"}
    cerezler = [h.lower() for h in r.headers.get_list("set-cookie")]
    assert cerezler and all("path=/admin/dev" in h for h in cerezler)
    me = sso.get("/api/v1/session/me", headers=_cerez(sso))
    assert me.status_code == 200 and me.json()["data"]["is_admin"] is True


def test_sso_sirsiz_yanlis_sir_ve_kisa_sir_reddedilir(sso, monkeypatch):
    kotu = [
        {k: v for k, v in YONETICI.items() if k != "X-TAM-Proxy-Secret"},
        {**YONETICI, "X-TAM-Proxy-Secret": "x" * 40},
        {**YONETICI, "X-TAM-User": ""},
        {**YONETICI, "X-TAM-User": "a b;c"},
        {**YONETICI, "X-TAM-Role": "root"},
    ]
    for basliklar in kotu:
        assert sso.post("/api/v1/session/sso", headers=basliklar).status_code == 401, basliklar
    monkeypatch.setenv("TAMLIFE_SSO_SECRET", "kisa")
    assert sso.post("/api/v1/session/sso", headers={**YONETICI, "X-TAM-Proxy-Secret": "kisa"}).status_code == 401
    assert sso.get("/api/v1/session/me", headers=_cerez(sso)).status_code == 401


def test_sso_loopback_disindan_reddedilir(monkeypatch):
    monkeypatch.setenv("TAMLIFE_SSO_SECRET", SIR)
    with TestClient(create_app(), base_url="http://testserver", client=("10.1.2.3", 50000)) as c:
        assert c.post("/api/v1/session/sso", headers=YONETICI).status_code == 401


def test_sso_kapali_iken_secret_bos(client):
    assert client.post("/api/v1/session/sso", headers=YONETICI).status_code == 401


def test_sso_origin_denetimi_gecerli(sso):
    r = sso.post("/api/v1/session/sso", headers={**YONETICI, "Origin": "https://baska.example"})
    assert r.status_code == 403


def test_cikis_cerezi_ayni_yoldan_siler(sso):
    sso.post("/api/v1/session/sso", headers=YONETICI)
    r = sso.post("/api/v1/session/logout", headers={**_cerez(sso), "X-CSRF-Token": sso.cookies.get("tamlife_csrf") or ""})
    assert r.status_code == 200
    assert all("path=/admin/dev" in h.lower() for h in r.headers.get_list("set-cookie"))


def test_arayuz_derlenmis_dizinden_sunulur(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>x</title><div id=root></div>", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (tmp_path / "assets" / "a.js").write_text("console.log(1)", encoding="utf-8")
    gizli = tmp_path.parent / "gizli.txt"
    gizli.write_text("gizli", encoding="utf-8")
    monkeypatch.setenv("TAMLIFE_STATIC_DIR", str(tmp_path))
    with TestClient(create_app(), base_url="http://testserver") as c:
        kok = c.get("/")
        assert kok.status_code == 200 and "root" in kok.text
        assert "script-src 'self'" in kok.headers["content-security-policy"]
        assert c.get("/assets/a.js").status_code == 200
        assert c.get("/favicon.svg").status_code == 200
        assert c.get("/yok.png").status_code == 404
        assert c.get("/..%2fgizli.txt").status_code == 404
        assert c.get("/%2e%2e/gizli.txt").status_code == 404
        # API cevaplari kati CSP'de kalir
        api = c.get("/api/v1/health")
        assert api.headers["content-security-policy"].startswith("default-src 'none'")


def test_arayuz_dizini_yoksa_yalniz_api(tmp_path, monkeypatch):
    monkeypatch.setenv("TAMLIFE_STATIC_DIR", str(Path(tmp_path) / "yok"))
    with TestClient(create_app(), base_url="http://testserver") as c:
        assert c.get("/").status_code == 404
        assert c.get("/api/v1/health").status_code == 200


def test_sqlite_dev_test_disinda_yalniz_acik_izinle(monkeypatch, tmp_path):
    from app.gateway import make_engine

    url = f"sqlite:///{(tmp_path / 'x.db').as_posix()}"
    monkeypatch.setenv("TAMLIFE_ENV", "production")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        make_engine(url)
    monkeypatch.setenv("TAMLIFE_SQLITE_IZIN", "true")
    make_engine(url).dispose()
