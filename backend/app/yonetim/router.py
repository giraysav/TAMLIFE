"""Yonetim HTTP katmani (/api/v1/yonetim). Hepsi yalniz admin; yazanlar CSRF'li (guvenlik kapisi). Is kurali bu paketin modullerindedir."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import ad, baglantilar
from app import session as oturum
from app.audit import audit_log
from app.db import engine, get_db
from app.deps import require_admin, require_veri_yazma
from app.ortak import KimlikTipi, ok
from app.session import Principal
from app.tampon import oracle
from app.yonetim import arizalar, dosya_gunlugu, gunlukler, musteri_listesi, ozet, veritabani

router = APIRouter(prefix="/api/v1/yonetim", tags=["yonetim"], dependencies=[Depends(require_admin)])  # yeni uc eklense de admin disi giremez



def _denetim(admin: Principal, islem: str, detay: str = "") -> None:
    audit_log.remember(actor=admin.username, action=islem, outcome="allow", module_key="yonetim", detail=detay)


class ArizaDurumu(BaseModel):
    durum: str = Field(max_length=12)
    notu: str = Field(default="", max_length=500)


# --- Genel durum ----------------------------------------------------------------------------------------------------
@router.get("/ozet")
def genel_durum(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(ozet.ozet(db))


# --- Kurum baglantilari (AD/LDAPS) ---------------------------------------------------------------------------------
@router.get("/kurum")
def kurum_baglantilari(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok({"baglantilar": baglantilar.kurum_baglantilari(db)})


@router.post("/kurum/ad-testi")
def ad_erisim_testi(admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    """DNS -> TCP -> TLS/sertifika (python -m app.ad ile ayni; bind YOK, parola istenmez). En fazla ~15 sn (adim basina 5 sn)."""
    adimlar = ad.erisim_adimlari()
    tamam = all(x["durum"] == "ok" for x in adimlar)
    _denetim(admin, "yonetim.ad_erisim_testi", "ok" if tamam else f"hata={adimlar[-1]['adim']}")
    return ok({"tamam": tamam, "adimlar": adimlar})


@router.post("/kurum/eposta-testi")
def eposta_erisim_testi(admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    """Aylik rapor SMTP'si: ayar -> DNS -> TCP -> EHLO (rapor/smtp_gonderim.py). ILETI GONDERILMEZ; kip eml iken de calisir."""
    from app.rapor import smtp_gonderim

    adimlar = smtp_gonderim.erisim_adimlari()
    tamam = all(x["durum"] == "ok" for x in adimlar) and adimlar[-1]["adim"] == "ehlo"
    _denetim(admin, "yonetim.eposta_erisim_testi", "ok" if tamam else f"hata={adimlar[-1]['adim']}")
    return ok({"tamam": tamam, "kip": smtp_gonderim.kip(), "adimlar": adimlar})


@router.post("/kurum/{kaynak}/test")
def oracle_erisim_testi(kaynak: str, admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    """Oracle kaynagi (oracle_reportdb | oracle_onent | oracle_galapagos): ayar -> DNS -> TCP -> oturum (SELECT 1 FROM DUAL, ayri
    surecte). Yazmaz, tablo okumaz; yanit adres/parola tasimaz."""
    from app.tampon import postgres

    if kaynak in postgres.KAYNAKLAR:  # PostgreSQL (ONENTDB / ONEDESKDB): ayar -> DNS -> TCP -> salt okunur oturum (SELECT 1)
        adimlar = postgres.erisim_adimlari(kaynak)
    elif kaynak not in oracle.KAYNAKLAR:
        raise oracle.OracleHata("Bu kaynak bir Oracle kaynağı değil.", 404)
    else:
        adimlar = oracle.erisim_adimlari(kaynak)
    tamam = all(x["durum"] == "ok" for x in adimlar) and adimlar[-1]["adim"] == "oturum"
    _denetim(admin, "yonetim.oracle_erisim_testi", f"kaynak={kaynak} " + ("ok" if tamam else f"hata={adimlar[-1]['adim']}"))
    return ok({"tamam": tamam, "adimlar": adimlar})


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


# --- TAM Utilizasyon > Musteri Listesi ------------------------------------------------------------------------------
class MusteriSilGovde(BaseModel):
    ids: list[KimlikTipi] = Field(default_factory=list, max_length=musteri_listesi.EN_FAZLA_SILINECEK)
    hepsi: bool = False
    onay: str = Field(default="", max_length=20)  # hepsi=true iken "SIL" yazilmali


class MusteriSatiri(BaseModel):
    name: str = Field(max_length=300)  # servis 150 karakter sinirini Turkce mesajla uygular
    segment: str | None = Field(default=None, max_length=100)


class MusteriTopluEkleGovde(BaseModel):
    satirlar: list[MusteriSatiri] = Field(max_length=musteri_listesi.EN_FAZLA_EKLENECEK)
    parent_id: KimlikTipi | None = None
    owner_id: KimlikTipi | None = None


@router.get("/musteriler")
def musteri_listesi_oku(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(musteri_listesi.liste(db))


@router.post("/musteriler/sil")
def musteri_sil(body: MusteriSilGovde, admin: Principal = Depends(require_veri_yazma), db: Session = Depends(get_db)) -> dict[str, Any]:
    sonuc = musteri_listesi.sil(db, body.ids, body.hepsi, body.onay)
    db.commit()
    _denetim(admin, "yonetim.musteri_sil", f"silinen={sonuc['silinen']} istenen={sonuc['istenen']} hepsi={sonuc['hepsi']}")
    return ok(sonuc)


@router.post("/musteriler/toplu-ekle")
def musteri_toplu_ekle(body: MusteriTopluEkleGovde, admin: Principal = Depends(require_veri_yazma), db: Session = Depends(get_db)) -> dict[str, Any]:
    sonuc = musteri_listesi.toplu_ekle(db, admin, [s.model_dump() for s in body.satirlar], body.parent_id, body.owner_id)
    db.commit()
    _denetim(admin, "yonetim.musteri_toplu_ekle", f"eklenen={sonuc['eklenen']} atlanan={len(sonuc['atlanan'])} ust={body.parent_id or '-'}")
    return ok(sonuc)
