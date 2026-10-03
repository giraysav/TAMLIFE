"""SQLAlchemy tabani ve cekirdek kimlik tablosu.

users sahibi core. pin_code ve totp_secret kolonlari yok.
is_2fa_enabled bayragi durur; 2FA akisi Q8 ile kapsam disi.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    allowed_modules: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ad_domain: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_ad_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_2fa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
