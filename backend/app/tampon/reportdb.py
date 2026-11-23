"""ReportDB alarm ozeti (uretim kutucuklar/veri/reportdb_tampon.py uyarlamasi): kurumsal (NETWORK = NOC DESTECH) alarm sayilari.

Akis (isci surec: python -m app.isci reportdb; zamanlanmis gorev her 6 dk, Oracle giris tetikleyicisinin izin verdigi kimlikle):
SORGU -> tampon partisi (kaynak 'oracle_reportdb'). Parti yalniz baglanti sagligi / tazelik ve TAM Radar'in kayit yokken kullandigi
eski ozet icindir: KARTLARA YAZILMAZ. 2026-11-23 kullanici karari: kart alarm sayilari (alarm_count, alarm_closed_count) TEK yazandan,
alarm KAYITLARINDAN (tampon/temip_kayit.py -> onedesk/sayac.sayaclari_yenile) gelir; eski 'Kartlara yaz' dagitim kurallari kaldirildi.
Panel sureci Oracle'a baglanmaz; Oracle'a yalniz SELECT gider (oracle.sorgu_temizle). Kucuklme korumasi (depo.EN_AZ_ORAN) aynen.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import IngestBatch
from app.ortak import UygulamaHatasi, simdi
from app.tampon import depo, oracle
from app.tampon.eslestirme import anahtar

KAYNAK = "oracle_reportdb"
KAYIT_KAYNAGI = "oracle_reportdb_kayit"  # 2026-10-17 oncesi kayit partileri (adlandirma icin; yeni parti yazilmaz)
ISCI = "reportdb"  # parti / uygulama yazari
TAZELIK_DAKIKA = 20  # 6 dk'lik dongunun 3 kacirilmasi: bundan eski parti kartlara yazilmaz

# Yil basindan (TRUNC(SYSDATE,'YYYY')) bugune; kapanan taraf ust sinirli (EVENTTIME bolum anahtari: ust sinirsiz aralik gelecek tarihli
# bozuk bolumleri de tarar). Aktif: TEMIP.ACTIVEALARMS_5DK (5 dk'lik anlik goruntu); Kapanan: TEMIP.VIEW_REPORT_ACTIVE (bolumlu).
_MUSTERI = "REGEXP_LIKE(INFORMATION1,'^[0-9]{8}$') AND INFORMATION2 IS NOT NULL"
_KURUMSAL = "REPLACE(NETWORK,'\"','') IN ('NOC DESTECH')"
SORGU = (
    'SELECT COALESCE(A.MNO, K.MNO) AS "Musteri No", COALESCE(A.UNVAN, K.UNVAN) AS "Musteri Unvani", '
    'NVL(A.ADET, 0) AS "Aktif Alarm", NVL(A.BILETLI, 0) AS "Biletli Aktif Alarm", '
    'NVL(K.ADET, 0) AS "Kapanan Alarm", NVL(K.BILETLI, 0) AS "Biletli Kapanan Alarm", '
    "TO_CHAR(LEAST(NVL(A.ILK, K.ILK), NVL(K.ILK, A.ILK)), 'YYYY-MM-DD HH24:MI:SS') AS \"En Eski Alarm\", "
    "TO_CHAR(K.SON_KAPANIS, 'YYYY-MM-DD HH24:MI:SS') AS \"Son Kapanis\", "
    "TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS') AS \"Veri Zamani\" "
    'FROM (SELECT INFORMATION1 AS MNO, MAX(INFORMATION2) AS UNVAN, COUNT(*) AS ADET, '
    'COUNT(ALARMOBJECTOPERATORNO) AS BILETLI, MIN(ORIGINALEVENTTIME) AS ILK '
    "FROM TEMIP.ACTIVEALARMS_5DK WHERE ORIGINALEVENTTIME >= TRUNC(SYSDATE, 'YYYY') "
    f'AND {_KURUMSAL} AND {_MUSTERI} GROUP BY INFORMATION1) A '
    'FULL OUTER JOIN (SELECT INFORMATION1 AS MNO, MAX(INFORMATION2) AS UNVAN, COUNT(*) AS ADET, '
    'COUNT(ALARMOBJECTOPERATORNO) AS BILETLI, MIN(EVENTTIME) AS ILK, MAX(CLOSETIMESTAMP) AS SON_KAPANIS '
    "FROM TEMIP.VIEW_REPORT_ACTIVE WHERE EVENTTIME >= TRUNC(SYSDATE, 'YYYY') AND EVENTTIME < TRUNC(SYSDATE) + 1 "
    f'AND {_KURUMSAL} AND {_MUSTERI} GROUP BY INFORMATION1) K ON K.MNO = A.MNO '
    'ORDER BY NVL(A.ADET, 0) + NVL(K.ADET, 0) DESC')  # fmt: skip
GEREKLI = ("Musteri No", "Musteri Unvani", "Aktif Alarm", "Biletli Aktif Alarm", "Kapanan Alarm", "Biletli Kapanan Alarm")
BASLIKLAR = [*GEREKLI, "En Eski Alarm", "Son Kapanis", "Veri Zamani"]


class ReportdbHata(UygulamaHatasi):
    """Yoneticiye / gunluge gosterilecek hata (uretim reportdb_tampon.TamponHatasi)."""

    def __init__(self, mesaj: str, kod: int = 400) -> None:
        super().__init__(kod, mesaj)


def _sayi(v: Any) -> int:
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def _metin(v: Any, azami: int = 300) -> str | None:
    return " ".join(str(v).split())[:azami] if v not in (None, "") else None


def _azami() -> int:
    return get_settings().ingest_max_rows


# --- Ozet: cekim ve tampon ------------------------------------------------------------------------------------------
def cek() -> tuple[list[str], list[list[Any]]]:
    """SORGU'yu ReportDB'de calistirir -> (basliklar, satirlar). Baglanti ORACLE_REPORTDB_* (kapali/eksikse OracleHata)."""
    akis = oracle.ayar(KAYNAK).akis(oracle.sorgu_temizle(SORGU), _azami() + 1)
    basliklar = [str(b) for b in next(akis)]
    satirlar = [[oracle.deger(v) for v in s] for blok in akis for s in blok]
    if len(satirlar) > _azami():
        raise ReportdbHata("Sorgu çok büyük.")
    return basliklar, satirlar


def satirlari_hazirla(basliklar: list[str], satirlar: list[list[Any]]) -> list[list[Any]]:
    """Uretim yenile(): zorunlu sutunlar; Musteri No'suz ve tekrar eden numara (rakam disi / bastaki sifir yok sayilir) atlanir;
    sayilar >= 0 tam sayi. Cikti BASLIKLAR sirasinda."""
    ix = {b: i for i, b in enumerate(basliklar)}
    eksik = [b for b in GEREKLI if b not in ix]
    if eksik:
        raise ReportdbHata("Sorgu sütunları eksik: " + ", ".join(eksik))

    def hucre(s: list[Any], ad: str) -> Any:
        i = ix.get(ad)
        return s[i] if i is not None and i < len(s) else None

    temiz: list[list[Any]] = []
    gorulen: set[str] = set()
    for s in satirlar:
        no = anahtar(hucre(s, "Musteri No"))
        if not no or no in gorulen:
            continue
        gorulen.add(no)
        temiz.append(
            [str(hucre(s, "Musteri No")).strip(), _metin(hucre(s, "Musteri Unvani")) or no]
            + [_sayi(hucre(s, ad)) for ad in GEREKLI[2:]]
            + [_metin(hucre(s, ad)) for ad in BASLIKLAR[6:]]
        )
    if not temiz:
        raise ReportdbHata("Sorgu satır döndürmedi.")
    return temiz


def tampona_yaz(db: Session, basliklar: list[str], satirlar: list[list[Any]], sure_sn: float | None = None) -> IngestBatch:
    """Ozeti yeni parti olarak yazar: 'ready' ya da kucuklme korumasina takilirsa 'rejected' (kartlara yazilmaz; onceki parti durur)."""
    temiz = satirlari_hazirla(basliklar, satirlar)
    veri_zamani = temiz[0][-1]
    etiket = f"ReportDB alarm özeti · {len(temiz)} müşteri" + (f" · {sure_sn:.1f} sn" if sure_sn is not None else "")
    parti = depo.parti_olustur(db, KAYNAK, etiket + (f" · veri {veri_zamani}" if veri_zamani else ""), ISCI)
    db.commit()
    return depo.ice_al(db, parti, BASLIKLAR, temiz)


def hata_yaz(db: Session, mesaj: str) -> IngestBatch:
    """Basarisiz cekim: 'failed' parti (son hata ekranda); onceki hazir parti ve kartlar degismez."""
    parti = depo.parti_olustur(db, KAYNAK, "ReportDB alarm özeti (çekim başarısız)", ISCI)
    db.commit()
    depo.basarisiz(db, parti.id, mesaj)
    return parti


def _yas_dk(parti: IngestBatch) -> float | None:
    if parti.received_at is None:
        return None
    zaman = parti.received_at if parti.received_at.tzinfo else parti.received_at.replace(tzinfo=simdi().tzinfo)
    return (simdi() - zaman) / timedelta(minutes=1)


def durum(db: Session) -> dict[str, Any]:
    """Kaynak satiri icin: son hazir partinin yasi / tazeligi."""
    son = db.scalars(
        select(IngestBatch).where(IngestBatch.source_key == KAYNAK, IngestBatch.status == "ready").order_by(IngestBatch.id.desc()).limit(1)
    ).first()
    yas = _yas_dk(son) if son is not None else None
    return {
        "yas_dk": None if yas is None else round(yas, 1),
        "taze": yas is not None and yas <= TAZELIK_DAKIKA,
        "tazelik_dk": TAZELIK_DAKIKA,
    }
