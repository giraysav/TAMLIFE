"""Musteri Yonetimi ve Aylik Rapor HTTP katmani. Is kurali musteri_servis.py ve rapor_servis.py'dedir."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.audit import audit_log
from app.config import get_settings
from app.db import get_db, oturum
from app.erisim import Erisim, modul_erisim, musteri_alani_erisim
from app.musteri import kayitlar as mk
from app.musteri import servis as ms
from app.ortak import EN_BUYUK_KIMLIK, EN_BUYUK_SAYFA_NO, KimlikTipi, govde_oku, ok
from app.rapor import servis as rs
from app.session import Principal

router = APIRouter(prefix="/api/v1", tags=["musteri"])


musteri_erisim = musteri_alani_erisim()  # Toptan / Baglantili Araclar kartlari kendi modul yetkisiyle
rapor_erisim = modul_erisim("rapor")


def _yap(db: Session, islem: Callable[[], Any], yaz: bool = False) -> Any:
    """Servis cagrisini calistirir; yazma ise commit eder. Hatalar UygulamaHatasi olarak yukari cikar (tek isleyici HTTP'ye cevirir)."""
    sonuc = islem()
    if yaz:
        db.commit()
    return ok(sonuc)


def _denetim(user: Principal, islem: str, detay: str) -> None:
    audit_log.remember(actor=user.username, action=islem, outcome="allow", module_key="musteri", detail=detay)


class YeniMusteri(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    segment: str | None = Field(default=None, max_length=100)
    parent_id: KimlikTipi | None = None
    owner_id: KimlikTipi | None = None


class Serbest(BaseModel):
    """Alan listesi servis katmaninda dogrulanir; burada yalniz boyut sinirlanir."""

    model_config = {"extra": "allow"}


class SorumluGovde(BaseModel):
    owner_id: KimlikTipi


class AyriRaporGovde(BaseModel):
    ayri_rapor: bool


class TaslakGovde(BaseModel):
    alanlar: dict = Field(default_factory=dict)


class AlicilarGovde(BaseModel):
    kime: str | list[str] | None = Field(default=None, max_length=5000)
    bilgi: str | list[str] | None = Field(default=None, max_length=5000)


class GonderGovde(BaseModel):
    onay: bool = False
    to: str | list[str] | None = None
    cc: str | list[str] | None = None
    subject: str | None = Field(default=None, max_length=400)
    body_text: str | None = Field(default=None, max_length=10000)  # bos: kayitli taslak / hazir metin
    signature: str | None = Field(default=None, max_length=2000)
    lang: Literal["tr", "en"] | None = None
    pdf_base64: str | None = Field(default=None, max_length=45 * 1024 * 1024)
    alanlar: dict | None = None  # gonderilen rapor metni; taslak olarak saklanir (takip icin)


def _govde(model: BaseModel) -> dict:
    return model.model_dump(exclude_unset=True)


# --- musteri ---------------------------------------------------------------------------------------
@router.get("/musteri")
def liste(
    q: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1, le=EN_BUYUK_SAYFA_NO),
    per_page: int = Query(default=ms.SAYFA_BASINA, ge=1, le=ms.EN_FAZLA_SAYFA_BASINA),
    e: Erisim = Depends(musteri_erisim),
    db: Session = Depends(get_db),
):
    return _yap(db, lambda: ms.liste(db, e.user, q, page, per_page))


@router.get("/musteri/portfoy")
def portfoy(
    q: str = Query(default="", max_length=100),
    tam: int | None = Query(default=None, ge=1, le=EN_BUYUK_KIMLIK),
    segment: str = Query(default="", max_length=20),
    page: int = Query(default=1, ge=1, le=EN_BUYUK_SAYFA_NO),
    per_page: int = Query(default=ms.PORTFOY_SAYFA, ge=1, le=ms.EN_FAZLA_SAYFA_BASINA),
    e: Erisim = Depends(musteri_erisim),
    db: Session = Depends(get_db),
):
    return _yap(db, lambda: ms.portfoy(db, e.user, q, tam, segment, page, per_page))


@router.get("/musteri/{musteri_id:int}/kayitlar")
def kart_kayitlari(
    musteri_id: KimlikTipi,
    tur: str = Query(pattern="^(alarm|talep|sikayet)$"),
    durum: str = Query(pattern="^(acik|kapali)$"),
    yil: int | None = Query(default=None, ge=2000, le=2100),
    page: int = Query(default=1, ge=1, le=EN_BUYUK_SAYFA_NO),
    per_page: int = Query(default=mk.SAYFA, ge=1, le=mk.EN_COK),
    e: Erisim = Depends(musteri_erisim),
    db: Session = Depends(get_db),
):
    """Kart Operasyon dugmeleri: kartin secilen turdeki acik (su an) ya da kapanan (yil ici) kayitlari."""
    return _yap(db, lambda: mk.kart_kayitlari(db, e.user, musteri_id, tur, durum, yil, page, per_page))


@router.get("/musteri/secenekler")
def secenekler(e: Erisim = Depends(musteri_erisim), db: Session = Depends(get_db)):
    return _yap(db, lambda: ms.secenekler(db, e.user))


@router.post("/musteri")
def ekle(
    body: YeniMusteri, e: Erisim = Depends(musteri_erisim), db: Session = Depends(get_db)
):
    sonuc = _yap(db, lambda: ms.musteri_ekle(db, e.user, _govde(body)), yaz=True)
    if isinstance(sonuc, dict):
        _denetim(e.user, "musteri.ekle", f"musteri={sonuc['data']['id']}")
    return sonuc


@router.get("/musteri/{musteri_id:int}")
def kart(musteri_id: KimlikTipi, e: Erisim = Depends(musteri_erisim), db: Session = Depends(get_db)):
    return _yap(db, lambda: ms.karti(db, e.user, musteri_id, e.izinli))


@router.put("/musteri/{musteri_id:int}/kimlik")
def kimlik(
    musteri_id: KimlikTipi,
    body: Serbest,
    e: Erisim = Depends(musteri_erisim),
    db: Session = Depends(get_db),
):
    sonuc = _yap(db, lambda: ms.kimlik_guncelle(db, e.user, musteri_id, _govde(body)), yaz=True)
    if isinstance(sonuc, dict):
        _denetim(e.user, "musteri.kimlik", f"musteri={musteri_id}")
    return sonuc


@router.put("/musteri/{musteri_id:int}/iletisim")
def iletisim(
    musteri_id: KimlikTipi,
    body: Serbest,
    e: Erisim = Depends(musteri_erisim),
    db: Session = Depends(get_db),
):
    sonuc = _yap(db, lambda: ms.iletisim_kaydet(db, e.user, musteri_id, _govde(body)), yaz=True)
    if isinstance(sonuc, dict):
        _denetim(e.user, "musteri.iletisim", f"musteri={musteri_id}")
    return sonuc


@router.put("/musteri/{musteri_id:int}/sorumlu")
def sorumlu(
    musteri_id: KimlikTipi,
    body: SorumluGovde,
    e: Erisim = Depends(musteri_erisim),
    db: Session = Depends(get_db),
):
    sonuc = _yap(db, lambda: ms.tam_degistir(db, e.user, musteri_id, body.owner_id), yaz=True)
    if isinstance(sonuc, dict):
        _denetim(e.user, "musteri.sorumlu", f"musteri={musteri_id} yeni={body.owner_id}")
    return sonuc


@router.delete("/musteri/{musteri_id:int}")
def sil(
    musteri_id: KimlikTipi, e: Erisim = Depends(musteri_erisim), db: Session = Depends(get_db)
):
    sonuc = _yap(db, lambda: ms.sil(db, e.user, musteri_id), yaz=True)
    if isinstance(sonuc, dict):
        _denetim(e.user, "musteri.sil", f"musteri={musteri_id} adet={sonuc['data']['silinen']}")
    return sonuc


# --- aylik rapor -----------------------------------------------------------------------------------
@router.put("/musteri/{musteri_id:int}/ayri-rapor")
def ayri_rapor(
    musteri_id: KimlikTipi,
    body: AyriRaporGovde,
    e: Erisim = Depends(musteri_erisim),
    db: Session = Depends(get_db),
):
    return _yap(db, lambda: rs.ayri_rapor_ayarla(db, e.user, musteri_id, body.ayri_rapor), yaz=True)


@router.get("/musteri/{musteri_id:int}/rapor/taslak")
def taslak_oku(musteri_id: KimlikTipi, e: Erisim = Depends(musteri_erisim), db: Session = Depends(get_db)):
    return _yap(db, lambda: rs.taslak_getir(db, e.user, musteri_id))


@router.put("/musteri/{musteri_id:int}/rapor/taslak")
def taslak_yaz(musteri_id: KimlikTipi, body: TaslakGovde, e: Erisim = Depends(musteri_erisim), db: Session = Depends(get_db)):
    return _yap(db, lambda: rs.taslak_kaydet(db, e.user, musteri_id, body.alanlar), yaz=True)


@router.put("/musteri/{musteri_id:int}/rapor/alicilar")
def alicilar(musteri_id: KimlikTipi, body: AlicilarGovde, e: Erisim = Depends(musteri_erisim), db: Session = Depends(get_db)):
    return _yap(db, lambda: rs.alicilar_kaydet(db, e.user, musteri_id, _govde(body)), yaz=True)


@router.post("/musteri/{musteri_id:int}/rapor/gonder")
def gonder(musteri_id: KimlikTipi, body: GonderGovde, e: Erisim = Depends(musteri_erisim), db: Session = Depends(get_db)):
    """Gonderim hatasi admin'e bildirilir (rs.gonderim_hatasi_bildir): teslim hatasi (EpostaHata) ve beklenmeyen hata. Kullanici
    girdisi hatalari (onay yok, ay kilitli, gecersiz alici: RaporHata 4xx) bildirim uretmez."""
    from app import ariza
    from app.ortak import UygulamaHatasi
    from app.rapor import smtp_gonderim

    try:
        sonuc = _yap(db, lambda: rs.gonder(db, e.user, musteri_id, _govde(body)), yaz=True)
    except UygulamaHatasi as exc:
        if isinstance(exc, smtp_gonderim.EpostaHata) or exc.kod >= 500:
            db.rollback()  # istek oturumunun yazma kilidi birakilsin: ariza kaydi ayri oturumla yazilir
            rs.gonderim_hatasi_bildir(e.user, musteri_id, exc.mesaj)
        raise
    except Exception as exc:
        db.rollback()  # SMTP kipinde ileti teslim edilmis, kayit yazilamamis olabilir: bildirimde belirtilir
        kayit = rs.gonderim_hatasi_bildir(e.user, musteri_id, f"{type(exc).__name__} (SMTP kipinde ileti alıcıya gitmiş olabilir)", exc=exc)
        raise UygulamaHatasi(500, ariza.mesaj(rs.GONDERIM_ARIZASI, kayit)) from exc
    if isinstance(sonuc, dict):
        _denetim(e.user, "rapor.gonder", f"musteri={musteri_id}")
    return sonuc


def _ayri_oturumda(islem: Callable[[Session], Any]) -> Any:
    """Excel okumasi CPU-yogun: threadpool'da kendi oturumuyla calisir, olay dongusunu bekletmez."""
    with oturum() as db:
        sonuc = islem(db)
        db.commit()
        return sonuc


@router.get("/musteri/{musteri_id:int}/rapor/sla")
def sla_oku(musteri_id: KimlikTipi, e: Erisim = Depends(musteri_erisim), db: Session = Depends(get_db)):
    return _yap(db, lambda: rs.sla_getir(db, e.user, musteri_id))


@router.put("/musteri/{musteri_id:int}/rapor/sla")
async def sla_yukle(
    musteri_id: KimlikTipi, request: Request, dosya: str = Query(default="", max_length=200), e: Erisim = Depends(musteri_erisim)
):
    """SLA Excel'i (.xlsx govdesi). Donemde oncekinin yerine gecer; rapor gonderilirken iletiye otomatik eklenir."""
    veri = await govde_oku(request, min(get_settings().ingest_max_mb, 30) * 1048576)
    sonuc = await run_in_threadpool(_ayri_oturumda, lambda db: rs.sla_yukle(db, e.user, musteri_id, veri, dosya))
    _denetim(e.user, "rapor.sla_yukle", f"musteri={musteri_id} boyut={len(veri)}")
    return ok(sonuc)


@router.delete("/musteri/{musteri_id:int}/rapor/sla")
def sla_sil(musteri_id: KimlikTipi, e: Erisim = Depends(musteri_erisim), db: Session = Depends(get_db)):
    return _yap(db, lambda: rs.sla_sil(db, e.user, musteri_id))


@router.post("/musteri/{musteri_id:int}/rapor/gorsel")
async def gorsel_ekle(
    musteri_id: KimlikTipi, request: Request, baslik: str = Query(default="", max_length=200), e: Erisim = Depends(musteri_erisim)
):
    """Elle eklenen rapor grafigi (MRTG vb.; GALAPAGOS baglanana kadar). PNG/JPEG/GIF govdesi."""
    veri = await govde_oku(request, 10 * 1048576)
    return ok(await run_in_threadpool(_ayri_oturumda, lambda db: rs.gorsel_ekle(db, e.user, musteri_id, veri, baslik)))


@router.delete("/musteri/{musteri_id:int}/rapor/gorsel/{numara:int}")
def gorsel_sil(musteri_id: KimlikTipi, numara: KimlikTipi, e: Erisim = Depends(musteri_erisim), db: Session = Depends(get_db)):
    return _yap(db, lambda: rs.gorsel_sil(db, e.user, musteri_id, numara))


@router.post("/musteri/{musteri_id:int}/rapor/dosya")
async def dosya_ekle(
    musteri_id: KimlikTipi, request: Request, ad: str = Query(default="", max_length=200), e: Erisim = Depends(musteri_erisim)
):
    """Rapor iletisine eklenecek dosya (ham govde). Gonderimde iletiye otomatik girer."""
    veri = await govde_oku(request, 20 * 1048576)
    sonuc = await run_in_threadpool(_ayri_oturumda, lambda db: rs.dosya_ekle(db, e.user, musteri_id, veri, ad))
    _denetim(e.user, "rapor.dosya_ekle", f"musteri={musteri_id} boyut={len(veri)}")
    return ok(sonuc)


@router.delete("/musteri/{musteri_id:int}/rapor/dosya/{numara:int}")
def dosya_sil(musteri_id: KimlikTipi, numara: KimlikTipi, e: Erisim = Depends(musteri_erisim), db: Session = Depends(get_db)):
    return _yap(db, lambda: rs.dosya_sil(db, e.user, musteri_id, numara))


@router.post("/musteri/{musteri_id:int}/rapor/sla/analiz")
async def sla_analizi(musteri_id: KimlikTipi, body: Serbest, e: Erisim = Depends(musteri_erisim)):
    """SLA Excel'inin tum verisinin ozeti; `yz: true` ise (ve YZ aciksa) dil modeli yorumu da. Excel okumasi threadpool'da."""
    govde = body.model_dump()
    sonuc = await run_in_threadpool(_ayri_oturumda, lambda db: rs.sla_analizi(db, e.user, musteri_id, govde))
    if govde.get("yz") is True:
        _denetim(e.user, "rapor.sla_yz", f"musteri={musteri_id}")
    return ok(sonuc)


@router.post("/musteri/{musteri_id:int}/rapor/cevir")
async def cevir(musteri_id: KimlikTipi, body: Serbest, e: Erisim = Depends(musteri_erisim)):
    """Personelin yazdigi rapor alanlarinin TR -> EN makine cevirisi (ayri surecte; uzun surebilir)."""
    govde = body.model_dump()
    return ok(await run_in_threadpool(_ayri_oturumda, lambda db: rs.metin_cevir(db, e.user, musteri_id, govde)))


@router.get("/musteri/{musteri_id:int}/rapor/gecmis")
def gecmis(musteri_id: KimlikTipi, e: Erisim = Depends(musteri_erisim), db: Session = Depends(get_db)):
    return _yap(db, lambda: rs.gonderimler(db, e.user, musteri_id=musteri_id))


@router.post("/rapor/gonderim/{gonderim_id:int}/geri-al")
def geri_al(gonderim_id: KimlikTipi, e: Erisim = Depends(musteri_erisim), db: Session = Depends(get_db)):
    sonuc = _yap(db, lambda: rs.geri_al(db, e.user, gonderim_id), yaz=True)
    if isinstance(sonuc, dict):
        _denetim(e.user, "rapor.geri_al", f"gonderim={gonderim_id}")
    return sonuc


# --- Gonderilen Aylik Rapor modulu -------------------------------------------------------------------
@router.get("/rapor/gonderilenler")
def gonderilenler(
    yil: int | None = Query(default=None, ge=2000, le=2100),
    ay: int | None = Query(default=None, ge=1, le=12),
    e: Erisim = Depends(rapor_erisim),
    db: Session = Depends(get_db),
):
    return _yap(db, lambda: rs.gonderimler(db, e.user, yil=yil, ay=ay))


@router.get("/rapor/durum")
def durum(
    yil: int | None = Query(default=None, ge=2000, le=2100),
    ay: int | None = Query(default=None, ge=1, le=12),
    e: Erisim = Depends(rapor_erisim),
    db: Session = Depends(get_db),
):
    simdi_yil, simdi_ay = rs.donem()
    return _yap(db, lambda: rs.durum_ozeti(db, e.user, ay or simdi_ay, yil or simdi_yil))
