"""Ortak FastAPI bagimliliklari: oturum, yetki ve veritabani oturumu."""

from __future__ import annotations

import threading
from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.authz import is_admin
from app.config import get_settings
from app.gateway import make_engine, session_factory
from app.session import Principal, current_user

_ENGINES: dict[str, Engine] = {}
_LOCK = threading.Lock()


def engine() -> Engine:
    url = get_settings().database_url
    with _LOCK:
        if url not in _ENGINES:
            _ENGINES[url] = make_engine(url)
        return _ENGINES[url]


def dispose_engines() -> None:
    with _LOCK:
        for e in _ENGINES.values():
            e.dispose()
        _ENGINES.clear()


def get_db() -> Iterator[Session]:
    """Istek basina oturum. Commit endpointte acikca yapilir; hata olursa kapanista geri alinir."""
    db = session_factory(engine())()
    try:
        yield db
    finally:
        db.close()


def require_user(request: Request) -> Principal:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Oturum gerekli")
    return user


def require_admin(request: Request) -> Principal:
    user = require_user(request)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Yetki yok")
    return user
