# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Final skor / TAM Utilizasyon HTTP katmani (/api/v1/skor). Is kurali servis.py, motor.py, kaynaklar.py'dedir.

Yetki (uretim moduller.py: utilizasyon yalniz_admin; uclar @modul_gerekli('utilizasyon') / @admin_required): yonetim uclarinin
hepsi admin ya da `utilizasyon.yonet` yetkisi (rolgorunum; 2026-11-11). Tek istisna TAM tarafindaki "skor atamasi iste" (POST /talepler): oturum + kendi musterisi.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.audit import audit_log
from app.config import get_settings
from app.db import get_db, oturum
from app.deps import require_user
from app.erisim import utilizasyon_yetkisi
from app.kullanicilar import kullanici_kaydi
from app.ortak import KimlikTipi, govde_oku, ok
from app.session import Principal
from app.skor import kaynak_secimi, servis, urun_tutar

router = APIRouter(prefix="/api/v1/skor", tags=["skor"])


def _denetim(user: Principal, islem: str, detay: str = "") -> None:
    audit_log.remember(actor=user.username, action=islem, outcome="allow", module_key="utilizasyon", detail=detay)


def _kimlik(db: Session, user: Principal) -> int:
    return kullanici_kaydi(db, user).id


class KriterGovde(BaseModel):
    criteria: list[dict] = Field(max_length=servis.EN_FAZLA_KRITER)


class TopluOnizleme(BaseModel):
    tam_id: KimlikTipi | None = None


class TopluUygula(BaseModel):
    customer_ids: list[KimlikTipi] = Field(min_length=1, max_length=servis.EN_FAZLA_TOPLU)


class ManuelSecim(BaseModel):
    secimler: dict[str, int | list[str]] = Field(max_length=servis.EN_FAZLA_KRITER)


class MusteriSkoru(BaseModel):
    tam_id: KimlikTipi
    score: float | int | str
    detay: list[dict] = Field(default_factory=list, max_length=servis.EN_FAZLA_KRITER)


class TalepGovde(BaseModel):
    customer_id: KimlikTipi


class KararGovde(BaseModel):
    action: str


class PuanlamaDisi(BaseModel):
    disi: list[KimlikTipi] = Field(max_length=2000)


class IstirakGovde(BaseModel):
    dahil: bool


class OnizleGovde(BaseModel):
    satir: dict


