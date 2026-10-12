"""Takip Edilen Projeler HTTP katmani. Gorme ve yazma: 'proje' modulu; kayit kapsami servis katmaninda (Member yalniz kendi).

  GET    /proje                          -> TAM ozeti + proje detay listesi (aksiyonlarla) + sorumlu secenekleri
  POST   /proje/kalem                    -> yeni proje
  PATCH  /proje/kalem/{id}               -> durum / oncelik / hedef tarih
  DELETE /proje/kalem/{id}               -> projeyi aksiyonlariyla sil
  POST   /proje/kalem/{id}/aksiyon       -> aksiyon / not ekle
  GET    /proje/musteri                  -> musteri bazli calismalar (?tam_id=)
  PUT    /proje/musteri/{id}/{kategori}  -> isaret + detay (aninda kaydedilir)
  GET    /proje/rapor.xlsx               -> musteri bazli calisma raporu (?tam_id=)
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit_log
from app.db import get_db
from app.deps import require_veri_yazma
from app.erisim import Erisim, modul_erisim
from app.ortak import KimlikTipi, ok
from app.proje import servis
from app.session import Principal

router = APIRouter(prefix="/api/v1/proje", tags=["proje"])
proje_erisim = modul_erisim("proje")

Kategori = Literal["proje", "calisma", "ddos", "dc_tasima", "topoloji"]
Durum = Literal["acik", "devam", "beklemede", "kapandi"]
Oncelik = Literal["dusuk", "orta", "yuksek", "kritik"]


class KalemGovde(BaseModel):
    owner_id: KimlikTipi | None = None
    category: Kategori
    title: str = Field(max_length=200)
    description: str = Field(default="", max_length=5000)
    priority: Oncelik = "orta"
    start_date: date | None = None
    target_date: date | None = None


class GuncelleGovde(BaseModel):
    status: Durum | None = None
    priority: Oncelik | None = None
    target_date: date | None = None


class AksiyonGovde(BaseModel):
    metin: str = Field(max_length=2000)


class CalismaGovde(BaseModel):
    yapildi: bool = False
    detay: str = Field(default="", max_length=servis.AZAMI_DETAY)


def _denetim(e: Erisim, eylem: str, ayrinti: str) -> None:
    audit_log.remember(actor=e.user.username, action=eylem, outcome="allow", module_key="proje", detail=ayrinti)


@router.get("")
def ekran(e: Erisim = Depends(proje_erisim), db: Session = Depends(get_db)):
    sonuc = servis.ekran(db, e.user)
    db.commit()  # kullanici kaydi ilk kez acildiysa
    return ok(sonuc)


@router.post("/kalem")
def kalem_ekle(body: KalemGovde, e: Erisim = Depends(proje_erisim), db: Session = Depends(get_db), _y: Principal = Depends(require_veri_yazma)):
    kimlik = servis.kalem_ekle(db, e.user, body.model_dump())
    db.commit()
    _denetim(e, "proje.ekle", f"proje={kimlik}")
    return ok({"id": kimlik})


@router.patch("/kalem/{kalem_id}")
def kalem_guncelle(kalem_id: KimlikTipi, body: GuncelleGovde, e: Erisim = Depends(proje_erisim), db: Session = Depends(get_db), _y: Principal = Depends(require_veri_yazma)):
    degisiklik = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None or k == "target_date"}
    degisen = servis.kalem_guncelle(db, e.user, kalem_id, degisiklik)
    db.commit()
    if degisen:
        _denetim(e, "proje.guncelle", f"proje={kalem_id} alanlar={','.join(degisen)}")
    return ok({"id": kalem_id, "degisen": degisen})


@router.delete("/kalem/{kalem_id}")
def kalem_sil(kalem_id: KimlikTipi, e: Erisim = Depends(proje_erisim), db: Session = Depends(get_db), _y: Principal = Depends(require_veri_yazma)):
    servis.kalem_sil(db, e.user, kalem_id)
    db.commit()
    _denetim(e, "proje.sil", f"proje={kalem_id}")
    return ok({"id": kalem_id})


@router.post("/kalem/{kalem_id}/aksiyon")
def aksiyon_ekle(kalem_id: KimlikTipi, body: AksiyonGovde, e: Erisim = Depends(proje_erisim), db: Session = Depends(get_db), _y: Principal = Depends(require_veri_yazma)):
    servis.aksiyon_ekle(db, e.user, kalem_id, body.metin)
    db.commit()
    return ok({"id": kalem_id})


@router.get("/musteri")
def calismalar(tam_id: KimlikTipi | None = None, e: Erisim = Depends(proje_erisim), db: Session = Depends(get_db)):
    sonuc = servis.calisma_ekrani(db, e.user, tam_id)
    db.commit()
    return ok(sonuc)


@router.put("/musteri/{musteri_id}/{kategori}")
def calisma_kaydet(musteri_id: KimlikTipi, kategori: Kategori, body: CalismaGovde, e: Erisim = Depends(proje_erisim), db: Session = Depends(get_db)):
    zaman = servis.calisma_kaydet(db, e.user, musteri_id, kategori, body.yapildi, body.detay)
    db.commit()
    return ok({"zaman": zaman})


@router.get("/rapor.xlsx")
def rapor(tam_id: KimlikTipi | None = None, e: Erisim = Depends(proje_erisim), db: Session = Depends(get_db)) -> Response:
    icerik = servis.rapor_excel(db, e.user, tam_id)
    db.commit()
    _denetim(e, "proje.rapor", f"tam={tam_id or '-'}")
    ad = f"Proje_Calisma_Raporu_{date.today():%Y%m%d}.xlsx"
    return Response(
        icerik,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{ad}"'},
    )
