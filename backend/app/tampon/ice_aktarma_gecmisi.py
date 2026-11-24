"""Elle yuklenen dosya aktarimlarinin gecmisi ve GERI ALMA (2026-11-01 kullanici: "urun-tutar'i eklenen musteri icin geri alma
secenegi yok; importa manuel eklenen dosya olursa geri alma secenegi de olmali").

Kapsam: Urun-Tutar, Gelir Faydasi ve Takip Edilen Projeler Excel'i. Ham Musteri Verisi (customer_import_run) ve parti olusturan
yuklemeler (dagitim geri alma) kendi geri almalarina sahiptir. Kural digerleriyle ayni: yalniz aktarimdan sonra elle
DEGISTIRILMEMIS kayitlar geri doner (yazildigi andaki updated_at / uploaded_at hala ayniysa); degisenler korunur ve sayilir.

record bicimi:
  urun_tutar   : {'musteriler': [{'id', 'zaman' (yeni uploaded_at), 'onceki': None | {'ozet', 'dosya', 'yukleyen', 'zaman', 'devreler'}}]}
  gelir_uretim : {'kayitlar': [{'id', 'zaman' (updated_at)}]}
  proje        : {'kayitlar': [{'id', 'zaman' (updated_at)}]}
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.dil import m
from app.gelir_uretim.models import RevenueBenefit, RevenueBenefitPerson
from app.models import ProjectAction, ProjectItem, UrunTutarOzet
from app.ortak import UygulamaHatasi, iso, simdi
from app.tampon.models import FileImportRun

TURLER = ("urun_tutar", "gelir_uretim", "proje")
_kilit = threading.Lock()


def kaydet(db: Session, tur: str, dosya: str, yapan: str, ozet: dict, kayit: dict) -> FileImportRun:
    """Aktarimi gecmise yazar (flush eder; commit aktarimla ayni islemde cagirana aittir)."""
    satir = FileImportRun(kind=tur, file_name=(dosya or "")[:200], at=simdi(), actor=(yapan or "")[:120], summary=ozet, record=kayit)
    db.add(satir)
    db.flush()
    return satir


def liste(db: Session, adet: int = 50) -> list[dict[str, Any]]:
    sorgu = select(FileImportRun).order_by(FileImportRun.id.desc()).limit(adet)
    return [
        {
            "id": k.id, "tur": k.kind, "dosya": k.file_name, "zaman": iso(k.at), "kullanici": k.actor, "ozet": k.summary or {},
            "geri_alinan": {"zaman": iso(k.reverted_at), "kullanici": k.reverted_by} if k.reverted_at else None,
        }
        for k in db.scalars(sorgu)
    ]  # fmt: skip


def _urun_tutar(db: Session, kayit: dict) -> tuple[int, int]:
    geri = korunan = 0
    for g in kayit.get("musteriler") or []:
        satir = db.get(UrunTutarOzet, g["id"])
        if satir is None or iso(satir.uploaded_at) != g.get("zaman"):
            korunan += 1  # sonradan yeniden yuklenmis ya da silinmis
            continue
        onceki = g.get("onceki")
        if onceki:
            satir.summary, satir.file_name, satir.uploaded_by = onceki.get("ozet") or {}, onceki.get("dosya") or "", onceki.get("yukleyen") or ""
            satir.circuits = onceki.get("devreler") or []  # 2026-11-24 oncesi kayitlarda devre listesi yoktu
            satir.uploaded_at = datetime.fromisoformat(onceki["zaman"]) if onceki.get("zaman") else None
        else:
            db.delete(satir)
        geri += 1
    return geri, korunan


def _gelir(db: Session, kayit: dict) -> tuple[int, int]:
    geri = korunan = 0
    for g in kayit.get("kayitlar") or []:
        satir = db.get(RevenueBenefit, g["id"])
        if satir is None:
            continue
        if iso(satir.updated_at) != g.get("zaman"):
            korunan += 1
            continue
        db.execute(delete(RevenueBenefitPerson).where(RevenueBenefitPerson.item_id == satir.id))
        db.delete(satir)
        geri += 1
    return geri, korunan


def _proje(db: Session, kayit: dict) -> tuple[int, int]:
    geri = korunan = 0
    for g in kayit.get("kayitlar") or []:
        kalem = db.get(ProjectItem, g["id"])
        if kalem is None:
            continue
        if iso(kalem.updated_at) != g.get("zaman"):
            korunan += 1  # sonradan aksiyon/duzenleme girilmis
            continue
        db.execute(delete(ProjectAction).where(ProjectAction.item_id == kalem.id))
        db.delete(kalem)
        geri += 1
    return geri, korunan


_GERI_AL = {"urun_tutar": _urun_tutar, "gelir_uretim": _gelir, "proje": _proje}


def geri_al(db: Session, kayit_id: int, kullanici: str) -> dict[str, Any]:
    with _kilit:
        k = db.get(FileImportRun, kayit_id)
        if k is None:
            raise UygulamaHatasi(404, m("Aktarım kaydı bulunamadı.", "Import record not found."))
        if k.reverted_at is not None:
            raise UygulamaHatasi(409, m("Bu aktarım zaten geri alınmış.", "This import has already been undone."))
        geri, korunan = _GERI_AL[k.kind](db, k.record or {})
        k.reverted_at, k.reverted_by = simdi(), kullanici[:120]
        db.flush()
        return {"geri_alinan": geri, "korunan": korunan}
