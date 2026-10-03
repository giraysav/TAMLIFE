"""Dis kaynaklar. Uretim anahtar adlari ve ice alma tablolari.

Deger okunmaz, surucu yuklenmez, baglanti acilmaz.
OneDesk, Onent ve Urun-Tutar anahtarlari api_services.OracleSourceConfig
ile integrations.py kaydindan gelir. ORACLE_REPORTDB_* yalniz canli ortamda
tanimli anahtarlardir; kod on eki ONEDESK_DB'dir.
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

ORACLE_REPORTDB_KEYS: tuple[str, ...] = (
    "ORACLE_REPORTDB_ENABLED",
    "ORACLE_REPORTDB_HOST",
    "ORACLE_REPORTDB_PORT",
    "ORACLE_REPORTDB_SERVICE_NAME",
    "ORACLE_REPORTDB_USER",
    "ORACLE_REPORTDB_PASSWORD",
    "ORACLE_REPORTDB_TIMEOUT",
)

SOURCES: tuple[Source, ...] = (
    Source(
        "oracle_onedesk",
        "oracle",
        "OneDesk / Oracle",
        "ONEDESK_DB_ENABLED",
        _oracle("ONEDESK_DB", "ONEDESK_DB_URL", "ONEDESK_BASE_URL", "ONEDESK_API_KEY"),
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
        "oracle_onedesk_import",
        "oracle",
        "OneDesk / veri iceri alma",
        "ONEDESK_DB_IMPORT_QUERY",
        _oracle("ONEDESK_DB", "ONEDESK_DB_URL"),
    ),
    Source(
        "oracle_onent_import",
        "oracle",
        "Onent / veri iceri alma",
        "ONENTDB_DB_IMPORT_QUERY",
        _oracle("ONENTDB_DB", "ONENT_DB_URL"),
    ),
    Source(
        "oracle_reportdb",
        "oracle",
        "Oracle REPORTDB",
        "ORACLE_REPORTDB_ENABLED",
        ORACLE_REPORTDB_KEYS,
    ),
)

SOURCE_SLOTS: tuple[tuple[str, str, str], ...] = tuple(
    (item.id, item.kind, item.enabled_key) for item in SOURCES
)

# ham_veri.db semasi (kutucuklar/veri/ham_depo.py). Satir yok.
INGEST_TABLES: dict[str, tuple[str, ...]] = {
    "veri_setleri": (
        "id",
        "kaynak",
        "dosya",
        "sayfa",
        "basliklar",
        "satir_sayisi",
        "yukleyen",
        "zaman",
        "durum",
        "ilerleme",
        "hata",
        "profil",
        "guncel",
    ),
    "ham_bloklar": ("set_id", "blok", "adet", "veri"),
    "kurallar": ("id", "tanim", "guncelleyen", "zaman"),
    "metrikler": ("customer_id", "hedef", "deger", "kural_id", "set_id", "zaman"),
    "uygulama_gunlugu": ("id", "kural_id", "set_id", "musteri", "uygulayan", "zaman"),
}

# Panel PostgreSQL inis tablolari. Uretim ham deposunun adi bunlar degildir.
PANEL_INGEST_TABLES: tuple[str, ...] = ("ingest_batch", "ingest_record")


def source_key_names() -> tuple[str, ...]:
    names: list[str] = list(SHARED_ORACLE_KEYS)
    seen = set(names)
    for source in SOURCES:
        for key in source.keys:
            if key not in seen:
                seen.add(key)
                names.append(key)
    return tuple(names)
