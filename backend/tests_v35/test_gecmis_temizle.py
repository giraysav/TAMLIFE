# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Gecmis veri temizligi (app.gecmis_temizle) ve Onedesk'in ozet / eski panel partilerini kayit diye almamasi."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import gecmis_temizle
from app.db import engine
from app.models import AuditEvent, Customer, IngestBatch, OnedeskRecord
from app.tampon import depo, reportdb
from tests_v35.conftest import login_ok


def _parti(db: Session, kaynak: str, kullanici: str) -> int:
    p = depo.parti_olustur(db, kaynak, "test", kullanici)
    db.commit()
    depo.ice_al(db, p, ["Çağrı No", "Müşteri No", "Müşteri Adı", "Kayıt Türü"], [["K1", "10000001", "ORNEK", "Alarm"]])
    return p.id


def _hazirla() -> dict[str, int]:
    with Session(engine()) as db:
        m = Customer(external_key="k1", name="Ornek A.S.", customer_no="10000001", alarm_count=99, complaint_count=7)
        db.add(m)
        db.flush()
        kapanis = datetime(datetime.now(UTC).year, 2, 1, tzinfo=UTC)
        db.add_all(
            [
                OnedeskRecord(kind="alarm", external_key="", customer_id=m.id, status="open", source="import"),  # ozetten sahte
                OnedeskRecord(kind="alarm", external_key="", customer_id=m.id, status="open", source="import"),
                OnedeskRecord(kind="alarm", external_key="INC1", customer_id=m.id, status="open", source="import"),  # gercek
                OnedeskRecord(kind="talep", external_key="REQ1", customer_id=m.id, status="closed", closed_at=kapanis, source="import"),
            ]
        )
        db.commit()
        mid = m.id
        eski = _parti(db, reportdb.KAYNAK, "eski_aktar")
        yeni = _parti(db, "csv", "admin")
    return {"musteri": mid, "eski": eski, "yeni": yeni}


def _durum(mid: int) -> tuple:
    with Session(engine()) as db:
        m = db.get(Customer, mid)
        return (
            sorted(db.scalars(select(IngestBatch.id))),
            sorted(db.scalars(select(OnedeskRecord.external_key))),
            (m.alarm_count, m.complaint_count, m.request_count, m.request_closed_count),
            db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "gecmis.temizle")),
        )


def test_kuru_deneme_hicbir_sey_silmez(client):
    h = _hazirla()
    once = _durum(h["musteri"])
    with Session(engine()) as db:
        s = gecmis_temizle.temizle(db)
    assert (s["eski_parti"], s["eski_parti_satir"], s["onedesk_numarasiz"], s["onedesk_kalan"], s["sayaci_degisen_musteri"]) == (
        1,
        1,
        2,
        2,
        1,
    )
    assert _durum(h["musteri"]) == once


def test_uygula_eski_partiyi_ve_numarasiz_kayitlari_siler(client):
    h = _hazirla()
    with Session(engine()) as db:
        gecmis_temizle.temizle(db, uygula=True)
    partiler, kayitlar, sayac, denetim = _durum(h["musteri"])
    assert partiler == [h["yeni"]] and kayitlar == ["INC1", "REQ1"]
    assert sayac == (1, 0, 0, 1) and denetim == 1  # sayaclar kalan gercek kayitlardan
    with Session(engine()) as db:  # ikinci calistirma bos gecer
        s = gecmis_temizle.temizle(db, uygula=True)
    assert (s["eski_parti"], s["onedesk_numarasiz"], s["sayaci_degisen_musteri"]) == (0, 0, 0)


def test_komut_satiri_kuru_ve_uygula(client, capsys):
    h = _hazirla()
    assert gecmis_temizle.main([]) == 0
    assert "KURU DENEME" in capsys.readouterr().out and len(_durum(h["musteri"])[0]) == 2
    assert gecmis_temizle.main(["--uygula"]) == 0
    cikti = capsys.readouterr().out
    assert "UYGULAMA" in cikti and "numarasiz aktarilmis Onedesk kaydi: 2" in cikti
    assert _durum(h["musteri"])[0] == [h["yeni"]]


def test_onedesk_ozet_ve_eski_panel_partisini_almaz(client):
    hdr = login_ok(client)
    with Session(engine()) as db:
        ozet = _parti(db, reportdb.KAYNAK, "isci")
        eski = _parti(db, "csv", "eski_aktar")
        csv = _parti(db, "csv", "admin")
    for pid in (ozet, eski):
        r = client.post(f"/api/v1/onedesk/ice-al/{pid}", json={}, headers=hdr)
        assert r.status_code == 400 and "Onedesk kaydı değildir" in r.text
    assert {p["id"] for p in client.get("/api/v1/onedesk/kaynak").json()["data"]["partiler"]} == {csv}
