"""Onedesk HTTP katmani (Kayit Takibi). Okuma: Onedesk modulunu gorenler (kapsam servis katmaninda). Kayitlar yalniz isci aktarimlariyla
gelir (alarm: tampon/temip_kayit, sikayet / talep: onedesk/canli); elle aktarim yolu 2026-11-21 kaldirildi."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.audit import audit_log
from app.db import get_db
from app.erisim import Erisim, modul_erisim
from app.onedesk import servis
from app.ortak import ok

router = APIRouter(prefix="/api/v1/onedesk", tags=["onedesk"])
erisim = modul_erisim("onedesk")

Yil = Query(default=None, ge=2000, le=2100)


@router.get("/durum")
def durum(kapsam: str = Query(default="acik", max_length=10), yil: int | None = Yil, e: Erisim = Depends(erisim), db: Session = Depends(get_db)):
    return ok(servis.durum(db, e.user, kapsam, yil))


@router.get("/top10")
def top10(yil: int | None = Yil, e: Erisim = Depends(erisim), db: Session = Depends(get_db)):
    return ok(servis.top10(db, e.user, yil))


@router.get("/rca")
def rca(yil: int | None = Yil, e: Erisim = Depends(erisim), db: Session = Depends(get_db)):
    return ok(servis.rca_ozeti(db, e.user, yil))


@router.get("/oneriler")
def oneriler(yil: int | None = Yil, e: Erisim = Depends(erisim), db: Session = Depends(get_db)):
    return ok(servis.oneriler(db, e.user, yil))


@router.post("/yz-yorum")
def yz_yorum(yil: int | None = Yil, e: Erisim = Depends(erisim), db: Session = Depends(get_db)):
    sonuc = servis.yz_yorumu(db, e.user, yil)
    audit_log.remember(actor=e.user.username, action="onedesk.yz_yorum", outcome="allow", module_key="onedesk", detail=f"yil={sonuc['yil']}")
    return ok(sonuc)
