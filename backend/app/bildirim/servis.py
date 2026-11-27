# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Kisiye ozel panel bildirimi (2026-10-31 kullanici: "talepte durum degisince talep sahibine bildirim gitsin").

Panel e-posta gondermez (SMTP 2026-10-31 kaldirildi); bildirim ust cubuk zilinde gorunur. Ureten modul `ekle` ile yazar
(commit cagirana aittir), kisi yalniz KENDI bildirimlerini gorur ve okundu isaretler.
"""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.dil import m
from app.kullanicilar import kullanici_kaydi
from app.models import UserNotification
from app.ortak import UygulamaHatasi, iso, simdi
from app.session import Principal

LISTE_SINIRI = 20
# Yanitlanabilen bildirim turleri ve kararlari (2026-11-27: Erken Uyari -> "ilgilendim / gerekmedi"; uyari dongusu olculur)
YANITLANIR = frozenset({"erken_uyari"})
KARARLAR = ("ilgilendim", "gerekmedi")


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
        "son": [
            {
                "id": b.id, "tur": b.kind, "mesaj": b.message, "adres": b.link, "zaman": iso(b.created_at), "okundu": b.read_at is not None,
                "yanitlanir": b.kind in YANITLANIR, "yanit": b.response or "",
            }
            for b in satirlar
        ],  # fmt: skip
    }


def okundu(db: Session, user: Principal, kimlikler: list[int] | None = None) -> int:
    """Kisinin okunmamis bildirimlerini (verildiyse yalniz o kimlikleri) okundu yapar; donus: isaretlenen sayisi."""
    kisi = kullanici_kaydi(db, user)
    sorgu = update(UserNotification).where(UserNotification.user_id == kisi.id, UserNotification.read_at.is_(None))
    if kimlikler is not None:
        sorgu = sorgu.where(UserNotification.id.in_(kimlikler))
    return db.execute(sorgu.values(read_at=simdi())).rowcount or 0


def yanitla(db: Session, user: Principal, kimlik: int, karar: str) -> dict:
    """Kisinin KENDI yanitlanabilir bildirimine karar yazar (bir kez; degistirmek yeniden yazar) ve okundu yapar.
    Baskasinin bildirimi ya da yanitlanamayan tur 404 (varligi sizdirilmaz)."""
    if karar not in KARARLAR:
        raise UygulamaHatasi(422, m("Geçersiz yanıt.", "Invalid response."))
    kisi = kullanici_kaydi(db, user)
    b = db.get(UserNotification, kimlik)
    if b is None or b.user_id != kisi.id or b.kind not in YANITLANIR:
        raise UygulamaHatasi(404, m("Bildirim bulunamadı.", "Notification not found."))
    an = simdi()
    b.response, b.responded_at = karar, an
    b.read_at = b.read_at or an
    return {"id": b.id, "yanit": karar, "tur": b.kind, "ref_id": b.ref_id}
