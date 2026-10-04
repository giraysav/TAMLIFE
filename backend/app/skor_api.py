"""Final skor HTTP katmani (/api/v1/skor). Is kurali skor_servis.py ve skor.py'dedir."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import skor_servis as servis
from app.audit import audit_log
from app.deps import get_db, require_admin, require_user
from app.session import Principal

router = APIRouter(prefix="/api/v1/skor", tags=["skor"])


@contextmanager
def _hata() -> Iterator[None]:
    try:
        yield
    except servis.SkorHata as exc:
        raise HTTPException(status_code=exc.kod, detail=exc.mesaj) from exc


def _final_yetki(user: Principal = Depends(require_user)) -> Principal:
    if not servis.final_skor_yetkisi(user):
        raise HTTPException(status_code=403, detail="Yetki yok")
    return user


def _ok(data: object) -> dict:
    return {"status": "success", "data": data}


def _denetim(user: Principal, islem: str, detay: str = "") -> None:
    audit_log.remember(actor=user.username, action=islem, outcome="allow", module_key="utilizasyon", detail=detay)


class KriterGovde(BaseModel):
    criteria: list[dict] = Field(max_length=servis.EN_FAZLA_KRITER)


class TopluOnizleme(BaseModel):
    tam_id: int | None = None


class TopluUygula(BaseModel):
    customer_ids: list[int] = Field(min_length=1, max_length=servis.EN_FAZLA_TOPLU)


class MusteriSkoru(BaseModel):
    tam_id: int
    score: float | int | str
    detay: list[dict] = Field(default_factory=list, max_length=servis.EN_FAZLA_KRITER)


class TalepGovde(BaseModel):
    customer_id: int


class KararGovde(BaseModel):
    action: str


class PuanlamaDisi(BaseModel):
    disi: list[int] = Field(max_length=2000)


class IstirakGovde(BaseModel):
    dahil: bool


@router.get("/kriterler/{scope}")
def kriterleri_oku(scope: str, user: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    with _hata():
        surum, satirlar = servis.kriterler_oku(db, scope)
    return _ok({"scope": scope, "version": surum, "criteria": satirlar})


@router.put("/kriterler/{scope}")
def kriterleri_kaydet(scope: str, body: KriterGovde, user: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    with _hata():
        sonuc = servis.kriterler_kaydet(db, scope, body.criteria, user.username)
        db.commit()
    _denetim(user, "skor.kriter_kaydet", f"scope={scope} surum={sonuc['version']}")
    return _ok(sonuc)


@router.post("/toplu/onizleme")
def toplu_onizleme(body: TopluOnizleme, user: Principal = Depends(_final_yetki), db: Session = Depends(get_db)) -> dict:
    with _hata():
        kriterler, sonuc = servis.hesapla(db, servis.cati_musteriler(db, body.tam_id))
    return _ok(
        {
            "kriterler": [{"baslik": k.get("title"), "tur": k.get("type") or "manual", "agirlik": k.get("weight")} for k in kriterler],
            "musteriler": sonuc,
            "ozet": {"toplam": len(sonuc), "hazir": sum(1 for s in sonuc if s["tamam"])},
        }
    )


@router.post("/toplu/uygula")
def toplu_uygula(body: TopluUygula, user: Principal = Depends(_final_yetki), db: Session = Depends(get_db)) -> dict:
    with _hata():
        sonuc = servis.toplu_uygula(db, body.customer_ids, user.username)
        db.commit()
    _denetim(user, "skor.toplu_uygula", f"uygulanan={len(sonuc['uygulanan'])} atlanan={len(sonuc['atlanan'])}")
    return _ok(sonuc)


@router.put("/musteri/{musteri_id}")
def musteri_skoru(musteri_id: int, body: MusteriSkoru, user: Principal = Depends(_final_yetki), db: Session = Depends(get_db)) -> dict:
    with _hata():
        servis.musteri_skoru_ata(db, musteri_id, body.tam_id, body.score, body.detay, user.username)
        db.commit()
    _denetim(user, "skor.musteri", f"musteri={musteri_id}")
    return _ok({"customer_id": musteri_id})


@router.post("/talepler")
def talep_ac(body: TalepGovde, user: Principal = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    with _hata():
        talep_id = servis.talep_olustur(db, body.customer_id, user)
        db.commit()
    _denetim(user, "skor.talep_ac", f"musteri={body.customer_id}")
    return _ok({"id": talep_id})


@router.get("/talepler")
def talepleri_listele(user: Principal = Depends(_final_yetki), db: Session = Depends(get_db)) -> dict:
    satirlar = servis.talepler(db)
    return _ok({"count": len(satirlar), "requests": satirlar})


@router.post("/talepler/{talep_id}/karar")
def talep_karar(talep_id: int, body: KararGovde, user: Principal = Depends(_final_yetki), db: Session = Depends(get_db)) -> dict:
    with _hata():
        servis.talep_karar(db, talep_id, body.action, user)
        db.commit()
    _denetim(user, "skor.talep_karar", f"talep={talep_id} islem={body.action}")
    return _ok({"id": talep_id})


@router.put("/puanlama-disi")
def puanlama_disi(body: PuanlamaDisi, user: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    with _hata():
        kimlikler = servis.puanlama_disi_ayarla(db, body.disi, user.username)
        db.commit()
    _denetim(user, "skor.puanlama_disi", f"adet={len(kimlikler)}")
    return _ok({"disi": kimlikler})


@router.put("/istirak/{musteri_id}/final-dahil")
def istirak_final_dahil(musteri_id: int, body: IstirakGovde, user: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    with _hata():
        dahil = servis.final_dahil_ayarla(db, musteri_id, body.dahil)
        db.commit()
    _denetim(user, "skor.istirak_dahil", f"musteri={musteri_id} dahil={dahil}")
    return _ok({"dahil": dahil})
