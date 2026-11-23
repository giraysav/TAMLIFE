"""Baglanti yuvalarinin durumu (AD, Oracle kaynaklari): yalniz anahtar adlari, durum ve gizli olmayan ayar ozeti.

Bu modulden cikan JSON gizli deger icermez (parola/anahtar asla). Oracle icin adres bile verilmez; AD icin yalniz sunucu adi, port,
alan ve var/yok bilgileri (AD'de servis hesabi/parola yoktur); Oracle icin port, zaman asimi ve var/yok bilgileri. Kullananlar: yonetim/ozet, yonetim/saglik, yonetim/router (Kurum Baglantilari).
"""

from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.ad import directory
from app.config import get_settings
from app.external import SOURCES, acik_mi, oracle_eksikleri


def connections() -> list[dict[str, object]]:
    """AD, ORACLE_REPORTDB (REPORTDB), ONENTDB, ONEDESKDB. configured = *_ENABLED=true (uretimle ayni kural)."""
    return [
        {"id": "ad", "slot": "AD", "tur": "dizin", "configured": directory.configured()},
        {"id": "oracle_reportdb", "slot": "ORACLE_REPORTDB", "tur": "veritabani", "configured": acik_mi("ORACLE_REPORTDB_ENABLED")},
        {"id": "onent", "slot": "ONENTDB", "tur": "veritabani", "configured": acik_mi("ONENTDB_PG_ENABLED")},  # 2026-10-19: PostgreSQL
        {"id": "onedesk", "slot": "ONEDESKDB", "tur": "veritabani", "configured": acik_mi("ONEDESKDB_PG_ENABLED")},
    ]


def ad_ayarlari() -> dict[str, object]:
    """Kurum Baglantilari kartinda gosterilen AD ayarlari. CA dosyasinin yolu ve grup DN'leri verilmez, yalniz tanimli mi."""
    a = get_settings()
    adres = urlparse(a.ad_server.strip())
    try:
        port = adres.port or (636 if adres.scheme.lower() == "ldaps" else None)
    except ValueError:  # 'ldaps://dc:abc' gibi bozuk port
        port = None
    return {
        "sunucu": adres.hostname or "",
        "port": port,
        "ldaps": adres.scheme.lower() == "ldaps",
        "ssl": a.ad_use_ssl.strip().lower() == "true",
        "alan": a.ad_domain.strip(),
        "ca_dosyasi": bool(a.ad_ca_cert_file.strip()),
        "grup_kisiti": bool(a.ad_izinli_gruplar.strip()),
        "otomatik_ac": a.ad_otomatik_ac.strip().lower() == "true",
    }


# 2026-10-19 kullanici: ONENTDB PostgreSQL'dir (tampon/postgres pg_onent); eski Oracle yuvasi (ONENTDB_DB_*) Kurum Baglantilari'nda gosterilmez.
GIZLI_ORACLE = ("oracle_onent",)


def integrations() -> dict[str, object]:
    """Kurum bagimliliklarinin durumu. Oracle: yalniz anahtar adlari ve durum; AD: ek olarak gizli olmayan ayar ozeti."""
    settings = get_settings()
    items: list[dict[str, object]] = []
    ad_acik = settings.ad_enabled.strip().lower() == "true"
    ad_missing = [key for key in ("AD_SERVER", "AD_DOMAIN") if not settings.present(key)] if ad_acik else []
    items.append(
        {
            "id": "ad",
            "label": "AD / LDAPS",
            "state": "ready" if directory.configured() else ("incomplete" if ad_missing else "disabled"),
            "description": "Kullanici dogrulama (LDAPS, kullanicinin kendi bind'i)",
            "missing": ad_missing,
            "bilgiler": ad_ayarlari(),
        }
    )
    for source in SOURCES:
        if source.id.endswith("_import") or source.id in GIZLI_ORACLE:
            continue
        enabled = acik_mi(source.enabled_key)
        missing = oracle_eksikleri(source) if enabled else []
        state = "disabled" if not enabled else ("incomplete" if missing else "ready")
        items.append(
            {"id": source.id, "label": source.label, "state": state, "description": "Salt okunur dis kaynak (cekim isci surecte)", "missing": missing}
        )
    from app.tampon import postgres

    for k, t in postgres.KAYNAKLAR.items():
        d = postgres.durum(k)
        items.append({"id": k, "label": t.label, "state": d["state"], "description": "Salt okunur PostgreSQL kaynagi (katalog isci surecte)", "missing": d["eksik"]})
    return {"items": items, "runtime": {"network": "kapali (canli baglanti yok)", "assets": "yerel"}}


def kurum_baglantilari(db: Session) -> list[dict[str, object]]:
    """Yonetim > Kurum Baglantilari: AD/LDAPS + Oracle (REPORTDB) + PostgreSQL (ONENTDB, ONEDESKDB) kaynaklari. Gizli deger yok; Oracle'da
    adres/servis/kullanici yalniz tanimli mi. Canli baglanti yalniz test ucunda (ayri surec)."""
    from app.tampon import oracle, postgres

    sonuc: list[dict[str, object]] = []
    for i in integrations()["items"]:  # type: ignore[union-attr]
        if i["id"] == "ad":
            sonuc.append({**i, "tur": "dizin"})
        elif i["id"] in oracle.KAYNAKLAR:
            ek: dict[str, object] = {
                "tur": "oracle",
                "acma_anahtari": oracle.KAYNAKLAR[i["id"]].enabled_key,
                "bilgiler": oracle.bilgiler(i["id"]),
            }
            sonuc.append({**i, **ek})
        elif i["id"] in postgres.KAYNAKLAR:
            sonuc.append({**i, "tur": "postgres", "acma_anahtari": postgres.KAYNAKLAR[i["id"]].enabled_key, "bilgiler": postgres.bilgiler(i["id"]),
                          "katalog": postgres.agac(db, i["id"])["katalog"]})  # fmt: skip
    return sonuc
