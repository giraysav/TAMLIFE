# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Takip Edilen Projeler: ozet, aksiyon gecmisi, kapsam (Member yalniz kendi), musteri bazli calismalar ve Excel rapor."""

from __future__ import annotations

import io

from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser, Customer, ProjectAction, ProjectCustomerWork


def _giris(client, monkeypatch, kullanici: str, rol: str) -> dict[str, str]:
    client.post("/api/v1/session/logout")
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", kullanici)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    r = client.post("/api/v1/session/login", json={"username": kullanici, "password": "test-parola-1"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""}


def _kisiler() -> dict[str, int]:
    with Session(engine()) as db:
        return {k.username: k.id for k in db.scalars(select(AppUser))}


def _ekran(client) -> dict:
    r = client.get("/api/v1/proje")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_proje_acilis_durum_oncelik_aksiyon_ve_ozet(client, monkeypatch):
    _giris(client, monkeypatch, "ayse", "TeamMember")
    _giris(client, monkeypatch, "mehmet", "TeamMember")  # projesi olmayacak: ozette yine satir olur (0)
    hdr = _giris(client, monkeypatch, "mudur", "admin")  # kalem ekleme / guncelleme / silme yalniz admin
    ayse, mudur = _kisiler()["ayse"], _kisiler()["mudur"]
    r = client.post("/api/v1/proje/kalem", json={"owner_id": ayse, "category": "ddos", "title": "DDoS eşik ayarı", "target_date": "2026-12-31"}, headers=hdr)
    assert r.status_code == 200, r.text
    kimlik = r.json()["data"]["id"]
    # sorumlu yalniz TAM personeli: secilmezse (admin personel degil) ya da yonetici secilirse reddedilir
    assert client.post("/api/v1/proje/kalem", json={"category": "proje", "title": "SD-WAN geçişi"}, headers=hdr).json()["detail"] == "Sorumlu TAM seçin."
    assert client.post("/api/v1/proje/kalem", json={"owner_id": mudur, "category": "proje", "title": "SD-WAN geçişi"}, headers=hdr).status_code == 400
    assert client.post("/api/v1/proje/kalem", json={"owner_id": ayse, "category": "proje", "title": "SD-WAN geçişi"}, headers=hdr).status_code == 200

    assert client.patch(f"/api/v1/proje/kalem/{kimlik}", json={"status": "kapandi", "priority": "kritik"}, headers=hdr).json()["data"]["degisen"] == ["status", "priority"]
    assert client.patch(f"/api/v1/proje/kalem/{kimlik}", json={"status": "kapandi"}, headers=hdr).json()["data"]["degisen"] == []
    assert client.post(f"/api/v1/proje/kalem/{kimlik}/aksiyon", json={"metin": "Müşteriyle test yapıldı"}, headers=hdr).status_code == 200
    assert client.post(f"/api/v1/proje/kalem/{kimlik}/aksiyon", json={"metin": "  "}, headers=hdr).status_code == 400

    veri = _ekran(client)
    kalem = next(k for k in veri["kalemler"] if k["id"] == kimlik)
    assert kalem["tam"] == "ayse" and kalem["durum"] == "kapandi" and kalem["kapanis"] and kalem["hedef"] == "2026-12-31"
    assert [a["metin"] for a in kalem["aksiyonlar"]] == [
        "Müşteriyle test yapıldı",
        "Öncelik güncellendi: Orta → Kritik",
        "Durum güncellendi: Açık → Kapandı",
        "Proje kaydı oluşturuldu.",
    ]
    assert kalem["aksiyonlar"][0]["yapan"] == "mudur"
    ozet = {d["tam"]: d for d in veri["ozet"]}
    assert ozet["ayse"]["ddos"] == 1 and ozet["ayse"]["kapanan"] == 1 and ozet["ayse"]["toplam"] == 2
    assert ozet["ayse"]["proje"] == 1 and ozet["ayse"]["devam_eden"] == 1 and veri["genel_toplam"] == 2
    assert ozet["mehmet"]["toplam"] == 0 and "mudur" not in ozet  # projesi olmayan personel de satir; yonetici satir olmaz
    assert veri["yonetici"] is True and {t["ad"] for t in veri["tamlar"]} == {"ayse", "mehmet"} and veri["varsayilan_sorumlu"] in {ayse, _kisiler()["mehmet"]}

    # hedef tarih temizlenir; gecersiz deger 422
    assert client.patch(f"/api/v1/proje/kalem/{kimlik}", json={"target_date": None}, headers=hdr).json()["data"]["degisen"] == ["target_date"]
    assert client.patch(f"/api/v1/proje/kalem/{kimlik}", json={"status": "bitti"}, headers=hdr).status_code == 422
    assert client.post("/api/v1/proje/kalem", json={"category": "proje", "title": "x", "start_date": "2026-10-10", "target_date": "2026-10-01"}, headers=hdr).status_code == 400

    assert client.delete(f"/api/v1/proje/kalem/{kimlik}", headers=hdr).status_code == 200
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(ProjectAction).where(ProjectAction.item_id == kimlik)) == 0


