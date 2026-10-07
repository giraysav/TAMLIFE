"""Panel kullanici kaydi (app_user): oturum sahibinin satiri ve panele giris yapmis kisilerin listesi."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppUser
from app.ortak import simdi
from app.session import Principal


def kullanici_kaydi(db: Session, user: Principal) -> AppUser:
    """Oturumdaki kisinin app_user satiri; yoksa olusturur (yerel/dev oturumu icin)."""
    satir = db.scalar(select(AppUser).where(AppUser.username == user.username))
    if satir is None:
        satir = AppUser(username=user.username, display_name=user.username, role=user.role, is_admin=user.is_admin)
        db.add(satir)
        db.flush()
    return satir


def giris_isle(db: Session, user: Principal) -> None:
    """Basarili girisi kaydeder: kisi yoksa eklenir, rol ve son giris zamani guncellenir (TAM Takvim listesi buradan beslenir)."""
    satir = kullanici_kaydi(db, user)
    satir.role, satir.is_admin, satir.last_login_at = user.role, user.is_admin, simdi()
    db.commit()


def giris_yapmislar(db: Session) -> list[AppUser]:
    """Panele en az bir kez giris yapmis, etkin kisiler (ada gore)."""
    return list(db.scalars(select(AppUser).where(AppUser.last_login_at.is_not(None), AppUser.active.is_(True)).order_by(AppUser.display_name, AppUser.username)))
