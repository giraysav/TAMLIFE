"""Yonetim HTTP katmani (/api/v1/yonetim). Hepsi yalniz admin; yazanlar CSRF'li (guvenlik kapisi). Is kurali bu paketin modullerindedir."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import session as oturum
from app.audit import audit_log
from app.deps import engine, get_db, require_admin
from app.ortak import KimlikTipi, ok
from app.session import Principal
from app.yonetim import arizalar, dosya_gunlugu, gunlukler, ozet, veritabani

router = APIRouter(prefix="/api/v1/yonetim", tags=["yonetim"])



def _denetim(admin: Principal, islem: str, detay: str = "") -> None:
    audit_log.remember(actor=admin.username, action=islem, outcome="allow", module_key="yonetim", detail=detay)


class ArizaDurumu(BaseModel):
    durum: str = Field(max_length=12)
    notu: str = Field(default="", max_length=500)


# --- Genel durum ----------------------------------------------------------------------------------------------------
@router.get("/ozet")
def genel_durum(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(ozet.ozet(db))


# --- Veritabani -----------------------------------------------------------------------------------------------------
@router.get("/veritabani")
def veritabani_bilgisi(admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    return ok(veritabani.bilgi(engine()))


@router.post("/veritabani/yedek")
def yedek_al(admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    sonuc = veritabani.yedek_al(admin.username)
    _denetim(admin, "yonetim.yedek_al", sonuc["ad"])
    return ok(sonuc)


@router.post("/veritabani/yedek/{ad}/dogrula")
def yedek_dogrula(ad: str, admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    return ok(veritabani.yedek_dogrula(ad))


# --- Arizalar -------------------------------------------------------------------------------------------------------
@router.get("/arizalar")
def ariza_listesi(
    durum: str = Query(default="", max_length=12),
    seviye: str = Query(default="", max_length=10),
    kod: str = Query(default="", max_length=20),
    q: str = Query(default="", max_length=100),
    sayfa: int = Query(default=1, ge=1),
    adet: int = Query(default=25, ge=1, le=200),
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(arizalar.liste(db, durum=durum, seviye=seviye, kod=kod, q=q, sayfa=sayfa, adet=adet))


@router.post("/arizalar/{ariza_id}/durum")
def ariza_durumu(
    ariza_id: KimlikTipi, govde: ArizaDurumu, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)
) -> dict[str, Any]:
    sonuc = arizalar.durum_degistir(db, ariza_id, govde.durum, govde.notu, admin.username)
    db.commit()
    _denetim(admin, "yonetim.ariza_durum", f"kayit={sonuc['kayit_no']} durum={govde.durum}")
    return ok(sonuc)


@router.get("/ariza-kodlari")
def ariza_kodlari(admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    return ok(arizalar.kodlar())


# --- Gunlukler ------------------------------------------------------------------------------------------------------
def _filtre(
    olay: str = Query(default="", max_length=80),
    sonuc: str = Query(default="", max_length=10),
    kullanici: str = Query(default="", max_length=120),
    modul: str = Query(default="", max_length=80),
    q: str = Query(default="", max_length=100),
    bas: str = Query(default="", max_length=10),
    bit: str = Query(default="", max_length=10),
) -> dict[str, Any]:
    return {
        "aksiyon": olay,
        "sonuc": sonuc,
        "kullanici": kullanici,
        "modul": modul,
        "q": q,
        "bas": gunlukler.tarih_oku(bas),
        "bit": gunlukler.tarih_oku(bit, gun_sonu=True),
    }


@router.get("/gunlukler")
def gunluk_listesi(
    filtre: dict[str, Any] = Depends(_filtre),
    sayfa: int = Query(default=1, ge=1),
    adet: int = Query(default=50, ge=1, le=200),
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(gunlukler.sorgula(db, sayfa=sayfa, adet=adet, **filtre))


@router.get("/gunlukler.csv")
def gunluk_csv(
    filtre: dict[str, Any] = Depends(_filtre), admin: Principal = Depends(require_admin), db: Session = Depends(get_db)
) -> Response:
    icerik = gunlukler.csv_uret(db, **filtre)
    _denetim(admin, "yonetim.gunluk_indir", "csv")
    return Response(icerik, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="gunlukler.csv"'})


@router.get("/oturumlar")
def oturum_listesi(admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    return ok({"oturumlar": gunlukler.oturumlar(), "siz": admin.username})


@router.post("/oturumlar/{kullanici}/kapat")
def oturum_kapat(kullanici: str, admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    kapanan = oturum.kullanici_oturumlarini_kapat(kullanici)
    _denetim(admin, "yonetim.oturum_kapat", f"kullanici={kullanici[:60]} adet={kapanan}")
    return ok({"kapatilan": kapanan})


@router.get("/uygulama-gunlugu")
def uygulama_gunlugu(
    kayit: str = Query(default="", max_length=8),
    satir: int = Query(default=200, ge=10, le=1000),
    admin: Principal = Depends(require_admin),
) -> dict[str, Any]:
    return ok(dosya_gunlugu.oku(kayit, satir))