def test_uye_yalniz_kendi_projesini_gorur_ve_yazar(client, monkeypatch):
    _giris(client, monkeypatch, "mehmet", "TeamMember")
    _giris(client, monkeypatch, "ayse", "TeamMember")
    kisiler = _kisiler()
    hdr_admin = _giris(client, monkeypatch, "mudur", "admin")
    mehmet_kalemi = client.post("/api/v1/proje/kalem", json={"owner_id": kisiler["mehmet"], "category": "calisma", "title": "Mehmet işi"}, headers=hdr_admin).json()["data"]["id"]
    assert client.post("/api/v1/proje/kalem", json={"owner_id": kisiler["ayse"], "category": "proje", "title": "Ayşe işi"}, headers=hdr_admin).status_code == 200
    hdr = _giris(client, monkeypatch, "ayse", "TeamMember")
    veri = _ekran(client)  # 2026-10-20: herkes tum kalemleri gorur, yalniz kendisine atanani degistirir
    assert {(k["baslik"], k["duzenlenebilir"]) for k in veri["kalemler"]} == {("Ayşe işi", True), ("Mehmet işi", False)}
    assert veri["yonetici"] is False and veri["tamlar"] == [{"id": kisiler["ayse"], "ad": "ayse"}]  # sorumlu secimi yalniz kendisi
    for istek in (
        client.patch(f"/api/v1/proje/kalem/{mehmet_kalemi}", json={"status": "devam"}, headers=hdr),
        client.post(f"/api/v1/proje/kalem/{mehmet_kalemi}/aksiyon", json={"metin": "x"}, headers=hdr),
        client.delete(f"/api/v1/proje/kalem/{mehmet_kalemi}", headers=hdr),
    ):
        assert istek.status_code == 403
    yeni = client.post("/api/v1/proje/kalem", json={"category": "proje", "title": "Yeni"}, headers=hdr)
    assert yeni.status_code == 200
    kimlik = yeni.json()["data"]["id"]
    assert client.patch(f"/api/v1/proje/kalem/{kimlik}", json={"status": "devam"}, headers=hdr).status_code == 200
    assert client.post(f"/api/v1/proje/kalem/{kimlik}/aksiyon", json={"metin": "x"}, headers=hdr).status_code == 200
    assert client.delete(f"/api/v1/proje/kalem/{kimlik}", headers=hdr).status_code == 200


def test_musteri_bazli_calismalar_kapsam_ve_rapor(client, monkeypatch):
    _giris(client, monkeypatch, "ayse", "TeamMember")
    hdr = _giris(client, monkeypatch, "mudur", "TeamMngr")
    k = _kisiler()
    with Session(engine()) as db:
        db.add_all(
            [
                Customer(id=1, external_key="a", name="Alfa A.Ş.", owner_id=k["ayse"]),
                Customer(id=2, external_key="ai", name="Alfa İştirak", owner_id=k["ayse"], parent_id=1),
                Customer(id=3, external_key="b", name="Beta Ltd", owner_id=k["mudur"]),
            ]
        )
        db.commit()
    veri = client.get("/api/v1/proje/musteri").json()["data"]
    assert [(m["ad"], m["istirak"]) for m in veri["musteriler"]] == [("Alfa A.Ş.", False), ("Alfa İştirak", True), ("Beta Ltd", False)]
    assert [m["ad"] for m in client.get("/api/v1/proje/musteri", params={"tam_id": k["mudur"]}).json()["data"]["musteriler"]] == ["Beta Ltd"]

    hdr = _giris(client, monkeypatch, "ayse", "TeamMember")
    liste = client.get("/api/v1/proje/musteri").json()["data"]["musteriler"]  # 2026-10-20: herkes hepsini gorur
    assert [(m["id"], m["duzenlenebilir"]) for m in liste] == [(1, True), (2, True), (3, False)]
    r = client.put("/api/v1/proje/musteri/2/ddos", json={"yapildi": True, "detay": "Eşik 2 Gbps"}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["zaman"]
    client.put("/api/v1/proje/musteri/1/topoloji", json={"yapildi": False, "detay": "Planlanıyor"}, headers=hdr)
    assert client.put("/api/v1/proje/musteri/3/ddos", json={"yapildi": True}, headers=hdr).status_code == 403  # baskasinin musterisi
    assert client.put("/api/v1/proje/musteri/1/yok", json={"yapildi": True}, headers=hdr).status_code == 422
    isaret = client.get("/api/v1/proje/musteri").json()["data"]["isaretler"]
    assert isaret["2"]["ddos"]["yapildi"] is True and isaret["2"]["ddos"]["guncelleyen"] == "ayse"
    assert isaret["1"]["topoloji"] == {**isaret["1"]["topoloji"], "yapildi": False, "detay": "Planlanıyor"}
    # personel ozeti: isaretlenen kutu ilgili kategori sutununa yazilir (istirak catisinin TAM'ina); yalniz detay sayilmaz
    satir = next(d for d in client.get("/api/v1/proje").json()["data"]["ozet"] if d["tam"] == "ayse")
    assert (satir["ddos"], satir["topoloji"], satir["toplam"]) == (1, 0, 1)

    r = client.get("/api/v1/proje/rapor.xlsx")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    ws = load_workbook(io.BytesIO(r.content)).active
    satirlar = [[h.value for h in s] for s in ws.iter_rows(min_row=3)]
    assert satirlar[0][:3] == ["Müşteri", "TAM", "Proje"]
    assert satirlar[2][0] == "   ↳ Alfa İştirak" and satirlar[2][4] == "✓" and satirlar[2][-1] == "Ddos Optimizasyonu: Eşik 2 Gbps"
    assert len(satirlar) == 4  # baslik + tum musteriler (2026-10-20: herkes hepsini gorur)

    # isaret ve detay bosalinca kayit silinir; musteri silinince isaretleri de gider
    client.put("/api/v1/proje/musteri/1/topoloji", json={"yapildi": False, "detay": ""}, headers=hdr)
    hdr = _giris(client, monkeypatch, "admin", "admin")
    assert client.delete("/api/v1/musteri/1", headers=hdr).status_code == 200
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(ProjectCustomerWork)) == 0
