# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Musteri Radar HTTP katmani. Gorme: 'radar' modulu (rol gorunumu). Elle veri girisi yok.

GET  /radar?sayfa=&adet=&q=          -> Veri Girisi > Fark'ta Radar'a atanan kartsiz numaralarin TEMIP kayitlari, musteri bazinda (TEMIP
                                        kaydi yoksa eski ozet kurali: en cok alarm ureten ilk 10)
GET  /radar/sunum                    -> yonetim sunumu: portfoy toplamlari + musteri bazinda analiz, firsat skoru, oneriler (radar.analiz)
GET  /radar/{musteri_no}/analiz      -> tek musterinin analizi
POST /radar/{musteri_no}/yz          -> YZ yonetim yorumu uret ve sakla (yalniz admin; YZ kapaliysa 503)
GET  /radar/{musteri_no}/kayitlar    -> o musterinin kayitlari (ticket, CI, baslik, durum), sayfali
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.audit import audit_log
from app.db import get_db
from app.deps import require_admin
from app.erisim import Erisim, modul_erisim
from app.ortak import ok
from app.radar import analiz, servis
from app.session import Principal

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


@router.get("/sunum")
def sunum(_: Erisim = Depends(radar_erisim), db: Session = Depends(get_db)):
    return ok(analiz.portfoy(db))


@router.get("/{musteri_no}/analiz")
def musteri_analizi(musteri_no: str, _: Erisim = Depends(radar_erisim), db: Session = Depends(get_db)):
    return ok(analiz.musteri(db, musteri_no[:20]))


@router.post("/{musteri_no}/yz")
def yz_yorumu(musteri_no: str, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    sonuc = analiz.yz_uret(db, musteri_no[:20], admin.username)
    audit_log.remember(actor=admin.username, action="radar.yz_analiz", outcome="allow", module_key="radar", detail=f"musteri_no={musteri_no[:20]}")
    return ok(sonuc)


@router.get("/{musteri_no}/kayitlar")
def kayitlar(musteri_no: str, sayfa: int = Query(1, ge=1, le=100_000), _: Erisim = Depends(radar_erisim), db: Session = Depends(get_db)):
    return ok(servis.kayitlar(db, musteri_no, sayfa))
