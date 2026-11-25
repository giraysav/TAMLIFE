"""Profil fotografi (2026-10-15): kisi kendi fotografini yukler, hesap karti /session/photo ile gosterir; baskasina gitmez."""

from __future__ import annotations

JPEG = b"\xff\xd8\xff\xe0" + b"\x10" * 200 + b"\xff\xd9"


def _giris(client, monkeypatch, kullanici: str) -> dict[str, str]:
    client.post("/api/v1/session/logout")
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", kullanici)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    assert client.post("/api/v1/session/login", json={"username": kullanici, "password": "test-parola-1"}).status_code == 200
    return {"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""}


def test_profil_fotografi_yukle_goster_sil(client, monkeypatch):
    hdr = _giris(client, monkeypatch, "ayse")
    assert client.get("/api/v1/session/me").json()["data"]["profile"]["photo_version"] is None
    assert client.get("/api/v1/session/photo").status_code == 404

    jpeg = {**hdr, "Content-Type": "image/jpeg"}
    assert client.put("/api/v1/session/photo", content=JPEG, headers={"Content-Type": "image/jpeg"}).status_code == 403  # CSRF
    assert client.put("/api/v1/session/photo", content=b"\x89PNG" + b"0" * 200, headers=jpeg).status_code == 400
    assert client.put("/api/v1/session/photo", content=b"\xff\xd8\xff" + b"0" * (512 * 1024), headers=jpeg).status_code == 413
    r = client.put("/api/v1/session/photo", content=JPEG, headers=jpeg)
    assert r.status_code == 200 and r.json()["data"]["photo_version"]
    assert client.get("/api/v1/session/me").json()["data"]["profile"]["photo_version"] == r.json()["data"]["photo_version"]
    foto = client.get("/api/v1/session/photo")
    assert foto.content == JPEG and foto.headers["content-type"] == "image/jpeg" and foto.headers["x-content-type-options"] == "nosniff"

    _giris(client, monkeypatch, "mehmet")  # baskasinin fotografi gelmez
    assert client.get("/api/v1/session/photo").status_code == 404

    hdr = _giris(client, monkeypatch, "ayse")
    assert client.delete("/api/v1/session/photo", headers=hdr).json()["data"]["photo_version"] is None
    assert client.get("/api/v1/session/photo").status_code == 404
    client.post("/api/v1/session/logout", headers=hdr)
    assert client.get("/api/v1/session/photo").status_code == 401
