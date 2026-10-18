"""ReportDB alarm senkronu (uretim kutucuklar/veri/reportdb_tampon.py uyarlamasi): kurumsal (NETWORK = NOC DESTECH) alarm sayilari.

Akis (isci surec: python -m app.isci reportdb; zamanlanmis gorev her 6 dk, Oracle giris tetikleyicisinin izin verdigi kimlikle):
SORGU -> tampon partisi (kaynak 'oracle_reportdb') -> 'Kartlara yaz' aciksa dagitim (Aktif Alarm -> alarm_count, Kapanan Alarm ->
alarm_closed_count). Alarm KAYITLARI (tek tek, 01.01.2026'dan; karta ya da TAM Radar'a) ayri modulde: tampon/temip_kayit.py.
Panel sureci Oracle'a baglanmaz; Oracle'a yalniz SELECT gider (oracle.sorgu_temizle).

Uretimle ayni kurallar: eslesme YALNIZ Musteri No; numarasi dolu kartin verisi partide yoksa 0; parti TAZELIK_DAKIKA'dan eskiyse
ya da kucuklme korumasina takildiysa (depo.EN_AZ_ORAN) kartlara HIC yazilmaz; ilk deger saklanir, geri alma yalniz hala bu isin
yazdigi degerde duran kartlari dondurur. DEV yapisi geregi farklar:
- 'Kartlara yaz' anahtari = bu kaynagin dagitim kurallari (KURALLAR; ilk basarili cekimde KAPALI acilir, Veri Girisi > Dagitim'da
  etkinlestirilir). Tampon = degismez parti; son hata = kaynagin 'failed' partisi.
- Uygulama kayitlari her turda tek uygulamada BIRIKIR (_birlestir): kart basina ilk eski deger + son yazilan (uretim
  reportdb_kart_onceki). 'Eski degerlere don' = kurallari kapat + son uygulamayi geri al.
- Bir numara birden cok karta dusuyorsa dagitim o satiri atlar (belirsiz); uretim hepsine yaziyordu.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import IngestBatch
from app.ortak import UygulamaHatasi, simdi
from app.tampon import dagitim, depo, oracle
from app.tampon.eslestirme import anahtar
from app.tampon.models import DistributionLog, DistributionRule

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
# (kural adi, hedef, deger sutunu): 'Kartlara yaz'. Anahtar 'Musteri No', islem topla (bir kartta birden cok numara: sayilar toplanir).
KURALLAR = (
    ("ReportDB · Aktif alarm", "customer.alarm_count", "Aktif Alarm"),
    ("ReportDB · Kapanan alarm (yıl)", "customer.alarm_closed_count", "Kapanan Alarm"),
)


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
    """Kaynak satiri icin: kartlara yaz acik mi, son hazir partinin yasi / tazeligi."""
    son = db.scalars(
        select(IngestBatch).where(IngestBatch.source_key == KAYNAK, IngestBatch.status == "ready").order_by(IngestBatch.id.desc()).limit(1)
    ).first()
    yas = _yas_dk(son) if son is not None else None
    kurallar = db.scalars(select(DistributionRule.enabled).where(DistributionRule.source_key == KAYNAK)).all()
    return {
        "kartlara_yaz": any(kurallar),
        "kural": len(kurallar),
        "yas_dk": None if yas is None else round(yas, 1),
        "taze": yas is not None and yas <= TAZELIK_DAKIKA,
        "tazelik_dk": TAZELIK_DAKIKA,
    }


# --- Kartlara yazma (DEV dagitimi) ------------------------------------------------------------------------------------
def kurallari_hazirla(db: Session) -> list[DistributionRule]:
    """Kaynagin hedef basina dagitim kurali yoksa KAPALI acar (uretim 'Kartlara yaz' varsayilan KAPALI). Yonetici duzenleyebilir."""
    mevcut = {k.target: k for k in db.scalars(select(DistributionRule).where(DistributionRule.source_key == KAYNAK))}
    for ad, hedef, sutun in KURALLAR:
        if hedef not in mevcut:
            govde = {"name": ad, "source_key": KAYNAK, "match_field": "customer_no", "key_column": "Musteri No", "target": hedef,
                     "operation": "topla", "value_column": sutun, "zero_unmatched": True, "max_age_minutes": TAZELIK_DAKIKA}  # fmt: skip
            mevcut[hedef] = dagitim.kural_olustur(db, govde, ISCI)
    db.commit()
    return [mevcut[h] for _, h, _ in KURALLAR]


def kartlara_uygula(db: Session, parti_id: int, kullanici: str = ISCI) -> dict[str, Any]:
    """Etkin kurallari partiye uygular (tek islem). Kural yoksa / parti hazir degilse / eskiyse HICBIR SEY yazmaz (uretim neden'leri)."""
    kurallar = db.scalars(
        select(DistributionRule).where(DistributionRule.source_key == KAYNAK, DistributionRule.enabled.is_(True)).order_by(DistributionRule.id)
    ).all()
    if not kurallar:
        return {"uygulandi": False, "neden": "kapali"}
    parti = db.get(IngestBatch, parti_id)
    if parti is None or parti.status != "ready" or parti.source_key != KAYNAK:
        return {"uygulandi": False, "neden": "tampon_bos"}
    yas = _yas_dk(parti)
    if yas is None or yas > TAZELIK_DAKIKA:
        return {"uygulandi": False, "neden": "eski"}
    guncellenen = sifirlanan = 0
    for kural in kurallar:
        s = dagitim.uygula(db, kural.id, parti_id, kullanici)
        guncellenen, sifirlanan = guncellenen + s["yazilan"], sifirlanan + s["sifirlanacak"]
        _birlestir(db, kural.id, s["run_id"], parti_id, kullanici)
    db.commit()
    depo.eskileri_temizle(db, KAYNAK)  # birlesen eski uygulamalarin partileri artik serbest
    return {"uygulandi": True, "kural": len(kurallar), "guncellenen": guncellenen, "sifirlanan": sifirlanan}


def _birlestir(db: Session, kural_id: int, run_id: str, parti_id: int, kullanici: str) -> None:
    """Kuralin geri alinmamis ESKI kayitlarini bu uygulamaya toplar: kart basina ILK eski deger + SON yazilan deger.
    Boylece eski partiler serbest kalir ve bu uygulamanin geri alinmasi kartlari ilk degerine dondurur (elle degisen korunur)."""
    yeni = {k.customer_id: k for k in db.scalars(select(DistributionLog).where(DistributionLog.run_id == run_id))}
    gruplar: dict[int, list[DistributionLog]] = defaultdict(list)
    for k in db.scalars(
        select(DistributionLog)
        .where(DistributionLog.rule_id == kural_id, DistributionLog.reverted.is_(False), DistributionLog.run_id != run_id)
        .order_by(DistributionLog.id)
    ):
        gruplar[k.customer_id].append(k)
    an = simdi()
    for cid, eskiler in gruplar.items():
        hedef = yeni.get(cid) or eskiler[-1]
        hedef.old_value = eskiler[0].old_value
        hedef.run_id, hedef.batch_id, hedef.at, hedef.actor = run_id, parti_id, an, kullanici[:120]
        for k in eskiler:
            if k is not hedef:
                db.delete(k)
        if (hedef.old_value or "") == (hedef.new_value or ""):
            db.delete(hedef)  # kart ilk degerine donmus: geri alinacak bir sey yok
    db.flush()
