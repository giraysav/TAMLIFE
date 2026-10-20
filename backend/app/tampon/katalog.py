"""Kaynak katalogu (ham tampon): ReportDB'deki izinli semalarin nesne -> alt nesne -> sutun agaci ve ornek satirlari
(2026-10-18 kullanici istegi: "tum veriyi almadan hangi veriyi kullanacagimiz anlasilmiyor; agacta goster, adim adim secelim").

Tarama ISCI surecindedir (python -m app.isci reportdb-katalog); panel Oracle'a baglanmaz, yalniz okur. Paneldeki "Yenile" dugmesi
isciyi AYRI surec olarak baslatir (baglanti testindeki gibi; Oracle giris tetikleyicisi panelin calistigi Windows kimligini kabul eder).

Agac kurali (Oracle'da sema icinde hiyerarsi yoktur; ilişkiler veri sozlugunden):
  * ana nesne: es ad (SYNONYM), gorunum (VIEW) ve baska bir nesneye bagli olmayan tablo
  * alt nesne: es adin hedefi ve ayni onekle baslayan esi (ACTIVEALARMS_5DK -> _S1 / _S2 cift tamponu), gorunumun dayandigi
    tablolar (ALL_DEPENDENCIES); bolumlu tablonun bolumleri ayrintida (sayi + en yeni BOLUM_ADEDI)
  * sutun: tip, bos olabilir mi, aciklama + ornek satirlardan profil (doluluk, farkli deger, en sik degerler)
Ornek satir: bolumlu tabloda bolum anahtari DATE ise son ORNEK_SAAT saatin bolumunden (budama), bos gelirse ROWNUM ile genel ornek.
Yalniz SELECT (veri sozlugu + ornek). KISISEL_NESNELER (kisi adi / telefon iceren) yalniz yapisiyla alinir, satiri okunmaz.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import zlib
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ortak import UygulamaHatasi, iso, simdi
from app.tampon import oracle
from app.tampon.models import SourceCatalog, SourceCatalogObject

KAYNAK = "oracle_reportdb"
ORNEK_ADET = 200
ORNEK_SAAT = 1
BOLUM_ADEDI = 12
ORNEK_DEGER = 5  # sutun basina en sik deger
DEGER_UZUNLUK = 300
SAKLANAN = 5  # kaynak basina son N katalog
SORGU_SURESI_MS = 180_000  # arama taramasi: penceredeki satirlarda tum metin sutunlari tek sorguda
# Arama parametreleri (2026-10-18 kullanici: "1- nw_li_cust (kurumsal alarmlar)  2- domain ACCESS ve NOC DESTECH"; 2026-10-19: ACCESS kaldirildi). Domain degeri veride NETWORK sutunundadir
# (tirnakli gelebilir: REPLACE ile temizlenir). Pencere: bolumlu tabloda son `saat` saat, buyuk tabloda ilk `satir_siniri` satir.
VARSAYILAN_PARAMETRE: dict[str, Any] = {
    "ara": "nw_li_cust", "alan": "NETWORK", "degerler": ["NOC DESTECH"], "saat": 6, "satir_siniri": 1_000_000, "ornek": 50, "ham": 3_000_000,
    "baslangic": "2026-01-01 00:00",
}  # fmt: skip
DOMAIN_YOK = "(domain sütunu yok)"
CALISIYOR_DK = 180  # 'receiving' bundan eskiyse coken calisma sayilir (01.01'den bugune tarama dakikalar surer)
ARALIK_SURESI_MS = 1_800_000  # ay dilimi sorgusu (bolum budamali tam tarama) en fazla 30 dk
# Yoklamada gorulmese de arama metnini tasiyabilen CI sutunlari (2026-10-18 taramasi): aralik taramasinda hep aranir
BILINEN_CI_SUTUNLARI = ("MANAGEDOBJECT", "NODE", "NODE1", "ADDITIONALTEXT", "REMOTE_CI", "USERTEXT", "TARGETENTITIES", "CINAME")
HAM_DIZIN = Path(__file__).resolve().parents[2] / "var" / "ham"
HAM_SAKLANAN = 1  # ham satir dosyasi yalniz son hazir katalog icin tutulur (tarama basina ~5 GB; 2026-10-20 kullanici onayi)
HAM_DEGER_UZUNLUK = 1000
DEGER_SAYACI_SINIRI = 200_000
# Sik suzulen / siralanan sutunlar: ham dosyada indekslenir (aday CI sutunlarina ek)
INDEKS_SUTUNLARI = ("EVENTTIME", "ALARMHEADER", "STATE", "PROBLEMSTATUS", "PERCEIVEDSEVERITY", "INFORMATION1", "INFORMATION2",
                    "OCNAME", "CITY", "CLOSEUSERIDENTIFIER", "TTASSIGNED", "ALARMOBJECTOPERATORNO", "IDENTIFIER")  # fmt: skip
DEGER_TABLOSU = "_degerler"  # ham dosyada sutun x domain basina onceden sayilmis degerler (Excel listesi aninda)  # ornek deger sayaci sutun basina en fazla bu kadar satirdan
KISISEL_NESNELER = {"TEMIP.LOG"}  # eski IVR arama gunlugu: kisi adi ve telefon numarasi (docs/reportdb-tablo-kesfi.md)
NESNE_TURLERI = ("TABLE", "VIEW", "MATERIALIZED VIEW", "SYNONYM")
_AD = re.compile(r"^[A-Z0-9_$#]{1,128}$")


class KatalogHata(UygulamaHatasi):
    pass


# --- Isci: Oracle taramasi --------------------------------------------------------------------------------------------
def _sorgu(cur: Any, sql: str, **binds: Any) -> list[dict[str, Any]]:
    cur.execute(sql, binds)
    adlar = [d[0].lower() for d in cur.description]
    return [dict(zip(adlar, (oracle.deger(v) for v in satir), strict=True)) for satir in cur.fetchall()]


def _tip(s: dict[str, Any]) -> str:
    t = s["data_type"] or ""
    if t in ("VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR", "RAW"):
        return f"{t}({s['data_length']})"
    if t == "NUMBER" and s.get("data_precision") is not None:
        return f"NUMBER({s['data_precision']},{s.get('data_scale') or 0})"
    return t


def _ad(ad: str) -> str:
    if not _AD.match(ad or ""):
        raise KatalogHata(400, f"Geçersiz nesne adı: {ad[:40]}")
    return f'"{ad}"'


def _metin(v: Any) -> Any:
    v = oracle.deger(v)
    return v[:DEGER_UZUNLUK] if isinstance(v, str) else v


def profil(basliklar: list[str], satirlar: list[list[Any]]) -> dict[str, dict[str, Any]]:
    """Ornek satirlardan sutun profili: doluluk (%), farkli deger sayisi, en sik ORNEK_DEGER deger (adetiyle)."""
    sonuc: dict[str, dict[str, Any]] = {}
    n = len(satirlar)
    for i, ad in enumerate(basliklar):
        sayac = Counter(str(s[i])[:80] for s in satirlar if s[i] not in (None, ""))
        dolu = sum(sayac.values())
        sonuc[ad] = {
            "doluluk": round(100 * dolu / n, 1) if n else None,
            "farkli": len(sayac),
            "ornekler": [{"deger": d, "adet": a} for d, a in sayac.most_common(ORNEK_DEGER)],
        }
    return sonuc


def _ornek_al(cur: Any, tablo: str, anahtar: str | None, adet: int) -> tuple[list[str], list[list[Any]], str]:
    """(basliklar, satirlar, not). anahtar: DATE bolum anahtari (varsa once son ORNEK_SAAT saat)."""
    denemeler = []
    if anahtar:
        denemeler.append(
            (
                f"SELECT * FROM {tablo} WHERE {_ad(anahtar)} >= SYSDATE - {ORNEK_SAAT}/24 AND {_ad(anahtar)} < SYSDATE + 1 AND ROWNUM <= :n",
                f"son {ORNEK_SAAT} saat ({anahtar})",
            )
        )
    denemeler.append((f"SELECT * FROM {tablo} WHERE ROWNUM <= :n", "ilk satırlar (sırasız)"))
    for sql, aciklama in denemeler:
        cur.execute(oracle.sorgu_temizle(sql), {"n": int(adet)})
        basliklar = [d[0] for d in cur.description]
        satirlar = [[_metin(v) for v in s] for s in cur.fetchall()]
        if satirlar or sql is denemeler[-1][0]:
            return basliklar, satirlar, f"{len(satirlar)} satır · {aciklama}"
    return [], [], ""


def parametre_temizle(p: dict[str, Any] | None) -> dict[str, Any]:
    """Arama parametreleri: ara (metin, kucuk harf), alan (sutun adi), degerler (en fazla 10), saat (1-48), satir_siniri, ornek."""
    p = {**VARSAYILAN_PARAMETRE, **{k: v for k, v in (p or {}).items() if v not in (None, "", [])}}
    ara = str(p["ara"]).strip().lower()[:60]
    alan = str(p["alan"]).strip().upper()
    if not ara or not _AD.match(alan):
        raise KatalogHata(400, "Arama metni ve domain sütunu geçerli olmalı.")
    degerler = [" ".join(str(d).replace("_", " ").split()).upper()[:60] for d in p["degerler"]][:10]
    return {"ara": ara, "alan": alan, "degerler": [d for d in degerler if d], "saat": max(1, min(int(p["saat"]), 48)),
            "satir_siniri": max(1_000, min(int(p["satir_siniri"]), 2_000_000)), "ornek": max(1, min(int(p["ornek"]), 200)),
            "ham": max(1, min(int(p["ham"]), 5_000_000)), "baslangic": _baslangic(p["baslangic"])}  # fmt: skip


def _baslangic(deger: Any) -> str:
    """'YYYY-AA-GG[ SS:DD]' -> 'YYYY-AA-GG SS:DD' (Turkiye saati; Oracle DATE dilimsiz)."""
    metin = str(deger).strip().replace("T", " ")
    for bicim, uzunluk in (("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(metin[:uzunluk], bicim).strftime("%Y-%m-%d %H:%M")  # noqa: DTZ007 - Oracle DATE dilimsiz
        except ValueError:
            continue
    raise KatalogHata(400, "Başlangıç YYYY-AA-GG SS:DD biçiminde olmalı.")


def _sq(ad: str) -> str:
    """SQLite tanimlayicisi (cift tirnak kacisli)."""
    q = chr(34)
    return q + str(ad).replace(q, q * 2) + q


class HamYazici:
    """Ham satirlar ayri SQLite dosyasina (var/ham/katalog_<id>.db): nesne basina gercek sutunlu tablo + "__D" (domain).
    Panel DB'si sismez; panel bu dosyayi salt okur (SQL ile suzer / siralar / sayfalar). Yeniden uretilebilir: gunluk yok."""

    def __init__(self, katalog_id: int):
        HAM_DIZIN.mkdir(parents=True, exist_ok=True)
        self.yol = HAM_DIZIN / f"katalog_{katalog_id}.db"
        self.yol.unlink(missing_ok=True)
        self.bag = sqlite3.connect(str(self.yol))
        self.bag.execute("PRAGMA journal_mode=OFF")
        self.bag.execute("PRAGMA synchronous=OFF")

    @staticmethod
    def tablo_adi(sahip: str, ad: str) -> str:
        return f"t_{sahip}__{ad}"

    def olustur(self, tablo: str, sutunlar: list[str]) -> None:
        self.bag.execute(f"CREATE TABLE IF NOT EXISTS {_sq(tablo)} ({', '.join(_sq(c) for c in ['__D', *sutunlar])})")

    def yaz(self, tablo: str, satirlar: list[list[Any]]) -> None:
        if satirlar:
            self.bag.executemany(f"INSERT INTO {_sq(tablo)} VALUES ({', '.join('?' * len(satirlar[0]))})", satirlar)
            self.bag.commit()

    def indeksle(self, tablo: str, sutunlar: list[str]) -> None:
        ham_hazirla(self.bag, tablo, sutunlar)

    def kapat(self) -> None:
        self.bag.commit()
        self.bag.close()


