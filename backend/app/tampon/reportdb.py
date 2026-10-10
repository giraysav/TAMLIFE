"""ReportDB alarm senkronu (uretim kutucuklar/veri/reportdb_tampon.py uyarlamasi): kurumsal (NETWORK = NOC DESTECH) alarm sayilari.

Akis (isci surec: python -m app.isci reportdb; zamanlanmis gorev her 6 dk, Oracle giris tetikleyicisinin izin verdigi kimlikle):
SORGU -> tampon partisi (kaynak 'oracle_reportdb') -> 'Kartlara yaz' aciksa dagitim (Aktif Alarm -> alarm_count, Kapanan Alarm ->
alarm_closed_count) + alarm kayit listeleri (kapanan: yil basindan, acik: su an) -> parti 'oracle_reportdb_kayit' -> Onedesk
kayitlari (isci, onedesk.ice_al.kaynak_yenile). Panel sureci Oracle'a baglanmaz; Oracle'a yalniz SELECT gider (oracle.sorgu_temizle).

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

import re
from collections import defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Customer, IngestBatch
from app.ortak import UygulamaHatasi, simdi
from app.tampon import dagitim, depo, oracle
from app.tampon.eslestirme import anahtar, musteri_anahtarlari
from app.tampon.models import DistributionLog, DistributionRule

KAYNAK = "oracle_reportdb"
KAYIT_KAYNAGI = "oracle_reportdb_kayit"
ONEDESK_KAYNAGI = "reportdb"  # onedesk_record.source
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
KAYIT_SATIR_SINIRI = 500  # kart basina liste (en yeni once)
KAYIT_IN_PARCASI = 200  # sorguya giren Musteri No sayisi (Oracle IN sinirinin cok altinda)
_NO8 = re.compile(r"^\d{8}$")


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


# --- Alarm kayit listeleri (Onedesk'e) ------------------------------------------------------------------------------
def _kolonlar(acik: bool) -> list[tuple[str, str, str]]:
    """[(SQL ifadesi, ASCII takma ad, baslik)]. Basliklar onedesk.ice_al sutun eslemesiyle uyumlu (Cagri No, CI Adi, Kategori,
    Acilis/Kapanis Tarihi). Kisisel veri (kapatan kullanici vb.) alinmaz."""
    zaman = "ORIGINALEVENTTIME" if acik else "EVENTTIME"
    k = [("NVL(ALARMOBJECTOPERATORNO, TO_CHAR(IDENTIFIER))", "CAGRI_NO", "Çağrı No"),
         ("SUBSTR(NODE1, 1, 200)", "CI_ADI", "CI Adı"),
         ("SUBSTR(ALARMHEADER, 1, 200)", "KATEGORI", "Kategori"),
         ("SUBSTR(PERCEIVEDSEVERITY, 1, 30)", "SIDDET", "Şiddet"),
         (f"TO_CHAR({zaman}, 'YYYY-MM-DD HH24:MI:SS')", "ACILIS", "Açılış Tarihi")]  # fmt: skip
    if not acik:
        k.append(("TO_CHAR(CLOSETIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')", "KAPANIS", "Kapanış Tarihi"))
    k += [("SUBSTR(TTASSIGNED, 1, 100)", "EKIP", "Atanan Ekip"), ("SUBSTR(TTINFORMATION, 1, 100)", "BILET_ISLEMI", "Bilet İşlemi"),
          ("SUBSTR(CITY, 1, 60)", "IL", "İl"), ("SUBSTR(CORPARATECIRCUITDETAIL, 1, 100)", "URUN", "Çağrı Ürün Adı"),
          ("SUBSTR(SERVICENAME, 1, 100)", "SERVIS", "Çağrı Servisi")]  # fmt: skip
    return k


def kayit_sorgusu(acik: bool, numaralar: list[str]) -> str:
    """acik=True: TEMIP.ACTIVEALARMS_5DK (su an acik); False: TEMIP.VIEW_REPORT_ACTIVE (yil basindan bugune, EVENTTIME ust sinirli).
    Musteri basina en yeni KAYIT_SATIR_SINIRI satir + toplam. numaralar: 8 haneli Musteri No'lar (baska bir sey sorguya girmez)."""
    if not numaralar or not all(_NO8.match(n) for n in numaralar):
        raise ReportdbHata("Geçersiz Müşteri No listesi.")
    tablo = "TEMIP.ACTIVEALARMS_5DK" if acik else "TEMIP.VIEW_REPORT_ACTIVE"
    zaman = "ORIGINALEVENTTIME" if acik else "EVENTTIME"
    sira = "ORIGINALEVENTTIME DESC" if acik else "CLOSETIMESTAMP DESC NULLS LAST"
    ust = "" if acik else " AND EVENTTIME < TRUNC(SYSDATE) + 1"
    kolon = ", ".join(f"{ifade} AS {ad}" for ifade, ad, _ in _kolonlar(acik))
    liste = ", ".join(f"'{n}'" for n in numaralar)
    return ("SELECT * FROM (SELECT INFORMATION1 AS MNO, COUNT(*) OVER (PARTITION BY INFORMATION1) AS TOPLAM, "
            f"{kolon}, ROW_NUMBER() OVER (PARTITION BY INFORMATION1 ORDER BY {sira}) AS RN FROM {tablo} "
            f"WHERE {zaman} >= TRUNC(SYSDATE, 'YYYY'){ust} AND {_KURUMSAL} AND INFORMATION1 IN ({liste}) "
            f"AND INFORMATION2 IS NOT NULL) WHERE RN <= {KAYIT_SATIR_SINIRI} ORDER BY MNO, RN")  # fmt: skip


