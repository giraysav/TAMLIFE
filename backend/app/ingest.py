"""Incoming external databases. Key names and ingest tables only.

connect() never loads a driver and never opens Oracle.
"""

from __future__ import annotations

import os

from app.external import INGEST_TABLES, PANEL_INGEST_TABLES, SHARED_ORACLE_KEYS, SOURCES


class IngestDisabled(RuntimeError):
    pass


def _set(key: str) -> bool:
    return bool(os.environ.get(key, "").strip())


def status() -> dict:
    rows = []
    for source in SOURCES:
        rows.append(
            {
                "key": source.id,
                "kind": source.kind,
                "label": source.label,
                "dsn_env": source.enabled_key,
                "keys": list(source.keys),
                "configured": _set(source.enabled_key),
                "connected": False,
            }
        )
    return {
        "sources": rows,
        "shared_keys": list(SHARED_ORACLE_KEYS),
        "ingest_tables": {name: list(columns) for name, columns in INGEST_TABLES.items()},
        "panel_ingest_tables": list(PANEL_INGEST_TABLES),
    }


def connect(source_key: str) -> None:
    known = {item.id for item in SOURCES}
    if source_key not in known:
        raise KeyError(source_key)
    raise IngestDisabled("live external database connections are disabled")
