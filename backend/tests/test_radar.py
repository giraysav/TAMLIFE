"""Musteri Radar: bos durum, eski ReportDB ozet yedeginin kalktigi ve rol gorunurlugu. TEMIP kayitli Radar akisi
test_temip_kayit.py / test_fark.py'de."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import Customer, RoleView
from app.tampon import depo, reportdb
from tests.conftest import login_ok

# Eski ReportDB alarm ozeti partisi (2026-11-23 oncesi bicim; uydurma veri).
BASLIK = ["Musteri No", "Musteri Unvani", "Aktif Alarm", "Biletli Aktif Alarm", "Kapanan Alarm", "Biletli Kapanan Alarm",
          "En Eski Alarm", "Son Kapanis", "Veri Zamani"]  # fmt: skip


def _ozet_partisi(*satirlar) -> None:
    with Session(engine()) as db:
        p = depo.parti_olustur(db, reportdb.KAYNAK, "eski ozet", "test")
        db.commit()
        assert depo.ice_al(db, p, BASLIK, [list(s) for s in satirlar]).status == "ready"


def test_veri_yoksa_bos_ve_aciklamali(client):
    login_ok(client)
    veri = client.get("/api/v1/radar").json()["data"]
    assert veri == {"var": False, "taze": False, "veri_zamani": None, "kaynak": "", "satirlar": [], "toplam_musteri": 0, "toplam_kayit": 0, "sayfa": 1, "adet": 10}


def test_eski_reportdb_ozeti_radara_yedek_olmaz(client):
    """2026-11-23 (834d541): Radar yalniz TEMIP kayitlarindan (Fark'ta Radar'a atanan kartsiz numaralar); eski ReportDB ozet partisi
    yedegi kaldirildi. Hazir bir ozet partisi dursa bile kayit yokken liste bos kalir."""
    login_ok(client)
    with Session(engine()) as db:
        db.add(Customer(id=1, external_key="k1", name="Kartli Numara A.S.", customer_no="10000001"))
        db.commit()
    _ozet_partisi(
        ["10000004", "BETA ENERJI", 30, 0, 0, 0, "2026-05-14 15:00:00", "2026-10-06 12:00:00", "2026-10-06 12:30:00"],
        ["10000003", "ALFA LOJISTIK", 5, 0, 20, 0, "2026-05-14 15:00:00", "2026-10-06 12:00:00", "2026-10-06 12:30:00"],
    )
    veri = client.get("/api/v1/radar").json()["data"]
    assert veri == {"var": False, "taze": False, "veri_zamani": None, "kaynak": "", "satirlar": [], "toplam_musteri": 0, "toplam_kayit": 0, "sayfa": 1, "adet": 10}


def test_rol_kaydi_radari_gizler_veya_acar(client, monkeypatch):
    with Session(engine()) as db:
        db.add(RoleView(role="TeamMember", modules=["musteri"], landing="ozet", permissions=[]))
        db.commit()
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    login_ok(client)
    # radar modulu verilmedigi icin kapali ve 403 doner
    assert client.get("/api/v1/radar").status_code == 403
    # admin radari verirse acilir
    with Session(engine()) as db:
        satir = db.scalar(select(RoleView).where(RoleView.role == "TeamMember"))
        satir.modules = ["musteri", "radar"]
        db.commit()
    assert client.get("/api/v1/radar").status_code == 200
