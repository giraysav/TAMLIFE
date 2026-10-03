"""Tek audit_event tablosu. Gizli alan reddedilir."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from app.core.errors import error_body
from app.core.session import current_user
from app.data.base import Base
from app.data.gateway import make_engine, session_factory

BANNED = ("pin_code", "totp_secret", "totp", "password", "set-cookie", "cookie")


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    path: Mapped[str] = mapped_column(String(256), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


def _reject(value: str) -> None:
    lowered = value.lower()
    for word in BANNED:
        if word in lowered:
            raise ValueError("secret field")


def write(
    factory: sessionmaker[Session],
    *,
    actor_id: int | None,
    action: str,
    module: str,
    target_id: str | None,
    result: str,
    path: str,
    detail: dict | None,
) -> None:
    blob = "" if not detail else "&".join(f"{key}={value}" for key, value in detail.items())
    for item in (action, module, result, path, blob):
        _reject(item)
    if detail:
        for key, value in detail.items():
            _reject(str(key))
            _reject(str(value))
    row = AuditEvent(
        created_at=datetime.now(timezone.utc),
        actor_id=actor_id,
        action=action,
        module=module,
        target_id=target_id,
        result=result,
        path=path,
        detail=blob or None,
    )
    db = factory()
    try:
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def setup(app: FastAPI) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite:///") and ":memory:" not in url:
        raw = url.removeprefix("sqlite:///")
        target = Path(raw)
        if target.parent and str(target.parent) not in {"", "."}:
            target.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(url)
    AuditEvent.__table__.create(engine, checkfirst=True)
    factory = session_factory(engine)
    app.state.audit_factory = factory

    @app.exception_handler(HTTPException)
    async def handle_http(request: Request, exc: HTTPException) -> JSONResponse:
        if exc.status_code == 403:
            user = current_user(request)
            module = request.url.path.rstrip("/").split("/")[-1] or "-"
            write(
                factory,
                actor_id=getattr(user, "id", None),
                action="denied",
                module=module,
                target_id=None,
                result="denied",
                path=request.url.path,
                detail=None,
            )
        code = "TL-MOD-01" if exc.status_code == 403 else "TL-SRV-01"
        message = "Yetki yok" if exc.status_code == 403 else "Istek reddedildi"
        return JSONResponse(status_code=exc.status_code, content=error_body(code, message))
