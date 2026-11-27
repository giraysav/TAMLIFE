"""Devre trafik olcumleri (giris / cikis bit/sn) MSSQL LOE raporlama veritabanlarindan (isci tarafi; panel bu modulu kullanmaz).

2026-11-26 kullanici: "inbound / outbound trafik loe_reporting_* tablolarinda (MSSQL)"; 2026-11-27 okuma yetkisi geldi. Sema
(loe_reporting_bb / _int / _vrf ayni yapida):
  details<YYYY>    gunluk grafik tanimi: rrdid, rrdname = "<IMT>|<musteri>|<lokasyon>|<hizmet> / <cihaz> / <arayuz>", measuredate
                   (kumelenmis indeks rrdid, measuredate). IMT -> rrdid eslesmesi buradan (yilin tablosu bir kez taranir).
  data<YYYYMMDD>   5 dakikalik olcum: rrdid, inbound, outbound (bit/sn, sablon inoutbits64), measuretime (yerel saat); kumelenmis
                   indeks rrdid, measuretime. Gunun tablosu ertesi gun dolar (bir gun gecikme).
  tempcilist (bb) / tempcilistrel (vrf)  CI adi -> RRD_ID eslemesi. Tabloda IP sutunlari da var: YALNIZ CINAME ve RRD_ID okunur
                   (envanter kurali: IP alinmaz; GRAPH_NAME de IP tasiyabildigi icin okunmaz).

2026-11-27 kullanici: "IMT gelince ONENT'ten CI adi, sonra o IMT ve CI adi ile MSSQL'de karsilastir". Eslesme sirasi (devre basina):
  1) CI adi -> tempcilist RRD_ID ("ci"); ayni grafik IMT ile de bulunursa "ci_imt" (iki yol ayni grafigi gosteriyor)
  2) CI adi bulunamazsa IMT -> details<YYYY>.rrdname ("imt"); bir IMT birden cok rrdid'ye (arayuz degisimi) dagilabilir: toplanir.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta

from app.tampon import mssql

_log = logging.getLogger("tamlife.loe_trafik")
PARCA = 200  # IN listesi parametre sayisi (SQL Server siniri 2100)


def acik() -> bool:
    return mssql.ayar().hazir()


def carpan() -> float:
    """Birim duzeltmesi (varsayilan 1: kaynak bit/sn). Olcum bayt/sn cikarsa .env MSSQL_LOE_TRAFIK_CARPAN=8."""
    try:
        return float((os.environ.get("MSSQL_LOE_TRAFIK_CARPAN") or "1").replace(",", "."))
    except ValueError:
        return 1.0


def _parcalar(degerler: list, n: int = PARCA):
    for i in range(0, len(degerler), n):
        yield degerler[i : i + n]


def _gunler(bas: datetime, bit: datetime) -> list[date]:
    """Araligi kapsayan gun tablolari; sinir saatleri komsu gunun tablosunda olabilir (gun tablosu 01:00 - ertesi 00:55)."""
    g, son, sonuc = (bas - timedelta(days=1)).date(), bit.date(), []
    while g <= son:
        sonuc.append(g)
        g += timedelta(days=1)
    return sonuc


def _rrd_haritasi(cur, imtler: list[str], bas: datetime, bit: datetime) -> dict[int, str]:
    """rrdid -> IMT (araliktaki yil tablolari; yalniz araliktaki gunlerde tanimli grafikler)."""
    sonuc: dict[int, str] = {}
    mevcut = {r[0] for r in cur.execute("SELECT name FROM sys.objects WHERE type = 'U' AND name LIKE 'details[0-9][0-9][0-9][0-9]'")}
    for yil in range(bas.year, bit.year + 1):
        tablo = f"details{yil}"
        if tablo not in mevcut:
            continue
        for parca in _parcalar(imtler):
            yer = ", ".join("?" * len(parca))
            sorgu = (
                f"SELECT rrdid, LEFT(rrdname, CHARINDEX('|', rrdname) - 1) FROM dbo.{tablo} "
                f"WHERE measuredate >= ? AND measuredate < ? AND isaggregate = 0 AND CHARINDEX('|', rrdname) > 1 "
                f"AND LEFT(rrdname, CHARINDEX('|', rrdname) - 1) IN ({yer}) GROUP BY rrdid, LEFT(rrdname, CHARINDEX('|', rrdname) - 1)"
            )
            for rrd, imt in cur.execute(sorgu, bas.replace(hour=0, minute=0), bit, *parca):
                sonuc[int(rrd)] = str(imt)
    return sonuc


def _saatlik(cur, rrdler: list[int], bas: datetime, bit: datetime) -> dict[int, dict[datetime, list[float]]]:
    """rrdid -> saat -> [ortalama giris, ortalama cikis] (5 dakikalik olcumlerin saatlik ortalamasi)."""
    sonuc: dict[int, dict[datetime, list[float]]] = defaultdict(dict)
    mevcut = {r[0] for r in cur.execute("SELECT name FROM sys.objects WHERE type = 'U' AND name LIKE 'data[0-9]%'")}
    for g in _gunler(bas, bit):
        tablo = f"data{g:%Y%m%d}"
        if tablo not in mevcut:
            continue
        for parca in _parcalar(rrdler):
            yer = ", ".join("?" * len(parca))
            sorgu = (
                f"SELECT rrdid, DATEADD(hour, DATEDIFF(hour, 0, measuretime), 0) saat, AVG(inbound), AVG(outbound) FROM dbo.{tablo} "
                f"WHERE rrdid IN ({yer}) AND measuretime >= ? AND measuretime < ? GROUP BY rrdid, DATEADD(hour, DATEDIFF(hour, 0, measuretime), 0)"
            )
            for rrd, saat, gir, cik in cur.execute(sorgu, *parca, bas, bit):
                sonuc[int(rrd)][saat] = [gir, cik]
    return sonuc


ESLEME_TABLOLARI = ("tempcilist", "tempcilistrel")  # CI adi -> RRD_ID (veritabanina gore biri bulunur)


def _ci_rrd(cur, cinames: list[str]) -> dict[str, set[int]]:
    """CI adi -> RRD_ID kumesi (yalniz CINAME ve RRD_ID sutunlari)."""
    sonuc: dict[str, set[int]] = defaultdict(set)
    mevcut = {r[0] for r in cur.execute("SELECT name FROM sys.objects WHERE type = 'U' AND name IN ('tempcilist', 'tempcilistrel')")}
    for tablo in ESLEME_TABLOLARI:
        if tablo not in mevcut:
            continue
        for parca in _parcalar(cinames):
            yer = ", ".join("?" * len(parca))
            for ci, rrd in cur.execute(f"SELECT CINAME, RRD_ID FROM dbo.{tablo} WHERE RRD_ID IS NOT NULL AND CINAME IN ({yer})", *parca):
                sonuc[str(ci)].add(int(rrd))
    return sonuc


def saatlik_trafik(imtler: dict[str, str], bas: datetime, bit: datetime) -> dict[str, dict]:
    """CI adi -> IMT eslemesinden: CI adi -> {"seri": {saat (yerel, saat basi): (giris bps, cikis bps)}, "eslesme": ci_imt|ci|imt}.
    Hicbir yolla bulunamayan devre sozlukte yok."""
    a = mssql.ayar()
    if not imtler or not a.hazir():
        return {}
    k = carpan()
    toplam: dict[str, dict[datetime, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0]))
    eslesme: dict[str, str] = {}
    with a.baglan() as conn:
        cur = conn.cursor()
        for vt in a.veritabanlari:
            cur.execute(f"USE [{vt}]")
            ci_rrd = {ci: r for ci, r in _ci_rrd(cur, sorted(imtler)).items() if ci not in eslesme}
            kalan_imt = sorted({imtler[ci] for ci in imtler if imtler[ci] and ci not in eslesme and ci not in ci_rrd})
            ci_imt_rrd: dict[str, set[int]] = defaultdict(set)
            imt_rrd = _rrd_haritasi(cur, sorted({*kalan_imt, *(imtler[ci] for ci in ci_rrd if imtler.get(ci))}), bas, bit)
            for rrd, imt in imt_rrd.items():
                ci_imt_rrd[imt].add(rrd)
            hedef: dict[int, set[str]] = defaultdict(set)  # rrdid -> CI adlari
            for ci, rrdler in ci_rrd.items():
                eslesme[ci] = "ci_imt" if rrdler & ci_imt_rrd.get(imtler.get(ci) or "", set()) else "ci"
                for r in rrdler:
                    hedef[r].add(ci)
            for ci, imt in imtler.items():
                if ci in eslesme or not imt or imt not in ci_imt_rrd:
                    continue
                eslesme[ci] = "imt"
                for r in ci_imt_rrd[imt]:
                    hedef[r].add(ci)
            if not hedef:
                continue
            for rrd, saatler in _saatlik(cur, sorted(hedef), bas, bit).items():
                for ci in hedef[rrd]:
                    for saat, (gir, cik) in saatler.items():
                        h = toplam[ci][saat]
                        h[0] += gir or 0.0
                        h[1] += cik or 0.0
                        h[2] += 1
    return {
        ci: {"seri": {s: (round(v[0] * k, 2), round(v[1] * k, 2)) for s, v in saatler.items() if v[2]}, "eslesme": eslesme[ci]}
        for ci, saatler in toplam.items()
    }
