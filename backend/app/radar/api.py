"""Musteri Radar HTTP katmani. Gorme: 'radar' modulu (rol gorunumu). Yalniz okuma; liste ReportDB tamponundan uretilir.

  GET /radar  -> panelde karti olmayan, en cok alarm ureten ilk 10 musteri
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.erisim import Erisim, modul_erisim
from app.ortak import ok
from app.radar import servis

router = APIRouter(prefix="/api/v1/radar", tags=["radar"])
radar_erisim = modul_erisim("radar")


@router.get("")
def adaylar(_: Erisim = Depends(radar_erisim), db: Session = Depends(get_db)):
    return ok(servis.adaylar(db))
