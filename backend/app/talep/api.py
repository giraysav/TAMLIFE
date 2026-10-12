"""Gelistirme Talepleri HTTP katmani. Gorme/acma: 'talep' modulu (herkese acik). Yonetme: admin, TeamMngr ya da rolgorunum.TALEP_YETKISI.

  GET    /talep             -> is listesi (yonetebilen herkesinkini, digerleri kendi taleplerini gorur); ?durum=acik|<durum>|bos
  POST   /talep             -> yeni talep
  PATCH  /talep/{id}        -> durum / oncelik / atanan_id / hedef_surum / admin_notu (yonetebilen)
  DELETE /talep/{id}        -> sil (yalniz admin; gecmis de silinir)
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit_log
from app.authz import is_admin, yonetici_mi
from app.db import get_db
from app.erisim import Erisim, modul_erisim
from app.ortak import KimlikTipi, ok
from app.rolgorunum import TALEP_YETKISI
from app.talep import servis
from app.talep.servis import TalepHata

router = APIRouter(prefix="/api/v1/talep", tags=["talep"])
talep_erisim = modul_erisim("talep")

Tur = Literal["ozellik", "iyilestirme", "hata"]
Oncelik = Literal["dusuk", "orta", "yuksek", "kritik"]
Durum = Literal["yeni", "incelemede", "planlandi", "yapiliyor", "tamamlandi", "reddedildi"]


class TalepGovde(BaseModel):
    baslik: str = Field(max_length=160)
    tur: Tur = "ozellik"
    oncelik: Oncelik = "orta"
    modul: str = Field(default="", max_length=40)
    mevcut_durum: str = Field(max_length=4000)
    beklenen_durum: str = Field(max_length=4000)
    kabul_olcutu: str = Field(default="", max_length=2000)


class GuncelleGovde(BaseModel):
    durum: Durum | None = None
    oncelik: Oncelik | None = None
    atanan_id: KimlikTipi | None = None
    hedef_surum: str | None = Field(default=None, max_length=40)
    admin_notu: str | None = Field(default=None, max_length=4000)


def yonetebilir_mi(e: Erisim) -> bool:
    return yonetici_mi(e.user) or e.yetkili_mi(TALEP_YETKISI)


@router.get("")
def liste(durum: str = Query(default="acik", max_length=20), e: Erisim = Depends(talep_erisim), db: Session = Depends(get_db)):
    sonuc = servis.liste(db, e.user, yonetebilir_mi(e), durum)
    db.commit()  # kullanici kaydi ilk kez acildiysa
    return ok({**sonuc, "silebilir": is_admin(e.user)})


@router.post("")
def olustur(body: TalepGovde, e: Erisim = Depends(talep_erisim), db: Session = Depends(get_db)):
    talep_id = servis.olustur(db, e.user, body.model_dump())
    db.commit()
    audit_log.remember(actor=e.user.username, action="talep.olustur", outcome="allow", module_key="talep", detail=f"talep={talep_id}")
    return ok({"id": talep_id})


@router.patch("/{talep_id}")
def guncelle(talep_id: KimlikTipi, body: GuncelleGovde, e: Erisim = Depends(talep_erisim), db: Session = Depends(get_db)):
    if not yonetebilir_mi(e):
        raise TalepHata(403, "Talepleri yönetme yetkiniz yok; yönetici Rol Yönetimi'nden verir.")
    # Yalniz gonderilen alanlar; atanan_id icin null "atamayi kaldir" demektir.
    degisiklik = body.model_dump(exclude_unset=True)
    degisiklik = {k: v for k, v in degisiklik.items() if v is not None or k == "atanan_id"}
    degisen = servis.guncelle(db, e.user, talep_id, degisiklik)
    db.commit()
    if degisen:
        audit_log.remember(actor=e.user.username, action="talep.guncelle", outcome="allow", module_key="talep", detail=f"talep={talep_id} alanlar={','.join(degisen)}")
    return ok({"id": talep_id, "degisen": degisen})


@router.delete("/{talep_id}")
def sil(talep_id: KimlikTipi, e: Erisim = Depends(talep_erisim), db: Session = Depends(get_db)):
    if not is_admin(e.user):
        raise TalepHata(403, "Talebi yalnız admin silebilir; kuyruğu yürüten talebi Tamamlandı ya da Reddedildi yapar.")
    servis.sil(db, talep_id)
    db.commit()
    audit_log.remember(actor=e.user.username, action="talep.sil", outcome="allow", module_key="talep", detail=f"talep={talep_id}")
    return ok({"id": talep_id})
