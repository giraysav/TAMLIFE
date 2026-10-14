"""Gelir Faydasi Saglanan Isler HTTP katmani. Gorme: modul_erisim("gelir_uretim") (rol gorunumune bagli); yazma ve ice aktarma: yalniz admin.

  GET    /gelir-uretim?q=&tur=&durum=&fayda=&tam=&yil=  -> {items, ozet, secenekler, yazabilir}
  POST   /gelir-uretim                                   -> yeni kayit
  PUT    /gelir-uretim/{id}                              -> kaydi guncelle (tum alanlar)
  DELETE /gelir-uretim/{id}                              -> kaydi sil
  POST   /gelir-uretim/ice-al/onizleme?dosya=            -> ham .xlsx govdesi (en fazla 5 MB, 500 satir): ayristirma onizlemesi, hicbir sey yazmaz
  POST   /gelir-uretim/ice-al/uygula?dosya=              -> ayni dosya: yalniz YENI satirlari tek islemde ekler
  GET    /gelir-uretim/excel                             -> kaynak tablo sutun duzeninde .xlsx
Her yazma denetim kaydina alan ADLARIYLA yazilir (deger yazilmaz); kayit islem onaylandiktan SONRA denetlenir.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.audit import audit_log
from app.authz import is_admin
from app.db import get_db, oturum
from app.deps import require_veri_yazma
from app.dil import m
from app.erisim import Erisim, modul_erisim
from app.gelir_uretim import excel, ice_al, servis
from app.ortak import KimlikTipi, ok
from app.session import Principal

router = APIRouter(prefix="/api/v1/gelir-uretim", tags=["gelir-uretim"])
gelir_uretim_erisim = modul_erisim("gelir_uretim")
MODUL = "gelir_uretim"

Tur = Literal["proje", "inisiyatif"]
FaydaTuru = Literal["gelir", "tasarruf", "verimlilik"]
Durum = Literal["baslamadi", "devam", "tamamlandi", "iptal"]
Para = Literal["TRY", "USD", "EUR"]
Donem = Literal["ay", "yil", "tek_sefer"]


class KayitGovde(BaseModel):
    kind: Tur = "proje"
    benefit_type: FaydaTuru = "gelir"
    title: str = Field(min_length=1, max_length=300)
    status: Durum = "devam"
    status_note: str = Field(default="", max_length=4000)
    description: str = Field(default="", max_length=8000)
    customers: str = Field(default="", max_length=500)
    revenue_amount: float | None = Field(default=None, ge=0, le=1e13, allow_inf_nan=False)
    revenue_currency: Para = "TRY"
    revenue_period: Donem = "ay"
    revenue_note: str = Field(default="", max_length=500)
    year_revenue: float | None = Field(default=None, ge=0, le=1e13, allow_inf_nan=False)
    hours_per_month: float | None = Field(default=None, ge=0, le=1e6, allow_inf_nan=False)
    hours_note: str = Field(default="", max_length=500)
    extra_note: str = Field(default="", max_length=4000)
    start_date: date | None = None
    end_date: date | None = None
    other_people: str = Field(default="", max_length=300)
    person_ids: list[KimlikTipi] = Field(default_factory=list, max_length=60)

    def alanlar(self) -> dict:
        return self.model_dump(exclude={"person_ids"})


def _denetim(e: Erisim, eylem: str, ayrinti: str) -> None:
    audit_log.remember(actor=e.user.username, action=eylem, outcome="allow", module_key=MODUL, detail=ayrinti)


@router.get("")
def liste(
    q: str = Query(default="", max_length=100),
    tur: Tur | None = None,
    durum: Durum | None = None,
    fayda: FaydaTuru | None = None,
    tam: KimlikTipi | None = None,
    yil: int | None = Query(default=None, ge=2000, le=2100),
    e: Erisim = Depends(gelir_uretim_erisim),
    db: Session = Depends(get_db),
):
    sonuc = servis.liste(db, q=q, tur=tur, durum=durum, fayda=fayda, tam=tam, yil=yil)
    return ok({**sonuc, "yazabilir": is_admin(e.user)})


@router.post("")
def ekle(body: KayitGovde, e: Erisim = Depends(gelir_uretim_erisim), db: Session = Depends(get_db), _y: Principal = Depends(require_veri_yazma)):
    kimlik = servis.olustur(db, e.user, body.alanlar(), body.person_ids)
    db.commit()
    _denetim(e, "gelir_uretim.ekle", f"is={kimlik}")
    return ok({"id": kimlik})


@router.put("/{kayit_id}")
def guncelle(
    kayit_id: KimlikTipi,
    body: KayitGovde,
    e: Erisim = Depends(gelir_uretim_erisim),
    db: Session = Depends(get_db),
    _y: Principal = Depends(require_veri_yazma),
):
    degisen = servis.guncelle(db, e.user, kayit_id, body.alanlar(), body.person_ids)
    db.commit()
    if degisen:
        _denetim(e, "gelir_uretim.guncelle", f"is={kayit_id} alanlar={','.join(degisen)}")
    return ok({"id": kayit_id, "degisen": degisen})


@router.delete("/{kayit_id}")
def sil(kayit_id: KimlikTipi, e: Erisim = Depends(gelir_uretim_erisim), db: Session = Depends(get_db), _y: Principal = Depends(require_veri_yazma)):
    servis.sil(db, kayit_id)
    db.commit()
    _denetim(e, "gelir_uretim.sil", f"is={kayit_id}")
    return ok({"id": kayit_id})


# --- Excel ice aktarma ----------------------------------------------------------------------------------------------
async def _dosya_govdesi(request: Request) -> bytes:
    """Ham .xlsx govdesi (cok parcali form yok); boyut siniri akis sirasinda uygulanir."""
    sinir = ice_al.AZAMI_BAYT
    mesaj = m(f"Dosya çok büyük (en fazla {sinir // (1024 * 1024)} MB).", f"File too large (max {sinir // (1024 * 1024)} MB).")
    bildirilen = request.headers.get("content-length", "")
    if bildirilen.isdigit() and int(bildirilen) > sinir:
        raise servis.GelirUretimHata(413, mesaj)
    parcalar: list[bytes] = []
    boyut = 0
    async for parca in request.stream():
        boyut += len(parca)
        if boyut > sinir:
            raise servis.GelirUretimHata(413, mesaj)
        parcalar.append(parca)
    return b"".join(parcalar)


def _onizle(veri: bytes, dosya: str) -> dict:
    with oturum() as db:
        return ice_al.onizleme(db, veri, dosya)


def _uygula(user: Principal, veri: bytes, dosya: str) -> dict:
    with oturum() as db:
        sonuc = ice_al.uygula(db, user, veri, dosya)
        db.commit()
        return sonuc


@router.post("/ice-al/onizleme")
async def ice_al_onizleme(
    request: Request,
    dosya: str = Query(default="", max_length=200),
    e: Erisim = Depends(gelir_uretim_erisim),
    _y: Principal = Depends(require_veri_yazma),
):
    veri = await _dosya_govdesi(request)
    return ok(await run_in_threadpool(_onizle, veri, dosya))


@router.post("/ice-al/uygula")
async def ice_al_uygula(
    request: Request,
    dosya: str = Query(default="", max_length=200),
    e: Erisim = Depends(gelir_uretim_erisim),
    _y: Principal = Depends(require_veri_yazma),
):
    veri = await _dosya_govdesi(request)
    sonuc = await run_in_threadpool(_uygula, e.user, veri, dosya)
    _denetim(e, "gelir_uretim.ice_al", f"satir={sonuc['toplam']} eklendi={sonuc['eklendi']} var={sonuc['var']} tekrar={sonuc['tekrar']} hatali={sonuc['hatali']}")
    return ok(sonuc)


@router.get("/excel")
def disa_aktar(e: Erisim = Depends(gelir_uretim_erisim), db: Session = Depends(get_db)) -> Response:
    icerik = excel.excel_olustur(db)
    _denetim(e, "gelir_uretim.excel", "")
    ad = f"Gelir_Faydasi_{date.today():%Y%m%d}.xlsx"
    return Response(
        icerik,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{ad}"'},
    )
