"""Ortak FastAPI bagimliliklari: oturum ve yetki."""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.authz import is_admin
from app.dil import m
from app.session import Principal, current_user


def require_user(request: Request) -> Principal:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Oturum gerekli")
    return user


def require_admin(request: Request) -> Principal:
    user = require_user(request)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Yetki yok")
    return user


def require_veri_yazma(request: Request) -> Principal:
    """Veri ekleme, degistirme ve silme: yalniz admin (kullanici karari 2026-10-11). Kapsami degistirmek icin tek yer burasi."""
    user = require_user(request)
    if not is_admin(user):
        raise HTTPException(
            status_code=403,
            detail=m(
                "Veri ekleme, değiştirme ve silme yalnızca admin yetkisindedir.", "Adding, changing and deleting data is limited to admins."
            ),
        )
    return user
