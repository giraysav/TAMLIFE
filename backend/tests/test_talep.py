"""Gelistirme Talepleri: zorunlu alanlar, kendi talepleri / is listesi ayrimi, degisiklik gecmisi, yetki ve silme kurali."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser, DemandLog, RoleView

TALEP = {
    "baslik": "Müşteri listesinde personel süzgeci",
    "tur": "iyilestirme",
    "oncelik": "yuksek",
    "modul": "musteri",
    "mevcut_durum": "Liste yalnız müşteri adına göre süzülüyor.",
    "beklenen_durum": "Sorumlu TAM'a göre de süzülebilsin.",
    "kabul_olcutu": "Süzgeç seçilince yalnız o kişinin müşterileri kalır.",
}


def _giris(client, monkeypatch, kullanici: str, rol: str) -> dict[str, str]:
    client.post("/api/v1/session/logout")
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", kullanici)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    r = client.post("/api/v1/session/login", json={"username": kullanici, "password": "test-parola-1"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""}


def _ac(client, hdr, **ek) -> int:
    r = client.post("/api/v1/talep", json={**TALEP, **ek}, headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _liste(client, durum: str = "acik") -> dict:
    r = client.get("/api/v1/talep", params={"durum": durum})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_mevcut_ve_beklenen_durum_ayri_ayri_zorunlu(client, monkeypatch):
    hdr = _giris(client, monkeypatch, "ayse", "TeamMember")
    for eksik in ("baslik", "mevcut_durum", "beklenen_durum"):
        r = client.post("/api/v1/talep", json={**TALEP, eksik: "   "}, headers=hdr)
        assert r.status_code == 400, eksik
    assert client.post("/api/v1/talep", json={**TALEP, "tur": "istek"}, headers=hdr).status_code == 422
    assert client.post("/api/v1/talep", json={**TALEP, "modul": "yok"}, headers=hdr).status_code == 400
    assert client.post("/api/v1/talep", json={**TALEP, "baslik": "x" * 161}, headers=hdr).status_code == 422


def test_uye_yalniz_kendi_talebini_gorur_ve_yonetemez(client, monkeypatch):
    hdr = _giris(client, monkeypatch, "ayse", "TeamMember")
    ayse_talebi = _ac(client, hdr)
    hdr = _giris(client, monkeypatch, "mehmet", "TeamMember")
    _ac(client, hdr, baslik="Takvimde hafta numarası")
    veri = _liste(client)
    assert [t["baslik"] for t in veri["talepler"]] == ["Takvimde hafta numarası"]
    assert veri["yonetebilir"] is False and veri["silebilir"] is False
    assert "acik_sayisi" not in veri and "kisiler" not in veri and "gecmis" not in veri["talepler"][0]
    assert client.patch(f"/api/v1/talep/{ayse_talebi}", json={"durum": "incelemede"}, headers=hdr).status_code == 403
    assert client.delete(f"/api/v1/talep/{ayse_talebi}", headers=hdr).status_code == 403


def test_yonetici_is_listesi_gecmis_ve_acik_suzgeci(client, monkeypatch):
    hdr = _giris(client, monkeypatch, "ayse", "TeamMember")
    talep_id = _ac(client, hdr)
    hdr = _giris(client, monkeypatch, "mudur", "TeamMngr")
    veri = _liste(client)
    assert veri["yonetebilir"] is True and veri["acik_sayisi"] == 1
    satir = veri["talepler"][0]
    assert satir["talep_eden"] == "ayse" and satir["durum"] == "yeni" and satir["kabul_olcutu"] == TALEP["kabul_olcutu"]
    assert [g["alan"] for g in satir["gecmis"]] == ["olusturma"]
    ayse = next(k for k in veri["kisiler"] if k["ad"] == "ayse")

    r = client.patch(f"/api/v1/talep/{talep_id}", json={"durum": "planlandi", "atanan_id": ayse["id"], "hedef_surum": "3.6.0", "admin_notu": "Sprint 4"}, headers=hdr)
    assert r.status_code == 200, r.text
    assert set(r.json()["data"]["degisen"]) == {"durum", "atanan_id", "hedef_surum", "admin_notu"}
    # ayni deger tekrar gelirse gecmise yazilmaz
    r = client.patch(f"/api/v1/talep/{talep_id}", json={"durum": "planlandi", "hedef_surum": " 3.6.0 "}, headers=hdr)
    assert r.json()["data"]["degisen"] == []
    satir = _liste(client)["talepler"][0]
    assert satir["atanan"] == "ayse" and satir["guncellendi"]
    gecmis = {g["alan"]: g for g in satir["gecmis"]}
    assert (gecmis["durum"]["eski"], gecmis["durum"]["yeni"], gecmis["durum"]["yapan"]) == ("yeni", "planlandi", "mudur")
    assert (gecmis["atanan_id"]["eski"], gecmis["atanan_id"]["yeni"]) == ("", "ayse")
    assert len(satir["gecmis"]) == 5

    # atamayi kaldir; olmayan kisi atanamaz
    assert client.patch(f"/api/v1/talep/{talep_id}", json={"atanan_id": None}, headers=hdr).json()["data"]["degisen"] == ["atanan_id"]
    assert client.patch(f"/api/v1/talep/{talep_id}", json={"atanan_id": 999}, headers=hdr).status_code == 400

    client.patch(f"/api/v1/talep/{talep_id}", json={"durum": "tamamlandi"}, headers=hdr)
    assert _liste(client)["talepler"] == [] and _liste(client)["acik_sayisi"] == 0
    assert len(_liste(client, "")["talepler"]) == 1 and len(_liste(client, "tamamlandi")["talepler"]) == 1
    assert client.get("/api/v1/talep", params={"durum": "bilinmeyen"}).status_code == 400

    # talep eden kapanan talebini "Tümü" ile gorur; durum ve not gorunur, gecmis gorunmez
    _giris(client, monkeypatch, "ayse", "TeamMember")
    kendi = _liste(client, "")["talepler"][0]
    assert kendi["durum"] == "tamamlandi" and kendi["admin_notu"] == "Sprint 4" and "gecmis" not in kendi


def test_silme_yalniz_admin_ve_gecmisi_de_siler(client, monkeypatch):
    hdr = _giris(client, monkeypatch, "mudur", "TeamMngr")
    talep_id = _ac(client, hdr)
    client.patch(f"/api/v1/talep/{talep_id}", json={"durum": "incelemede"}, headers=hdr)
    assert client.delete(f"/api/v1/talep/{talep_id}", headers=hdr).status_code == 403
    hdr = _giris(client, monkeypatch, "admin", "admin")
    assert _liste(client)["silebilir"] is True
    assert client.delete(f"/api/v1/talep/{talep_id}", headers=hdr).status_code == 200
    assert client.delete(f"/api/v1/talep/{talep_id}", headers=hdr).status_code == 404
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(DemandLog)) == 0


def test_ek_yetkiyle_uye_de_yonetir(client, monkeypatch):
    with Session(engine()) as db:
        db.add(RoleView(role="TeamMember", modules=["talep"], landing="ozet", permissions=["talep.yonet"]))
        db.commit()
    hdr = _giris(client, monkeypatch, "mehmet", "TeamMember")
    talep_id = _ac(client, hdr)
    _giris(client, monkeypatch, "ayse", "TeamMember")
    veri = _liste(client)
    assert veri["yonetebilir"] is True and len(veri["talepler"]) == 1
    hdr = {"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""}
    assert client.patch(f"/api/v1/talep/{talep_id}", json={"oncelik": "kritik"}, headers=hdr).status_code == 200
    with Session(engine()) as db:
        assert db.scalar(select(AppUser.display_name).where(AppUser.username == "ayse")) == "ayse"
