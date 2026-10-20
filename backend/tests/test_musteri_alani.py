"""Toptan / Baglantili Araclar kartlari Musteri Yonetimi'nden ayri (app.musteri_alani): liste, kart, ekleme ve silme yalniz istegin
alaninda; Toptan'dan silmek Musteri Yonetimi kartina dokunmaz; diger moduller (baslik yok) yalniz Musteri Yonetimi kartlarini gorur.
Uydurma test verisi."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import musteri_alani
from app.db import engine
from app.models import Customer
from tests.conftest import login_ok
from tests.test_musteri import veri  # noqa: F401 - fixture

TOPTAN = {"X-Musteri-Alani": "toptan"}


def _adlar(c, basliklar=None):
    return sorted(i["name"] for i in c.get("/api/v1/musteri", headers=basliklar or {}).json()["data"]["items"])


def test_toptan_kartlari_ayri_eklenir_silinir_ve_musteri_yonetimine_dokunmaz(veri):  # noqa: F811
    hdr = login_ok(veri)
    assert _adlar(veri, TOPTAN) == []  # Toptan bos baslar; Musteri Yonetimi kartlari gorunmez
    assert veri.get("/api/v1/musteri/1", headers=TOPTAN).status_code == 404  # baska alanin karti acilmaz
    r = veri.post("/api/v1/musteri", json={"name": "Alfa Test A.S.", "owner_id": 2}, headers={**hdr, **TOPTAN})  # ayni unvan ayri alanda serbest
    assert r.status_code == 200, r.text
    yeni = r.json()["data"]["id"]
    assert _adlar(veri, TOPTAN) == ["Alfa Test A.S."]
    assert _adlar(veri) == ["Alfa Istirak", "Alfa Test A.S.", "Beta Test Ltd"]
    assert veri.post("/api/v1/musteri", json={"name": "ALFA TEST A.S.", "owner_id": 2}, headers={**hdr, **TOPTAN}).status_code == 409
    assert veri.delete(f"/api/v1/musteri/{yeni}", headers=hdr).status_code == 404  # Musteri Yonetimi'nden Toptan karti silinmez
    assert veri.delete("/api/v1/musteri/1", headers={**hdr, **TOPTAN}).status_code == 404  # Toptan'dan Musteri Yonetimi karti silinmez
    assert veri.delete(f"/api/v1/musteri/{yeni}", headers={**hdr, **TOPTAN}).status_code == 200
    assert _adlar(veri, TOPTAN) == [] and _adlar(veri) == ["Alfa Istirak", "Alfa Test A.S.", "Beta Test Ltd"]
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Customer)) == 3


def test_baslik_yoksa_ve_gecersizse_musteri_alani_isci_sorgulari_suzulur(veri):  # noqa: F811
    login_ok(veri)
    assert _adlar(veri, {"X-Musteri-Alani": "bilinmeyen"}) == ["Alfa Istirak", "Alfa Test A.S.", "Beta Test Ltd"]
    jeton = musteri_alani.ayarla("baglantili")
    try:
        with Session(engine()) as db:
            db.add(Customer(external_key="baglantili-x", name="Bag Arac"))
            db.commit()
            assert [c.name for c in db.scalars(select(Customer))] == ["Bag Arac"]
    finally:
        musteri_alani.geri_al(jeton)
    with Session(engine()) as db:  # isci / diger moduller: varsayilan alan
        assert db.scalar(select(func.count()).select_from(Customer)) == 3
        assert db.get(Customer, 1) is not None
        assert db.scalars(select(Customer.name).where(Customer.name == "Bag Arac")).all() == []
    assert _adlar(veri, {"X-Musteri-Alani": "baglantili"}) == ["Bag Arac"]


def test_toptan_yalniz_modul_sahibi_ve_admin_yazar_digerleri_gorur(veri, monkeypatch):  # noqa: F811
    """2026-10-20 kullanici karari: Toptan (KAAN USTUN) / Baglantili Araclar (UGUR KULEKCI) yonetimli; sahibi ve admin yazar."""
    from app.models import AppUser
    from tests.test_musteri import _cikis, _giris

    hdr = login_ok(veri)
    kart = veri.post("/api/v1/musteri", json={"name": "Toptan Kart", "owner_id": 2}, headers={**hdr, **TOPTAN}).json()["data"]["id"]
    _cikis(veri, hdr)
    hdr = _giris(veri, monkeypatch, "TeamMember")  # 'admin' satirina bagli personel; Toptan'in sahibi degil
    assert _adlar(veri, TOPTAN) == ["Toptan Kart"]  # icerigi gorur
    assert veri.get(f"/api/v1/musteri/{kart}", headers=TOPTAN).json()["data"]["erisim"]["kimlik_duzenle"] is False
    assert veri.get("/api/v1/musteri/secenekler", headers=TOPTAN).json()["data"]["ekleyebilir"] is False
    assert veri.put(f"/api/v1/musteri/{kart}/kimlik", json={"sector": "X"}, headers={**hdr, **TOPTAN}).status_code == 403
    assert veri.post("/api/v1/musteri", json={"name": "Yeni Toptan"}, headers={**hdr, **TOPTAN}).status_code == 403
    assert veri.delete(f"/api/v1/musteri/{kart}", headers={**hdr, **TOPTAN}).status_code == 403
    with Session(engine()) as db:
        db.scalar(select(AppUser).where(AppUser.username == "admin")).module_owner = "toptan"
        db.commit()
    assert veri.put(f"/api/v1/musteri/{kart}/kimlik", json={"sector": "X"}, headers={**hdr, **TOPTAN}).status_code == 200  # sahibi
    assert veri.put(f"/api/v1/musteri/{kart}/sorumlu", json={"owner_id": 2}, headers={**hdr, **TOPTAN}).status_code == 200
    assert veri.post("/api/v1/musteri", json={"name": "Yeni Toptan", "owner_id": 2}, headers={**hdr, **TOPTAN}).status_code == 200
    assert veri.put("/api/v1/musteri/3/kimlik", json={"sector": "X"}, headers=hdr).status_code == 403  # Musteri Yonetimi'nde: kendisine atanmamis
    assert veri.post("/api/v1/musteri", json={"name": "Bag"}, headers={**hdr, "X-Musteri-Alani": "baglantili"}).status_code == 403  # baska modul
