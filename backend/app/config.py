"""Runtime settings from the environment. This file holds no password."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TAMLIFE_", env_file=None, extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+psycopg://localhost:5432/tamlife"

    cookie_name: str = "tamlife_session"
    cookie_secure: bool = False

    # Dev login only. Empty user or password keeps login closed.
    local_user: str = ""
    local_password: str = ""
    local_role: str = "TeamMember"

    # Directory slots. The fake adapter never binds, even when these are set.
    ad_host: str = ""
    ad_port: int = 636
    ad_use_ssl: bool = True
    ad_base_dn: str = ""
    ad_bind_user: str = ""
    ad_bind_password: str = ""

    # External database slots. A value is never written back to disk.
    reportdb_dsn: str = ""
    secondary_dsn: str = ""
    secondary_kind: str = "unconfigured"


def get_settings() -> Settings:
    return Settings()
