"""Aylik rapor devre grafikleri: ReportDB LOE sorgusu (isci tarafi; panel sureci bu modulu Oracle icin KULLANMAZ).

2026-11-20 kullanici: "reportdb'den alacagimiz veri ile grafigi cizecegiz; LOE_Reportdb_Sorgu.txt'deki sorguyu kullanacagiz, tablo
bilgisine gore optimize et" + "LOE sorgusundaki iki hatayi duzelt; EXCHOURS'u simdilik pas gec".

Kaynak nesneler (REPORTDB, kullanici TAMLIFEADLOG): BRIX.CORPORATE_HR (saatlik olcum), ODS_RPT.CORPORATE_FOR_CMDB (CI -> musteri,
EXCHOURS). Orijinal sorgudan farklar:
  1) Gun filtresi: TO_CHAR(tarih,'D') oturumun NLS_TERRITORY'sine bagli (AMERICA: Pzt=2, Paz=1 -> "Mon-Fri" Pazar-Persembe
     olurdu). Yerine TRUNC(tarih) - TRUNC(tarih,'IW') + 1 (ISO hafta: Pzt=1 ... Paz=7; ayardan bagimsiz).
  2) Tarih araligi: "BETWEEN ay_basi AND ayin_son_gunu 00:00" son gunun 01:00-23:00 saatlerini disarida birakiyordu. Yerine
     ay_basi <= DATETIME < sonraki_ay_basi.
  3) Donem SYSDATE'ten degil, raporun donemiden (bind); yalniz secili devreler (CINAME IN ...) okunur, tum tablo taranmaz.
  4) Grafik icin aylik tek satir yerine SAATLIK satirlar alinir; aylik ozet ayni formulle Python'da hesaplanir:
       erisilebilirlik = SUM(NVL(AVAIL_TIME,0)) / SUM(TOTAL_TIME), gecikme = AVG(DELAY_AVG)/1000, jitter = AVG(JITTER_AVG)/1000,
       paket kaybi = AVG(PACKET_LOST_AVG)/100  (yalniz EXCHOURS penceresindeki saatler; AVG = SUM/COUNT, NULL'lar sayilmaz).
EXCHOURS kurallari orijinaldeki 8 CASE blogunun aynisi (PENCERELER); listede olmayan deger orijinaldeki gibi ozete girmez.
SOL.V_ONEDESK_ORG yalniz ORGANIZATIONNAME icindi; musteri adi panelde var, eslesme Musteri No ile (CMDB.CUSTOMERNO).
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import musteri_alani
from app.models import AppSetting, Customer, CustomerCi, ReportCircuit, ReportCircuitData, ReportCmdb
from app.ortak import simdi
from app.rapor import loe_trafik
from app.tampon import oracle
from app.tampon.eslestirme import anahtar, musteri_anahtarlari

_log = logging.getLogger("tamlife.loe")
KAYNAK = "oracle_reportdb"
DURUM_ANAHTARI = "rapor.loe_durum"
IMT_BICIMI = re.compile(r"^\d{9,15}$")  # gecerli IMT (envanterdeki '-', '1' gibi yer tutucular eslesmez)
TR = timezone(timedelta(hours=3))  # ReportDB DATETIME yerel saat (Turkiye, yaz saati yok)

_AD = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*(\.[A-Za-z][A-Za-z0-9_$#]*)?$")


def _nesne(anahtar_: str, varsayilan: str) -> str:
    """Tablo adi .env'den degistirilebilir (S1/S2 gecisi icin); yalniz SEMA.TABLO bicimi kabul edilir (sorguya birlesir)."""
    deger = (os.environ.get(anahtar_) or "").strip() or varsayilan
    if not _AD.match(deger):
        raise oracle.OracleHata(f"{anahtar_} geçersiz tablo adı.")
    return deger


def cmdb_tablosu() -> str:
    return _nesne("LOE_CMDB_TABLO", "ODS_RPT.CORPORATE_FOR_CMDB")


def olcum_tablosu() -> str:
    return _nesne("LOE_OLCUM_TABLO", "BRIX.CORPORATE_HR")


