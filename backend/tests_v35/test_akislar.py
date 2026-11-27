# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Veri Girisi ust paneli: veri akislari (tum ice alma yollari tek bakista), kaynak listesi sorgu sayisi, TEMIP eslesme ucu."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppSetting, AuditEvent, Customer, IngestBatch
from app.tampon import akislar, kaynak, reportdb
from tests_v35.conftest import login_ok
from tests_v35.test_temip_kayit import SahteTemip, calistir, eslesme_satirlari, kart, kisi, sahip

CSV = "Müşteri No;Adet\n10000001;2\n"


def _akis(veri, anahtar):
    return next(a for a in veri["akislar"] if a["anahtar"] == anahtar)


def test_akislar_bos_panelde_yok_csv_ve_denetimden_son_gelis(client):
    hdr = login_ok(client)
    r = client.get("/api/v1/tampon/akislar")
    assert r.status_code == 200
    veri = r.json()["data"]
    assert {a["anahtar"] for a in veri["akislar"]} == {
        "musteri_ham",
        "oracle_reportdb",
        "temip",
        "onedesk",
        "urun_tutar",
        "gelir_uretim",
        "csv",
    }
    assert all(a["durum"] == "yok" for a in veri["akislar"]) and veri["dagitim"] == {"kural": 0, "etkin": 0, "son_uygulama": None}
    assert _akis(veri, "temip")["aciklama"].startswith("İlk yükleme yapılmadı")
    assert (
        client.put(
            "/api/v1/tampon/yukle?kaynak=alarm&dosya=a.csv", content=CSV.encode(), headers={**hdr, "Content-Type": "text/csv"}
        ).status_code
        == 200
    )
    with Session(engine()) as db:
        db.add(AuditEvent(at=datetime.now(UTC), actor="admin", action="onedesk.ice_al", outcome="allow", module_key="onedesk", detail=""))
        db.commit()
    veri = client.get("/api/v1/tampon/akislar").json()["data"]
    assert (_akis(veri, "csv")["durum"], _akis(veri, "onedesk")["durum"]) == ("bilgi", "bilgi")  # elle gelen dosya: tazelik beklentisi yok


def test_akislar_reportdb_bayat_uyarir_kapaliyken_uyarmaz(client, monkeypatch):
    login_ok(client)
    with Session(engine()) as db:
        db.add(IngestBatch(source_key=reportdb.KAYNAK, label="ReportDB", status="ready", row_count=1, created_by="reportdb",
                           received_at=datetime.now(UTC) - timedelta(days=3)))  # fmt: skip
        db.commit()
    monkeypatch.setenv("ORACLE_REPORTDB_ENABLED", "true")
    for k in ("HOST", "SERVICE_NAME", "USER", "PASSWORD"):
        monkeypatch.setenv(f"ORACLE_REPORTDB_{k}", "x")
    veri = client.get("/api/v1/tampon/akislar").json()["data"]
    assert _akis(veri, "oracle_reportdb")["durum"] == "bayat" and veri["uyarilar"] == ["ReportDB alarm özeti: veri bayat"]
    monkeypatch.setenv("ORACLE_REPORTDB_ENABLED", "false")
    veri = client.get("/api/v1/tampon/akislar").json()["data"]
    assert _akis(veri, "oracle_reportdb")["durum"] == "bilgi" and veri["uyarilar"] == []


def test_kaynak_listesi_sorgu_sayisi_kaynak_sayisindan_bagimsiz(client):
    hdr = login_ok(client)
    for ad in ("a", "b", "c", "d"):
        client.put(f"/api/v1/tampon/yukle?kaynak={ad}&dosya={ad}.csv", content=CSV.encode(), headers={**hdr, "Content-Type": "text/csv"})
    sayac = {"n": 0}

    def say(*_):
        sayac["n"] += 1

    motor = engine()
    event.listen(motor, "before_cursor_execute", say)
    try:
        with Session(motor) as db:
            liste = kaynak.durumlar(db)
    finally:
        event.remove(motor, "before_cursor_execute", say)
    assert {k["anahtar"]: k["parti_sayisi"] for k in liste if k["anahtar"].startswith("csv_")} == {f"csv_{x}": 1 for x in "abcd"}
    assert sayac["n"] <= 8  # eskisi kaynak basina 2 sorgu (8 kaynakta 16+)


def test_temip_eslesme_ucu_suzgec_arama_sayfa_ve_sema_korumasi(client, monkeypatch):
    tam = kisi("tam")
    sahip(kart("ORNEK-A", "10000001"), tam)
    kart("IKIZ-1", "30000003")
    kart("IKIZ-2", "30000003")
    t = SahteTemip(monkeypatch)
    eslesme_satirlari(t)
    calistir()
    login_ok(client)
    r = client.get("/api/v1/tampon/temip/eslesme").json()["data"]
    assert r["hazir"] and r["ozet"]["kart"]["acik"] == 2 and r["toplam"] == 5 and r["musteriler"][0]["musteri_no"] == "10000001"
    assert [p["personel_kullanici"] for p in r["personel"]] == ["ornek_tam"] and r["uyari"]["belirsiz_numara"] == ["30000003"]
    assert client.get("/api/v1/tampon/temip/eslesme?durum=belirsiz").json()["data"]["toplam"] == 1
    assert client.get("/api/v1/tampon/temip/eslesme?q=ornek%20tam").json()["data"]["toplam"] == 1  # personel adiyla arama
    with Session(engine()) as db:
        assert db.get(AppSetting, "temip.surum") is not None
        db.get(Customer, 1).customer_no = "99999999"  # kart numarasi degisti: onbellekteki gruplarla da guncel eslesme
        db.commit()
    assert client.get("/api/v1/tampon/temip/eslesme").json()["data"]["ozet"]["kart"]["musteri"] == 0
    veri = client.get("/api/v1/tampon/akislar").json()["data"]
    assert _akis(veri, "temip")["durum"] in ("taze", "bilgi") and _akis(veri, "temip")["acik"] == 6
    monkeypatch.setattr(akislar, "temip_semasi_hazir", lambda _db: False)
    assert client.get("/api/v1/tampon/temip/eslesme").json()["data"] == {"hazir": False, "neden": "0013_onedesk_temip uygulanmadı."}


def test_yeni_uclar_yalniz_admin(client):
    for yol in ("/api/v1/tampon/akislar", "/api/v1/tampon/temip/eslesme"):
        assert client.get(yol).status_code == 401
