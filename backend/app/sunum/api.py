# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Ceyrek Sunum HTTP katmani. Gorme: 'sunum' modulu (rol gorunumu). Yonetme: admin ya da rolgorunum.SUNUM_YETKISI.

  GET  /sunum/donem       -> secilen ceyregin ogeleri (gecmis ceyrekte ilk goruntulemede dondurulur)
  GET  /sunum/kaynaklar   -> sunumun alanlari (her modul), sirasi ve gorunurlugu (Sunum sayfasindaki 'Sunum icerigi' penceresi)
  PUT  /sunum/kaynaklar   -> gorunur alanlar + (opsiyonel) yeni sira (yetkili)
  POST /sunum/gonder      -> kaynagin ceyrek goruntusunu sabitle / kaldir (yetkili; onayli ceyrekte 409); TAM Takvim kutusu /takvim/sunuma-gonder'i kullanir
  POST /sunum/onay        -> ceyregin sunumunu onayla (o anki hali sabitlenir) ya da onayi kaldir (yetkili)
  GET  /sunum/karsilastir -> kayitli ceyrek goruntuleri ile canli verinin karsilastirmasi (hicbir sey yazmaz)
  POST /sunum/senkron     -> farkli / eksik goruntuleri canli veriyle yenile (yetkili; onayli ceyrekte 409)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit_log
from app.db import get_db
from app.erisim import Erisim, modul_erisim
from app.ortak import ok
from app.rolgorunum import SUNUM_YETKISI
from app.sunum import servis
from app.sunum.servis import SunumHata

router = APIRouter(prefix="/api/v1/sunum", tags=["sunum"])
sunum_erisim = modul_erisim("sunum")
YETKISIZ = "Çeyrek sunumu yönetme yetkiniz yok; yönetici Rol Yönetimi › Çeyrek Sunum'dan verir."


class KaynakGovde(BaseModel):
    kaynaklar: list[str] = Field(max_length=50)
    sira: list[str] | None = Field(default=None, max_length=50)


class GonderGovde(BaseModel):
    kaynak: str = Field(max_length=30)
    yil: int = Field(ge=2000, le=2100)
    ceyrek: int = Field(ge=1, le=4)
    gonder: bool


class OnayGovde(BaseModel):
    yil: int = Field(ge=2000, le=2100)
    ceyrek: int = Field(ge=1, le=4)
    onay: bool


def yetkili_olmali(e: Erisim) -> None:
    if not e.yetkili_mi(SUNUM_YETKISI):
        raise SunumHata(403, YETKISIZ)


@router.get("/donem")
def donem(yil: int | None = Query(default=None, ge=2000, le=2100), ceyrek: int | None = Query(default=None, ge=1, le=4), e: Erisim = Depends(sunum_erisim), db: Session = Depends(get_db)):
    vy, vc = servis.bu_ceyrek()
    sonuc = servis.donem(db, yil or vy, ceyrek or vc, e.user.username)
    db.commit()  # ilk goruntulemede dondurulenler
    return ok({**sonuc, "yonetebilir": e.yetkili_mi(SUNUM_YETKISI)})


@router.get("/excel")
def excel(yil: int = Query(ge=2000, le=2100), ceyrek: int = Query(ge=1, le=4), e: Erisim = Depends(sunum_erisim), db: Session = Depends(get_db)) -> Response:
    """Ceyregin tum alanlari Excel'de: Ozet sayfasi + alan basina bir sayfa (ekrandaki veriyle ayni)."""
    from app.sunum import disa_aktar as da

    icerik = da.excel(da.bolumler(db, yil, ceyrek, e.user.username))
    db.commit()
    audit_log.remember(actor=e.user.username, action="sunum.excel", outcome="allow", module_key="sunum", detail=f"donem={yil}-Q{ceyrek}")
    return Response(icerik, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="TAMLIFE_Ceyrek_Sunum_{yil}_Q{ceyrek}.xlsx"'})  # fmt: skip


@router.get("/kaynaklar")
def kaynaklar(e: Erisim = Depends(sunum_erisim), db: Session = Depends(get_db)):
    return ok({"kaynaklar": servis.kaynak_listesi(db), "duzenleyebilir": e.yetkili_mi(SUNUM_YETKISI)})


@router.put("/kaynaklar")
def kaynaklar_kaydet(body: KaynakGovde, e: Erisim = Depends(sunum_erisim), db: Session = Depends(get_db)):
    yetkili_olmali(e)
    secili = servis.kaynaklar_kaydet(db, body.kaynaklar, e.user.username, body.sira)
    db.commit()
    audit_log.remember(actor=e.user.username, action="sunum.kaynaklar", outcome="allow", module_key="sunum", detail=f"kaynaklar={','.join(secili)}")
    return ok({"kaynaklar": servis.kaynak_listesi(db)})


@router.post("/gonder")
def gonder(body: GonderGovde, e: Erisim = Depends(sunum_erisim), db: Session = Depends(get_db)):
    yetkili_olmali(e)
    sonuc = servis.gonder(db, e.user, body.kaynak, body.yil, body.ceyrek, body.gonder)
    db.commit()
    audit_log.remember(
        actor=e.user.username,
        action="sunum.gonder" if body.gonder else "sunum.kaldir",
        outcome="allow",
        module_key="sunum",
        detail=f"kaynak={body.kaynak} donem={sonuc['donem']}",
    )
    return ok(sonuc)


@router.post("/onay")
def onay(body: OnayGovde, e: Erisim = Depends(sunum_erisim), db: Session = Depends(get_db)):
    yetkili_olmali(e)
    sonuc = servis.onayla(db, e.user, body.yil, body.ceyrek, body.onay)
    db.commit()
    audit_log.remember(actor=e.user.username, action="sunum.onay" if body.onay else "sunum.onay_kaldir", outcome="allow", module_key="sunum", detail=f"donem={sonuc['donem']}")
    return ok(sonuc)


class DonemGovde(BaseModel):
    yil: int = Field(ge=2000, le=2100)
    ceyrek: int = Field(ge=1, le=4)


@router.get("/karsilastir")
def karsilastir(yil: int = Query(ge=2000, le=2100), ceyrek: int = Query(ge=1, le=4), e: Erisim = Depends(sunum_erisim), db: Session = Depends(get_db)):
    return ok({**servis.karsilastir(db, yil, ceyrek, e.user.username), "yonetebilir": e.yetkili_mi(SUNUM_YETKISI)})


@router.post("/senkron")
def senkron(body: DonemGovde, e: Erisim = Depends(sunum_erisim), db: Session = Depends(get_db)):
    yetkili_olmali(e)
    sonuc = servis.senkronla(db, e.user, body.yil, body.ceyrek)
    db.commit()
    audit_log.remember(actor=e.user.username, action="sunum.senkron", outcome="allow", module_key="sunum", detail=f"donem={sonuc['donem']} yenilenen={','.join(sonuc['yenilenen']) or '-'}")
    return ok(sonuc)