def ham_hazirla(bag: sqlite3.Connection, tablo: str, adaylar: list[str]) -> None:
    """Ham tabloyu okumaya hazirlar: domain + aday + sik kullanilan sutunlara indeks; her sutun x domain icin deger sayimi
    (en fazla DEGER_LISTESI + 1 deger, farkli deger sayisiyla). Mevcut dosyaya sonradan da uygulanabilir (idempotent)."""
    sutunlar = [x[1] for x in bag.execute(f"PRAGMA table_info({_sq(tablo)})")]
    for c in ["__D", *[c for c in [*adaylar, *INDEKS_SUTUNLARI] if c in sutunlar]]:
        bag.execute(f"CREATE INDEX IF NOT EXISTS {_sq(f'{tablo}__{c}')} ON {_sq(tablo)} ({_sq(c)})")
    bag.execute(f"CREATE TABLE IF NOT EXISTS {_sq(DEGER_TABLOSU)} (tablo TEXT, sutun TEXT, d TEXT, v TEXT, n INTEGER, farkli INTEGER)")
    bag.execute(f"CREATE INDEX IF NOT EXISTS {_sq(DEGER_TABLOSU + '_i')} ON {_sq(DEGER_TABLOSU)} (tablo, sutun, d)")
    bag.execute(f"DELETE FROM {_sq(DEGER_TABLOSU)} WHERE tablo = ?", [tablo])
    domainler = [d for (d,) in bag.execute(f"SELECT DISTINCT {_sq('__D')} FROM {_sq(tablo)}")]
    for c in sutunlar:
        if c == "__D":
            continue
        deger = f"COALESCE(NULLIF(CAST({_sq(c)} AS TEXT), ''), ?)"
        for d in domainler:
            satirlar = bag.execute(
                f"SELECT {deger} AS v, COUNT(*) FROM {_sq(tablo)} WHERE {_sq('__D')} = ? GROUP BY v ORDER BY COUNT(*) DESC LIMIT ?",
                [BOS, d, DEGER_LISTESI * 2],
            ).fetchall()
            farkli = len(satirlar) if len(satirlar) < DEGER_LISTESI * 2 else bag.execute(
                f"SELECT COUNT(DISTINCT {deger}) FROM {_sq(tablo)} WHERE {_sq('__D')} = ?", [BOS, d]).fetchone()[0]  # fmt: skip
            bag.executemany(
                f"INSERT INTO {_sq(DEGER_TABLOSU)} VALUES (?, ?, ?, ?, ?, ?)", [(tablo, c, d, v, n, farkli) for v, n in satirlar]
            )
    bag.commit()


def _ay_dilimleri(bas: str) -> list[tuple[str, str]]:
    """'YYYY-AA-GG SS:DD' -> [(alt, ust)] ay ay (son dilimin ustu None = SYSDATE + 1)."""
    alt = datetime.strptime(bas, "%Y-%m-%d %H:%M")  # noqa: DTZ007
    bugun = datetime.now()  # noqa: DTZ005 - Oracle SYSDATE ile ayni (sunucu yerel saati)
    dilimler: list[tuple[str, str]] = []
    while alt <= bugun:
        ust = datetime(alt.year + (alt.month == 12), alt.month % 12 + 1, 1)  # noqa: DTZ001
        dilimler.append((alt.strftime("%Y-%m-%d %H:%M"), "" if ust > bugun else ust.strftime("%Y-%m-%d %H:%M")))
        alt = ust
    return dilimler