@router.get("/kriterler/{scope}")
def kriterleri_oku(scope: str, user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    return ok(servis.kriter_tablosu(db, scope))


@router.put("/kriterler/{scope}")
def kriterleri_kaydet(scope: str, body: KriterGovde, user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    sonuc = servis.kriterler_kaydet(db, scope, body.criteria, user.username, _kimlik(db, user))
    db.commit()
    u = sonuc["uygulama"]
    ek = f" uygulanan={len(u['uygulanan'])} atlanan={len(u['atlanan'])} degismeyen={u['degismeyen']}" if u else ""
    _denetim(user, "skor.kriter_kaydet", f"scope={scope} surum={sonuc['version']}{ek}")
    return ok(sonuc)


@router.get("/meta")
def meta(user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    return ok(servis.meta(db))


@router.post("/kaynak-onizle")
def kaynak_onizle(body: OnizleGovde, user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    return ok(kaynak_secimi.onizle(db, body.satir))


@router.post("/toplu/onizleme")
def toplu_onizleme(body: TopluOnizleme, user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    return ok(servis.onizleme(db, body.tam_id))


@router.post("/toplu/uygula")
def toplu_uygula(body: TopluUygula, user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    sonuc = servis.toplu_uygula(db, body.customer_ids, user.username, _kimlik(db, user))
    db.commit()
    _denetim(user, "skor.toplu_uygula", f"uygulanan={len(sonuc['uygulanan'])} atlanan={len(sonuc['atlanan'])}")
    return ok(sonuc)


@router.put("/toplu/manuel/{musteri_id}")
def toplu_manuel(musteri_id: KimlikTipi, body: ManuelSecim, user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    sonuc = servis.manuel_ata(db, musteri_id, body.secimler, user.username, _kimlik(db, user))
    db.commit()
    _denetim(user, "skor.manuel", f"musteri={musteri_id} skor={sonuc['yeni']}")
    return ok(sonuc)


@router.get("/agac")
def agac(user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    return ok(servis.agac(db))


@router.get("/siralama")
def siralama(user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    return ok(servis.siralama(db))


@router.put("/musteri/{musteri_id}")
def musteri_skoru(musteri_id: KimlikTipi, body: MusteriSkoru, user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    servis.musteri_skoru_ata(db, musteri_id, body.tam_id, body.score, body.detay, user.username, _kimlik(db, user))
    db.commit()
    _denetim(user, "skor.musteri", f"musteri={musteri_id}")
    return ok({"customer_id": musteri_id})


@router.post("/talepler")
def talep_ac(body: TalepGovde, user: Principal = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    talep_id = servis.talep_olustur(db, body.customer_id, user)
    db.commit()
    _denetim(user, "skor.talep_ac", f"musteri={body.customer_id}")
    return ok({"id": talep_id})


@router.get("/talepler")
def talepleri_listele(user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    satirlar = servis.talepler(db)
    return ok({"count": len(satirlar), "requests": satirlar})


@router.post("/talepler/{talep_id}/karar")
def talep_karar(talep_id: KimlikTipi, body: KararGovde, user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    servis.talep_karar(db, talep_id, body.action, _kimlik(db, user))
    db.commit()
    _denetim(user, "skor.talep_karar", f"talep={talep_id} islem={body.action}")
    return ok({"id": talep_id})


@router.put("/puanlama-disi")
def puanlama_disi(body: PuanlamaDisi, user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    kimlikler = servis.puanlama_disi_ayarla(db, body.disi, user.username)
    db.commit()
    _denetim(user, "skor.puanlama_disi", f"adet={len(kimlikler)}")
    return ok({"disi": kimlikler})


@router.put("/istirak/{musteri_id}/final-dahil")
def istirak_final_dahil(musteri_id: KimlikTipi, body: IstirakGovde, user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    dahil = servis.final_dahil_ayarla(db, musteri_id, body.dahil)
    db.commit()
    _denetim(user, "skor.istirak_dahil", f"musteri={musteri_id} dahil={dahil}")
    return ok({"dahil": dahil})


@router.get("/urun-tutar")
def urun_tutar_listesi(user: Principal = Depends(utilizasyon_yetkisi), db: Session = Depends(get_db)) -> dict:
    return ok(servis.urun_tutar_listesi(db))


def _urun_tutar_yukle(musteri_id: int, veri: bytes, dosya: str, kullanici: str) -> dict:
    """Kendi oturumunda (threadpool): openpyxl okumasi CPU-yogun; olay dongusunu bekletmez."""
    with oturum() as db:
        sonuc = urun_tutar.yukle(db, musteri_id, veri, dosya, kullanici)
        db.commit()
        return sonuc


@router.put("/urun-tutar/{musteri_id}")
async def urun_tutar_yukle(
    musteri_id: KimlikTipi,
    request: Request,
    dosya: str = Query(default="", max_length=200),
    user: Principal = Depends(utilizasyon_yetkisi),
) -> dict:
    """Ham .xlsx govdesi (tampon yuklemesiyle ayni kalip: cok parcali form yok). Ozet musteri basina son yuklemeyle degisir."""
    veri = await govde_oku(request, get_settings().ingest_max_mb * 1048576)
    sonuc = await run_in_threadpool(_urun_tutar_yukle, musteri_id, veri, dosya or "urun_tutar.xlsx", user.username)
    _denetim(user, "skor.urun_tutar", f"musteri={musteri_id} ozet={len(sonuc['musteriler'])} eslesen={sonuc['eslesen']}")
    return ok(sonuc)
