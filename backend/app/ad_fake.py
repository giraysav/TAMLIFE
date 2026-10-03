"""Fake AD/LDAP adapter. No ldap library and no network bind."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings


@dataclass(frozen=True)
class DirectoryUser:
    username: str
    role: str
    is_admin: bool


class FakeDirectory:
    """Config slots are visible. authenticate never opens a socket."""

    def __init__(self) -> None:
        self.lookups = 0
        self.ldap_calls = 0

    def slot(self) -> dict:
        settings = get_settings()
        return {
            "mode": "fake",
            "bind": "disabled",
            "host": settings.ad_host,
            "port": settings.ad_port,
            "use_ssl": settings.ad_use_ssl,
            "base_dn": settings.ad_base_dn,
            "bind_user": settings.ad_bind_user,
            "bind_password_set": bool(settings.ad_bind_password),
            "ldap_calls": self.ldap_calls,
        }

    def authenticate(self, username: str, password: str) -> DirectoryUser | None:
        settings = get_settings()
        self.lookups += 1
        expected_user = settings.local_user
        expected_password = settings.local_password
        if not expected_user or not expected_password:
            return None
        if username != expected_user or password != expected_password:
            return None
        role = settings.local_role or "TeamMember"
        return DirectoryUser(username=username, role=role, is_admin=role == "admin")


directory = FakeDirectory()
