# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
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
from datetime import date, datetime, timedelta, timezone

from app.tampon import mssql

_log = logging.getLogger("tamlife.loe_trafik")
TR = timezone(timedelta(hours=3))  # olcum zamani yerel saat (Turkiye)
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


def _bes_dakika(cur, rrdler: list[int], bas: datetime, bit: datetime) -> dict[int, list[tuple[datetime, float, float]]]:
    """rrdid -> [(olcum zamani, giris, cikis)] ham 5 dakikalik olcumler (konsolidasyon panelde, LookOutEyes kuraliyla)."""
    sonuc: dict[int, list[tuple[datetime, float, float]]] = defaultdict(list)
    mevcut = {r[0] for r in cur.execute("SELECT name FROM sys.objects WHERE type = 'U' AND name LIKE 'data[0-9]%'")}
    for g in _gunler(bas, bit):
        tablo = f"data{g:%Y%m%d}"
        if tablo not in mevcut:
            continue
        for parca in _parcalar(rrdler):
            yer = ", ".join("?" * len(parca))
            sorgu = f"SELECT rrdid, measuretime, inbound, outbound FROM dbo.{tablo} WHERE rrdid IN ({yer}) AND measuretime >= ? AND measuretime < ?"
            for rrd, zaman, gir, cik in cur.execute(sorgu, *parca, bas, bit):
                sonuc[int(rrd)].append((zaman, gir or 0.0, cik or 0.0))
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


def trafik_serileri(imtler: dict[str, str], bas: datetime, bit: datetime) -> dict[str, dict]:
    """CI adi -> IMT eslemesinden: CI adi -> {"seri": [(epoch sn, giris bps, cikis bps)] 5 dakikalik, zamana gore, "eslesme":
    ci_imt|ci|imt}. Ayni CI'ya dusen arayuzlerin ayni andaki olcumleri toplanir. Bulunamayan devre sozlukte yok."""
    a = mssql.ayar()
    if not imtler or not a.hazir():
        return {}
    k = carpan()
    toplam: dict[str, dict[datetime, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
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
            for rrd, olcumler in _bes_dakika(cur, sorted(hedef), bas, bit).items():
                for ci in hedef[rrd]:
                    for zaman, gir, cik in olcumler:
                        h = toplam[ci][zaman]
                        h[0] += gir
                        h[1] += cik
    return {
        ci: {"seri": [(int(z.replace(tzinfo=TR).timestamp()), round(v[0] * k, 2), round(v[1] * k, 2)) for z, v in sorted(zamanlar.items())],
             "eslesme": eslesme[ci]}
        for ci, zamanlar in toplam.items()
    }  # fmt: skip


# --- LookOutEyes ile ayni gosterim (2026-11-27 kullanici: "LookOutEyes ile ayni veriler; fark hata aramaya yol acar") -------------
# LookOutEyes RRD arsivinden cizer: grafik, araligin BASLANGICINI hala kapsayan en ince arsivi kullanir (arsivler simdiden geriye):
# 5 dk x 600 (50 saat), 30 dk x 700 (14,6 gun), 2 saat x 775 (64,6 gun), 1 gun x 797. Noktalar UTC epoch'una hizali adim
# ortalamasi; Avg / Max / Last bu noktalardan. Dogrulama (Ekim 2026, 2 saat): Avg birebir (122,60 / 36,36 M); Max / Last ~%1 icinde
# (LOE kendi 2 saatlik arsivini okur, o arsiv disa aktarilmiyor; panel 5 dakikalik olcumden ayni adimla yeniden hesaplar).
ARSIVLER = ((300, 600), (1800, 700), (7200, 775), (86400, 797))


def cozunurluk(bas_sn: float, simdi_sn: float) -> int:
    """Araligin baslangicini kapsayan en ince arsivin adimi (sn)."""
    geri = max(0.0, simdi_sn - bas_sn)
    return next((adim for adim, satir in ARSIVLER if adim * satir >= geri), ARSIVLER[-1][0])


def konsolide(seri: list[list[float]], bas_sn: float, bit_sn: float, adim: int) -> dict:
    """5 dk seriyi adim ortalamasina indirir (epoch'a hizali); araliktaki noktalar ve LookOutEyes ozeti (son / en yuksek / ortalama)."""
    kova: dict[int, list[float]] = {}
    for t, gir, cik in seri:
        k = int(t // adim) * adim
        if bas_sn <= k <= bit_sn:  # baslangici araliktaki dilimler (LookOutEyes karsilastirmasinda en yakin: Avg birebir)
            h = kova.setdefault(k, [0.0, 0.0, 0])
            h[0] += gir
            h[1] += cik
            h[2] += 1
    noktalar = [[k * 1000, round(v[0] / v[2], 2), round(v[1] / v[2], 2)] for k, v in sorted(kova.items())]

    def ozet(i: int) -> dict | None:
        d = [n[i] for n in noktalar]
        return {"son": d[-1], "en_yuksek": max(d), "ort": round(sum(d) / len(d), 2)} if d else None

    return {"adim": adim, "noktalar": noktalar, "giris": ozet(1), "cikis": ozet(2)}

