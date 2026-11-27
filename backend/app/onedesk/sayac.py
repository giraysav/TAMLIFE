# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Kayit yardimcilari (alarm / talep / sikayet): OneDesk ve Oracle tarihlerini okuma, kart sayaclarini kayitlardan yenileme.

Kayitlar yalniz isci aktarimlariyla gelir: alarm ReportDB TEMIP (tampon/temip_kayit), sikayet / talep OneDesk (onedesk/canli).
2026-11-21: eski elle parti aktarimi (Veri Girisi partisi -> kayit) kaldirildi; yardimcilar buraya tasindi.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import musteri_alani
from app.models import Customer, OnedeskRecord
from app.ortak import simdi

_BICIMLER = ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y")
_FRAKSIYON = re.compile(r"\.\d+$")

TR_SAATI = timezone(timedelta(hours=3), "TR")  # Onedesk disa aktarimi ve Oracle saatleri yerel ve dilimsiz; Turkiye 2016'dan beri sabit +03


def tarih_oku(deger: object) -> datetime | None:
    """Dilimsiz deger Turkiye saati sayilir ve UTC'ye cevrilir (DB'de tum zamanlar UTC); dilimli deger oldugu gibi UTC'ye."""
    if isinstance(deger, datetime):
        return (deger if deger.tzinfo else deger.replace(tzinfo=TR_SAATI)).astimezone(UTC)
    m = _FRAKSIYON.sub("", str(deger or "").strip())
    if not m:
        return None
    for bicim in _BICIMLER:
        try:
            return datetime.strptime(m, bicim).replace(tzinfo=TR_SAATI).astimezone(UTC)
        except ValueError:
            continue
    return None


@musteri_alani.tum_alanlarda
def sayaclari_yenile(db: Session, musteri_idleri: set[int]) -> None:
    """Musteri kartindaki sayaclar kayitlardan: acik (tur basina) ve bu yil kapanan."""
    if not musteri_idleri:
        return
    yil = simdi().year
    bas, son = datetime(yil, 1, 1, tzinfo=UTC), datetime(yil + 1, 1, 1, tzinfo=UTC)
    acik: dict[tuple[int, str], int] = {}
    for cid, tur, adet in db.execute(
        select(OnedeskRecord.customer_id, OnedeskRecord.kind, func.count())
        .where(OnedeskRecord.customer_id.in_(musteri_idleri), OnedeskRecord.status == "open")
        .group_by(OnedeskRecord.customer_id, OnedeskRecord.kind)
    ):
        acik[(cid, tur)] = adet
    kapali: dict[tuple[int, str], int] = {}
    for cid, tur, adet in db.execute(
        select(OnedeskRecord.customer_id, OnedeskRecord.kind, func.count())
        .where(OnedeskRecord.customer_id.in_(musteri_idleri), OnedeskRecord.status == "closed", OnedeskRecord.closed_at >= bas, OnedeskRecord.closed_at < son)
        .group_by(OnedeskRecord.customer_id, OnedeskRecord.kind)
    ):
        kapali[(cid, tur)] = adet
    for m in db.scalars(select(Customer).where(Customer.id.in_(musteri_idleri))):
        m.alarm_count, m.request_count, m.complaint_count = acik.get((m.id, "alarm"), 0), acik.get((m.id, "talep"), 0), acik.get((m.id, "sikayet"), 0)
        m.alarm_closed_count, m.request_closed_count, m.complaint_closed_count = (
            kapali.get((m.id, "alarm"), 0),
            kapali.get((m.id, "talep"), 0),
            kapali.get((m.id, "sikayet"), 0),
        )
