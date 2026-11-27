"""Kisiye ozel bildirim HTTP katmani: oturumu olan herkes yalniz kendi bildirimlerini gorur.

  GET  /bildirim          -> okunmamis sayisi + son bildirimler
  POST /bildirim/okundu   -> {ids: [..]} verilirse onlar, verilmezse tumu okundu
  POST /bildirim/{id}/yanit -> {karar: ilgilendim|gerekmedi} (yalniz yanitlanabilir tur; Erken Uyari)
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit_log
from app.bildirim import servis
from app.db import get_db
from app.deps import require_user
from app.ortak import KimlikTipi, ok
from app.session import Principal

router = APIRouter(prefix="/api/v1/bildirim", tags=["bildirim"])


class OkunduGovde(BaseModel):
    ids: list[KimlikTipi] | None = Field(default=None, max_length=200)


@router.get("")
def liste(user: Principal = Depends(require_user), db: Session = Depends(get_db)):
    sonuc = servis.liste(db, user)
    db.commit()  # kullanici kaydi ilk kez acildiysa
    return ok(sonuc)


@router.post("/okundu")
def okundu(body: OkunduGovde, user: Principal = Depends(require_user), db: Session = Depends(get_db)):
    adet = servis.okundu(db, user, body.ids)
    db.commit()
    return ok({"okundu": adet})


class YanitGovde(BaseModel):
    karar: Literal["ilgilendim", "gerekmedi"]


@router.post("/{kimlik:int}/yanit")
def yanit(kimlik: KimlikTipi, body: YanitGovde, user: Principal = Depends(require_user), db: Session = Depends(get_db)):
    sonuc = servis.yanitla(db, user, kimlik, body.karar)
    db.commit()
    audit_log.remember(actor=user.username, action=f"{sonuc['tur']}.yanit", outcome="allow", module_key="musteri", detail=f"musteri={sonuc['ref_id']} {body.karar}")
    return ok({"id": sonuc["id"], "yanit": sonuc["yanit"]})
