"""Modul erisim bagimliligi (ortak): rolun gorunumunde modul varsa gecer, yoksa 403. Yetki sunucuda zorlanir."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.authz import can_open, is_admin
from app.catalog import get
from app.db import get_db
from app.deps import require_user
from app.rolgorunum import UTILIZASYON_YETKISI, etkin
from app.session import Principal


@dataclass(frozen=True)
class Erisim:
    user: Principal
    izinli: frozenset[str] | None
    yetkiler: frozenset[str] = frozenset()  # eylem yetkileri (rolgorunum.YETKILER)

    def yetkili_mi(self, yetki: str) -> bool:
        return yetki in self.yetkiler


def modul_erisim(*anahtarlar: str) -> Callable[..., Erisim]:
    """Verilen modullerden en az biri acilabiliyorsa gecer (orn. TAM Takvim icin takvim ya da takvim_ozet)."""

    def bagimlilik(user: Principal = Depends(require_user), db: Session = Depends(get_db)) -> Erisim:
        gorunum = etkin(db, user)
        if not any(can_open(user, get(a), get, gorunum.izinli) for a in anahtarlar):
            raise HTTPException(status_code=403, detail="Yetki yok")
        return Erisim(user, gorunum.izinli, gorunum.yetkiler)

    return bagimlilik


def musteri_alani_erisim() -> Callable[..., Erisim]:
    """Musteri karti uclari: istegin alanindaki modul (musteri / toptan / baglantili; app.musteri_alani) acilabiliyorsa gecer."""
    from app import musteri_alani

    def bagimlilik(user: Principal = Depends(require_user), db: Session = Depends(get_db)) -> Erisim:
        gorunum = etkin(db, user)
        if not can_open(user, get(musteri_alani.secili()), get, gorunum.izinli):
            raise HTTPException(status_code=403, detail="Yetki yok")
        return Erisim(user, gorunum.izinli, gorunum.yetkiler)

    return bagimlilik


def utilizasyon_yetkisi(user: Principal = Depends(require_user), db: Session = Depends(get_db)) -> Principal:
    """TAM Utilizasyon uclari: admin ya da rolden / kisiden `utilizasyon.yonet` ek yetkisi alan kullanici. Sunucuda zorlanir (2026-11-11)."""
    if is_admin(user) or UTILIZASYON_YETKISI in etkin(db, user).yetkiler:
        return user
    raise HTTPException(status_code=403, detail="Yetki yok")
