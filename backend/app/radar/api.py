"""Musteri Radar HTTP katmani. Gorme: 'radar' modulu (rol gorunumu). Yalniz okuma; elle giris yok.

GET /radar?sayfa=&adet=&q=          -> Musteri No'su hicbir kartla eslesmeyen TEMIP kayitlari, musteri bazinda (TEMIP kaydi yoksa
                                        eski ozet kurali: en cok alarm ureten ilk 10)
GET /radar/{musteri_no}/kayitlar    -> o musterinin kayitlari (ticket, CI, baslik, durum), sayfali
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.erisim import Erisim, modul_erisim
from app.ortak import ok
from app.radar import servis

router = APIRouter(prefix="/api/v1/radar", tags=["radar"])
radar_erisim = modul_erisim("radar")


@router.get("")
def adaylar(
    sayfa: int = Query(1, ge=1, le=100_000),
    adet: int = Query(servis.RADAR_ADET, ge=1, le=servis.EN_COK_ADET),
    q: str = Query("", max_length=100),
    _: Erisim = Depends(radar_erisim),
    db: Session = Depends(get_db),
):
    return ok(servis.adaylar(db, adet, sayfa, q))


@router.get("/{musteri_no}/kayitlar")
def kayitlar(musteri_no: str, sayfa: int = Query(1, ge=1, le=100_000), _: Erisim = Depends(radar_erisim), db: Session = Depends(get_db)):
    return ok(servis.kayitlar(db, musteri_no, sayfa))
