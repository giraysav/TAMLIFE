# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Takip Edilen Projeler Excel ice aktarma (2026-10-31): TAM ceyrek Excel'i -> onizleme -> uygulama; eslesmeyen TAM atamasi, tekrar yok."""

from __future__ import annotations

import io
import json
from datetime import UTC, date, datetime

from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser, ProjectAction, ProjectItem

URL = "/api/v1/proje/ice-al"
DOSYA = "Proje çalışma Ddos opt. çalışması DC taşıma Topoloji iyileştirme sayı ve detayları 2026.xlsm"
KATEGORI = ["", "", "Proje", "", "Çalışma", "", "Ddos Optimizasyon", "", "DC Taşıması", "", "Topoloji iyileştirme", "", "Toplam"]
ALT = ["", "", "Sayı", "Detay", "Sayı", "Detay", "Sayı", "Detay", "Sayı", "Detay", "Sayı", "Detay"]


def _giris(client, monkeypatch, kullanici: str, rol: str) -> dict[str, str]:
    client.post("/api/v1/session/logout")
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", kullanici)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    r = client.post("/api/v1/session/login", json={"username": kullanici, "password": "test-parola-1"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""}


def _excel() -> bytes:
    """Kaynak dosyanin bicimi: Q sayfalarinda TAM bloklari, kategori basina Sayi + Detay; TOPLAM satiri ve ozet sayfasi atlanir."""
    kitap = Workbook()
    kitap.active.title = "Bu sheet'te islem yapiniz"
    q1 = kitap.create_sheet("Q1")
    q1.append(["Q1", "TAM", "Q1 (Ocak, Şubat, Mart)"])
    q1.append(KATEGORI)
    q1.append(ALT)
    q1.append(["", "AYŞE", 1, "Alfa: SD-WAN geçişi", 2, "Beta: devre taşıma", 1, "Alfa", 0, None, 0, None, 4])
    q1.append(["", None, None, None, None, "Gama: " + "uzun açıklama " * 30])
    q1.append(["", "Sevil Yenihan", 0, None, 1, "Delta: topoloji incelemesi"])
    q1.append(["", "TOPLAM", 1, None, 3, None, 1])
    q4 = kitap.create_sheet("Q4")
    q4.append(["Q4", "TAM", "Q4 (Ekim, Kasım, Aralık)"])
    q4.append(KATEGORI)
    q4.append(ALT)
    q4.append(["", "Ayse", 0, None, 0, None, 1, "Alfa", 0, None, 1, "Beta: yedekli topoloji"])
    kitap.create_sheet("2026 TOP").append(["", "TAM", "2026 TOPLAM"])
    cikti = io.BytesIO()
    kitap.save(cikti)
    return cikti.getvalue()


def _istek(client, hdr, yol: str, veri: bytes, atamalar: dict | None = None):
    params = {"dosya": DOSYA, **({"atamalar": json.dumps(atamalar)} if atamalar is not None else {})}
    return client.post(f"{URL}/{yol}", params=params, content=veri, headers=hdr)


