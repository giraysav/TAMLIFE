"""Dis kaynaklar (Oracle): REPORTDB (ORACLE_REPORTDB_*), ONENTDB (ONENTDB_DB_*), GALAPAGOSDB (GALAPAGOSDB_DB_*).

Burada yalniz *_ENABLED bayragi okunur (acik_mi); surucu yuklenmez, baglanti acilmaz (baglanti: app.tampon.oracle, isci surecte).
REPORTDB (Onedesk DB), canli .env'deki adiyla ORACLE_REPORTDB_* on ekini kullanir (eski kodun ONEDESK_DB_* adi artik yok). ONENTDB
anahtarlari api_services.OracleSourceConfig'ten gelir; GALAPAGOSDB ayni kalibi kullanir (2026-10-10, Urun-Tutar DB'nin yerine).
"""

from __future__ import annotations

import os
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
        "REPORTDB",
        "ORACLE_REPORTDB_ENABLED",
        _oracle("ORACLE_REPORTDB", "ORACLE_REPORTDB_URL", "ONEDESK_BASE_URL", "ONEDESK_API_KEY"),
    ),
    Source(
        "oracle_onent",
        "oracle",
        "ONENTDB",
        "ONENTDB_DB_ENABLED",
        _oracle("ONENTDB_DB", "ONENT_DB_URL"),
    ),
    Source(
        "oracle_galapagos",
        "oracle",
        "GALAPAGOSDB",
        "GALAPAGOSDB_DB_ENABLED",
        _oracle("GALAPAGOSDB_DB"),
    ),
    Source(
        "oracle_reportdb_import",
        "oracle",
        "REPORTDB veri iceri alma",
        "ORACLE_REPORTDB_IMPORT_QUERY",
        _oracle("ORACLE_REPORTDB", "ORACLE_REPORTDB_URL"),
    ),
    Source(
        "oracle_onent_import",
        "oracle",
        "ONENTDB veri iceri alma",
        "ONENTDB_DB_IMPORT_QUERY",
        _oracle("ONENTDB_DB", "ONENT_DB_URL"),
    ),
)

ORACLE_ZORUNLU = ("HOST", "SERVICE_NAME", "USER", "PASSWORD")  # uretim baglanti_eksikleri; PORT bossa 1521


def acik_mi(anahtar: str) -> bool:
    """*_ENABLED bayragi: yalniz 'true' acar (uretim OracleSourceConfig ile ayni; 'false' dolu diye acik sayilmaz)."""
    return os.environ.get(anahtar, "").strip().lower() == "true"


def on_ek(source: Source) -> str:
    """'ORACLE_REPORTDB_ENABLED' -> 'ORACLE_REPORTDB'."""
    return source.enabled_key.rsplit("_ENABLED", 1)[0]


def oracle_eksikleri(source: Source) -> list[str]:
    """Bos zorunlu baglanti anahtarlarinin ADLARI (deger degil)."""
    return [f"{on_ek(source)}_{ad}" for ad in ORACLE_ZORUNLU if not os.environ.get(f"{on_ek(source)}_{ad}", "").strip()]


def source_key_names() -> tuple[str, ...]:
    names: list[str] = list(SHARED_ORACLE_KEYS)
    seen = set(names)
    for source in SOURCES:
        for key in source.keys:
            if key not in seen:
                seen.add(key)
                names.append(key)
    return tuple(names)
