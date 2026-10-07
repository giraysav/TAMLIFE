"""Yonetim tablolari. Base ortak (app.models); alembic ve create_all hepsini gorur."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class FaultEvent(Base):
    """Ariza kaydi: her kayit KOD + KAYIT NO tasir. Ham istisna metni yoktur; yigin izi dosya gunlugundedir."""

    __tablename__ = "fault_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    record_no: Mapped[str] = mapped_column(String(32), unique=True)
    code: Mapped[str] = mapped_column(String(20), index=True)
    severity: Mapped[str] = mapped_column(String(10), default="error")  # error | warning
    source: Mapped[str] = mapped_column(String(160), default="")
    message: Mapped[str] = mapped_column(String(300), default="")
    exc_type: Mapped[str] = mapped_column(String(120), default="")
    actor: Mapped[str] = mapped_column(String(120), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(12), default="open", index=True)  # open | ack | closed
    note: Mapped[str] = mapped_column(String(500), default="")
    resolved_by: Mapped[str] = mapped_column(String(120), default="")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
