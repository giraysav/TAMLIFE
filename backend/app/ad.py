"""AD/LDAP adapter. Checks production config presence. Does not bind.

No ldap library, no socket, no directory bind. LDAPS settings use the AD_*
names from the old service; there is no separate LDAP_* key.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from app.config import AD_LDAP_KEYS, AD_REQUIRED_KEYS, get_settings


@dataclass(frozen=True)
class DirectoryUser:
    username: str
    role: str
    is_admin: bool


class Directory:
    """Slot names are visible. authenticate never opens a socket."""

    def __init__(self) -> None:
        self.lookups = 0
        self.ldap_calls = 0

    def configured(self) -> bool:
        settings = get_settings()
        enabled = settings.ad_enabled.strip().lower() == "true"
        return bool(enabled and settings.present("AD_SERVER") and settings.present("AD_DOMAIN"))

    def slot(self) -> dict:
        settings = get_settings()
        flags = {key: settings.present(key) for key in AD_LDAP_KEYS}
        return {
            "mode": "presence",
            "bind": "disabled",
            "configured": self.configured(),
            "present": [key for key, filled in flags.items() if filled],
            "missing": [key for key in AD_REQUIRED_KEYS if not flags[key]],
            "keys": list(AD_LDAP_KEYS),
            "ldap_calls": self.ldap_calls,
        }

    def authenticate(self, username: str, password: str) -> DirectoryUser | None:
        """Panel-local check only. A filled AD slot still does not bind."""
        settings = get_settings()
        self.lookups += 1
        _ = self.configured()
        if settings.env not in {"dev", "test"}:
            return None
        expected_user = settings.local_user
        expected_password = settings.local_password
        if not expected_user or not expected_password:
            return None
        user_ok = hmac.compare_digest(username.encode(), expected_user.encode())
        pass_ok = hmac.compare_digest(password.encode(), expected_password.encode())
        if not (user_ok and pass_ok):
            return None
        role = settings.local_role or "TeamMember"
        return DirectoryUser(username=username, role=role, is_admin=role == "admin")


directory = Directory()
