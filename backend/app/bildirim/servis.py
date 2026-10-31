"""Kisiye ozel panel bildirimi (2026-10-31 kullanici: "talepte durum degisince talep sahibine bildirim gitsin").

Panel e-posta gondermez (SMTP 2026-10-31 kaldirildi); bildirim ust cubuk zilinde gorunur. Ureten modul `ekle` ile yazar
(commit cagirana aittir), kisi yalniz KENDI bildirimlerini gorur ve okundu isaretler.
"""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.kullanicilar import kullanici_kaydi
from app.models import UserNotification
from app.ortak import iso, simdi
from app.session import Principal

LISTE_SINIRI = 20


def ekle(db: Session, kisi_id: int, tur: str, mesaj: str, adres: str = "", ref_id: int | None = None) -> None:
    db.add(UserNotification(user_id=kisi_id, kind=tur, ref_id=ref_id, message=mesaj[:400], link=adres[:200], created_at=simdi()))


def liste(db: Session, user: Principal) -> dict:
    """Son bildirimler (yeniden eskiye) ve okunmamis sayisi."""
    kisi = kullanici_kaydi(db, user)
    okunmamis = db.scalar(select(func.count()).select_from(UserNotification).where(UserNotification.user_id == kisi.id, UserNotification.read_at.is_(None)))
    satirlar = db.scalars(
        select(UserNotification).where(UserNotification.user_id == kisi.id).order_by(UserNotification.created_at.desc(), UserNotification.id.desc()).limit(LISTE_SINIRI)
    )
    return {
        "okunmamis": okunmamis or 0,
        "son": [{"id": b.id, "tur": b.kind, "mesaj": b.message, "adres": b.link, "zaman": iso(b.created_at), "okundu": b.read_at is not None} for b in satirlar],
    }


def okundu(db: Session, user: Principal, kimlikler: list[int] | None = None) -> int:
    """Kisinin okunmamis bildirimlerini (verildiyse yalniz o kimlikleri) okundu yapar; donus: isaretlenen sayisi."""
    kisi = kullanici_kaydi(db, user)
    sorgu = update(UserNotification).where(UserNotification.user_id == kisi.id, UserNotification.read_at.is_(None))
    if kimlikler is not None:
        sorgu = sorgu.where(UserNotification.id.in_(kimlikler))
    return db.execute(sorgu.values(read_at=simdi())).rowcount or 0
