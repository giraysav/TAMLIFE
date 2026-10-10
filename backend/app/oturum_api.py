"""Oturum uclari: giris, cikis ve /session/me (menu, giris sayfasi, izinler)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import ad, kullanicilar
from app.ad import directory
from app.audit import SecretAuditError, audit_log
from app.config import get_settings
from app.db import get_db
from app.deps import require_user
from app.kullanicilar import giris_isle
from app.models import AppUser
from app.navigation import navigation_for
from app.ortak import ok
from app.rolgorunum import etkin
from app.security import client_ip, limiter
from app.session import Principal, current_user, login, logout

router = APIRouter(prefix="/api/v1/session", tags=["oturum"])


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def _kimlik_dogrula(db: Session, girdi: str, parola: str) -> tuple[Principal | None, str]:
    """Eski servis (auth_bp) sirasi: pasif -> AD kullanicisi AD ile -> yerel acil hesap parolasi -> dev yerel kullanici -> kaydi
    olmayan kisi AD ile (dogrulanirsa TeamMember acilir). Rol her zaman panel DB'sinden; AD rol vermez. (kisi, sebep kodu)"""
    kisa, alan = ad.domain_ayristir(girdi)
    try:
        satir = kullanicilar.bul(db, kisa) if kisa else None
    except SQLAlchemyError:
        db.rollback()
        satir = None  # DB yokken yalniz dev yerel giris acik; AD ile hesap acma asagida DB ister (kapali kalir)
    if satir is not None and not satir.active:
        return None, "kullanici_pasif"
    if satir is not None and satir.is_ad_user:
        tamam, sebep = ad.dogrula(girdi, parola)
        return (_kisi(satir) if tamam else None), sebep
    if satir is not None and satir.password_hash:
        tamam = kullanicilar.parola_dogru(parola, satir.password_hash)
        return (_kisi(satir) if tamam else None), "yerel_parola" if tamam else "yerel_parola_hatali"
    yerel = directory.yerel(girdi, parola)
    if yerel is not None:
        return Principal(yerel.username, yerel.role, yerel.is_admin), "dev_yerel"
    if satir is not None or not ad.etkin():
        return None, "kullanici_yok" if satir is None else "kimlik_yok"
    tamam, sebep = ad.dogrula(girdi, parola)
    if not tamam:
        return None, sebep
    if get_settings().ad_otomatik_ac.strip().lower() != "true":
        return None, "ad_onayladi_otomatik_kapali"
    try:
        return _kisi(kullanicilar.ad_kullanicisi_ac(db, kisa, alan)), "ad_kullanici_acildi"
    except SQLAlchemyError:
        db.rollback()
        return None, "ad_onayladi_kayit_acilamadi"


def _kisi(satir: AppUser) -> Principal:
    return Principal(satir.username, satir.role, bool(satir.is_admin or satir.role == "admin"))


@router.post("/login", response_model=None)
def open_session(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)) -> Response | dict:
    ip = client_ip(request)
    name = body.username.strip()
    wait = limiter.retry_after(ip, name)
    if wait:
        audit_log.remember(actor=name, action="login", outcome="deny", detail="locked")
        return JSONResponse({"detail": "Cok fazla deneme"}, status_code=429, headers={"Retry-After": str(wait)})
    kisi, sebep = _kimlik_dogrula(db, name, body.password)
    if kisi is None:
        limiter.failed(ip, name)
        audit_log.remember(actor=name, action="login", outcome="deny", detail=sebep)
        raise HTTPException(status_code=401, detail="Giris reddedildi")  # sebep kullaniciya donmez (hesap varligi sizmasin)
    limiter.succeeded(ip, name)
    login(request, response, kisi)
    try:
        giris_isle(db, kisi)  # kisi listesi ve son giris; DB sorunu girisi engellemez
    except SQLAlchemyError:
        db.rollback()
    try:
        audit_log.remember(actor=kisi.username, action="login", outcome="allow", detail=sebep)
    except SecretAuditError:
        pass
    return ok({"username": kisi.username, "role": kisi.role})


@router.post("/logout")
def close_session(request: Request, response: Response) -> dict:
    user = current_user(request)
    logout(request, response)
    if user is not None:
        audit_log.remember(actor=user.username, action="logout", outcome="allow")
    return ok({})


@router.get("/me")
def whoami(user: Principal = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    gorunum = etkin(db, user)
    nav = navigation_for(user, gorunum.izinli)
    return ok(
        {
            "username": user.username,
            "role": user.role,
            "is_admin": user.is_admin,
            "idle_timeout_minutes": get_settings().session_idle_minutes,
            "navigation": nav,
            "landing": gorunum.landing,
            "permissions": {"modules": [item["id"] for item in nav], "actions": sorted(gorunum.yetkiler)},
        }
    )
