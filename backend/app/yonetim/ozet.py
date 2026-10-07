"""Genel Durum: tek istekte saglik kontrolleri + gostergeler + baglanti yuvalari (ilk acilis tek gidis-donus)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import baglantilar
from app.models import IngestBatch
from app.ortak import iso
from app.tampon.models import DistributionRule
from app.yonetim import arizalar, gunlukler, saglik, veritabani


def ozet(db: Session) -> dict[str, Any]:
    baglanti = db.connection()
    yol = veritabani.sqlite_yolu()
    kayitli, hedef = veritabani.surum(baglanti), veritabani.surum_head()
    hazir = db.scalar(select(func.count()).select_from(IngestBatch).where(IngestBatch.status == "ready")) or 0
    son = db.scalars(select(IngestBatch).order_by(IngestBatch.id.desc()).limit(1)).first()
    kural = db.scalar(select(func.count()).select_from(DistributionRule)) or 0
    kural_etkin = db.scalar(select(func.count()).select_from(DistributionRule).where(DistributionRule.enabled.is_(True))) or 0
    return {
        "saglik": saglik.calistir(db),
        "gostergeler": {
            "veritabani": {
                "motor": baglanti.dialect.name,
                "boyut_bayt": veritabani.boyut_bayt(yol),
                "surum": kayitli,
                "surum_uyumlu": None if kayitli is None or hedef is None else kayitli == hedef,
            },
            "ariza": arizalar.ozet(db),
            "gunluk": gunlukler.ozet(db),
            "oturum": {"aktif": len(gunlukler.oturumlar())},
            "tampon": {
                "hazir_parti": hazir,
                "kural": kural,
                "kural_etkin": kural_etkin,
                "son": None
                if son is None
                else {"id": son.id, "kaynak": son.source_key, "durum": son.status, "satir": son.row_count, "zaman": iso(son.received_at)},
            },
        },
        "baglantilar": baglantilar.connections(),
    }