def _aralik_cek(
    cur: Any, tablo: str, sahip_ad: tuple[str, str], tarih: str | None, bolumlu: bool, alan: str | None, adaylar: list[str],
    p: dict[str, Any], yazici: HamYazici | None, nabiz: Any,
) -> dict[str, Any]:  # fmt: skip
    """Baslangictan bugune domain + arama metnini iceren TUM satirlar (bolumlu tabloda ay ay budamali); ham dosyaya yazar.
    Donus: {pencere, gruplar: {domain: {isabet, sutunlar}}, ornek_degerler, ham_tablo, ham_satir, dolu_sutunlar, basliklar}."""
    dexpr = f"REPLACE(t.{_ad(alan)}, '\"', '')" if alan else f"'{DOMAIN_YOK}'"
    deger_bind = {f"d{i}": d for i, d in enumerate(p["degerler"])}
    kosul = [f"({' OR '.join(f'INSTR(LOWER(t.{_ad(c)}), :ara) > 0' for c in adaylar)})"]
    if alan and deger_bind:
        kosul.append(f"{dexpr} IN ({', '.join(':' + k for k in deger_bind)})")
    if tarih:
        dilimler = _ay_dilimleri(p["baslangic"]) if bolumlu else [(p["baslangic"], "")]
        pencere = f"{p['baslangic'][:10].split('-')[2]}.{p['baslangic'][5:7]}.{p['baslangic'][:4]} {p['baslangic'][11:]} → bugün ({tarih})"
    else:
        dilimler, pencere = [("", "")], "tüm tablo (tarih sütunu yok)"
    tablo_adi = HamYazici.tablo_adi(*sahip_ad)
    gruplar: dict[str, dict[str, Any]] = {}
    degerler: dict[str, Counter] = defaultdict(Counter)
    basliklar: list[str] = []
    dolu: set[int] = set()
    toplam = 0
    for alt, ust in dilimler:
        zaman = []
        binds: dict[str, Any] = {"ara": p["ara"], **(deger_bind if alan else {})}
        if tarih:
            zaman.append(f"t.{_ad(tarih)} >= TO_DATE(:alt, 'YYYY-MM-DD HH24:MI')")
            binds["alt"] = alt
            if ust:
                zaman.append(f"t.{_ad(tarih)} < TO_DATE(:ust, 'YYYY-MM-DD HH24:MI')")
                binds["ust"] = ust
            else:
                zaman.append(f"t.{_ad(tarih)} < SYSDATE + 1")
        nabiz(f"{sahip_ad[0]}.{sahip_ad[1]} · {alt[:7] if alt else 'tüm'}")
        sql = f'SELECT {dexpr} AS "__D", t.* FROM {tablo} t WHERE {" AND ".join(zaman + kosul)}'
        cur.arraysize = 5_000
        cur.execute(oracle.sorgu_temizle(sql), binds)
        if not basliklar:
            basliklar = [x[0] for x in cur.description][1:]
            if yazici is not None:
                yazici.olustur(tablo_adi, basliklar)
        aday_ix = [(c, basliklar.index(c)) for c in adaylar if c in basliklar]
        while True:
            blok = cur.fetchmany(5_000)
            if not blok:
                break
            satirlar = []
            for s in blok:
                d = str(s[0] if s[0] is not None else "(boş)")
                deg = [oracle.deger(v) for v in s[1:]]
                deg = [v[:HAM_DEGER_UZUNLUK] if isinstance(v, str) else v for v in deg]
                g = gruplar.setdefault(d, {"satir": None, "isabet": 0, "sutunlar": {}})
                g["isabet"] += 1
                for c, i in aday_ix:
                    v = deg[i]
                    if isinstance(v, str) and p["ara"] in v.lower():
                        g["sutunlar"][c] = g["sutunlar"].get(c, 0) + 1
                        if sum(degerler[c].values()) < DEGER_SAYACI_SINIRI:
                            degerler[c][v[:120]] += 1
                dolu.update(i for i, v in enumerate(deg) if v not in (None, ""))
                satirlar.append([d, *deg])
            if yazici is not None:
                yazici.yaz(tablo_adi, satirlar)
            toplam += len(satirlar)
            if toplam >= p["ham"]:
                break
        if toplam >= p["ham"]:
            pencere += f" · ilk {p['ham']:,} satırda kesildi".replace(",", ".")
            break
    if yazici is not None and basliklar:
        yazici.indeksle(tablo_adi, [c for c in adaylar if c in basliklar])
    for d in p["degerler"] if alan else [DOMAIN_YOK]:
        gruplar.setdefault(d, {"satir": None, "isabet": 0, "sutunlar": {}})
    return {
        "pencere": pencere, "gruplar": gruplar, "ham_tablo": tablo_adi if yazici is not None and basliklar else "", "ham_satir": toplam,
        "dolu_sutunlar": [basliklar[i] for i in sorted(dolu)], "basliklar": basliklar,
        "ornek_degerler": {c: [{"deger": v, "adet": n} for v, n in cnt.most_common(ORNEK_DEGER)] for c, cnt in degerler.items()},
    }  # fmt: skip


def _sikistir(veri: Any) -> bytes:
    return zlib.compress(json.dumps(veri, ensure_ascii=False, default=str).encode("utf-8"), 6)


def _arama(
    cur: Any, tablo: str, kolonlar: list[dict[str, Any]], tarih_anahtari: str | None, satir: int | None, p: dict[str, Any],
    sahip_ad: tuple[str, str] = ("", ""), yazici: HamYazici | None = None, nabiz: Any = None,
) -> tuple[dict[str, Any], dict[str, list[list[Any]]], list[str]]:  # fmt: skip
    """Pencerede domain (alan) basina satir sayisi ve her metin sutununda `ara` isabeti (tek sorgu), ardindan domain basina
    `ara` iceren ornek satirlar. Donus: (ozet, {domain: satirlar}, basliklar)."""
    metin = [s["ad"] for s in kolonlar if s["tip"].startswith(("VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR"))]
    alan = p["alan"] if any(s["ad"] == p["alan"] for s in kolonlar) else None
    if tarih_anahtari:
        kipler = ["zaman", "sinir"]
    elif satir is not None and satir <= p["satir_siniri"]:
        kipler = ["tam"]
    else:
        kipler = ["sinir"]
    dexpr = f"REPLACE({_ad(alan)}, '\"', '')" if alan else f"'{DOMAIN_YOK}'"
    deger_bind = {f"d{i}": d for i, d in enumerate(p["degerler"])}
    nerede = f" WHERE {dexpr} IN ({', '.join(':' + k for k in deger_bind)})" if alan and deger_bind else ""

    def kaynak(kip: str) -> tuple[str, dict[str, Any], str]:
        if kip == "zaman":
            k = _ad(tarih_anahtari or "")
            return (f"(SELECT * FROM {tablo} WHERE {k} >= SYSDATE - :saat/24 AND {k} < SYSDATE + 1)", {"saat": p["saat"]},
                    f"son {p['saat']} saat ({tarih_anahtari})")  # fmt: skip
        if kip == "sinir":
            return (
                f"(SELECT * FROM {tablo} WHERE ROWNUM <= :sinir)",
                {"sinir": p["satir_siniri"]},
                f"ilk {p['satir_siniri']:,} satır".replace(",", "."),
            )
        return tablo, {}, "tüm tablo"

    isabet = [f"INSTR(LOWER({_ad(c)}), :ara) > 0" for c in metin]
    secim = [
        f"{dexpr} AS D",
        "COUNT(*) AS N",
        f"SUM(CASE WHEN {' OR '.join(isabet)} THEN 1 ELSE 0 END) AS HERHANGI" if isabet else "0 AS HERHANGI",
    ]
    secim += [f'SUM(CASE WHEN {x} THEN 1 ELSE 0 END) AS "H{i}"' for i, x in enumerate(isabet)]
    gruplar: dict[str, dict[str, Any]] = {}
    pencere, kaynak_sql, kaynak_bind = "", tablo, {}
    for kip in kipler:
        kaynak_sql, kaynak_bind, pencere = kaynak(kip)
        binds = {**kaynak_bind, **(deger_bind if nerede else {}), **({"ara": p["ara"]} if isabet else {})}
        cur.execute(oracle.sorgu_temizle(f"SELECT {', '.join(secim)} FROM {kaynak_sql}{nerede} GROUP BY {dexpr}"), binds)
        gruplar = {}
        for r in cur.fetchall():
            d = str(r[0] if r[0] is not None else "(boş)")
            gruplar[d] = {"satir": int(r[1] or 0), "isabet": int(r[2] or 0),
                          "sutunlar": {c: int(h or 0) for c, h in zip(metin, r[3:], strict=True) if h}}  # fmt: skip
        if sum(g["satir"] for g in gruplar.values()):
            break
    for d in p["degerler"] if alan else [DOMAIN_YOK]:
        gruplar.setdefault(d, {"satir": 0, "isabet": 0, "sutunlar": {}})
    if yazici is not None or nabiz is not None:
        # Aralik: yoklamada isabet goren sutunlar + bilinen CI sutunlari (yalniz bunlarda aranir; 102 sutunda aramak cok pahali)
        gorulen = {c for g in gruplar.values() for c in g["sutunlar"]}
        adaylar = [c for c in metin if c in gorulen or c in BILINEN_CI_SUTUNLARI]
        tarih = tarih_anahtari or next((s["ad"] for s in kolonlar if s["ad"] == "EVENTTIME" and s["tip"].startswith("DATE")), None)
        if not adaylar:
            return ({"ara": p["ara"], "pencere": "aday sütun yok", "domain_sutunu": alan or "", "gruplar": {}, "yoklama": gruplar,
                     "ornek_degerler": {}, "ham_tablo": "", "ham_satir": 0, "dolu_sutunlar": []}, {}, [])  # fmt: skip
        a = _aralik_cek(cur, tablo, sahip_ad, tarih, bool(tarih_anahtari), alan, adaylar, p, yazici, nabiz or (lambda _m: None))
        basliklar = a.pop("basliklar")
        return {"ara": p["ara"], "domain_sutunu": alan or "", "yoklama": gruplar, **a}, {}, basliklar
    ornekler: dict[str, list[list[Any]]] = {}
    basliklar: list[str] = []
    degerler: dict[str, Counter] = defaultdict(Counter)
    for d, g in gruplar.items():
        if not g["isabet"]:
            continue
        hc = list(g["sutunlar"])
        kosul = " OR ".join(f"INSTR(LOWER({_ad(c)}), :ara) > 0" for c in hc)
        dk = f"{dexpr} = :d AND " if alan else ""
        # Ham tampon: domain + arama metnini iceren satirlarin hepsi (en fazla `ham`); panel bunlari suzer / siralar (Excel filtresi)
        binds = {**kaynak_bind, "ara": p["ara"], "n": p["ham"], **({"d": d} if alan else {})}
        cur.arraysize = 2_000
        cur.execute(oracle.sorgu_temizle(f"SELECT * FROM {kaynak_sql} WHERE {dk}({kosul}) AND ROWNUM <= :n"), binds)
        basliklar = [x[0] for x in cur.description]
        ornekler[d] = [[_metin(v) for v in s] for s in cur.fetchall()]
        for c in hc:
            i = basliklar.index(c)
            degerler[c].update(str(s[i])[:120] for s in ornekler[d] if s[i] is not None and p["ara"] in str(s[i]).lower())
    ozet = {"ara": p["ara"], "pencere": pencere, "domain_sutunu": alan or "", "gruplar": gruplar,
            "ornek_degerler": {c: [{"deger": v, "adet": n} for v, n in cnt.most_common(ORNEK_DEGER)] for c, cnt in degerler.items()}}  # fmt: skip
    return ozet, ornekler, basliklar


