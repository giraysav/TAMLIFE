"""Onedesk HTTP katmani. Okuma: Onedesk modulunu gorenler (kapsam servis katmaninda); kaynak yonetimi ve aktarim: yalniz admin."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit_log
from app.baglantilar import connections
from app.db import get_db
from app.deps import require_admin
from app.erisim import Erisim, modul_erisim
from app.models import IngestBatch
from app.onedesk import ice_al, servis
from app.ortak import KimlikTipi, iso, ok
from app.session import Principal

router = APIRouter(prefix="/api/v1/onedesk", tags=["onedesk"])
erisim = modul_erisim("onedesk")

Yil = Query(default=None, ge=2000, le=2100)


class AktarGovde(BaseModel):
    tur: str | None = Field(default=None, max_length=20)  # kaynakta tur sutunu yoksa: alarm | talep | sikayet


@router.get("/durum")
def durum(kapsam: str = Query(default="acik", max_length=10), yil: int | None = Yil, e: Erisim = Depends(erisim), db: Session = Depends(get_db)):
    return ok(servis.durum(db, e.user, kapsam, yil))


@router.get("/top10")
def top10(yil: int | None = Yil, e: Erisim = Depends(erisim), db: Session = Depends(get_db)):
    return ok(servis.top10(db, e.user, yil))


@router.get("/rca")
def rca(yil: int | None = Yil, e: Erisim = Depends(erisim), db: Session = Depends(get_db)):
    return ok(servis.rca_ozeti(db, e.user, yil))


@router.get("/oneriler")
def oneriler(yil: int | None = Yil, e: Erisim = Depends(erisim), db: Session = Depends(get_db)):
    return ok(servis.oneriler(db, e.user, yil))


@router.post("/yz-yorum")
def yz_yorum(yil: int | None = Yil, e: Erisim = Depends(erisim), db: Session = Depends(get_db)):
    sonuc = servis.yz_yorumu(db, e.user, yil)
    audit_log.remember(actor=e.user.username, action="onedesk.yz_yorum", outcome="allow", module_key="onedesk", detail=f"yil={sonuc['yil']}")
    return ok(sonuc)


@router.get("/kaynak")
def kaynak(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    """Admin: kayit durumu, canli baglanti yuvasi ve aktarilabilir (hazir) Veri Girisi partileri."""
    partiler = db.scalars(select(IngestBatch).where(IngestBatch.status == "ready").order_by(IngestBatch.id.desc()).limit(20)).all()
    yuva = next((c for c in connections() if c["id"] == "oracle_reportdb"), {})
    return ok(
        {
            **servis.kaynak_bilgisi(db),
            "canli_baglanti": {"yuva": yuva.get("slot", "ORACLE_REPORTDB"), "yapilandirildi": bool(yuva.get("configured")), "acik": False},
            "partiler": [
                {"id": p.id, "kaynak": p.source_key, "etiket": p.label, "satir": p.row_count, "zaman": iso(p.received_at), "sutunlar": list(p.columns or [])}
                for p in partiler
            ],
        }
    )


@router.post("/ice-al/{parti_id:int}")
def ice_al_parti(parti_id: KimlikTipi, body: AktarGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    sonuc = ice_al.parti_aktar(db, parti_id, body.tur)
    db.commit()
    audit_log.remember(
        actor=admin.username,
        action="onedesk.ice_al",
        outcome="allow",
        module_key="onedesk",
        detail=f"parti={parti_id} eklenen={sonuc['eklenen']} guncellenen={sonuc['guncellenen']}",
    )
    return ok(sonuc)
