"""PostgreSQL gateway. Importing this module does not connect."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def database_url() -> str:
    return get_settings().database_url


def make_engine(url: str | None = None) -> Engine:
    target = url or database_url()
    ayar = get_settings()
    sqlite_ok = target.startswith("sqlite") and (ayar.env in {"dev", "test"} or ayar.sqlite_izin)
    if not (target.startswith("postgresql") or sqlite_ok):
        raise RuntimeError("panel database must be PostgreSQL (sqlite only in dev/test or TAMLIFE_SQLITE_IZIN=true)")
    # PostgreSQL erisilemezse istek dakikalarca beklemesin: 3 sn'de hata (arka plan yazicilar ve saglik kontrolu de buna guvenir).
    argumanlar = {"connect_timeout": 3} if target.startswith("postgresql") else {}
    return create_engine(target, pool_pre_ping=True, connect_args=argumanlar)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
