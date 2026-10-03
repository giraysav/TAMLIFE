"""Role gate for the catalog. admin, TeamMngr, TeamMember."""

from __future__ import annotations

from collections.abc import Callable

from app.catalog import Module
from app.session import Principal

ROLES = frozenset({"admin", "TeamMngr", "TeamMember"})


def can_open(user: Principal, module: Module, lookup: Callable[[str], Module]) -> bool:
    if user.role not in ROLES and not user.is_admin:
        return False
    if module.admin_only and not (user.is_admin or user.role == "admin"):
        return False
    if module.public:
        return True
    if user.is_admin or user.role == "admin":
        return True
    if module.permission:
        return can_open(user, lookup(module.permission), lookup)
    return user.role in {"TeamMngr", "TeamMember"}
