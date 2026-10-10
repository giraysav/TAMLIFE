"""Baglanti yuvalarinin durumu (AD, Oracle kaynaklari): yalniz anahtar adlari ve durum.

Bu modulden cikan JSON yalniz boolean ve ad icerir; gizli deger asla kopyalanmaz. Kullananlar: yonetim/ozet, yonetim/saglik.
"""

from __future__ import annotations

from app.ad import directory
from app.config import get_settings
from app.external import SOURCES, acik_mi, oracle_eksikleri


def connections() -> list[dict[str, object]]:
    """AD, ORACLE_REPORTDB (Onedesk DB), ONENT, URUNTUTAR. configured = *_ENABLED=true (uretimle ayni kural)."""
    return [
        {"id": "ad", "slot": "AD", "configured": directory.configured()},
        {"id": "oracle_reportdb", "slot": "ORACLE_REPORTDB", "configured": acik_mi("ORACLE_REPORTDB_ENABLED")},
        {"id": "onent", "slot": "ONENT", "configured": acik_mi("ONENTDB_DB_ENABLED")},
        {"id": "uruntutar", "slot": "URUNTUTAR", "configured": acik_mi("URUNTUTAR_DB_ENABLED")},
    ]


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
        enabled = acik_mi(source.enabled_key)
        missing = oracle_eksikleri(source) if enabled else []
        state = "disabled" if not enabled else ("incomplete" if missing else "ready")
        items.append(
            {"id": source.id, "label": source.label, "state": state, "description": "Salt okunur dis kaynak (cekim isci surecte)", "missing": missing}
        )
    return {"items": items, "runtime": {"network": "kapali (canli baglanti yok)", "assets": "yerel"}}
