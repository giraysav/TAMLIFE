"""Takvim HTTP katmani.

  /takvim/ben, /takvim/gun, /takvim/toplu  -> Izin&Takvim Yonetimi (takvim): kisi yalniz kendi gunlerini yazar
  /takvim/ekip...                           -> TAM Takvim (takvim_ozet): panele giris yapmis herkesin ozeti
  /takvim/sunuma-gonder                     -> yalniz 'sunum.gonder' yetkisi olan rol (admin her zaman); yetkiyi admin Rol Yonetimi › Ceyrek Bazli Sunum'dan verir
Ceyrek Bazli Sunum sayfasinin uclari app.sunum.api'dedir.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit_log
from app.db import get_db
from app.erisim import Erisim, modul_erisim
from app.ortak import KimlikTipi, ok
from app.rolgorunum import SUNUM_YETKISI
from app.sunum import servis as sunum_servis
from app.sunum.api import yetkili_olmali
from app.takvim import servis

router = APIRouter(prefix="/api/v1", tags=["takvim"])
kendi_erisim = modul_erisim("takvim")
ekip_erisim = modul_erisim("takvim_ozet")
Yil = Query(ge=2000, le=2100)


class Serbest(BaseModel):
    model_config = {"extra": "allow"}


class SunumaGovde(BaseModel):
    yil: int = Field(ge=2000, le=2100)
    ceyrek: int = Field(ge=1, le=4)  # tum yil sunuma gonderilmez
    gonder: bool


@router.get("/takvim/ben")
def ben(yil: int = Yil, ay: int = Query(ge=1, le=12), e: Erisim = Depends(kendi_erisim)):
    return ok(servis.ay_oku(e.user, yil, ay))


@router.put("/takvim/gun")
def gun(body: Serbest, e: Erisim = Depends(kendi_erisim)):
    return ok(servis.gun_kaydet(e.user, body.model_dump()))


@router.put("/takvim/toplu")
def toplu(body: Serbest, e: Erisim = Depends(kendi_erisim)):
    sonuc = servis.toplu_kaydet(e.user, body.model_dump())
    audit_log.remember(actor=e.user.username, action="takvim.toplu", outcome="allow", module_key="takvim", detail=f"gun={sonuc['atanan']}")
    return ok(sonuc)


@router.get("/takvim/ekip")
def ekip(yil: int | None = Query(default=None, ge=2000, le=2100), ceyrek: int | None = Query(default=None, ge=0, le=4), e: Erisim = Depends(ekip_erisim), db: Session = Depends(get_db)):
    vy, vc = servis.bu_ceyrek()
    sonuc = servis.ekip(db, yil or vy, vc if ceyrek is None else ceyrek)
    sonuc["sunuma_gonderebilir"] = e.yetkili_mi(SUNUM_YETKISI)
    return ok(sonuc)


@router.get("/takvim/ekip/{uye_id:int}")
def uye(uye_id: KimlikTipi, yil: int = Yil, ceyrek: int = Query(ge=0, le=4), e: Erisim = Depends(ekip_erisim), db: Session = Depends(get_db)):
    return ok(servis.uye_gunleri(db, yil, ceyrek, uye_id))


@router.post("/takvim/sunuma-gonder")
def sunuma_gonder(body: SunumaGovde, e: Erisim = Depends(ekip_erisim), db: Session = Depends(get_db)):
    yetkili_olmali(e)
    sonuc = sunum_servis.gonder(db, e.user, servis.SUNUM_KAYNAK, body.yil, body.ceyrek, body.gonder)
    db.commit()
    audit_log.remember(
        actor=e.user.username,
        action="sunum.gonder" if body.gonder else "sunum.kaldir",
        outcome="allow",
        module_key="takvim_ozet",
        detail=f"donem={sonuc['donem']}",
    )
    return ok(sonuc)