# (EXCHOURS, son gun (Pzt=1), baslangic HH24MISS, bitis HH24MISS): orijinal sorgunun CASE bloklari
PENCERELER: tuple[tuple[str, int, str, str], ...] = (
    ("Mon-Sun {00:00-23:59} 7x24", 7, "000000", "235959"),
    ("Mon-Fri {00:00-23:59} 7x24", 5, "000000", "235959"),
    ("Mon-Fri {00:00-23:59} 5x24", 5, "000000", "235959"),
    ("Mon-Sun {10:00-22:00} 7x12", 7, "100000", "220000"),
    ("Mon-Fri {07:45-17:15} 5x9", 5, "074500", "171500"),
    ("Mon-Fri {07:45-17:15} - 5x9", 5, "074500", "171500"),
    ("Mon-Sun {09:15-21:45}", 7, "091500", "214500"),
    ("Mon-Sun {09:15-21:45} 7x12", 7, "091500", "214500"),
)
PARCA = 500  # IN listesi bind sayisi (Oracle siniri 1000)
CMDB_YENILEME_SAAT = 20
CMDB_HATA_BEKLEME_DK = 60
GUNCEL_AY_YENILEME_DK = 60  # icinde bulunulan ay
ONCEKI_AY_YENILEME_DK = 360  # kapanan ay: ay bitiminden KESINLESME_GUN sonrasina kadar
KESINLESME_GUN = 3
AZAMI_SATIR = 2_000_000


# --- SQL ---------------------------------------------------------------------------------------------------------------------
def _pencere_sql() -> str:
    return " UNION ALL ".join(
        f"SELECT '{e}' EXCHOURS, {g} SON_GUN, '{b}' BAS, '{s}' BIT FROM DUAL" for e, g, b, s in PENCERELER
    )


def _in(onek: str, degerler: list[str]) -> tuple[str, dict[str, str]]:
    adlar = {f"{onek}{i}": d for i, d in enumerate(degerler)}
    return ", ".join(f":{a}" for a in adlar), adlar


def cmdb_sorgusu(anahtarlar: list[str]) -> tuple[str, dict[str, str]]:
    yer, binds = _in("m", anahtarlar)
    return f"SELECT * FROM {cmdb_tablosu()} WHERE LTRIM(TRIM(CUSTOMERNO), '0') IN ({yer})", binds


def olcum_sorgusu(cinames: list[str], bas: datetime, bit: datetime) -> tuple[str, dict[str, Any]]:
    yer, binds = _in("c", cinames)
    # WITH yerine satir ici gorunumler: oracle.akis sorguyu "SELECT * FROM (...) WHERE ROWNUM <= n" ile sarar.
    sorgu = (
        "SELECT DY.CINAME, TO_CHAR(DY.DATETIME, 'YYYY-MM-DD HH24:MI:SS') ZAMAN, DY.AVAIL_TIME, DY.TOTAL_TIME, DY.DELAY_AVG, "
        "DY.JITTER_AVG, DY.PACKET_LOST_AVG, ORG.EXCHOURS, "
        "CASE WHEN ORG.CINAME IS NULL THEN 1 WHEN P.EXCHOURS IS NOT NULL "
        "AND TRUNC(DY.DATETIME) - TRUNC(DY.DATETIME, 'IW') + 1 <= P.SON_GUN "
        "AND TO_CHAR(DY.DATETIME, 'HH24MISS') BETWEEN P.BAS AND P.BIT THEN 1 ELSE 0 END PENCERE "
        f"FROM {olcum_tablosu()} DY "
        f"LEFT JOIN (SELECT CINAME, MAX(EXCHOURS) EXCHOURS FROM {cmdb_tablosu()} WHERE CINAME IN ({yer}) GROUP BY CINAME) ORG "
        "ON ORG.CINAME = DY.CINAME "
        f"LEFT JOIN ({_pencere_sql()}) P ON P.EXCHOURS = ORG.EXCHOURS "
        f"WHERE DY.CINAME IN ({yer}) AND DY.DATETIME >= :bas AND DY.DATETIME < :bit"
    )
    return sorgu, {**binds, "bas": bas, "bit": bit}


# --- Hesap -------------------------------------------------------------------------------------------------------------------
def _sayi(v: Any) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def ay_araligi(yil: int, ay: int) -> tuple[datetime, datetime]:
    bas = datetime(yil, ay, 1)
    return bas, datetime(yil + (ay == 12), ay % 12 + 1, 1)


