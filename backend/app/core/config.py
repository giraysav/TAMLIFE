"""Ortam ayarlari. .env dosyasi okunmaz. Deger repoda yok."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TAMLIFE_", env_file=None, extra="ignore")

    env: str = "prod"
    cookie_secure: bool = False
    local_user: str = ""
    local_password: str = ""
    local_role: str = "TeamMember"
    database_url: str = "sqlite:///./var/tamlife.db"
    json_limit: int = 1024 * 1024
    upload_limit: int = 20 * 1024 * 1024
    port: int = 8117
    masking: bool = True


def get_settings() -> Settings:
    return Settings()
