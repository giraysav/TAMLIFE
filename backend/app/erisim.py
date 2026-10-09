"""Modul erisim bagimliligi (ortak): rolun gorunumunde modul varsa gecer, yoksa 403. Yetki sunucuda zorlanir."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.authz import can_open
from app.catalog import get
from app.db import get_db
from app.deps import require_user
from app.rolgorunum import etkin
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
