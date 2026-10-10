"""Panel kullanici kaydi (app_user): oturum sahibinin satiri, AD ile ilk giriste acilan kisi, yerel acil hesap parolasi, giris yapmislar."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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


def bul(db: Session, kisa_ad: str) -> AppUser | None:
    """Kullanici adi buyuk/kucuk harfe duyarsiz."""
    return db.scalar(select(AppUser).where(func.lower(AppUser.username) == kisa_ad.strip().lower()))


def tam_ad_uret(kisa_ad: str) -> str:
    """'giray.sav' -> 'Giray Sav' (Turkce i/I)."""
    parcalar = [p for p in kisa_ad.replace("_", ".").split(".") if p]
    return " ".join({"i": "İ", "ı": "I"}.get(p[0], p[0].upper()) + p[1:] for p in parcalar) or kisa_ad


def ad_kullanicisi_ac(db: Session, kisa_ad: str, alan: str) -> AppUser:
    """AD'de DOGRULANMIS, panelde kaydi olmayan kisi: TeamMember, yonetici degil, yalniz AD ile girer. Ayni anda iki giris olursa mevcut satir doner."""
    satir = AppUser(username=kisa_ad.lower(), display_name=tam_ad_uret(kisa_ad), role="TeamMember", is_admin=False, active=True, is_ad_user=True, ad_domain=alan.lower())
    db.add(satir)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        mevcut = bul(db, kisa_ad)
        if mevcut is None:
            raise
        return mevcut
    return satir


# --- yerel acil hesap parolasi (scrypt; ayar degeri koda gomulu degil) ------------------------------------------------
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}
EN_KISA_PAROLA = 12


def parola_ozeti(parola: str) -> str:
    if len(parola) < EN_KISA_PAROLA:
        raise ValueError(f"Parola en az {EN_KISA_PAROLA} karakter olmali.")
    tuz = secrets.token_bytes(16)
    ozet = hashlib.scrypt(parola.encode(), salt=tuz, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${tuz.hex()}${ozet.hex()}"


def parola_dogru(parola: str, kayit: str | None) -> bool:
    try:
        tur, n, r, p, tuz, ozet = (kayit or "").split("$")
        if tur != "scrypt":
            return False
        aday = hashlib.scrypt(parola.encode(), salt=bytes.fromhex(tuz), dklen=32, n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(aday.hex(), ozet)
