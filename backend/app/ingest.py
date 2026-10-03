"""Incoming external databases. Slots only; connect() never opens a driver."""

from __future__ import annotations

from app.config import get_settings
from app.models import SOURCE_SLOTS


class IngestDisabled(RuntimeError):
    pass


def status() -> list[dict]:
    settings = get_settings()
    configured = {
        "reportdb": bool(settings.reportdb_dsn),
        "secondary": bool(settings.secondary_dsn),
    }
    kinds = {
        "reportdb": "oracle",
        "secondary": settings.secondary_kind or "unconfigured",
    }
    rows = []
    for key, kind, env_name in SOURCE_SLOTS:
        rows.append(
            {
                "key": key,
                "kind": kinds.get(key, kind),
                "dsn_env": env_name,
                "configured": configured.get(key, False),
                "connected": False,
            }
        )
    return rows


def connect(source_key: str) -> None:
    known = {key for key, _kind, _env in SOURCE_SLOTS}
    if source_key not in known:
        raise KeyError(source_key)
    raise IngestDisabled("live external database connections are disabled")