def tara(
    db: Session,
    kullanici: str,
    semalar: list[str] | None = None,
    adet: int = ORNEK_ADET,
    kaynak: str = KAYNAK,
    parametre: dict[str, Any] | None = None,
    kalp: Any = None,
) -> SourceCatalog:
    """Izinli semalari tarar ve yeni katalog yazar. Hata olursa katalog 'failed' (mesaj maskeli) ve hata yeniden firlatilir."""
    p = parametre_temizle(parametre)
    kat = SourceCatalog(source_key=kaynak, status="receiving", started_at=simdi(), created_by=kullanici[:120], summary={}, error="")
    db.add(kat)
    db.commit()
    t0 = time.time()
    a = oracle.ayar(kaynak)
    yazici = HamYazici(kat.id)

    def nabiz(mesaj: str) -> None:  # panel ilerlemeyi gosterir; isci kilidini tazeler (cagiran verirse)
        kat.summary = {"ilerleme": mesaj[:200], "sure_sn": round(time.time() - t0)}
        db.commit()
        if kalp is not None:
            kalp()

    try:
        nesneler = _tara(a, semalar, adet, p, yazici, nabiz)
        yazici.kapat()
        for n in nesneler:
            db.add(SourceCatalogObject(catalog_id=kat.id, **n))
        kat.status, kat.finished_at = "ready", simdi()
        kat.summary = {
            "semalar": sorted({n["owner"] for n in nesneler}),
            "nesne": len(nesneler),
            "sutun": sum(len(n["columns"]) for n in nesneler),
            "ornek_adet": adet,
            "parametreler": p,
            "ham_satir": sum((n["details"].get("arama") or {}).get("ham_satir", 0) for n in nesneler),
            "sure_sn": round(time.time() - t0, 1),
        }
        db.commit()
    except Exception as e:
        db.rollback()
        try:
            yazici.kapat()
        except sqlite3.Error:
            pass
        yazici.yol.unlink(missing_ok=True)
        kat = db.get(SourceCatalog, kat.id)
        kat.status, kat.finished_at = "failed", simdi()
        kat.error = oracle.hata_metni(e, a.gizliler())[0][:500] if not isinstance(e, UygulamaHatasi) else str(e.mesaj)[:500]
        db.commit()
        raise
    _eskileri_sil(db, kaynak)
    return kat


def _eskileri_sil(db: Session, kaynak: str) -> None:
    eski = db.scalars(
        select(SourceCatalog.id).where(SourceCatalog.source_key == kaynak).order_by(SourceCatalog.id.desc()).offset(SAKLANAN)
    ).all()
    if eski:
        db.execute(delete(SourceCatalogObject).where(SourceCatalogObject.catalog_id.in_(eski)))  # SQLite'ta FK cascade kapali olabilir
        db.execute(delete(SourceCatalog).where(SourceCatalog.id.in_(eski)))
        db.commit()
    tut = {f"katalog_{i}.db" for i in db.scalars(
        select(SourceCatalog.id).where(SourceCatalog.source_key == kaynak, SourceCatalog.status == "ready").order_by(SourceCatalog.id.desc()).limit(HAM_SAKLANAN)
    )}  # fmt: skip
    if HAM_DIZIN.is_dir():
        for f in HAM_DIZIN.glob("katalog_*.db"):
            if f.name not in tut:
                f.unlink(missing_ok=True)


def _tara(
    a: oracle.OracleKaynak, semalar: list[str] | None, adet: int, p: dict[str, Any], yazici: HamYazici | None = None, nabiz: Any = None
) -> list[dict[str, Any]]:
    oracledb = oracle._oracledb()

    def _lob(cursor: Any, meta: Any) -> Any:
        if meta.type_code in (oracledb.DB_TYPE_CLOB, oracledb.DB_TYPE_NCLOB):
            return cursor.var(oracledb.DB_TYPE_LONG, arraysize=cursor.arraysize)
        if meta.type_code is oracledb.DB_TYPE_BLOB:
            return cursor.var(oracledb.DB_TYPE_LONG_RAW, arraysize=cursor.arraysize)
        return None

    with a._baglan(oracledb) as conn:
        conn.call_timeout = ARALIK_SURESI_MS
        conn.outputtypehandler = _lob
        with conn.cursor() as cur:
            izin = _sorgu(cur, "SELECT OWNER, TABLE_NAME FROM USER_TAB_PRIVS_RECD WHERE PRIVILEGE IN ('SELECT', 'READ')")
            sahipler = sorted({r["owner"] for r in izin})
            if semalar:
                sahipler = [s for s in sahipler if s in {x.upper() for x in semalar}]
            sonuc: list[dict[str, Any]] = []
            for sahip in sahipler:
                sonuc += _sema(cur, sahip, adet, p, yazici, nabiz)
            return sonuc


