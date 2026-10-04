"""Role gate for the catalog. admin, TeamMngr, TeamMember."""

from __future__ import annotations

from collections.abc import Callable

from app.catalog import Module
from app.session import Principal

ROLES = frozenset({"admin", "TeamMngr", "TeamMember"})


def can_open(
    user: Principal,
    module: Module,
    lookup: Callable[[str], Module],
    izinli: frozenset[str] | None = None,
) -> bool:
    """izinli: rolun gorunumunden gelen modul kimlikleri (None = kisit yok, admin)."""
    if user.role not in ROLES and not user.is_admin:
        return False
    if izinli is not None and not is_admin(user) and module.key not in izinli:
        return False
    if module.admin_only and not (user.is_admin or user.role == "admin"):
        return False
    if module.public:
        return True
    if user.is_admin or user.role == "admin":
        return True
    if module.permission:
        return can_open(user, lookup(module.permission), lookup, izinli)
    return user.role in {"TeamMngr", "TeamMember"}


def is_admin(user: Principal) -> bool:
    return bool(user.is_admin or user.role == "admin")