def test_onizleme_yazmaz_uygula_yalniz_yeni_ve_eslesmeyen_tam_atanir(client, monkeypatch):
    _giris(client, monkeypatch, "ayse", "TeamMember")
    _giris(client, monkeypatch, "mehmet", "TeamMember")
    with Session(engine()) as db:
        kisi = {k.username: k.id for k in db.scalars(select(AppUser))}
    hdr = _giris(client, monkeypatch, "mudur", "admin")
    veri = _excel()

    r = _istek(client, hdr, "onizleme", veri)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["yil"] == 2026 and d["plan"] == {"toplam": 7, "yeni": 6, "var": 0, "tekrar": 0, "tam_yok": 1}
    assert d["eslesmeyen"] == [{"ad": "Sevil Yenihan", "anahtar": "sevil yenihan", "kayit": 1}]
    assert {"id": kisi["mehmet"], "ad": "mehmet"} in d["kisiler"]
    uzun = next(s for s in d["satirlar"] if s["baslik"].startswith("Gama"))
    assert len(uzun["baslik"]) == 200 and uzun["baslik"].endswith("…") and uzun["kategori"] == "calisma"
    with Session(engine()) as db:
        assert db.scalar(select(ProjectItem.id)) is None  # onizleme yazmaz

    r = _istek(client, hdr, "uygula", veri)
    assert r.json()["data"] == {"toplam": 7, "yeni": 6, "var": 0, "tekrar": 0, "tam_yok": 1, "eklendi": 6}
    with Session(engine()) as db:
        kalemler = db.scalars(select(ProjectItem).order_by(ProjectItem.id)).all()
        assert {k.owner_id for k in kalemler} == {kisi["ayse"]} and {k.status for k in kalemler} == {"acik"}
        assert {(k.category, k.start_date) for k in kalemler} >= {("proje", date(2026, 1, 1)), ("ddos", date(2026, 10, 1)), ("topoloji", date(2026, 10, 1))}
        gama = next(k for k in kalemler if k.title.startswith("Gama"))
        assert gama.description.startswith("Gama: uzun") and len(gama.description) > 200  # aciklama kesilmez
        metinler = [a.text for a in db.scalars(select(ProjectAction).where(ProjectAction.item_id == kalemler[0].id))]
        assert metinler == ["Proje kaydı oluşturuldu.", f"Excel'den aktarıldı: {DOSYA} · Q1 2026"]

    # eslesmeyen TAM secilen kisiye: onceki kayitlar 'var', yalniz atanan eklenir; aciklamada asil TAM
    r = _istek(client, hdr, "uygula", veri, {"sevil yenihan": kisi["mehmet"]})
    assert r.json()["data"] == {"toplam": 7, "yeni": 1, "var": 6, "tekrar": 0, "tam_yok": 0, "eklendi": 1}
    with Session(engine()) as db:
        delta = db.scalar(select(ProjectItem).where(ProjectItem.title == "Delta: topoloji incelemesi"))
        assert delta.owner_id == kisi["mehmet"] and delta.description == "Asıl TAM: Sevil Yenihan\nDelta: topoloji incelemesi"
    assert _istek(client, hdr, "uygula", veri, {"sevil yenihan": kisi["mehmet"]}).json()["data"]["eklendi"] == 0  # ikinci yukleme


def test_yetki_ve_hatali_girdi(client, monkeypatch):
    hdr = _giris(client, monkeypatch, "ayse", "TeamMember")
    assert _istek(client, hdr, "onizleme", _excel()).status_code == 403  # Import yalniz admin
    hdr = _giris(client, monkeypatch, "mudur", "admin")
    assert _istek(client, hdr, "onizleme", b"excel degil").status_code == 400
    assert client.post(f"{URL}/onizleme", params={"atamalar": "[1]"}, content=_excel(), headers=hdr).status_code == 400
    assert client.post(f"{URL}/onizleme", content=_excel()).status_code == 403  # CSRF'siz
    bos = io.BytesIO()
    Workbook().save(bos)
    assert _istek(client, hdr, "onizleme", bos.getvalue()).json()["detail"].startswith("Q1–Q4 sayfalarında")


def test_aktarim_geri_alinir_sonradan_aksiyon_girilen_korunur(client, monkeypatch):
    """2026-11-01: proje Excel aktarimi Import > Ice aktarma gecmisi'nden geri alinir; sonradan guncellenen proje korunur."""
    _giris(client, monkeypatch, "ayse", "TeamMember")
    hdr = _giris(client, monkeypatch, "mudur", "admin")
    assert _istek(client, hdr, "uygula", _excel()).json()["data"]["eklendi"] == 6
    kayit = client.get("/api/v1/tampon/ice-aktarmalar").json()["data"][0]
    assert (kayit["tur"], kayit["dosya"], kayit["kullanici"], kayit["ozet"]["eklendi"]) == ("proje", DOSYA, "mudur", 6)
    with Session(engine()) as db:
        db.scalars(select(ProjectItem).order_by(ProjectItem.id)).first().updated_at = datetime(2020, 1, 1, tzinfo=UTC)
        db.commit()
    assert client.post(f"{"/api/v1/tampon/ice-aktarmalar"}/{kayit['id']}/geri-al", headers=hdr).json()["data"] == {"geri_alinan": 5, "korunan": 1}
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(ProjectItem)) == 1
        assert db.scalar(select(func.count()).select_from(ProjectAction)) == 2  # yalniz korunan projenin aksiyonlari
    personel = _giris(client, monkeypatch, "ayse", "TeamMember")
    assert client.post(f"{"/api/v1/tampon/ice-aktarmalar"}/{kayit['id']}/geri-al", headers=personel).status_code == 403
