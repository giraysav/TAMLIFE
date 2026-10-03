"""Admin area. Presence of connection slots and ingest table names.

JSON from this module is booleans and names only. Secret values are never copied.
"""

from __future__ import annotations

import os

from app.ad import directory
from app.config import get_settings
from app.external import INGEST_TABLES, PANEL_INGEST_TABLES, SOURCES

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


_REQUIRED_SUFFIXES = ("HOST", "PORT", "SERVICE_NAME", "USER", "PASSWORD")


def integrations() -> dict[str, object]:
    """Kurum bagimliliklarinin durumu. Yalniz anahtar adlari ve durum; deger hic okunmaz."""
    settings = get_settings()
    items: list[dict[str, object]] = []
    ad_missing = [key for key in ("AD_SERVER", "AD_DOMAIN") if not settings.present(key)]
    ad_on = directory.configured()
    items.append(
        {
            "id": "ad",
            "label": "AD / LDAP",
            "state": "ready" if ad_on else ("incomplete" if ad_missing and settings.present("AD_ENABLED") else "disabled"),
            "description": "Kullanici dogrulama (bind bu surumde kapali)",
            "missing": ad_missing if settings.present("AD_ENABLED") else [],
        }
    )
    for source in SOURCES:
        if source.id.endswith("_import"):
            continue
        prefix = source.enabled_key.rsplit("_ENABLED", 1)[0]
        enabled = settings.present(source.enabled_key)
        missing = [f"{prefix}_{s}" for s in _REQUIRED_SUFFIXES if not _present_name(f"{prefix}_{s}")] if enabled else []
        state = "disabled" if not enabled else ("incomplete" if missing else "ready")
        items.append(
            {"id": source.id, "label": source.label, "state": state, "description": "Salt okunur dis kaynak", "missing": missing}
        )
    return {"items": items, "runtime": {"network": "kapali (canli baglanti yok)", "assets": "yerel"}}


def _present_name(key: str) -> bool:
    return bool(os.environ.get(key, "").strip())


def overview() -> dict[str, object]:
    return {"connections": connections(), "data_management": data_management()}
