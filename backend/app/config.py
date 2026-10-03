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
    secret = alias.endswith("PASSWORD") or alias.endswith("API_KEY")
    return Field(default="", validation_alias=alias, repr=not secret)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TAMLIFE_",
        env_file=None,
        extra="ignore",
    )

    env: str = "dev"
    database_url: str = "postgresql+psycopg://localhost:5432/tamlife"

    cookie_name: str = "tamlife_session"
    cookie_secure: bool = False

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
    onedesk_db_enabled: str = _slot("ONEDESK_DB_ENABLED")
    onedesk_db_host: str = _slot("ONEDESK_DB_HOST")
    onedesk_db_port: str = _slot("ONEDESK_DB_PORT")
    onedesk_db_service_name: str = _slot("ONEDESK_DB_SERVICE_NAME")
    onedesk_db_user: str = _slot("ONEDESK_DB_USER")
    onedesk_db_password: str = _slot("ONEDESK_DB_PASSWORD")
    onedesk_db_query: str = _slot("ONEDESK_DB_QUERY")
    onedesk_db_timeout: str = _slot("ONEDESK_DB_TIMEOUT")
    onedesk_db_import_query: str = _slot("ONEDESK_DB_IMPORT_QUERY")
    onedesk_db_import_timeout: str = _slot("ONEDESK_DB_IMPORT_TIMEOUT")
    onedesk_db_url: str = _slot("ONEDESK_DB_URL")
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

    def present(self, key: str) -> bool:
        allowed = set(AD_LDAP_KEYS) | set(source_key_names())
        if key not in allowed:
            raise KeyError(key)
        return bool(os.environ.get(key, "").strip())


def get_settings() -> Settings:
    return Settings()