def ozet(satirlar: list[dict[str, Any]]) -> dict[str, Any]:
    """LOE formulu (yalniz pencere ici saatler). satir: avail, total, delay, jitter, loss (ham), pencere."""
    p = [s for s in satirlar if s["pencere"]]
    toplam = sum(s["total"] or 0 for s in p)

    def ort(alan: str, bolen: float) -> float | None:
        d = [s[alan] for s in p if s[alan] is not None]
        return (sum(d) / len(d)) / bolen if d else None

    return {
        "erisilebilirlik": (sum(s["avail"] or 0 for s in p) / toplam) if toplam else None,
        "gecikme": ort("delay", 1000),
        "jitter": ort("jitter", 1000),
        "kayip": ort("loss", 100),
        "saat": len(satirlar),
        "pencere_saat": len(p),
    }


def noktalar(satirlar: list[dict[str, Any]]) -> list[list[Any]]:
    """Grafik serisi: [epoch_ms, erisim (0-1), gecikme (ms), jitter (ms), kayip (0-1, LOE olcegi), pencere 0/1, giris bps, cikis bps];
    zamana gore sirali."""
    sonuc = []
    for s in sorted(satirlar, key=lambda x: x["zaman"]):
        t = s["total"]
        sonuc.append([
            int(s["zaman"].replace(tzinfo=TR).timestamp() * 1000),
            round((s["avail"] or 0) / t, 6) if t else None,
            None if s["delay"] is None else round(s["delay"] / 1000, 4),
            None if s["jitter"] is None else round(s["jitter"] / 1000, 4),
            None if s["loss"] is None else round(s["loss"] / 100, 6),
            1 if s["pencere"] else 0,
            s.get("giris"),
            s.get("cikis"),
        ])  # fmt: skip
    return sonuc


# --- Durum (panel ekrani icin; deger degil yalniz zaman / kisa hata) -----------------------------------------------------------
def durum_oku(db: Session) -> dict[str, Any]:
    kayit = db.get(AppSetting, DURUM_ANAHTARI)
    return dict(kayit.value) if kayit is not None and isinstance(kayit.value, dict) else {}


def _durum_yaz(db: Session, bolum: str, **alanlar: Any) -> None:
    kayit = db.get(AppSetting, DURUM_ANAHTARI)
    deger = dict(kayit.value) if kayit is not None and isinstance(kayit.value, dict) else {}
    deger[bolum] = {**(deger.get(bolum) or {}), **alanlar}
    if kayit is None:
        db.add(AppSetting(key=DURUM_ANAHTARI, value=deger, updated_by="isci", updated_at=simdi()))
    else:
        kayit.value, kayit.updated_by, kayit.updated_at = deger, "isci", simdi()
    db.commit()