def _sema(
    cur: Any, sahip: str, adet: int, p: dict[str, Any] | None = None, yazici: HamYazici | None = None, nabiz: Any = None
) -> list[dict[str, Any]]:
    p = p or parametre_temizle(None)
    turler = ", ".join(f"'{t}'" for t in NESNE_TURLERI)
    nesneler = _sorgu(
        cur,
        f"SELECT OBJECT_NAME, OBJECT_TYPE FROM ALL_OBJECTS WHERE OWNER = :o AND OBJECT_TYPE IN ({turler}) AND OBJECT_NAME NOT LIKE 'BIN$%'",
        o=sahip,
    )
    es_adlar = {
        r["synonym_name"]: r
        for r in _sorgu(
            cur,
            "SELECT OWNER, SYNONYM_NAME, TABLE_OWNER, TABLE_NAME FROM ALL_SYNONYMS WHERE OWNER = :o OR (OWNER = 'PUBLIC' AND TABLE_OWNER = :o)",
            o=sahip,
        )
    }
    sutun: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in _sorgu(
        cur,
        "SELECT TABLE_NAME, COLUMN_ID, COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE, NULLABLE FROM ALL_TAB_COLUMNS "
        "WHERE OWNER = :o ORDER BY TABLE_NAME, COLUMN_ID",
        o=sahip,
    ):
        sutun[r["table_name"]].append({"ad": r["column_name"], "tip": _tip(r), "bos_olabilir": r["nullable"] == "Y", "aciklama": ""})
    for r in _sorgu(
        cur, "SELECT TABLE_NAME, COLUMN_NAME, COMMENTS FROM ALL_COL_COMMENTS WHERE OWNER = :o AND COMMENTS IS NOT NULL", o=sahip
    ):
        for s in sutun.get(r["table_name"], []):
            if s["ad"] == r["column_name"]:
                s["aciklama"] = str(r["comments"])[:300]
    yorum = {
        r["table_name"]: str(r["comments"])[:1000]
        for r in _sorgu(cur, "SELECT TABLE_NAME, COMMENTS FROM ALL_TAB_COMMENTS WHERE OWNER = :o AND COMMENTS IS NOT NULL", o=sahip)
    }
    ist = {
        r["table_name"]: r
        for r in _sorgu(
            cur,
            "SELECT TABLE_NAME, NUM_ROWS, TO_CHAR(LAST_ANALYZED, 'YYYY-MM-DD') AS LA, PARTITIONED FROM ALL_TABLES WHERE OWNER = :o",
            o=sahip,
        )
    }
    anahtar: dict[str, list[str]] = defaultdict(list)
    for r in _sorgu(
        cur,
        "SELECT NAME, COLUMN_NAME FROM ALL_PART_KEY_COLUMNS WHERE OWNER = :o AND OBJECT_TYPE = 'TABLE' ORDER BY NAME, COLUMN_POSITION",
        o=sahip,
    ):
        anahtar[r["name"]].append(r["column_name"])
    bolum: dict[str, dict[str, Any]] = {}
    for r in _sorgu(
        cur,
        "SELECT TABLE_NAME, PARTITION_NAME, PARTITION_POSITION, NUM_ROWS, TO_CHAR(LAST_ANALYZED, 'YYYY-MM-DD') AS LA, "
        "COUNT(*) OVER (PARTITION BY TABLE_NAME) AS ADET, ROW_NUMBER() OVER (PARTITION BY TABLE_NAME ORDER BY PARTITION_POSITION DESC) AS RN "
        "FROM ALL_TAB_PARTITIONS WHERE TABLE_OWNER = :o",
        o=sahip,
    ):
        b = bolum.setdefault(r["table_name"], {"adet": r["adet"], "son": []})
        if r["rn"] <= BOLUM_ADEDI:
            b["son"].append({"ad": r["partition_name"], "sira": r["partition_position"], "satir": r["num_rows"], "analiz": r["la"] or ""})
    indeks: dict[str, dict[str, list[str]]] = defaultdict(dict)
    for r in _sorgu(
        cur,
        "SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME FROM ALL_IND_COLUMNS WHERE TABLE_OWNER = :o ORDER BY INDEX_NAME, COLUMN_POSITION",
        o=sahip,
    ):
        indeks[r["table_name"]].setdefault(r["index_name"], []).append(r["column_name"])
    bagim: dict[str, list[str]] = defaultdict(list)
    for r in _sorgu(
        cur,
        "SELECT NAME, REFERENCED_OWNER, REFERENCED_NAME FROM ALL_DEPENDENCIES WHERE OWNER = :o AND TYPE IN ('VIEW', 'MATERIALIZED VIEW') "
        "AND REFERENCED_TYPE IN ('TABLE', 'VIEW', 'SYNONYM')",
        o=sahip,
    ):
        bagim[r["name"]].append(f"{r['referenced_owner']}.{r['referenced_name']}")

    adlar = {r["object_name"]: r["object_type"] for r in nesneler}
    for ad in es_adlar:
        adlar.setdefault(ad, "SYNONYM")
    ust: dict[str, str] = {}
    for ad, s in es_adlar.items():  # es ad -> hedefi ve ayni onekli esi
        if s["table_owner"] == sahip and s["table_name"] in adlar:
            ust.setdefault(s["table_name"], ad)
        for diger, diger_tur in adlar.items():
            if diger != ad and diger.startswith(ad + "_") and diger_tur != "SYNONYM":
                ust.setdefault(diger, ad)
    for ad, refs in bagim.items():
        for ref in refs:
            o, n = ref.split(".", 1)
            if o == sahip and n in adlar and n != ad:
                ust.setdefault(n, ad)

    cikti = []
    for ad, tur in sorted(adlar.items()):
        es = es_adlar.get(ad)
        hedef_sahip, hedef = (es["table_owner"], es["table_name"]) if es else (sahip, ad)
        kolonlar = [dict(s) for s in sutun.get(hedef, [])] if hedef_sahip == sahip else []
        bilgi = ist.get(hedef, {})
        ayrinti: dict[str, Any] = {}
        if es:
            ayrinti["es_ad"] = {"sahip": es["owner"], "hedef": f"{es['table_owner']}.{es['table_name']}"}
        if anahtar.get(hedef):
            ayrinti["bolum_anahtari"] = anahtar[hedef]
        if bolum.get(hedef) and not es:
            ayrinti["bolumler"] = bolum[hedef]
        if indeks.get(hedef) and not es:
            ayrinti["indeksler"] = indeks[hedef]
        if bagim.get(ad):
            ayrinti["dayandigi"] = bagim[ad]
        kayit: dict[str, Any] = {
            "owner": sahip, "name": ad, "kind": tur, "parent": f"{sahip}.{ust[ad]}" if ad in ust else "",
            "row_count": bilgi.get("num_rows"), "analyzed": bilgi.get("la") or "", "comment": yorum.get(hedef, ""),
            "details": ayrinti, "sample_columns": [], "sample_rows": 0, "sample_note": "", "sample_data": None,
        }  # fmt: skip
        if f"{sahip}.{ad}" in KISISEL_NESNELER or f"{hedef_sahip}.{hedef}" in KISISEL_NESNELER:
            kayit["sample_note"] = "Kişisel veri (kişi adı / telefon) içerir: yalnız yapısı alındı, satır okunmadı."
        else:
            tablo = _ad(ad) if es and es["owner"] == "PUBLIC" else f"{_ad(sahip)}.{_ad(ad)}"
            tarih_anahtari = next(
                (k for k in anahtar.get(hedef, []) if any(s["ad"] == k and s["tip"].startswith(("DATE", "TIMESTAMP")) for s in kolonlar)),
                None,
            )
            gruplu: dict[str, list[list[Any]]] = {}
            satirlar: list[list[Any]] = []
            try:
                basliklar, satirlar, not_ = _ornek_al(cur, tablo, tarih_anahtari, adet)
                kayit.update(sample_columns=basliklar, sample_rows=len(satirlar), sample_note=not_)
                pr = profil(basliklar, satirlar)
                for s in kolonlar:
                    s.update(pr.get(s["ad"], {}))
            except Exception as e:  # noqa: BLE001 - tek nesnenin ornegi alinamazsa katalog yine yazilir
                kayit["sample_note"] = f"Örnek alınamadı: {type(e).__name__}"[:300]
            if not es:  # es adin verisi hedef tabloda aranir (ayni satirlar iki kez taranmaz)
                try:
                    ayrinti["arama"], gruplu, gruplu_baslik = _arama(
                        cur, tablo, kolonlar, tarih_anahtari, bilgi.get("num_rows"), p, (sahip, ad), yazici, nabiz
                    )
                    if gruplu_baslik:
                        kayit["sample_columns"] = gruplu_baslik  # ham tablo sutun sirasi (okuyucu bunu kullanir)
                except Exception as e:  # noqa: BLE001
                    ayrinti["arama"] = {"hata": f"Arama yapılamadı: {type(e).__name__}"[:200]}
            kayit["sample_data"] = _sikistir({"genel": satirlar, "gruplar": gruplu})
        kayit["columns"] = kolonlar
        cikti.append(kayit)
    return cikti


# --- Panel: okuma ---------------------------------------------------------------------------------------------------
def _katalog_satiri(k: SourceCatalog) -> dict[str, Any]:
    return {"id": k.id, "durum": k.status, "baslangic": iso(k.started_at), "bitis": iso(k.finished_at), "olusturan": k.created_by,
            "ozet": k.summary or {}, "hata": k.error}  # fmt: skip


def _calisiyor(db: Session, kaynak: str) -> SourceCatalog | None:
    esik = simdi() - timedelta(minutes=CALISIYOR_DK)
    return db.scalars(
        select(SourceCatalog)
        .where(SourceCatalog.source_key == kaynak, SourceCatalog.status == "receiving", SourceCatalog.started_at >= esik)
        .order_by(SourceCatalog.id.desc())
        .limit(1)
    ).first()


