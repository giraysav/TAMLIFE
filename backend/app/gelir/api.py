"""Gelir HTTP katmani: ICT SMS (tamsms modulu) ve APN kurulum + musteri calismalari (tamapn modulu). Yetki sunucuda; kapsam servis katmaninda."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import audit_log
from app.db import get_db
from app.deps import require_veri_yazma
from app.erisim import Erisim, modul_erisim
from app.gelir import servis as gs
from app.ortak import KimlikTipi, ok
from app.session import Principal

router = APIRouter(prefix="/api/v1/gelir", tags=["gelir"])
sms_erisim = modul_erisim("tamsms")
apn_erisim = modul_erisim("tamapn")
herhangi_erisim = modul_erisim("tamsms", "tamapn")

Yil = Query(default=None, ge=2000, le=2100)


class Serbest(BaseModel):
    """Alanlar servis katmaninda dogrulanir; burada yalniz fazlalik izin verilir."""

    model_config = {"extra": "allow"}


def _yaz(db: Session, user: Principal, islem: Callable[[], Any], eylem: str, modul: str):
    sonuc = islem()
    db.commit()
    audit_log.remember(actor=user.username, action=eylem, outcome="allow", module_key=modul, detail="")
    return ok(sonuc)


@router.get("/musteri-adlari")
def musteri_adlari(e: Erisim = Depends(herhangi_erisim), db: Session = Depends(get_db)):
    return ok(gs.musteri_adlari(db, e.user))


@router.get("/tamlar")
def tamlar(e: Erisim = Depends(herhangi_erisim), db: Session = Depends(get_db)):
    """Kayitta secilebilir TAM'lar (yalniz ortak personel kumesi); Member'a yalniz kendisi doner."""
    return ok(gs.tam_adlari(db, e.user))


# --- ICT SMS ---------------------------------------------------------------------------------------
@router.get("/sms")
def sms_liste(yil: int | None = Yil, e: Erisim = Depends(sms_erisim), db: Session = Depends(get_db)):
    return ok(gs.sms_liste(db, e.user, yil))


@router.post("/sms")
def sms_ekle(body: Serbest, e: Erisim = Depends(sms_erisim), db: Session = Depends(get_db), _y: Principal = Depends(require_veri_yazma)):
    return _yaz(db, e.user, lambda: gs.sms_ekle(db, e.user, body.model_dump()), "gelir.sms_ekle", "tamsms")


@router.put("/sms/{kayit_id:int}")
def sms_guncelle(
    kayit_id: KimlikTipi,
    body: Serbest,
    e: Erisim = Depends(sms_erisim),
    db: Session = Depends(get_db),
    _y: Principal = Depends(require_veri_yazma),
):
    return _yaz(db, e.user, lambda: gs.sms_guncelle(db, e.user, kayit_id, body.model_dump()), "gelir.sms_guncelle", "tamsms")


@router.delete("/sms/{kayit_id:int}")
def sms_sil(
    kayit_id: KimlikTipi, e: Erisim = Depends(sms_erisim), db: Session = Depends(get_db), _y: Principal = Depends(require_veri_yazma)
):
    return _yaz(db, e.user, lambda: gs.sms_sil(db, e.user, kayit_id), "gelir.sms_sil", "tamsms")


# --- APN kurulum -----------------------------------------------------------------------------------
@router.get("/apn/kurulum")
def kurulum_liste(yil: int | None = Yil, e: Erisim = Depends(apn_erisim), db: Session = Depends(get_db)):
    return ok(gs.kurulum_liste(db, e.user, yil))


@router.post("/apn/kurulum")
def kurulum_ekle(
    body: Serbest, e: Erisim = Depends(apn_erisim), db: Session = Depends(get_db), _y: Principal = Depends(require_veri_yazma)
):
    return _yaz(db, e.user, lambda: gs.kurulum_ekle(db, e.user, body.model_dump()), "gelir.apn_kurulum_ekle", "tamapn")


@router.put("/apn/kurulum/{kayit_id:int}")
def kurulum_guncelle(
    kayit_id: KimlikTipi,
    body: Serbest,
    e: Erisim = Depends(apn_erisim),
    db: Session = Depends(get_db),
    _y: Principal = Depends(require_veri_yazma),
):
    return _yaz(db, e.user, lambda: gs.kurulum_guncelle(db, e.user, kayit_id, body.model_dump()), "gelir.apn_kurulum_guncelle", "tamapn")


@router.delete("/apn/kurulum/{kayit_id:int}")
def kurulum_sil(
    kayit_id: KimlikTipi, e: Erisim = Depends(apn_erisim), db: Session = Depends(get_db), _y: Principal = Depends(require_veri_yazma)
):
    return _yaz(db, e.user, lambda: gs.kurulum_sil(db, e.user, kayit_id), "gelir.apn_kurulum_sil", "tamapn")


# --- APN musteri calismalari -------------------------------------------------------------------------
@router.get("/apn/calisma")
def calisma_liste(e: Erisim = Depends(apn_erisim), db: Session = Depends(get_db)):
    return ok(gs.calisma_liste(db, e.user))


@router.post("/apn/calisma")
def calisma_ekle(
    body: Serbest, e: Erisim = Depends(apn_erisim), db: Session = Depends(get_db), _y: Principal = Depends(require_veri_yazma)
):
    return _yaz(db, e.user, lambda: gs.calisma_ekle(db, e.user, body.model_dump()), "gelir.apn_calisma_ekle", "tamapn")


@router.put("/apn/calisma/{kayit_id:int}")
def calisma_guncelle(
    kayit_id: KimlikTipi,
    body: Serbest,
    e: Erisim = Depends(apn_erisim),
    db: Session = Depends(get_db),
    _y: Principal = Depends(require_veri_yazma),
):
    return _yaz(db, e.user, lambda: gs.calisma_guncelle(db, e.user, kayit_id, body.model_dump()), "gelir.apn_calisma_guncelle", "tamapn")


@router.delete("/apn/calisma/{kayit_id:int}")
def calisma_sil(
    kayit_id: KimlikTipi, e: Erisim = Depends(apn_erisim), db: Session = Depends(get_db), _y: Principal = Depends(require_veri_yazma)
):
    return _yaz(db, e.user, lambda: gs.calisma_sil(db, e.user, kayit_id), "gelir.apn_calisma_sil", "tamapn")
