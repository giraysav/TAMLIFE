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

AD_REQUIRED_KEYS: tuple[str, ...] = ("AD_ENABLED", "AD_SERVER", "AD_DOMAIN")


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
    sqlite_izin: bool = False  # dev/test disinda SQLite icin acik onay; yalniz /admin/dev on yayin asamasi (PostgreSQL gelene kadar)

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

    # Uretim paneli (Flask) arkasinda /admin/dev altinda calisma. Bos = kendi basina (taban yol "/").
    base_path: str = "/"  # cerez yolu; ornek "/admin/dev"
    sso_secret: str = Field(default="", repr=False)  # Flask vekili ile paylasilan sir (>=32 karakter); bos = SSO kapali
    static_dir: str = ""  # derlenmis arayuz (ekran-react/dist); bos = yok, yalniz API

    # Panel session only. Not a directory bind.
    local_user: str = ""
    local_password: str = Field(default="", repr=False)
    local_role: str = "TeamMember"

    ad_enabled: str = _slot("AD_ENABLED")
    ad_server: str = _slot("AD_SERVER")
    ad_domain: str = _slot("AD_DOMAIN")
    ad_use_ssl: str = _slot("AD_USE_SSL")
    ad_ca_cert_file: str = _slot("AD_CA_CERT_FILE")
    ad_izinli_alanlar: str = _slot("AD_IZINLI_ALANLAR")
    ad_alan_kontrolu: str = _slot("AD_ALAN_KONTROLU")
    ad_kimlik_kontrolu: str = _slot("AD_KIMLIK_KONTROLU")
    ad_izinli_gruplar: str = _slot("AD_IZINLI_GRUPLAR")
    ad_arama_koku: str = _slot("AD_ARAMA_KOKU")
    ad_otomatik_ac: str = _slot("AD_OTOMATIK_AC")

    oracle_client_dir: str = _slot("ORACLE_CLIENT_DIR")
    onedesk_base_url: str = _slot("ONEDESK_BASE_URL")
    onedesk_api_key: str = _slot("ONEDESK_API_KEY")
    onentdb_db_enabled: str = _slot("ONENTDB_DB_ENABLED")
    onentdb_db_host: str = _slot("ONENTDB_DB_HOST")
    onentdb_db_port: str = _slot("ONENTDB_DB_PORT")
    onentdb_db_service_name: str = _slot("ONENTDB_DB_SERVICE_NAME")
    onentdb_db_user: str = _slot("ONENTDB_DB_USER")
    onentdb_db_password: str = _slot("ONENTDB_DB_PASSWORD")
    onentdb_db_query: str = _slot("ONENTDB_DB_QUERY")
    onentdb_db_timeout: str = _slot("ONENTDB_DB_TIMEOUT")
    onentdb_db_import_query: str = _slot("ONENTDB_DB_IMPORT_QUERY")
    onentdb_db_import_timeout: str = _slot("ONENTDB_DB_IMPORT_TIMEOUT")
    onent_db_url: str = _slot("ONENT_DB_URL")
    uruntutar_db_enabled: str = _slot("URUNTUTAR_DB_ENABLED")
    uruntutar_db_host: str = _slot("URUNTUTAR_DB_HOST")
    uruntutar_db_port: str = _slot("URUNTUTAR_DB_PORT")
    uruntutar_db_service_name: str = _slot("URUNTUTAR_DB_SERVICE_NAME")
    uruntutar_db_user: str = _slot("URUNTUTAR_DB_USER")
    uruntutar_db_password: str = _slot("URUNTUTAR_DB_PASSWORD")
    uruntutar_db_query: str = _slot("URUNTUTAR_DB_QUERY")
    uruntutar_db_timeout: str = _slot("URUNTUTAR_DB_TIMEOUT")
    uruntutar_db_import_query: str = _slot("URUNTUTAR_DB_IMPORT_QUERY")
    uruntutar_db_import_timeout: str = _slot("URUNTUTAR_DB_IMPORT_TIMEOUT")
    urun_tutar_db_url: str = _slot("URUN_TUTAR_DB_URL")
    oracle_reportdb_enabled: str = _slot("ORACLE_REPORTDB_ENABLED")
    oracle_reportdb_host: str = _slot("ORACLE_REPORTDB_HOST")
    oracle_reportdb_port: str = _slot("ORACLE_REPORTDB_PORT")
    oracle_reportdb_service_name: str = _slot("ORACLE_REPORTDB_SERVICE_NAME")
    oracle_reportdb_user: str = _slot("ORACLE_REPORTDB_USER")
    oracle_reportdb_password: str = _slot("ORACLE_REPORTDB_PASSWORD")
    oracle_reportdb_timeout: str = _slot("ORACLE_REPORTDB_TIMEOUT")
    oracle_reportdb_query: str = _slot("ORACLE_REPORTDB_QUERY")
    oracle_reportdb_import_query: str = _slot("ORACLE_REPORTDB_IMPORT_QUERY")
    oracle_reportdb_import_timeout: str = _slot("ORACLE_REPORTDB_IMPORT_TIMEOUT")
    oracle_reportdb_url: str = _slot("ORACLE_REPORTDB_URL")

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