def agac(db: Session, kaynak: str = KAYNAK) -> dict[str, Any]:
    """Son hazir katalogun agaci (sutunlar ve ornekler YOK: nesne acilinca nesne() ile gelir) + calisan / son basarisiz tarama."""
    son = db.scalars(select(SourceCatalog).where(SourceCatalog.source_key == kaynak).order_by(SourceCatalog.id.desc()).limit(1)).first()
    hazir = db.scalars(
        select(SourceCatalog)
        .where(SourceCatalog.source_key == kaynak, SourceCatalog.status == "ready")
        .order_by(SourceCatalog.id.desc())
        .limit(1)
    ).first()
    calisan = _calisiyor(db, kaynak)
    sonuc: dict[str, Any] = {
        "kaynak": kaynak,
        "katalog": _katalog_satiri(hazir) if hazir else None,
        "calisiyor": calisan is not None,
        "ilerleme": (calisan.summary or {}).get("ilerleme", "") if calisan is not None else "",
        "ilerleme_sn": (calisan.summary or {}).get("sure_sn", 0) if calisan is not None else 0,
        "son_hata": son.error if son is not None and son.status == "failed" else "",
        "semalar": [],
    }
    if hazir is None:
        return sonuc
    satirlar = db.scalars(
        select(SourceCatalogObject)
        .where(SourceCatalogObject.catalog_id == hazir.id)
        .order_by(SourceCatalogObject.owner, SourceCatalogObject.name)
    ).all()
    dugum: dict[str, dict[str, Any]] = {}
    for n in satirlar:
        d = n.details or {}
        dugum[f"{n.owner}.{n.name}"] = {
            "id": n.id, "ad": n.name, "tur": n.kind, "satir": n.row_count, "analiz": n.analyzed, "aciklama": n.comment,
            "sutun_sayisi": len(n.columns or []), "ornek_satir": n.sample_rows, "ornek_notu": n.sample_note,
            "es_ad": (d.get("es_ad") or {}).get("hedef", ""), "bolum_anahtari": d.get("bolum_anahtari", []),
            "bolum_sayisi": (d.get("bolumler") or {}).get("adet", 0), "alt": [],
        }  # fmt: skip
    semalar: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for n in satirlar:
        d = dugum[f"{n.owner}.{n.name}"]
        if n.parent and n.parent in dugum:
            dugum[n.parent]["alt"].append(d)
        else:
            semalar[n.owner].append(d)
    sira = {"SYNONYM": 0, "VIEW": 1, "MATERIALIZED VIEW": 1, "TABLE": 2}
    for liste in semalar.values():
        liste.sort(key=lambda x: (sira.get(x["tur"], 3), -(x["satir"] or 0) if not x["alt"] else -(10**12), x["ad"]))
    sonuc["semalar"] = [{"ad": s, "nesneler": semalar[s]} for s in sorted(semalar, key=lambda s: (s != "TEMIP", s))]
    sonuc["parametreler"], sonuc["parametre_agaci"] = _parametre_agaci(satirlar, (hazir.summary or {}).get("parametreler") or {})
    return sonuc