def _kayitlari_cek(acik: bool, numaralar: list[str]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """(basliklar, {8 haneli Musteri No: {'toplam', 'satirlar'}}) - ReportDB'den, KAYIT_IN_PARCASI'lik parcalar halinde."""
    a = oracle.ayar(KAYNAK)
    kolonlar = _kolonlar(acik)
    sonuc: dict[str, dict[str, Any]] = {}
    for i in range(0, len(numaralar), KAYIT_IN_PARCASI):
        akis = a.akis(oracle.sorgu_temizle(kayit_sorgusu(acik, numaralar[i : i + KAYIT_IN_PARCASI])), _azami() + 1)
        ix = {c: j for j, c in enumerate(next(akis))}
        for blok in akis:
            for s in blok:
                kayit = sonuc.setdefault(str(s[ix["MNO"]]), {"toplam": _sayi(oracle.deger(s[ix["TOPLAM"]])), "satirlar": []})
                kayit["satirlar"].append([_metin(oracle.deger(s[ix[ad]]), 300) or "" for _, ad, _ in kolonlar])
    return [b for _, _, b in kolonlar], sonuc


def _birlestir_kayit(basliklar: list[str], parcalar: list[dict[str, Any]], tarih_basligi: str) -> tuple[list[list[Any]], int]:
    """Birden cok numaranin listesini tek listede toplar (en yeni once, azami KAYIT_SATIR_SINIRI); toplam = toplamlarin toplami."""
    satirlar: list[list[Any]] = []
    toplam = 0
    for p in parcalar:
        satirlar += p["satirlar"]
        toplam += p["toplam"]
    if len(parcalar) > 1 and tarih_basligi in basliklar:
        i = basliklar.index(tarih_basligi)
        satirlar.sort(key=lambda s: (s[i] if i < len(s) else "") or "", reverse=True)
    return satirlar[:KAYIT_SATIR_SINIRI], toplam


def kayit_partisi(db: Session) -> tuple[IngestBatch | None, dict[str, int]]:
    """Uretim kayitlari_yenile (cekim): Musteri No'su dolu TUM kartlar icin kapanan (yil basindan) + acik alarm listesi -> tek parti
    (KAYIT_KAYNAGI; Onedesk aktarim sutunlariyla). Kart basina liste en yeni once, en fazla KAYIT_SATIR_SINIRI. Kart yoksa ReportDB'ye
    sorgu gitmez. Hic kayit yoksa parti None (cagiran eski listeyi bosaltir). Liste tam yenilendigi icin kucuklme korumasi yok."""
    kartlar: dict[int, tuple[str, list[str]]] = {}
    for cid, ad, no in db.execute(select(Customer.id, Customer.name, Customer.customer_no).where(Customer.customer_no.isnot(None))):
        nolar = [n.zfill(8) for n in musteri_anahtarlari(no) if len(n) <= 8]
        if nolar:
            kartlar[cid] = (ad or "", nolar)
    ozet = {"musteri": len(kartlar), "kapanan_satir": 0, "acik_satir": 0}
    if not kartlar:
        return None, ozet
    numaralar = sorted({n for _, nolar in kartlar.values() for n in nolar})
    kapanan_baslik, kapanan = _kayitlari_cek(False, numaralar)
    acik_baslik, acik = _kayitlari_cek(True, numaralar)
    satirlar: list[list[Any]] = []
    for ad, nolar in kartlar.values():
        for durum_adi, baslik, veri, tarih, sayac in (
            ("Kapalı", kapanan_baslik, kapanan, "Kapanış Tarihi", "kapanan_satir"),
            ("Açık", acik_baslik, acik, "Açılış Tarihi", "acik_satir"),
        ):
            tam = ["Müşteri No", *baslik]
            parcalar = [{"toplam": veri[n]["toplam"], "satirlar": [[n, *s] for s in veri[n]["satirlar"]]} for n in nolar if n in veri]
            liste, _ = _birlestir_kayit(tam, parcalar, tarih)
            ozet[sayac] += len(liste)
            for s in liste:
                h = dict(zip(tam, s))
                satirlar.append([h["Müşteri No"], ad, "Alarm", durum_adi] + [h.get(b, "") for b in kapanan_baslik])
    if not satirlar:
        return None, ozet
    parti = depo.parti_olustur(db, KAYIT_KAYNAGI, f"ReportDB alarm kayıtları · {len(kartlar)} kart", ISCI)
    db.commit()
    parti = depo.ice_al(db, parti, ["Müşteri No", "Müşteri Adı", "Kayıt Türü", "Durum", *kapanan_baslik], satirlar)
    if parti.status == "rejected":
        parti = depo.kabul_et(db, parti.id)
        db.commit()
        depo.eskileri_temizle(db, KAYIT_KAYNAGI)
    return parti, ozet
