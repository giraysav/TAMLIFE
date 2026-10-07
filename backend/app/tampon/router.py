"""Tampon (Veri Girisi) HTTP katmani (/api/v1/tampon). Hepsi yalniz admin; yazanlar CSRF'li. Is kurali paketin modullerindedir."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import ariza
from app.audit import audit_log
from app.config import get_settings
from app.deps import engine, get_db, require_admin
from app.gateway import session_factory
from app.models import IngestBatch
from app.ortak import KimlikTipi, UygulamaHatasi, iso, ok, sayfa_bilgisi
from app.session import Principal
from app.tampon import analiz, dagitim, depo, kaynak

router = APIRouter(prefix="/api/v1/tampon", tags=["tampon"])



def _denetim(admin: Principal, islem: str, detay: str = "") -> None:
    audit_log.remember(actor=admin.username, action=islem, outcome="allow", module_key="tampon", detail=detay)


def _parti_satiri(p: IngestBatch) -> dict[str, Any]:
    return {
        "id": p.id,
        "kaynak": p.source_key,
        "etiket": p.label,
        "durum": p.status,
        "satir": p.row_count,
        "sutun_sayisi": len(p.columns or []),
        "hata": p.error,
        "olusturan": p.created_by,
        "zaman": iso(p.received_at),
        "bitis": iso(p.finished_at),
    }


def _parti(db: Session, parti_id: int) -> IngestBatch:
    parti = db.get(IngestBatch, parti_id)
    if parti is None:
        raise HTTPException(status_code=404, detail="Parti yok.")
    return parti


class OnizleGovde(BaseModel):
    parti_id: KimlikTipi


class UygulaGovde(BaseModel):
    parti_id: KimlikTipi
    onay: bool = False


class EtkinGovde(BaseModel):
    etkin: bool


class KuralGovde(BaseModel):
    """Alanlar dagitim.dogrula'da denetlenir; burada yalniz boyut/tur sinirlanir."""

    name: str = Field(default="", max_length=120)
    source_key: str = Field(default="", max_length=40)
    match_field: str = Field(default="customer_no", max_length=20)
    key_column: str = Field(default="", max_length=160)
    target: str = Field(default="", max_length=60)
    operation: str = Field(default="", max_length=20)
    value_column: str = Field(default="", max_length=160)
    conditions: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    zero_unmatched: bool = False
    max_age_minutes: int | None = None


