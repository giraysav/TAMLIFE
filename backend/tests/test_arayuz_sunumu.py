"""Derlenmis arayuzun sunumu, cerez yolu ve SQLite izni."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


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


def test_cerez_yolu_alt_yola_kisitlanir_ve_cikista_ayni_yoldan_silinir(client, monkeypatch):
    monkeypatch.setenv("TAMLIFE_BASE_PATH", "/panel")
    r = client.post("/api/v1/session/login", json={"username": "admin", "password": "test-parola-1"})
    cerezler = [h.lower() for h in r.headers.get_list("set-cookie")]
    assert r.status_code == 200 and len(cerezler) == 2 and all("path=/panel" in h for h in cerezler)
    # Tarayici /panel altinda istek atar; testte yol on eki yok, istemci cerezi gondermez: elle ekleriz.
    oturum, csrf = client.cookies.get("tamlife_session"), client.cookies.get("tamlife_csrf") or ""
    r = client.post("/api/v1/session/logout", headers={"Cookie": f"tamlife_session={oturum}; tamlife_csrf={csrf}", "X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert all("path=/panel" in h.lower() for h in r.headers.get_list("set-cookie"))


def test_sqlite_dev_test_disinda_yalniz_acik_izinle(monkeypatch, tmp_path):
    from app.gateway import make_engine

    url = f"sqlite:///{(tmp_path / 'x.db').as_posix()}"
    monkeypatch.setenv("TAMLIFE_ENV", "production")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        make_engine(url)
    monkeypatch.setenv("TAMLIFE_SQLITE_IZIN", "true")
    make_engine(url).dispose()
