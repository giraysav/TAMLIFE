# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Musteri karti kayit listesi (2026-10-18 kullanici istegi): Operasyon kutusundaki Alarm / Talep / Sikayet "acik / kapanan" dugmeleri
o kartin secilen tur ve durumdaki kayitlarini listeler. Kaynak onedesk_record (TEMIP alarmlari: tampon/temip_kayit; Onedesk aktarimi).
Kapanan = bu yil kapanan (karttaki "yil ici kapanan" sayaciyla ayni kapsam); acik = su an acik. Yalniz kartin kendi kayitlari
(sayaclar da yalniz kartin kendisini sayar). Yalniz okuma; gorunurluk kart erisimiyle ayni.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import OnedeskRecord
from app.musteri import servis as ms
from app.ortak import UygulamaHatasi, iso, simdi
from app.session import Principal

SAYFA = 10
EN_COK = 100
TURLER = ("alarm", "talep", "sikayet")
DURUMLAR = ("acik", "kapali")


class KayitHata(UygulamaHatasi):
    pass


def _sure_dk(r: OnedeskRecord) -> int | None:
    if not r.opened_at:
        return None
    bas = r.opened_at if r.opened_at.tzinfo else r.opened_at.replace(tzinfo=UTC)
    bit = r.closed_at or simdi()
    bit = bit if bit.tzinfo else bit.replace(tzinfo=UTC)
    return max(0, round((bit - bas).total_seconds() / 60))


def kart_kayitlari(
    db: Session, user: Principal, musteri_id: int, tur: str, durum: str, yil: int | None = None, sayfa: int = 1, adet: int = SAYFA
) -> dict[str, Any]:
    """Kartin `tur` turundeki acik (su an) ya da kapanan (yil icinde) kayitlari; acik en yeni acilan, kapanan en son kapanan once."""
    if tur not in TURLER or durum not in DURUMLAR:
        raise KayitHata(400, "Tür alarm / talep / sikayet, durum acik / kapali olmalı.")
    kart = ms.musteri_getir(db, user, musteri_id)
    yil = yil or simdi().year
    kosul = [OnedeskRecord.customer_id == kart.id, OnedeskRecord.kind == tur]
    if durum == "acik":
        kosul.append(OnedeskRecord.status == "open")
        sira = (OnedeskRecord.opened_at.desc(), OnedeskRecord.id.desc())
    else:
        bas, son = datetime(yil, 1, 1, tzinfo=UTC), datetime(yil + 1, 1, 1, tzinfo=UTC)
        kosul += [OnedeskRecord.status == "closed", OnedeskRecord.closed_at >= bas, OnedeskRecord.closed_at < son]
        sira = (OnedeskRecord.closed_at.desc(), OnedeskRecord.id.desc())
    toplam = db.scalar(select(func.count()).select_from(OnedeskRecord).where(*kosul)) or 0
    adet = max(1, min(int(adet), EN_COK))
    sayfa = max(1, min(int(sayfa), max(1, math.ceil(toplam / adet))))
    satirlar = db.scalars(select(OnedeskRecord).where(*kosul).order_by(*sira).offset((sayfa - 1) * adet).limit(adet)).all()
    return {
        "tur": tur,
        "durum": durum,
        "yil": yil,
        "toplam": toplam,
        "sayfa": sayfa,
        "adet": adet,
        "kayitlar": [
            {
                "id": r.id,
                "ticket": r.ticket_no or "",
                "ci": r.location or "",
                "baslik": r.category or "",
                "durum": r.detail or r.status,
                "acilis": iso(r.opened_at),
                "kapanis": iso(r.closed_at),
                "sure_dk": _sure_dk(r),
            }
            for r in satirlar
        ],
    }