# --- Kaynaklar ve katalog -------------------------------------------------------------------------------------------
@router.get("/kaynaklar")
def kaynaklar(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(kaynak.durumlar(db))


@router.get("/hedefler")
def hedefler(admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    return ok(dagitim.katalog())


# --- 1. Tampon: parti yukleme ve okuma ------------------------------------------------------------------------------
def _yukle(veri: bytes, kaynak_adi: str, dosya: str, kullanici: str) -> dict[str, Any]:
    """Kendi oturumunda calisir (threadpool): her blok kisa islemle yazilir."""
    with session_factory(engine())() as db:
        basliklar, satirlar = kaynak.csv_oku(veri)
        parti = depo.parti_olustur(
            db, kaynak.kaynak_anahtari(kaynak_adi or re.sub(r"\.[A-Za-z0-9]+$", "", dosya)), dosya or "yukleme.csv", kullanici
        )
        db.commit()
        try:
            parti = depo.ice_al(db, parti, basliklar, satirlar)
        except UygulamaHatasi:
            raise
        except Exception as hata:
            kayit = ariza.kaydet("TL-TAM-01", exc=hata, kaynak="tampon.yukle", kullanici=kullanici)
            raise UygulamaHatasi(500, ariza.mesaj("TL-TAM-01", kayit)) from hata
        return _parti_satiri(parti)


@router.put("/yukle")
async def yukle(
    request: Request,
    kaynak_adi: str = Query(default="", alias="kaynak", max_length=60),
    dosya: str = Query(default="", max_length=200),
    admin: Principal = Depends(require_admin),
) -> dict[str, Any]:
    """Ham CSV govdesi (cok parcali form yok: yeni bagimlilik gerektirmez). Boyut siniri akis sirasinda uygulanir."""
    sinir = get_settings().ingest_max_mb * 1024 * 1024
    bildirilen = request.headers.get("content-length", "")
    if bildirilen.isdigit() and int(bildirilen) > sinir:
        raise HTTPException(status_code=413, detail=f"Dosya çok büyük (en fazla {get_settings().ingest_max_mb} MB).")
    parcalar: list[bytes] = []
    boyut = 0
    async for parca in request.stream():
        boyut += len(parca)
        if boyut > sinir:
            raise HTTPException(status_code=413, detail=f"Dosya çok büyük (en fazla {get_settings().ingest_max_mb} MB).")
        parcalar.append(parca)
    sonuc = await run_in_threadpool(_yukle, b"".join(parcalar), kaynak_adi, dosya, admin.username)
    _denetim(admin, "tampon.yukle", f"parti={sonuc['id']} kaynak={sonuc['kaynak']} satir={sonuc['satir']} durum={sonuc['durum']}")
    return ok(sonuc)


@router.post("/ornek")
def ornek(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    parti = kaynak.ornek_parti(db, admin.username)
    _denetim(admin, "tampon.ornek", f"parti={parti.id} satir={parti.row_count}")
    return ok(_parti_satiri(parti))


@router.get("/partiler")
def partiler(
    kaynak_adi: str = Query(default="", alias="kaynak", max_length=40),
    durum: str = Query(default="", max_length=20),
    sayfa: int = Query(default=1, ge=1),
    adet: int = Query(default=20, ge=1, le=100),
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sorgu = select(IngestBatch)
    if kaynak_adi:
        sorgu = sorgu.where(IngestBatch.source_key == kaynak_adi)
    if durum in depo.DURUMLAR:
        sorgu = sorgu.where(IngestBatch.status == durum)
    toplam = db.scalar(select(func.count()).select_from(sorgu.subquery())) or 0
    sayfa, atla, adet = sayfa_bilgisi(sayfa, adet, toplam)
    satirlar = db.scalars(sorgu.order_by(IngestBatch.id.desc()).offset(atla).limit(adet)).all()
    return ok({"toplam": toplam, "sayfa": sayfa, "adet": adet, "satirlar": [_parti_satiri(p) for p in satirlar]})


@router.get("/partiler/{parti_id}")
def parti_ayrintisi(parti_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    parti = _parti(db, parti_id)
    profil = parti.profile or {}
    return ok(
        {
            **_parti_satiri(parti),
            "sutunlar": list(parti.columns or []),
            "profil": profil.get("sutunlar", []),
            "analiz": profil.get("analiz"),
            "kullanimda": depo.kullanimda_mi(db, parti_id),
        }
    )


@router.get("/partiler/{parti_id}/satirlar")
def parti_satirlari(
    parti_id: KimlikTipi,
    sayfa: int = Query(default=1, ge=1),
    adet: int = Query(default=25, ge=1, le=100),
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    parti = _parti(db, parti_id)
    sayfa, _, adet = sayfa_bilgisi(sayfa, adet, parti.row_count)
    return ok(
        {
            "basliklar": list(parti.columns or []),
            "satirlar": depo.sayfa_oku(db, parti_id, sayfa, adet),
            "toplam": parti.row_count,
            "sayfa": sayfa,
            "adet": adet,
        }
    )


# --- 2. Analiz ------------------------------------------------------------------------------------------------------
@router.post("/partiler/{parti_id}/analiz")
def parti_analizi(parti_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    parti = _parti(db, parti_id)
    if parti.status not in ("ready", "rejected"):
        raise HTTPException(status_code=409, detail="Parti analiz için hazır değil.")
    sonuc = analiz.analiz_et(db, parti)
    db.commit()
    return ok(sonuc)


@router.post("/partiler/{parti_id}/kabul")
def parti_kabul(parti_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    parti = depo.kabul_et(db, parti_id)
    db.commit()
    _denetim(admin, "tampon.kabul", f"parti={parti_id}")
    return ok(_parti_satiri(parti))


@router.delete("/partiler/{parti_id}")
def parti_sil(parti_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    depo.sil(db, parti_id)
    db.commit()
    _denetim(admin, "tampon.sil", f"parti={parti_id}")
    return ok({"id": parti_id})


# --- 3. Dagitim kurallari -------------------------------------------------------------------------------------------
@router.get("/kurallar")
def kural_listesi(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(dagitim.kurallar(db))


@router.post("/kurallar")
def kural_olustur(govde: KuralGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    kural = dagitim.kural_olustur(db, govde.model_dump(), admin.username)
    db.commit()
    _denetim(admin, "tampon.kural_olustur", f"kural={kural.id} hedef={kural.target}")
    return ok(dagitim.kural_satiri(kural))


@router.put("/kurallar/{kural_id}")
def kural_guncelle(
    kural_id: KimlikTipi, govde: KuralGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)
) -> dict[str, Any]:
    kural = dagitim.kural_guncelle(db, kural_id, govde.model_dump())
    db.commit()
    _denetim(admin, "tampon.kural_guncelle", f"kural={kural_id}")
    return ok(dagitim.kural_satiri(kural))


@router.post("/kurallar/{kural_id}/etkin")
def kural_etkin(
    kural_id: KimlikTipi, govde: EtkinGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)
) -> dict[str, Any]:
    kural = dagitim.kural_getir(db, kural_id)
    kural.enabled = govde.etkin
    db.commit()
    _denetim(admin, "tampon.kural_etkin", f"kural={kural_id} etkin={govde.etkin}")
    return ok(dagitim.kural_satiri(kural))


@router.delete("/kurallar/{kural_id}")
def kural_sil(kural_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    dagitim.kural_sil(db, kural_id)
    db.commit()
    _denetim(admin, "tampon.kural_sil", f"kural={kural_id}")
    return ok({"id": kural_id})


@router.post("/kurallar/{kural_id}/onizle")
def kural_onizle(
    kural_id: KimlikTipi, govde: OnizleGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)
) -> dict[str, Any]:
    return ok(dagitim.onizle(db, kural_id, govde.parti_id))


@router.post("/kurallar/{kural_id}/uygula")
def kural_uygula(
    kural_id: KimlikTipi, govde: UygulaGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)
) -> dict[str, Any]:
    if not govde.onay:
        raise HTTPException(status_code=400, detail="Uygulamak için onay gerekir.")
    sonuc = dagitim.uygula(db, kural_id, govde.parti_id, admin.username)
    db.commit()
    _denetim(admin, "tampon.uygula", f"kural={kural_id} parti={govde.parti_id} yazilan={sonuc['yazilan']} run={sonuc['run_id'][:8]}")
    return ok(sonuc)


@router.get("/uygulamalar")
def uygulama_listesi(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(dagitim.uygulamalar(db))


@router.post("/uygulamalar/{run_id}/geri-al")
def uygulama_geri_al(run_id: str, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise HTTPException(status_code=400, detail="Geçersiz uygulama kimliği.")
    sonuc = dagitim.geri_al(db, run_id, admin.username)
    db.commit()
    _denetim(admin, "tampon.geri_al", f"run={run_id[:8]} geri={sonuc['geri_alinan']} korunan={sonuc['korunan']}")
    return ok(sonuc)
