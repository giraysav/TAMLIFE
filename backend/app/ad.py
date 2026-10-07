"""AD/LDAP baglayicisi: yalniz yapilandirma doluluk denetimi ve panel-yerel giris. Dizine BAGLANMAZ (ldap kutuphanesi, soket, bind yok).

LDAPS ayarlari eski servisteki AD_* adlarini kullanir; ayri LDAP_* anahtari yoktur.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from app.config import get_settings


@dataclass(frozen=True)
class DirectoryUser:
    username: str
    role: str
    is_admin: bool


class Directory:
    def configured(self) -> bool:
        """AD_ENABLED=true ve AD_SERVER + AD_DOMAIN dolu mu (deger okunmaz, yalniz doluluk)."""
        settings = get_settings()
        enabled = settings.ad_enabled.strip().lower() == "true"
        return bool(enabled and settings.present("AD_SERVER") and settings.present("AD_DOMAIN"))

    def authenticate(self, username: str, password: str) -> DirectoryUser | None:
        """Yalniz dev/test'te panel-yerel kullanici (TAMLIFE_LOCAL_*). Dolu AD yuvasi bile bind yapmaz."""
        settings = get_settings()
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
