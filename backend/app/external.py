"""Dis kaynaklar: uretimdeki anahtar adlari (ORACLE_REPORTDB_*, ONENTDB_DB_*, URUNTUTAR_DB_*).

Deger okunmaz, surucu yuklenmez, baglanti acilmaz.
Onedesk DB, canli .env'deki adiyla ORACLE_REPORTDB_* on ekini kullanir (eski
kodun ONEDESK_DB_* adi artik yok). Onent ve Urun-Tutar anahtarlari
api_services.OracleSourceConfig ile integrations.py kaydindan gelir.
"""

from __future__ import annotations

from dataclasses import dataclass


def _oracle(prefix: str, *extra: str) -> tuple[str, ...]:
    suffixes = (
        "ENABLED",
        "HOST",
        "PORT",
        "SERVICE_NAME",
        "USER",
        "PASSWORD",
        "QUERY",
        "TIMEOUT",
        "IMPORT_QUERY",
        "IMPORT_TIMEOUT",
    )
    return tuple(f"{prefix}_{suffix}" for suffix in suffixes) + extra


@dataclass(frozen=True)
class Source:
    id: str
    kind: str
    label: str
    enabled_key: str
    keys: tuple[str, ...]


SHARED_ORACLE_KEYS: tuple[str, ...] = ("ORACLE_CLIENT_DIR",)

SOURCES: tuple[Source, ...] = (
    Source(
        "oracle_reportdb",
        "oracle",
        "Onedesk / REPORTDB",
        "ORACLE_REPORTDB_ENABLED",
        _oracle("ORACLE_REPORTDB", "ORACLE_REPORTDB_URL", "ONEDESK_BASE_URL", "ONEDESK_API_KEY"),
    ),
    Source(
        "oracle_onent",
        "oracle",
        "Onent / Oracle",
        "ONENTDB_DB_ENABLED",
        _oracle("ONENTDB_DB", "ONENT_DB_URL"),
    ),
    Source(
        "oracle_urun_tutar",
        "oracle",
        "Urun-Tutar / Oracle",
        "URUNTUTAR_DB_ENABLED",
        _oracle("URUNTUTAR_DB", "URUN_TUTAR_DB_URL"),
    ),
    Source(
        "oracle_reportdb_import",
        "oracle",
        "Onedesk / REPORTDB veri iceri alma",
        "ORACLE_REPORTDB_IMPORT_QUERY",
        _oracle("ORACLE_REPORTDB", "ORACLE_REPORTDB_URL"),
    ),
    Source(
        "oracle_onent_import",
        "oracle",
        "Onent / veri iceri alma",
        "ONENTDB_DB_IMPORT_QUERY",
        _oracle("ONENTDB_DB", "ONENT_DB_URL"),
    ),
)

def source_key_names() -> tuple[str, ...]:
    names: list[str] = list(SHARED_ORACLE_KEYS)
    seen = set(names)
    for source in SOURCES:
        for key in source.keys:
            if key not in seen:
                seen.add(key)
                names.append(key)
    return tuple(names)
