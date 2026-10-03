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
    if not target.startswith("postgresql"):
        raise RuntimeError("panel database must be PostgreSQL")
    return create_engine(target, pool_pre_ping=True)


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