def _zaman(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        z = datetime.fromisoformat(str(v))
    except ValueError:
        return None
    return z if z.tzinfo else z.replace(tzinfo=UTC)


def _aware(z: datetime | None) -> datetime | None:
    return None if z is None else (z if z.tzinfo else z.replace(tzinfo=UTC))


# --- Isci adimlari -----------------------------------------------------------------------------------------------------------
@musteri_alani.tum_alanlarda  # tum modullerin kartlari (Toptan / Baglantili dahil)
def musteri_anahtarlari_hepsi(db: Session) -> list[str]:
    sonuc: set[str] = set()
    for no in db.scalars(select(Customer.customer_no).where(Customer.customer_no.is_not(None))):
        sonuc.update(musteri_anahtarlari(no))
    return sorted(sonuc)


def cmdb_gerekli_mi(db: Session) -> bool:
    d = durum_oku(db).get("cmdb") or {}
    son_basari, son_deneme = _zaman(d.get("son_basari")), _zaman(d.get("son_deneme"))
    an = simdi()
    if son_deneme and d.get("hata") and an - son_deneme < timedelta(minutes=CMDB_HATA_BEKLEME_DK):
        return False
    return son_basari is None or an - son_basari >= timedelta(hours=CMDB_YENILEME_SAAT)


def _arama_metni(alanlar: dict[str, Any]) -> str:
    return " ".join(str(v) for v in alanlar.values() if v not in (None, "")).casefold()[:4000]


def _imt_haritasi(db: Session, anahtarlar: list[str]) -> dict[str, str]:
    """Envanterdeki (customer_ci.attrs['imt']) IMT: kucuk harf CI adi -> IMT. ReportDB CMDB'de IMT sutunu yok; 2026-11-26 kullanici
    devreyi IMT ile ariyor (ornek 100005049268), bu yuzden kopyaya IMT alani olarak eklenir ve aramaya girer."""
    harita: dict[str, str] = {}
    for i in range(0, len(anahtarlar), 5000):
        for ad, attrs in db.execute(select(CustomerCi.ci_name, CustomerCi.attrs).where(CustomerCi.customer_key.in_(anahtarlar[i : i + 5000]))):
            imt = str((attrs or {}).get("imt") or "").strip()
            if ad and imt:
                harita.setdefault(ad.strip().lower(), imt[:40])
    return harita


def cmdb_yenile(db: Session) -> int:
    """Paneldeki musteri numaralarinin CMDB satirlarini ceker ve kopyayi bastan yazar (envanterdeki IMT 'IMT' alani olarak eklenir).
    Donus: satir sayisi."""
    anahtarlar = musteri_anahtarlari_hepsi(db)
    imtler = _imt_haritasi(db, anahtarlar)
    a = oracle.ayar(KAYNAK)
    yeni: list[ReportCmdb] = []
    an = simdi()
    for i in range(0, len(anahtarlar), PARCA):
        sorgu, binds = cmdb_sorgusu(anahtarlar[i : i + PARCA])
        akis = a.akis(sorgu, AZAMI_SATIR, parametreler=binds)
        basliklar = [str(b) for b in next(akis)]
        for blok in akis:
            for s in blok:
                alanlar = {b: oracle.deger(v) for b, v in zip(basliklar, s, strict=False)}
                ci = str(alanlar.get("CINAME") or "").strip()
                if not ci:
                    continue
                if imt := imtler.get(ci.lower()):
                    alanlar["IMT"] = imt
                yeni.append(ReportCmdb(customer_key=anahtar(alanlar.get("CUSTOMERNO")), ciname=ci[:200], fields=alanlar,
                                       search_text=_arama_metni(alanlar), refreshed_at=an))  # fmt: skip
    db.execute(delete(ReportCmdb))
    db.add_all(yeni)
    db.commit()
    return len(yeni)


def gereken_donemler() -> list[tuple[int, int]]:
    """Raporun hazirlanabildigi donemler (rapor.servis.secilebilir_donemler ile ayni): onceki ay + icinde bulunulan ay."""
    from app.rapor.servis import secilebilir_donemler

    return secilebilir_donemler()


def _tazelenmeli(kayit: ReportCircuitData | None, yil: int, ay: int, an: datetime) -> bool:
    if kayit is None or kayit.fetched_at is None:
        return True
    cekildi = _aware(kayit.fetched_at)
    _, bit = ay_araligi(yil, ay)
    bit = bit.replace(tzinfo=TR)
    if loe_trafik.acik() and "trafik" not in (kayit.summary or {}):
        return True  # trafik kaynagi acildiktan sonra trafiksiz cekilmis ay bir kez yeniden cekilir (2026-11-27)
    if cekildi >= bit + timedelta(days=KESINLESME_GUN):
        return False  # ay kapandiktan sonra kesinlesmis veri
    esik = GUNCEL_AY_YENILEME_DK if an < bit else ONCEKI_AY_YENILEME_DK
    return an - cekildi >= timedelta(minutes=esik)


def olcum_cek(db: Session, cinames: list[str], yil: int, ay: int) -> int:
    """Devrelerin aylik saatlik olcumlerini ceker; her devre icin report_circuit_data satirini yazar (veri yoksa bos)."""
    bas, bit = ay_araligi(yil, ay)
    a = oracle.ayar(KAYNAK)
    gruplar: dict[str, list[dict[str, Any]]] = {c: [] for c in cinames}
    exch: dict[str, str] = {}
    for i in range(0, len(cinames), PARCA):
        sorgu, binds = olcum_sorgusu(cinames[i : i + PARCA], bas, bit)
        akis = a.akis(sorgu, AZAMI_SATIR, parametreler=binds)
        ix = {str(b): k for k, b in enumerate(next(akis))}
        for blok in akis:
            for s in blok:
                ci = str(s[ix["CINAME"]] or "").strip()
                if ci not in gruplar:
                    continue
                try:
                    zaman = datetime.strptime(str(s[ix["ZAMAN"]]), "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                exch[ci] = str(s[ix["EXCHOURS"]] or "")[:100]
                gruplar[ci].append({
                    "zaman": zaman, "avail": _sayi(s[ix["AVAIL_TIME"]]), "total": _sayi(s[ix["TOTAL_TIME"]]),
                    "delay": _sayi(s[ix["DELAY_AVG"]]), "jitter": _sayi(s[ix["JITTER_AVG"]]), "loss": _sayi(s[ix["PACKET_LOST_AVG"]]),
                    "pencere": bool(_sayi(s[ix["PENCERE"]])),
                })  # fmt: skip
    trafik = _trafik_ekle(db, gruplar, bas, bit)
    an = simdi()
    for ci, satirlar in gruplar.items():
        kayit = db.get(ReportCircuitData, (ci, yil, ay)) or ReportCircuitData(ciname=ci, year=yil, month=ay)
        ozet_ = ozet(satirlar)
        if trafik is not None:  # trafik cekildi (veri olsun olmasin); hata verdiyse anahtar yok, sonraki tazelemede yeniden denenir
            ozet_["trafik"] = "var" if ci in trafik else "yok"
            ozet_["trafik_eslesme"] = trafik.get(ci, "")
        kayit.points, kayit.summary, kayit.exchours, kayit.fetched_at = noktalar(satirlar), ozet_, exch.get(ci, ""), an
        db.merge(kayit)
    db.commit()
    return sum(len(v) for v in gruplar.values())


def devre_imtleri(db: Session, cinames: list[str]) -> dict[str, str]:
    """CI adi -> IMT: once ONENT envanteri (customer_ci.attrs.imt; 2026-11-27 kullanici "IMT'yi ONENT'ten"), yoksa CMDB kopyasi.
    Gecersiz IMT ('-', '1' gibi yer tutucular) alinmaz."""
    sonuc: dict[str, str] = {}
    for ad, attrs in db.execute(select(CustomerCi.ci_name, CustomerCi.attrs).where(CustomerCi.ci_name.in_(cinames))):
        imt = str((attrs or {}).get("imt") or "").strip()
        if IMT_BICIMI.match(imt):
            sonuc.setdefault(ad, imt)
    for k in db.scalars(select(ReportCmdb).where(ReportCmdb.ciname.in_([c for c in cinames if c not in sonuc]))):
        imt = str((k.fields or {}).get("IMT") or "").strip()
        if IMT_BICIMI.match(imt):
            sonuc.setdefault(k.ciname, imt)
    return {c: sonuc.get(c, "") for c in cinames}


def _trafik_ekle(db: Session, gruplar: dict[str, list[dict[str, Any]]], bas: datetime, bit: datetime) -> dict[str, str] | None:
    """Saatlik satirlara MSSQL trafigini (giris / cikis bps) yazar; Oracle olcumu olmayan saatler trafikle eklenir (pencere disi).
    Donus: trafigi bulunan CI adi -> eslesme turu (ci_imt | ci | imt). Kaynak kapali ya da hata: None (Oracle metrikleri yine
    yazilir; hata durum kaydina ve gunluge)."""
    if not loe_trafik.acik():
        return None
    imtler = devre_imtleri(db, list(gruplar))
    try:
        seriler = loe_trafik.saatlik_trafik(imtler, bas, bit)
    except Exception as e:  # noqa: BLE001 - trafik kaynagi hatasi olcumu durdurmaz
        from app.tampon import mssql

        mesaj = mssql.hata_metni(e, mssql.ayar().gizliler())
        _log.warning("trafik cekilemedi: %s", mesaj)
        _durum_yaz(db, "trafik", son_deneme=simdi().isoformat(), hata=mesaj)
        return None
    for ci, satirlar in gruplar.items():
        seri = dict((seriler.get(ci) or {}).get("seri") or {})
        for s in satirlar:
            if (v := seri.pop(s["zaman"].replace(minute=0, second=0), None)) is not None:
                s["giris"], s["cikis"] = v
        for saat, (gir, cik) in seri.items():  # Oracle olcumu olmayan saat: yalniz trafik
            satirlar.append({"zaman": saat, "avail": None, "total": None, "delay": None, "jitter": None, "loss": None, "pencere": False,
                             "giris": gir, "cikis": cik})  # fmt: skip
    _durum_yaz(db, "trafik", son_deneme=simdi().isoformat(), son_basari=simdi().isoformat(), hata="")
    return {ci: v["eslesme"] for ci, v in seriler.items() if ci in gruplar and v.get("seri")}


def senkron(db: Session, zorla: bool = False) -> dict[str, Any]:
    """Isci turu: gerekirse CMDB kopyasi, sonra secili devrelerin eksik / bayat donem verisi. Hatalar durum kaydina yazilir."""
    sonuc: dict[str, Any] = {"cmdb": None, "olcum": []}
    a = oracle.ayar(KAYNAK)
    if zorla or cmdb_gerekli_mi(db):
        t0 = time.time()
        try:
            n = cmdb_yenile(db)
            _durum_yaz(db, "cmdb", son_deneme=simdi().isoformat(), son_basari=simdi().isoformat(), hata="", satir=n)
            sonuc["cmdb"] = f"{n} satir, {time.time() - t0:.1f} sn"
        except Exception as e:  # noqa: BLE001 - durum ekranda; alarm senkronunu etkilemez
            db.rollback()
            mesaj = " ".join(oracle.hata_metni(e, a.gizliler())).strip()
            _durum_yaz(db, "cmdb", son_deneme=simdi().isoformat(), hata=mesaj)
            sonuc["cmdb"] = f"HATA {mesaj}"
    secili = sorted(set(db.scalars(select(ReportCircuit.ciname))))
    if not secili:
        return sonuc
    an = simdi()
    od = durum_oku(db).get("olcum") or {}
    son_hata = _zaman(od.get("son_deneme")) if od.get("hata") else None
    # Donem -> devreler: raporun donemleri tum secili devreler icin; tarih araligi secilmis musterilerde araligin aylari yalniz o
    # musterinin devreleri icin (2026-11-21: grafik araligi gun/ay/yil saat:dakika ile secilebilir).
    from app.rapor.trafik import aylar, ozel_araliklar

    donemler: dict[tuple[int, int], set[str]] = {d: set(secili) for d in gereken_donemler()}
    musteri_devre: dict[int, set[str]] = {}
    for mid, ci in db.execute(select(ReportCircuit.customer_id, ReportCircuit.ciname)):
        musteri_devre.setdefault(mid, set()).add(ci)
    yerel = an.astimezone(TR)
    for mid, (bas, bit) in ozel_araliklar(db).items():
        for d in aylar(bas, bit):
            if d <= (yerel.year, yerel.month):
                donemler.setdefault(d, set()).update(musteri_devre.get(mid, set()))
    for (yil, ay), cis in sorted(donemler.items(), reverse=True):
        hedef = sorted(cis)
        if not hedef:
            continue
        mevcut = {k.ciname: k for k in db.scalars(select(ReportCircuitData).where(
            ReportCircuitData.year == yil, ReportCircuitData.month == ay, ReportCircuitData.ciname.in_(hedef)))}  # fmt: skip
        gerek = [c for c in hedef if zorla or _tazelenmeli(mevcut.get(c), yil, ay, an)]
        if not gerek:
            continue
        yeni_var = any(c not in mevcut for c in gerek)
        if not zorla and not yeni_var and son_hata and an - son_hata < timedelta(minutes=CMDB_HATA_BEKLEME_DK):
            continue  # son cekim hata verdi: yalniz yeni eklenen devre varsa her turda yeniden denenir
        t0 = time.time()
        try:
            n = olcum_cek(db, gerek, yil, ay)
            _durum_yaz(db, "olcum", son_deneme=simdi().isoformat(), son_basari=simdi().isoformat(), hata="")
            sonuc["olcum"].append(f"{yil}-{ay:02d}: {len(gerek)} devre, {n} saat, {time.time() - t0:.1f} sn")
        except Exception as e:  # noqa: BLE001
            db.rollback()
            mesaj = " ".join(oracle.hata_metni(e, a.gizliler())).strip()
            _durum_yaz(db, "olcum", son_deneme=simdi().isoformat(), hata=mesaj)
            sonuc["olcum"].append(f"{yil}-{ay:02d}: HATA {mesaj}")
            break
    return sonuc
