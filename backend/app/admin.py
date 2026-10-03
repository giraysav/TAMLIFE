"""Admin area. Presence of connection slots and ingest table names.

JSON from this module is booleans and names only. Secret values are never copied.
"""

from __future__ import annotations

import os

from app.ad import directory
from app.config import get_settings
from app.external import INGEST_TABLES, PANEL_INGEST_TABLES

DATA_TABLES: tuple[str, ...] = (
    "veri_setleri",
    "ham_bloklar",
    "kurallar",
    "metrikler",
    "uygulama_gunlugu",
    "ingest_batch",
    "ingest_record",
)

_NOTE = "Satırlar TAMLIFE_DATABASE_URL tanımlıysa Postgres'e yazılır."


def connections() -> list[dict[str, object]]:
    """AD, ORACLE_REPORTDB, ONEDESK, ONENT, URUNTUTAR. Configured or not."""
    settings = get_settings()
    return [
        {"id": "ad", "slot": "AD", "configured": directory.configured()},
        {
            "id": "oracle_reportdb",
            "slot": "ORACLE_REPORTDB",
            "configured": settings.present("ORACLE_REPORTDB_ENABLED"),
        },
        {
            "id": "onedesk",
            "slot": "ONEDESK",
            "configured": settings.present("ONEDESK_DB_ENABLED"),
        },
        {
            "id": "onent",
            "slot": "ONENT",
            "configured": settings.present("ONENTDB_DB_ENABLED"),
        },
        {
            "id": "uruntutar",
            "slot": "URUNTUTAR",
            "configured": settings.present("URUNTUTAR_DB_ENABLED"),
        },
    ]


def data_management() -> dict[str, object]:
    known = set(INGEST_TABLES) | set(PANEL_INGEST_TABLES)
    tables = [name for name in DATA_TABLES if name in known]
    if tuple(tables) != DATA_TABLES:
        raise RuntimeError("ingest table list drifted")
    url_set = bool(os.environ.get("TAMLIFE_DATABASE_URL", "").strip())
    return {"tables": tables, "database_url_set": url_set, "note": _NOTE}


def overview() -> dict[str, object]:
    return {"connections": connections(), "data_management": data_management()}
