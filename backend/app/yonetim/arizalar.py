"""Ariza yonetimi (admin): listeleme, durum (acik -> incelemede -> kapali), ozet. Kayit yazma cekirdekte: app.ariza."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ariza import KODLAR, SEVIYELER, temizle
from app.ortak import UygulamaHatasi, iso, sayfa_bilgisi, simdi
from app.yonetim.models import FaultEvent

DURUMLAR = ("open", "ack", "closed")


def _satir(f: FaultEvent) -> dict[str, object]:
    return {
        "id": f.id,
        "kayit_no": f.record_no,
        "kod": f.code,
        "seviye": f.severity,
        "kaynak": f.source,
        "mesaj": f.message,
        "istisna": f.exc_type,
        "kullanici": f.actor,
        "zaman": iso(f.at),
        "durum": f.status,
        "not": f.note,
        "kapatan": f.resolved_by,
        "kapanis": iso(f.resolved_at),
        "cozum_adimi": KODLAR.get(f.code, KODLAR["TL-SRV-01"])[1],
    }


def liste(
    db: Session,
    *,
    durum: str = "",
    seviye: str = "",
    kod: str = "",
    q: str = "",
    sayfa: int = 1,
    adet: int = 25,
) -> dict[str, object]:
    sorgu = select(FaultEvent)
    if durum in DURUMLAR:
        sorgu = sorgu.where(FaultEvent.status == durum)
    if seviye in SEVIYELER:
        sorgu = sorgu.where(FaultEvent.severity == seviye)
    if kod:
        sorgu = sorgu.where(FaultEvent.code == kod)
    if q.strip():
        aranan = q.strip().lower()
        sorgu = sorgu.where(
            func.lower(FaultEvent.message).contains(aranan, autoescape=True)
            | func.lower(FaultEvent.source).contains(aranan, autoescape=True)
            | FaultEvent.record_no.startswith(aranan, autoescape=True)
        )
    toplam = db.scalar(select(func.count()).select_from(sorgu.subquery())) or 0
    sayfa, atla, adet = sayfa_bilgisi(sayfa, adet, toplam)
    satirlar = db.scalars(sorgu.order_by(FaultEvent.id.desc()).offset(atla).limit(adet)).all()
    return {"toplam": toplam, "sayfa": sayfa, "adet": adet, "satirlar": [_satir(f) for f in satirlar]}


def durum_degistir(db: Session, ariza_id: int, durum: str, not_: str, kullanici: str) -> dict[str, object]:
    if durum not in DURUMLAR:
        raise UygulamaHatasi(400, "Geçersiz durum.")
    kayit = db.get(FaultEvent, ariza_id)
    if kayit is None:
        raise UygulamaHatasi(404, "Arıza kaydı yok.")
    kayit.status = durum
    kayit.note = temizle(not_, 500) if not_.strip() else kayit.note
    if durum == "closed":
        kayit.resolved_by, kayit.resolved_at = temizle(kullanici, 120), simdi()
    else:
        kayit.resolved_by, kayit.resolved_at = "", None
    db.flush()
    return _satir(kayit)


def ozet(db: Session) -> dict[str, object]:
    """Gosterge ve saglik icin: acik kayit sayisi, son 24 saat ve son kayit zamani."""
    esik = simdi() - timedelta(hours=24)
    acik = db.scalar(select(func.count()).select_from(FaultEvent).where(FaultEvent.status != "closed")) or 0
    son24 = db.scalar(select(func.count()).select_from(FaultEvent).where(FaultEvent.at >= esik)) or 0
    son24_hata = db.scalar(select(func.count()).select_from(FaultEvent).where(FaultEvent.at >= esik, FaultEvent.severity == "error")) or 0
    son = db.scalar(select(func.max(FaultEvent.at)))
    return {"acik": acik, "son_24s": son24, "son_24s_hata": son24_hata, "son_zaman": iso(son)}


BILDIRIM_KODLARI = ("TL-RAP-01",)  # admin'in ust cubukta gordugu ariza kodlari (2026-10-26: aylik rapor gonderim hatasi)


def bildirimler(db: Session, adet: int = 5) -> dict[str, object]:
    """Admin bildirimi: kapanmamis (open / ack) bildirim kodlu kayitlar; sayi + son kayitlar. Kayit kapatilinca bildirim duser."""
    kosul = (FaultEvent.code.in_(BILDIRIM_KODLARI), FaultEvent.status != "closed")
    toplam = db.scalar(select(func.count()).select_from(FaultEvent).where(*kosul)) or 0
    son = db.scalars(select(FaultEvent).where(*kosul).order_by(FaultEvent.id.desc()).limit(adet)).all() if toplam else []
    return {"toplam": toplam, "son": [_satir(f) for f in son]}


def kodlar() -> list[dict[str, str]]:
    return [{"kod": k, "aciklama": a, "cozum": c} for k, (a, c) in KODLAR.items()]
