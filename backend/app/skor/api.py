"""Final skor HTTP katmani (/api/v1/skor). Is kurali skor_servis.py ve skor.py'dedir."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit_log
from app.db import get_db
from app.deps import require_admin, require_user
from app.ortak import KimlikTipi, ok
from app.session import Principal
from app.skor import servis

router = APIRouter(prefix="/api/v1/skor", tags=["skor"])


def _final_yetki(user: Principal = Depends(require_user)) -> Principal:
    if not servis.final_skor_yetkisi(user):
        raise HTTPException(status_code=403, detail="Yetki yok")
    return user



def _denetim(user: Principal, islem: str, detay: str = "") -> None:
    audit_log.remember(actor=user.username, action=islem, outcome="allow", module_key="utilizasyon", detail=detay)


class KriterGovde(BaseModel):
    criteria: list[dict] = Field(max_length=servis.EN_FAZLA_KRITER)


class TopluOnizleme(BaseModel):
    tam_id: KimlikTipi | None = None


class TopluUygula(BaseModel):
    customer_ids: list[KimlikTipi] = Field(min_length=1, max_length=servis.EN_FAZLA_TOPLU)


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


@router.get("/kriterler/{scope}")
def kriterleri_oku(scope: str, user: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    surum, satirlar = servis.kriterler_oku(db, scope)
    return ok({"scope": scope, "version": surum, "criteria": satirlar})


@router.put("/kriterler/{scope}")
def kriterleri_kaydet(scope: str, body: KriterGovde, user: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    sonuc = servis.kriterler_kaydet(db, scope, body.criteria, user.username)
    db.commit()
    _denetim(user, "skor.kriter_kaydet", f"scope={scope} surum={sonuc['version']}")
    return ok(sonuc)


@router.post("/toplu/onizleme")
def toplu_onizleme(body: TopluOnizleme, user: Principal = Depends(_final_yetki), db: Session = Depends(get_db)) -> dict:
    kriterler, sonuc = servis.hesapla(db, servis.cati_musteriler(db, body.tam_id))
    return ok(
        {
            "kriterler": [{"baslik": k.get("title"), "tur": k.get("type") or "manual", "agirlik": k.get("weight")} for k in kriterler],
            "musteriler": sonuc,
            "ozet": {"toplam": len(sonuc), "hazir": sum(1 for s in sonuc if s["tamam"])},
        }
    )


@router.post("/toplu/uygula")
def toplu_uygula(body: TopluUygula, user: Principal = Depends(_final_yetki), db: Session = Depends(get_db)) -> dict:
    sonuc = servis.toplu_uygula(db, body.customer_ids, user.username)
    db.commit()
    _denetim(user, "skor.toplu_uygula", f"uygulanan={len(sonuc['uygulanan'])} atlanan={len(sonuc['atlanan'])}")
    return ok(sonuc)


@router.put("/musteri/{musteri_id}")
def musteri_skoru(musteri_id: KimlikTipi, body: MusteriSkoru, user: Principal = Depends(_final_yetki), db: Session = Depends(get_db)) -> dict:
    servis.musteri_skoru_ata(db, musteri_id, body.tam_id, body.score, body.detay, user.username)
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
def talepleri_listele(user: Principal = Depends(_final_yetki), db: Session = Depends(get_db)) -> dict:
    satirlar = servis.talepler(db)
    return ok({"count": len(satirlar), "requests": satirlar})


@router.post("/talepler/{talep_id}/karar")
def talep_karar(talep_id: KimlikTipi, body: KararGovde, user: Principal = Depends(_final_yetki), db: Session = Depends(get_db)) -> dict:
    servis.talep_karar(db, talep_id, body.action, user)
    db.commit()
    _denetim(user, "skor.talep_karar", f"talep={talep_id} islem={body.action}")
    return ok({"id": talep_id})


@router.put("/puanlama-disi")
def puanlama_disi(body: PuanlamaDisi, user: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    kimlikler = servis.puanlama_disi_ayarla(db, body.disi, user.username)
    db.commit()
    _denetim(user, "skor.puanlama_disi", f"adet={len(kimlikler)}")
    return ok({"disi": kimlikler})


@router.put("/istirak/{musteri_id}/final-dahil")
def istirak_final_dahil(musteri_id: KimlikTipi, body: IstirakGovde, user: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    dahil = servis.final_dahil_ayarla(db, musteri_id, body.dahil)
    db.commit()
    _denetim(user, "skor.istirak_dahil", f"musteri={musteri_id} dahil={dahil}")
    return ok({"dahil": dahil})
