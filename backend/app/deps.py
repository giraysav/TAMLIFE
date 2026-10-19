"""Ortak FastAPI bagimliliklari: oturum ve yetki."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.authz import is_admin
from app.config import get_settings
from app.db import get_db
from app.dil import m
from app.models import AppUser
from app.session import Principal, current_user, kullanici_oturumlarini_kapat


def _hesap_gecerli(db: Session, user: Principal) -> bool:
    """Oturum bellekte; hesap baska surecte (python -m app.hesap) pasiflesir, silinir ya da rolu degisirse oturum burada duser.
    Veritabani okunamazsa oturum acik kalir (giris ve /me ile ayni kural)."""
    try:
        satir = db.execute(select(AppUser.active, AppUser.role).where(AppUser.username == user.username)).first()
    except SQLAlchemyError:
        db.rollback()
        return True
    if satir is None:
        ayar = get_settings()
        return ayar.env in {"dev", "test"} and user.username == ayar.local_user  # satirsiz yalniz dev yerel hesap (TAMLIFE_LOCAL_*)
    return satir.active is not False and satir.role == user.role


def require_user(request: Request, db: Session = Depends(get_db)) -> Principal:
    user = current_user(request)
    if user is not None and not _hesap_gecerli(db, user):
        kullanici_oturumlarini_kapat(user.username)
        user = None
    if user is None:
        raise HTTPException(status_code=401, detail="Oturum gerekli")
    return user


def require_admin(user: Principal = Depends(require_user)) -> Principal:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Yetki yok")
    return user


def require_veri_yazma(user: Principal = Depends(require_user)) -> Principal:
    """Yalniz admin: toplu / yonetim yazmalari (Yonetim musteri toplu ekle-sil, Gelir Uretim Excel ve sahip atama).
    2026-10-19 kullanici karari: musteri, gelir (SMS/APN) ve proje kayitlarinda herkes KENDI verisini ekler, duzenler ve siler
    (admin hepsini, TeamMngr ekibinin = gordugu tum personelin, TeamMember yalniz kendisinin); o uclarda bu kapi YOK, sahiplik
    servislerde (musteri_getir / silinebilir_mi, gelir _kayit, proje _getir)."""
    if not is_admin(user):
        raise HTTPException(
            status_code=403,
            detail=m(
                "Veri ekleme, değiştirme ve silme yalnızca admin yetkisindedir.", "Adding, changing and deleting data is limited to admins."
            ),
        )
    return user
