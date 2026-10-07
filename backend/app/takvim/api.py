"""Takvim HTTP katmani.

  /takvim/ben, /takvim/gun, /takvim/toplu  -> Izin&Takvim Yonetimi (takvim): kisi yalniz kendi gunlerini yazar
  /takvim/ekip...                           -> TAM Takvim (takvim_ozet): panele giris yapmis herkesin ozeti
  /takvim/sunuma-gonder                     -> yalniz 'takvim.sunuma_gonder' yetkisi olan rol (admin her zaman); yetkiyi admin Rol Yonetimi'nden verir
  /sunum/ogeler                             -> Ceyrek Bazli Sunum (sunum): gonderilmis ogeler
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit_log
from app.deps import get_db
from app.erisim import Erisim, modul_erisim
from app.ortak import KimlikTipi, ok
from app.takvim import servis
from app.takvim.servis import TakvimHata

router = APIRouter(prefix="/api/v1", tags=["takvim"])
kendi_erisim = modul_erisim("takvim")
ekip_erisim = modul_erisim("takvim_ozet")
sunum_erisim = modul_erisim("sunum")

YETKI_SUNUM = "takvim.sunuma_gonder"
Yil = Query(ge=2000, le=2100)


class Serbest(BaseModel):
    model_config = {"extra": "allow"}


class SunumaGovde(BaseModel):
    yil: int = Field(ge=2000, le=2100)
    ceyrek: int = Field(ge=0, le=4)
    gonder: bool


@router.get("/takvim/ben")
def ben(yil: int = Yil, ay: int = Query(ge=1, le=12), e: Erisim = Depends(kendi_erisim), db: Session = Depends(get_db)):
    return ok(servis.ay_oku(db, e.user, yil, ay))


@router.put("/takvim/gun")
def gun(body: Serbest, e: Erisim = Depends(kendi_erisim), db: Session = Depends(get_db)):
    sonuc = servis.gun_kaydet(db, e.user, body.model_dump())
    db.commit()
    return ok(sonuc)


@router.put("/takvim/toplu")
def toplu(body: Serbest, e: Erisim = Depends(kendi_erisim), db: Session = Depends(get_db)):
    sonuc = servis.toplu_kaydet(db, e.user, body.model_dump())
    db.commit()
    audit_log.remember(actor=e.user.username, action="takvim.toplu", outcome="allow", module_key="takvim", detail=f"gun={sonuc['atanan']}")
    return ok(sonuc)


@router.get("/takvim/ekip")
def ekip(yil: int | None = Query(default=None, ge=2000, le=2100), ceyrek: int | None = Query(default=None, ge=0, le=4), e: Erisim = Depends(ekip_erisim), db: Session = Depends(get_db)):
    vy, vc = servis.bu_ceyrek()
    sonuc = servis.ekip(db, e.user, yil or vy, vc if ceyrek is None else ceyrek)
    sonuc["sunuma_gonderebilir"] = e.yetkili_mi(YETKI_SUNUM)
    return ok(sonuc)


@router.get("/takvim/ekip/{uye_id:int}")
def uye(uye_id: KimlikTipi, yil: int = Yil, ceyrek: int = Query(ge=0, le=4), e: Erisim = Depends(ekip_erisim), db: Session = Depends(get_db)):
    return ok(servis.uye_gunleri(db, yil, ceyrek, uye_id))


@router.post("/takvim/sunuma-gonder")
def sunuma_gonder(body: SunumaGovde, e: Erisim = Depends(ekip_erisim), db: Session = Depends(get_db)):
    if not e.yetkili_mi(YETKI_SUNUM):
        raise TakvimHata(403, "Sunuma gönderme yetkiniz yok; yönetici Rol Yönetimi'nden verir.")
    sonuc = servis.sunuma_gonder(db, e.user, body.yil, body.ceyrek, body.gonder)
    db.commit()
    audit_log.remember(
        actor=e.user.username,
        action="takvim.sunuma_gonder" if body.gonder else "takvim.sunumdan_cikar",
        outcome="allow",
        module_key="takvim_ozet",
        detail=f"donem={sonuc['donem']}",
    )
    return ok(sonuc)


@router.get("/sunum/ogeler")
def sunum_ogeleri(yil: int | None = Query(default=None, ge=2000, le=2100), e: Erisim = Depends(sunum_erisim), db: Session = Depends(get_db)):
    return ok(servis.sunum_ogeleri(db, yil))
