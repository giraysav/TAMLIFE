"""Uc rol: admin, TeamMngr, TeamMember. Katalog import etmez."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

YONETICI_ROLLERI = ("admin", "TeamMngr")


def erisebilir(user: Any, modul: Any, lookup: Callable[[str], Any] | None = None) -> bool:
    if user is None or not getattr(user, "is_active", False):
        return False
    yetki = getattr(modul, "yetki", None)
    if yetki and lookup is not None:
        return erisebilir(user, lookup(yetki), lookup)
    if getattr(modul, "herkese_acik", False) or getattr(user, "is_admin", False) or user.role == "admin":
        return True
    if getattr(modul, "yalniz_admin", False):
        return False
    if user.role == "TeamMngr":
        return True
    if getattr(modul, "yalniz_yonetici", False):
        return False
    perms = getattr(user, "allowed_modules", None) or {}
    key = modul.anahtar
    modules = perms.get("modules") or {}
    cards = perms.get("dashboard_cards") or {}
    return bool(modules.get(key) or cards.get(key))