def _parametre_agaci(satirlar: Sequence[SourceCatalogObject], p: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Domain -> tablo -> `ara` iceren sutunlar (isabet sirali). Domain sutunu olmayan tablolar ayri dalda; isabetsiz tablolar
    'eslesmeyen' listesinde (agacta dal acmaz)."""
    if not p:
        return {}, []
    adlar = {f"{n.owner}.{n.name}": n for n in satirlar}
    dallar: dict[str, list[dict[str, Any]]] = defaultdict(list)
    eslesmeyen: list[str] = []
    for n in satirlar:
        a = (n.details or {}).get("arama")
        if not a or a.get("hata"):
            if a and a.get("hata"):
                eslesmeyen.append(f"{n.owner}.{n.name} ({a['hata']})")
            continue
        ust = adlar.get(n.parent)
        bulundu = False
        for d, g in (a.get("gruplar") or {}).items():
            if not g["isabet"] and (not g["satir"] or d == DOMAIN_YOK):
                continue  # domain sutunu olmayan tablo yalniz isabet varsa dal acar
            bulundu = bulundu or bool(g["isabet"])
            dallar[d].append({
                "id": n.id, "sahip": n.owner, "ad": n.name, "ust": ust.name if ust is not None and ust.kind == "SYNONYM" else "",
                "pencere": a.get("pencere", ""), "satir": g["satir"], "isabet": g["isabet"],
                "oran": round(100 * g["isabet"] / g["satir"], 1) if g["satir"] else 0.0,
                "sutunlar": [{"ad": c, "isabet": h, "oran": round(100 * h / g["satir"], 1) if g["satir"] else 0.0}
                             for c, h in sorted(g["sutunlar"].items(), key=lambda x: -x[1])],
            })  # fmt: skip
        if not bulundu:
            eslesmeyen.append(f"{n.owner}.{n.name}")
    sira = [*p.get("degerler", []), DOMAIN_YOK]
    agac_ = [
        {"domain": d, "tablolar": sorted(dallar[d], key=lambda t: (-t["isabet"], -(t["satir"] or 0), t["ad"])),
         "isabet": sum(t["isabet"] for t in dallar[d]), "satir": sum(t["satir"] or 0 for t in dallar[d])}
        for d in sira + sorted(set(dallar) - set(sira)) if d in dallar or d in p.get("degerler", [])
    ]  # fmt: skip
    return {**p, "eslesmeyen": sorted(eslesmeyen)}, agac_


def nesne(db: Session, nesne_id: int) -> dict[str, Any]:
    n = db.get(SourceCatalogObject, nesne_id)
    if n is None:
        raise KatalogHata(404, "Katalog nesnesi bulunamadı.")
    return {"id": n.id, "sahip": n.owner, "ad": n.name, "tur": n.kind, "ust": n.parent, "satir": n.row_count, "analiz": n.analyzed,
            "aciklama": n.comment, "sutunlar": n.columns or [], "ayrinti": n.details or {}, "ornek_satir": n.sample_rows,
            "ornek_notu": n.sample_note}  # fmt: skip


# --- Panel: ham veri okuyucu (Excel benzeri filtre) -------------------------------------------------------------------
VERI_SAYFA_EN_COK = 500
DEGER_LISTESI = 1_000  # sutun acilir listesinde en fazla farkli deger
BOS = "(Boş)"
_VERI_ONBELLEK: dict[tuple, tuple[list[str], list[list[Any]]]] = {}
_VERI_KILIT = threading.Lock()


def _ham(db: Session, nesne_id: int, domainler: list[str]) -> tuple[SourceCatalogObject, list[str], list[list[Any]]]:
    """Secili domainlerin ham satirlari (birlesik). Nesne kimligi tarama basina tekil: onbellek eskimez; en fazla 6 kayit."""
    n = db.get(SourceCatalogObject, nesne_id)
    if n is None:
        raise KatalogHata(404, "Katalog nesnesi bulunamadı.")
    anahtar = (n.id, tuple(sorted(domainler)))
    with _VERI_KILIT:
        if anahtar in _VERI_ONBELLEK:
            return n, *_VERI_ONBELLEK[anahtar]
    veri = json.loads(zlib.decompress(n.sample_data).decode("utf-8")) if n.sample_data else {}
    gruplar = veri.get("gruplar", {}) if isinstance(veri, dict) else {}
    secili = domainler or list(gruplar)
    satirlar = [s for d in secili for s in gruplar.get(d, [])]
    basliklar = list(n.sample_columns or [])
    with _VERI_KILIT:
        if len(_VERI_ONBELLEK) >= 6:
            _VERI_ONBELLEK.pop(next(iter(_VERI_ONBELLEK)))
        _VERI_ONBELLEK[anahtar] = (basliklar, satirlar)
    return n, basliklar, satirlar


def _hucre(v: Any) -> str:
    return BOS if v is None or v == "" else str(v)


def _filtre_coz(filtre: str) -> dict[str, list[str]]:
    if not filtre:
        return {}
    try:
        f = json.loads(filtre)
    except ValueError:
        raise KatalogHata(400, "Filtre okunamadı.") from None
    if not isinstance(f, dict) or len(f) > 200 or not all(isinstance(k, str) and isinstance(v, list) for k, v in f.items()):
        raise KatalogHata(400, "Filtre biçimi geçersiz.")
    return {k: [str(x) for x in v[:DEGER_LISTESI]] for k, v in f.items()}


def _suz(basliklar: list[str], satirlar: list[list[Any]], filtre: dict[str, list[str]], q: str, haric: str = "") -> list[list[Any]]:
    """Sutun filtresi (deger listesi; haric: acilir listesi hesaplanan sutun kendi filtresiyle daraltilmaz) + tum sutunlarda metin."""
    kosullar = [(basliklar.index(c), set(v)) for c, v in filtre.items() if c in basliklar and c != haric]
    q = q.strip().lower()
    sonuc = []
    for s in satirlar:
        if all(_hucre(s[i]) in izin for i, izin in kosullar) and (not q or any(v is not None and q in str(v).lower() for v in s)):
            sonuc.append(s)
    return sonuc


def _sirala_anahtar(v: Any) -> tuple:
    if v is None or v == "":
        return (2, 0, "")
    if isinstance(v, (int, float)):
        return (0, v, "")
    return (1, 0, str(v).lower())


def veri(
    db: Session,
    nesne_id: int,
    domainler: list[str],
    sayfa: int = 1,
    adet: int = 100,
    q: str = "",
    filtre: str = "",
    sirala: str = "",
    yon: str = "asc",
) -> dict[str, Any]:
    """Ham tamponda suzulmus / siralanmis sayfa. Secili domainlerde tamamen bos sutunlar gizlenir (isabetli sutunlar basta)."""
    dosya = _ham_dosyasi(db, nesne_id)
    if dosya is not None:
        return _veri_sql(*dosya, domainler, sayfa, adet, q, filtre, sirala, yon)
    n, basliklar, satirlar = _ham(db, nesne_id, domainler)
    f = _filtre_coz(filtre)
    suzulen = _suz(basliklar, satirlar, f, q)
    if sirala in basliklar:
        i = basliklar.index(sirala)
        suzulen = sorted(suzulen, key=lambda s: _sirala_anahtar(s[i]), reverse=yon == "desc")
    dolu = [i for i in range(len(basliklar)) if any(s[i] not in (None, "") for s in satirlar)]
    arama = (n.details or {}).get("arama") or {}
    isabetli: list[str] = []
    for g in (arama.get("gruplar") or {}).values():
        isabetli += [c for c in g.get("sutunlar", {}) if c not in isabetli]
    sira = [basliklar.index(c) for c in isabetli if c in basliklar and basliklar.index(c) in dolu]
    sira += [i for i in dolu if i not in sira]
    adet = max(1, min(int(adet), VERI_SAYFA_EN_COK))
    son = max(1, -(-len(suzulen) // adet))
    sayfa = max(1, min(int(sayfa), son))
    parca = suzulen[(sayfa - 1) * adet : sayfa * adet]
    return {
        "id": n.id, "ad": f"{n.owner}.{n.name}", "pencere": arama.get("pencere", ""), "ara": arama.get("ara", ""),
        "domainler": domainler, "sutunlar": [basliklar[i] for i in sira], "isabetli": [c for c in isabetli if c in basliklar],
        "gizlenen_bos": len(basliklar) - len(dolu), "toplam_ham": len(satirlar), "toplam": len(suzulen), "sayfa": sayfa, "adet": adet,
        "satirlar": [[s[i] for i in sira] for s in parca], "filtreli": sorted(c for c in f if c in basliklar),
    }  # fmt: skip


def degerler(db: Session, nesne_id: int, domainler: list[str], sutun: str, q: str = "", filtre: str = "", ara: str = "") -> dict[str, Any]:
    """Excel filtresi acilir listesi: sutunun farkli degerleri ve adetleri; diger sutunlarin filtresi ve genel arama uygulanmis."""
    dosya = _ham_dosyasi(db, nesne_id)
    if dosya is not None:
        return _degerler_sql(*dosya, domainler, sutun, q, filtre, ara)
    _, basliklar, satirlar = _ham(db, nesne_id, domainler)
    if sutun not in basliklar:
        raise KatalogHata(404, "Sütun bulunamadı.")
    i = basliklar.index(sutun)
    sayac = Counter(_hucre(s[i]) for s in _suz(basliklar, satirlar, _filtre_coz(filtre), q, haric=sutun))
    ara = ara.strip().lower()
    liste = [(v, c) for v, c in sayac.items() if not ara or ara in v.lower()]
    liste.sort(key=lambda x: (x[0] == BOS, -x[1], x[0].lower()))
    return {
        "sutun": sutun,
        "farkli": len(sayac),
        "degerler": [{"deger": v, "adet": c} for v, c in liste[:DEGER_LISTESI]],
        "kesildi": len(liste) > DEGER_LISTESI,
    }


# --- Ham dosya (var/ham/katalog_<id>.db) uzerinde SQL ---------------------------------------------------------------
def _ham_dosyasi(db: Session, nesne_id: int) -> tuple[SourceCatalogObject, Path, str] | None:
    n = db.get(SourceCatalogObject, nesne_id)
    if n is None:
        raise KatalogHata(404, "Katalog nesnesi bulunamadı.")
    tablo = ((n.details or {}).get("arama") or {}).get("ham_tablo") or ""
    if not tablo:
        return None
    yol = HAM_DIZIN / f"katalog_{n.catalog_id}.db"
    if not yol.is_file():
        raise KatalogHata(410, "Bu taramanın ham verisi silinmiş (yalnız son taramalar saklanır): kataloğu yenileyin.")
    return n, yol, tablo


def _baglan_ro(yol: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{yol.as_uri()}?mode=ro", uri=True, check_same_thread=False)


def _esler(degerler: list[str]) -> list[Any]:
    """Filtre degerleri: metin + (sayisal gorunuyorsa) sayi bicimi. Ham dosyada sutun turu yok (sayi INTEGER/REAL, metin TEXT saklanir);
    CAST'siz karsilastirma indeks kullanir."""
    sonuc: list[Any] = []
    for v in degerler:
        sonuc.append(v)
        if re.fullmatch(r"-?\d{1,18}", v):
            sonuc.append(int(v))
        elif re.fullmatch(r"-?\d+\.\d+", v):
            sonuc.append(float(v))
    return sonuc


def _kosul_sql(sutunlar: list[str], domainler: list[str], filtre: dict[str, list[str]], q: str, haric: str = "") -> tuple[str, list[Any]]:
    parca, arg = [], []
    if domainler:
        parca.append(f"{_sq('__D')} IN ({', '.join('?' * len(domainler))})")
        arg += domainler
    for c, degerler in filtre.items():
        if c not in sutunlar or c == haric:
            continue
        dolu = [v for v in degerler if v != BOS]
        alt = []
        if dolu:
            esler = _esler(dolu)
            alt.append(f"{_sq(c)} IN ({', '.join('?' * len(esler))})")
            arg += esler
        if BOS in degerler:
            alt.append(f"({_sq(c)} IS NULL OR {_sq(c)} = '')")
        parca.append("(" + " OR ".join(alt) + ")" if alt else "0")
    if q.strip():
        desen = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        parca.append("(" + " OR ".join(f"CAST({_sq(c)} AS TEXT) LIKE ? ESCAPE '\\'" for c in sutunlar) + ")")
        arg += [desen] * len(sutunlar)
    return (" WHERE " + " AND ".join(parca)) if parca else "", arg


def _sutun_sirasi(n: SourceCatalogObject) -> tuple[list[str], list[str], list[str]]:
    """(tum sutunlar, gosterilecek: isabetli basta + dolu, isabetli)."""
    arama = (n.details or {}).get("arama") or {}
    tum = list(n.sample_columns or [])
    dolu = [c for c in tum if c in set(arama.get("dolu_sutunlar") or tum)]
    isabetli: list[str] = []
    for g in (arama.get("gruplar") or {}).values():
        isabetli += [c for c in g.get("sutunlar", {}) if c not in isabetli and c in tum]
    return tum, [*[c for c in isabetli if c in dolu], *[c for c in dolu if c not in isabetli]], isabetli


def _veri_sql(
    n: SourceCatalogObject, yol: Path, tablo: str, domainler: list[str], sayfa: int, adet: int, q: str, filtre: str, sirala: str, yon: str
) -> dict[str, Any]:
    tum, goster, isabetli = _sutun_sirasi(n)
    f = _filtre_coz(filtre)
    nerede, arg = _kosul_sql(goster, domainler, f, q)
    dom, dom_arg = _kosul_sql(goster, domainler, {}, "")
    adet = max(1, min(int(adet), VERI_SAYFA_EN_COK))
    bag = _baglan_ro(yol)
    try:
        toplam_ham = bag.execute(f"SELECT COUNT(*) FROM {_sq(tablo)}{dom}", dom_arg).fetchone()[0]
        toplam = bag.execute(f"SELECT COUNT(*) FROM {_sq(tablo)}{nerede}", arg).fetchone()[0] if nerede != dom else toplam_ham
        son = max(1, -(-toplam // adet))
        sayfa = max(1, min(int(sayfa), son))
        sira = ""
        if sirala in goster:
            sira = f" ORDER BY ({_sq(sirala)} IS NULL OR {_sq(sirala)} = ''), {_sq(sirala)} {'DESC' if yon == 'desc' else 'ASC'}"
        secim = ", ".join(_sq(c) for c in goster)
        satirlar = bag.execute(
            f"SELECT {secim} FROM {_sq(tablo)}{nerede}{sira} LIMIT ? OFFSET ?", [*arg, adet, (sayfa - 1) * adet]
        ).fetchall()
    finally:
        bag.close()
    arama = (n.details or {}).get("arama") or {}
    return {
        "id": n.id, "ad": f"{n.owner}.{n.name}", "pencere": arama.get("pencere", ""), "ara": arama.get("ara", ""), "domainler": domainler,
        "sutunlar": goster, "isabetli": isabetli, "gizlenen_bos": len(tum) - len(goster), "toplam_ham": toplam_ham, "toplam": toplam,
        "sayfa": sayfa, "adet": adet, "satirlar": [list(s) for s in satirlar], "filtreli": sorted(c for c in f if c in goster),
    }  # fmt: skip


def _degerler_hazir(yol: Path, tablo: str, sutun: str, domainler: list[str], ara: str) -> dict[str, Any] | None:
    """Onceden sayilmis degerler (ham_hazirla); dosyada tablo yoksa None (canli sayima duser)."""
    bag = _baglan_ro(yol)
    try:
        if not bag.execute("SELECT 1 FROM sqlite_master WHERE name = ?", [DEGER_TABLOSU]).fetchone():
            return None
        kosul, arg = "tablo = ? AND sutun = ?", [tablo, sutun]
        if domainler:
            kosul += f" AND d IN ({', '.join('?' * len(domainler))})"
            arg += domainler
        if not bag.execute(f"SELECT 1 FROM {_sq(DEGER_TABLOSU)} WHERE tablo = ? LIMIT 1", [tablo]).fetchone():
            return None
        suz, suz_arg = "", []
        if ara.strip():
            suz = " AND v LIKE ? ESCAPE '\\'"
            suz_arg = ["%" + ara.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"]
        satirlar = bag.execute(
            f"SELECT v, SUM(n) FROM {_sq(DEGER_TABLOSU)} WHERE {kosul}{suz} GROUP BY v ORDER BY v = ?, SUM(n) DESC, LOWER(v) LIMIT ?",
            [*arg, *suz_arg, BOS, DEGER_LISTESI + 1],
        ).fetchall()
        farkli = bag.execute(
            f"SELECT COALESCE(SUM(f), 0) FROM (SELECT MAX(farkli) AS f FROM {_sq(DEGER_TABLOSU)} WHERE {kosul} GROUP BY d)", arg
        ).fetchone()[0]
        kesik = bag.execute(f"SELECT COUNT(*) FROM {_sq(DEGER_TABLOSU)} WHERE {kosul}", arg).fetchone()[0] < farkli
    finally:
        bag.close()
    return {"sutun": sutun, "farkli": farkli, "degerler": [{"deger": v, "adet": c} for v, c in satirlar[:DEGER_LISTESI]],
            "kesildi": len(satirlar) > DEGER_LISTESI or kesik}  # fmt: skip


def _degerler_sql(
    n: SourceCatalogObject, yol: Path, tablo: str, domainler: list[str], sutun: str, q: str, filtre: str, ara: str
) -> dict[str, Any]:
    _, goster, _ = _sutun_sirasi(n)
    if sutun not in goster:
        raise KatalogHata(404, "Sütun bulunamadı.")
    f = {c: v for c, v in _filtre_coz(filtre).items() if c != sutun and c in goster}
    if not f and not q.strip():
        hazir = _degerler_hazir(yol, tablo, sutun, domainler, ara)
        if hazir is not None:
            return hazir
    nerede, arg = _kosul_sql(goster, domainler, f, q, haric=sutun)
    deger = f"COALESCE(NULLIF(CAST({_sq(sutun)} AS TEXT), ''), ?)"
    ic = f"SELECT {deger} AS v FROM {_sq(tablo)}{nerede}"
    dis_arg: list[Any] = [BOS, *arg]
    suz = ""
    if ara.strip():
        suz = " WHERE v LIKE ? ESCAPE '\\'"
        dis_arg.append("%" + ara.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    bag = _baglan_ro(yol)
    try:
        satirlar = bag.execute(
            f"SELECT v, COUNT(*) FROM ({ic}){suz} GROUP BY v ORDER BY v = ?, COUNT(*) DESC, LOWER(v) LIMIT ?",
            [*dis_arg, BOS, DEGER_LISTESI + 1],
        ).fetchall()
        farkli = bag.execute(f"SELECT COUNT(DISTINCT v) FROM ({ic})", [BOS, *arg]).fetchone()[0]
    finally:
        bag.close()
    return {
        "sutun": sutun,
        "farkli": farkli,
        "degerler": [{"deger": v, "adet": c} for v, c in satirlar[:DEGER_LISTESI]],
        "kesildi": len(satirlar) > DEGER_LISTESI,
    }


def ornek(db: Session, nesne_id: int, grup: str = "") -> dict[str, Any]:
    n = db.get(SourceCatalogObject, nesne_id)
    if n is None:
        raise KatalogHata(404, "Katalog nesnesi bulunamadı.")
    veri = json.loads(zlib.decompress(n.sample_data).decode("utf-8")) if n.sample_data else []
    if isinstance(veri, list):  # ilk katalog bicimi: yalniz genel ornek
        veri = {"genel": veri, "gruplar": {}}
    if grup:
        satirlar = veri.get("gruplar", {}).get(grup, [])
        arama = (n.details or {}).get("arama") or {}
        not_ = f"{grup} · {arama.get('pencere', '')} · '{arama.get('ara', '')}' içeren {len(satirlar)} satır"
    else:
        satirlar, not_ = veri.get("genel", []), n.sample_note
    return {"id": n.id, "ad": f"{n.owner}.{n.name}", "basliklar": n.sample_columns or [], "satirlar": satirlar, "not": not_, "grup": grup}


def _ayri_baslat(komut: list[str], dizin: Path, gunluk: Path) -> None:
    """Isciyi panelin SUREC AGACININ DISINDA baslatir. Canli gorev betigi paneli `Start-Process -Wait` ile calistirir; PS 5.1 bu
    beklemeyi tum alt surecler icin yapar: panelin alt sureci olan ~1 saatlik tarama, panel yeniden baslatmasini tarama bitene
    kadar engelledi (2026-10-18 19:40, panel ~2 dk kapali kaldi). Windows'ta WMI Win32_Process.Create ile (ust surec WmiPrvSE),
    digerlerinde yeni oturumla baslatilir. Isci ayarlarini backend/.env'den kendisi okur."""
    if os.name != "nt":
        with open(gunluk, "a", encoding="utf-8") as f:
            subprocess.Popen(komut, cwd=str(dizin), stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        return
    satir = subprocess.list2cmdline(komut)
    cmd = f'cmd.exe /c "{satir} >> "{gunluk}" 2>&1"'
    ps = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$env:TL_KOMUT; CurrentDirectory=$env:TL_DIZIN}; "
          "exit [int]$r.ReturnValue")  # fmt: skip
    ortam = {**os.environ, "TL_KOMUT": cmd, "TL_DIZIN": str(dizin)}  # komut ortamdan: PowerShell tirnak kacisi gerekmez
    p = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], env=ortam, capture_output=True, timeout=60,
                       creationflags=subprocess.CREATE_NO_WINDOW, check=False)  # fmt: skip
    if p.returncode != 0:
        raise KatalogHata(500, f"Tarama işçisi başlatılamadı (WMI kodu {p.returncode}).")


def yenile(db: Session, kullanici: str, kaynak: str = KAYNAK) -> dict[str, Any]:
    """Isciyi ayri surecte baslatir (panel Oracle'a baglanmaz). Calisan tarama varsa yenisi baslamaz."""
    a = oracle.ayar(kaynak)
    if not a.ENABLED:
        raise KatalogHata(409, f"{a.kaynak.enabled_key}=true değil; ReportDB'ye bağlanılmaz.")
    if _calisiyor(db, kaynak) is not None:
        return {"basladi": False, "calisiyor": True}
    backend = Path(__file__).resolve().parents[2]
    gunluk = backend / "var" / "logs"
    gunluk.mkdir(parents=True, exist_ok=True)
    kisi = re.sub(r"[^A-Za-z0-9._@-]", "", kullanici)[:120] or "panel"
    _ayri_baslat([sys.executable, "-m", "app.isci", "reportdb-katalog", "--kullanici", kisi], backend, gunluk / "isci_katalog.log")
    return {"basladi": True, "calisiyor": True}
