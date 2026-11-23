"""Veri akislari: panele veri getiren TUM yollar tek bakista (Veri Girisi ust paneli). Yalniz okur; Oracle'a baglanmaz.

Her akis: nereden geldigi (dosya / isci / CLI), panelde nerede yonetildigi (ekran yolu), son gelis zamani ve durum.
Durum: 'taze' | 'bayat' (beklenen yenileme suresi gecti) | 'hata' (son deneme basarisiz) | 'yok' (hic veri gelmedi) | 'bilgi'
(elle gelen dosya: tazelik beklentisi yok). Zaman olcutleri tablolardan: tampon partisi, aktarim kaydi, denetim kaydi.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.models import AppSetting, AuditEvent, IngestBatch, OnedeskRecord, UrunTutarOzet
from app.ortak import iso, simdi
from app.tampon import kaynak, oracle, postgres, reportdb
from app.tampon.models import CustomerImportRun, DistributionLog, DistributionRule

TEMIP_SURUM = "temip.surum"  # temip_kayit.SURUM_AYARI (temip_kayit oracle zincirini yukler; burada yalniz ayar okunur)
TEMIP_KAYNAGI = "temip"
BAYAT_DK = reportdb.BAYAT_DK  # 30 dk'lik isci turunun iki kacirilmasi
ONEDESK_DURUM = "onedesk.kayit_durum"  # onedesk/canli.DURUM_ANAHTARI
ONEDESK_KAYNAGI = "onedesk"
ONEDESK_PG = "pg_onedesk"


def _utc(an: datetime | None) -> datetime | None:
    return None if an is None else (an if an.tzinfo else an.replace(tzinfo=UTC))


def _durum(son: datetime | None, bayat_dk: int | None, hata: bool = False) -> str:
    if hata:
        return "hata"
    if son is None:
        return "yok"
    if bayat_dk is None:
        return "bilgi"
    return "taze" if simdi() - son <= timedelta(minutes=bayat_dk) else "bayat"


def temip_semasi_hazir(db: Session) -> bool:
    """0013_onedesk_temip uygulandi mi (ticket_no sutunu). Uygulanmadan TEMIP kayit sorgulari calismaz."""
    return "ticket_no" in {c["name"] for c in inspect(db.get_bind()).get_columns("onedesk_record")}


def _son_parti(db: Session, anahtar: str) -> tuple[IngestBatch | None, IngestBatch | None]:
    """(son hazir parti, son parti)."""
    hazir = db.scalars(
        select(IngestBatch).where(IngestBatch.source_key == anahtar, IngestBatch.status == "ready").order_by(IngestBatch.id.desc()).limit(1)
    ).first()
    son = db.scalars(select(IngestBatch).where(IngestBatch.source_key == anahtar).order_by(IngestBatch.id.desc()).limit(1)).first()
    return hazir, son


def _denetim_son(db: Session, eylemler: tuple[str, ...]) -> dict[str, datetime]:
    return {
        a: _utc(t)
        for a, t in db.execute(
            select(AuditEvent.action, func.max(AuditEvent.at)).where(AuditEvent.action.in_(eylemler)).group_by(AuditEvent.action)
        )
        if t is not None
    }


def _akis(anahtar: str, ad: str, yontem: str, yer: str, son: datetime | None, durum: str, aciklama: str = "", **ek: Any) -> dict[str, Any]:
    return {"anahtar": anahtar, "ad": ad, "yontem": yontem, "yer": yer, "son": iso(son), "durum": durum, "aciklama": aciklama, **ek}


def akislar(db: Session) -> dict[str, Any]:
    liste: list[dict[str, Any]] = []

    # 1. Ham Musteri Verisi (dosya -> kartlar)
    hazir, _ = _son_parti(db, kaynak.KAYNAK)
    son_aktarim = db.scalars(select(CustomerImportRun).order_by(CustomerImportRun.id.desc()).limit(1)).first()
    zaman = _utc(son_aktarim.at) if son_aktarim else (_utc(hazir.received_at) if hazir else None)
    liste.append(
        _akis(
            "musteri_ham",
            "Ham Müşteri Verisi",
            "dosya",
            "yonetim/tampon?sekme=import",
            zaman,
            _durum(zaman, None),
            "Son aktarım geri alındı." if son_aktarim and son_aktarim.reverted_at else "",
            parti=hazir.id if hazir else None,
        )
    )

    a = oracle.ayar(reportdb.KAYNAK)
    # 2. TEMIP alarm kayitlari (30 dk'lik isci turu; ilk yukleme CLI)
    ayar = db.get(AppSetting, TEMIP_SURUM)
    deger = ayar.value if ayar is not None and isinstance(ayar.value, dict) else {}
    tzaman = _utc(datetime.fromisoformat(deger["an"])) if deger.get("an") else None
    sema = temip_semasi_hazir(db)
    sayilar = {"acik": 0, "kapali": 0, "radar": 0}
    if sema and tzaman:
        for durum, kartsiz, n in db.execute(
            select(OnedeskRecord.status, OnedeskRecord.customer_id.is_(None), func.count())
            .where(OnedeskRecord.source == TEMIP_KAYNAGI)
            .group_by(OnedeskRecord.status, OnedeskRecord.customer_id.is_(None))
        ):
            sayilar["acik" if durum == "open" else "kapali"] += n
            sayilar["radar"] += n if kartsiz else 0
    if not sema:
        tdurum, taciklama = "yok", "Şema hazır değil (0013_onedesk_temip uygulanmadı)."
    elif not tzaman:
        tdurum, taciklama = "yok", "İlk yükleme yapılmadı: kurulum\\temip_kayit_ice_al.ps1 -Adim Yukle"
    else:
        thata = reportdb.son_hata(reportdb.durum_oku(db))
        tdurum = _durum(tzaman, BAYAT_DK if a.ENABLED else None, bool(thata))
        taciklama = thata or f"Son tur: {deger.get('kip', '')}, +{deger.get('eklenen', 0)} yeni, {deger.get('guncellenen', 0)} güncel."
    liste.append(
        _akis("temip", "TEMIP alarm kayıtları", "işçi (30 dk) + CLI", "yonetim/tampon?sekme=akis", tzaman, tdurum, taciklama, sema=sema, **sayilar)
    )

    # 3. OneDesk sikayet / talep kayitlari (30 dk'lik isci turu; onedesk/canli)
    od = (db.get(AppSetting, ONEDESK_DURUM) or AppSetting(value={})).value or {}
    ozaman = _utc(datetime.fromisoformat(od["son_basari"])) if od.get("son_basari") else None
    ohata = bool(od.get("hata")) and od.get("son_deneme", "") >= od.get("son_basari", "")
    osayi = {("acik" if d == "open" else "kapali"): n for d, n in db.execute(
        select(OnedeskRecord.status, func.count()).where(OnedeskRecord.source == ONEDESK_KAYNAGI).group_by(OnedeskRecord.status))}  # fmt: skip
    liste.append(_akis("onedesk", "OneDesk şikayet / talep kayıtları", "işçi (30 dk)", "onedesk", ozaman,
                       _durum(ozaman, BAYAT_DK if postgres.ayar(ONEDESK_PG).ENABLED else None, ohata),
                       od.get("hata", "") if ohata else "", acik=osayi.get("acik", 0), kapali=osayi.get("kapali", 0)))  # fmt: skip

    # 4-5. Baska ekranlardan gelen dosyalar (denetim kaydi / yukleme zamani)
    denetim = _denetim_son(db, ("gelir_uretim.ice_al",))
    ut = _utc(db.scalar(select(func.max(UrunTutarOzet.uploaded_at))))
    liste.append(_akis("urun_tutar", "Ürün-Tutar Excel", "dosya", "yonetim/tampon?sekme=import", ut, _durum(ut, None)))
    liste.append(_akis("gelir_uretim", "Gelir Faydası Excel", "dosya", "yonetim/tampon?sekme=import", denetim.get("gelir_uretim.ice_al"),
                       _durum(denetim.get("gelir_uretim.ice_al"), None)))  # fmt: skip

    # 6. Genel CSV partileri (yalniz dagitim icin)
    csv_son = _utc(db.scalar(select(func.max(IngestBatch.received_at)).where(IngestBatch.source_key.startswith(kaynak.CSV_ON_EK))))
    liste.append(_akis("csv", "Genel CSV partileri", "dosya", "yonetim/tampon?sekme=import", csv_son, _durum(csv_son, None)))

    kural = db.scalar(select(func.count()).select_from(DistributionRule)) or 0
    etkin = db.scalar(select(func.count()).select_from(DistributionRule).where(DistributionRule.enabled.is_(True))) or 0
    son_uygulama = _utc(db.scalar(select(func.max(DistributionLog.at))))
    uyarilar = [f"{x['ad']}: {x['aciklama'] or 'veri bayat'}" for x in liste if x["durum"] in ("bayat", "hata")]
    return {
        "akislar": liste,
        "dagitim": {"kural": kural, "etkin": etkin, "son_uygulama": iso(son_uygulama)},
        "uyarilar": uyarilar,
        "zaman": iso(simdi()),
    }
