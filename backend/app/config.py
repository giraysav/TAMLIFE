"""Runtime settings. Production key names, empty defaults, no stored secret."""

from __future__ import annotations

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.external import source_key_names

AD_LDAP_KEYS: tuple[str, ...] = (
    "AD_ENABLED",
    "AD_SERVER",
    "AD_DOMAIN",
    "AD_USE_SSL",
    "AD_CA_CERT_FILE",
    "AD_IZINLI_ALANLAR",
    "AD_ALAN_KONTROLU",
    "AD_KIMLIK_KONTROLU",
    "AD_IZINLI_GRUPLAR",
    "AD_ARAMA_KOKU",
    "AD_OTOMATIK_AC",
)


def _slot(alias: str):
    secret = alias.endswith(("PASSWORD", "API_KEY"))
    return Field(default="", validation_alias=alias, repr=not secret)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TAMLIFE_",
        env_file=None,
        extra="ignore",
    )

    env: str = "dev"
    database_url: str = "postgresql+psycopg://localhost:5432/tamlife"
    sqlite_izin: bool = False  # dev/test disinda SQLite icin acik onay (PostgreSQL gelene kadar)
    kullanici_db_dizini: str = ""  # kullanici basina SQLite dosyalari; bos = panel DB'sinin yaninda kullanicilar/

    cookie_name: str = "tamlife_session"
    cookie_secure: bool | None = None  # bos: dev disinda otomatik true
    session_idle_minutes: int = 30
    session_max_hours: int = 12
    login_max_attempts: int = 5
    login_window_seconds: int = 300
    login_lockout_seconds: int = 300
    allowed_origins: str = ""  # virgulle ayrilmis ek Origin listesi
    allowed_hosts: str = "127.0.0.1,localhost,testserver"
    trusted_proxies: str = ""  # virgulle ayrilmis proxy IP'leri; X-Forwarded-For yalniz bunlardan kabul

    base_path: str = "/"  # cerez yolu; arayuz bir alt yolda sunulacaksa (orn. "/panel") oraya kisitlanir
    static_dir: str = ""  # derlenmis arayuz (ekran-react/dist); bos = yok, yalniz API

    # Yonetim: dosya gunlugu ve yedek klasorleri. Bos = backend/var/logs ve veritabani klasorunun yanindaki yedek/.
    # Yedek, veri ile AYNI diskte durmasin diye (tek disk ikisini birlikte kaybeder) uretimde ayri bir yola ayarlanmali.
    log_dir: str = ""
    backup_dir: str = ""
    backup_keep: int = 30
    # Tampon (Veri Girisi) sinirlari.
    ingest_max_rows: int = 300_000
    ingest_max_mb: int = 20
    ingest_keep_batches: int = 3  # kaynak basina saklanan hazir parti

    # Panel session only. Not a directory bind.
    local_user: str = ""
    local_password: str = Field(default="", repr=False)
    local_role: str = "TeamMember"

    ad_enabled: str = _slot("AD_ENABLED")  # diger AD/Oracle anahtarlari yalniz doluluk icin okunur: present()

    @property
    def cookie_secure_effective(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.env not in {"dev", "test"}

    @property
    def allowed_origins_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def trusted_proxies_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_proxies.split(",") if item.strip()]

    @property
    def cookie_path(self) -> str:
        yol = "/" + self.base_path.strip().strip("/")
        return yol if yol != "/" else "/"

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]

    def present(self, key: str) -> bool:
        allowed = set(AD_LDAP_KEYS) | set(source_key_names())
        if key not in allowed:
            raise KeyError(key)
        return bool(os.environ.get(key, "").strip())


def get_settings() -> Settings:
    return Settings()

