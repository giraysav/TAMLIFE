"""TopoMaker: devre envanterinden (CSV/XLSX) ag topolojisi, SPoF tespiti ve il bazli cihaz dagilimi.

Uretim kutucuklar/topoloji (engine.py + servis.py) is kurali tasindi; pandas/networkx/folium yerine duz Python. Sunucu HTML
uretmez: dugum/kenar/il listesi JSON doner, cizim istemcide SVG ile yapilir (hava bosluklu ortamda CDN/karo gerekmez).
Dosya saklanmaz, veritabanina yazilmaz; analiz istek bitince unutulur.

Uretimden bilincli farklar:
  - Bos hucre 'nan' metni olarak dugum adina girmez (uretimde 'SW_<lok>_nan' olusuyordu); bos IP noSW_/noRT_ yedek adini alir.
  - Lokasyon kolonu bulunamazsa bos grafik yerine anlasilir hata doner.
  - Il adi Turkce buyuk harfe cevrilerek eslenir ('istanbul', 'ISTANBUL', 'İstanbul' ayni ildir).
  - SPoF yalniz evet/hayir degil, hangi lokasyon ve BB router'da oldugu da doner.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile

from app.ortak import UygulamaHatasi

AZAMI_BAYT = 10 * 1024 * 1024
AZAMI_SATIR = 5000
BULUT = "ISP_CLOUD"

KABLO_RENKLERI = {
    "SOL Fiber": "#1A6FA6", "SOL RL": "#1A6FA6", "TT Fiber": "#B03A2E", "TT RL": "#B03A2E", "TTME": "#B03A2E",
    "xDSL": "#E67E22", "RL": "#8E44AD", "4.5G": "#6C3483", "Fiber/RL": "#1A6FA6", "LAN": "#7F8C8D",
}

IL_KOORDINAT = {
    "ADANA": (37.0000, 35.3213), "ANKARA": (39.9334, 32.8597), "ANTALYA": (36.8969, 30.7133),
    "BURSA": (40.1824, 29.0671), "DİYARBAKIR": (37.9144, 40.2306), "ERZURUM": (39.9043, 41.2679),
    "ESKİŞEHİR": (39.7767, 30.5206), "GAZİANTEP": (37.0662, 37.3833), "İSTANBUL": (41.0082, 28.9784),
    "İZMİR": (38.4192, 27.1287), "KAYSERİ": (38.7312, 35.4787), "KOCAELİ": (40.8533, 29.8815),
    "KONYA": (37.8667, 32.4833), "MERSİN": (36.8121, 34.6415), "SAMSUN": (41.2867, 36.3300),
    "TRABZON": (41.0015, 39.7178), "ŞANLIURFA": (37.1591, 38.7969),
}

KOLON_TAKMA_ADLARI = {
    "ci": ["ci", "configuration item", "ci adı", "name", "servis", "hizmet"],
    "loc": ["lokasyon_adi", "lokasyon", "location", "site", "yer"],
    "il": ["il", "sehir", "şehir", "city", "province"],
    "bb_host": ["bb_router_hostname", "bb_router", "hostname", "pe_router"],
    "c_no_primary": ["ci no", "ci_no", "circuit no", "devre no"],
    "me_ip": ["uplink sw ip", "me_switch_ip", "switch ip"],
    "rtr_ip": ["wan ip", "wan_ip", "ip adres", "ip_adres", "router wan port ve ip"],
    "devre_alt": ["devre_altyapisi", "altyapi", "altyapı", "infrastructure"],
}


class TopolojiHata(UygulamaHatasi):
    """kod = HTTP durumu."""


def _normal(deger: object) -> str:
    return " ".join(re.sub(r"[^\w]+|_", " ", str(deger).casefold()).split())


def kolon_bul(basliklar: list[str], anahtar: str) -> str:
    """Uretim find_col: once tam eslesme (kolon sirasi sonucu degistirmez), sonra kelime icerme; belirsizlik hatadir."""
    takma = KOLON_TAKMA_ADLARI.get(anahtar, [])
    kolonlar = [(b, _normal(b)) for b in basliklar]
    for ad in takma:
        tam = [b for b, n in kolonlar if n == _normal(ad)]
        if len(tam) > 1:
            raise TopolojiHata(400, f"Birden fazla kolon '{anahtar}' ile eşleşiyor; başlıkları düzenleyin.")
        if tam:
            return tam[0]
    adaylar = {b for b, n in kolonlar for ad in takma if f" {_normal(ad)} " in f" {n} "}
    if len(adaylar) > 1:
        raise TopolojiHata(400, f"'{anahtar}' için belirsiz kolon eşleşmesi; başlıkları düzenleyin.")
    return adaylar.pop() if adaylar else ""


def _katla(metin: str) -> str:
    """Turkce buyuk harf + ASCII katlama: 'Türk Telekom' -> 'TURK TELEKOM', 'izmir'/'IZMIR'/'İzmir' -> 'IZMIR'."""
    buyuk = metin.strip().replace("i", "İ").replace("ı", "I").upper()
    return buyuk.translate(str.maketrans("İŞĞÜÖÇ", "ISGUOC"))


def altyapi_bul(devre_altyapi: str) -> tuple[str, str]:
    """Uretim detect_infra: (altyapi, oncelik). Kural sirasi korunur (RL kontrolu SOLME'den once); metin katlanmis aranir."""
    if devre_altyapi:
        da = _katla(devre_altyapi)
        sade = re.sub(r"[^A-Z0-9]", "", da)
        if any(k in da for k in ("DSL", "ADSL", "VDSL", "XDSL")):
            return "xDSL", "backup"
        if "RL" in sade or "RADYO" in sade:
            return "RL", "backup"
        if "SOLME" in sade or "TELLME" in sade:
            return "SOL Fiber", "primary"
        if any(k in da for k in ("4.5G", "LTE", "4G", "MOBIL")):
            return "4.5G", "backup"
        if "TT" in da or "TURK TELEKOM" in da:
            return "TT Fiber", "primary"
        if "SOL" in da or "SUPERONLINE" in da:
            return "SOL Fiber", "primary"
    return "Fiber/RL", "primary"


_KOORDINAT = {_katla(ad): (ad, k) for ad, k in IL_KOORDINAT.items()}


def _hucre(deger: object) -> str:
    if deger is None:
        return ""
    if isinstance(deger, float) and deger.is_integer():
        deger = int(deger)
    return str(deger).strip()


def tablo_oku(icerik: bytes) -> list[dict[str, str]]:
    """XLSX (ZIP imzasi) ya da ';' ayrimli CSV (once UTF-8, olmazsa latin-1) -> baslikli satirlar."""
    if not icerik:
        raise TopolojiHata(400, "Dosya seçilmedi.")
    if icerik[:4] == b"PK\x03\x04":
        satirlar = _xlsx(icerik)
    else:
        satirlar = _csv(icerik)
    if not satirlar or not any(b for b in satirlar[0]):
        raise TopolojiHata(400, "Dosyada başlık satırı bulunamadı.")
    basliklar = [_hucre(b) for b in satirlar[0]]
    veri = [s for s in satirlar[1:] if any(_hucre(h) for h in s)]
    if len(veri) > AZAMI_SATIR:
        raise TopolojiHata(400, f"Dosya en fazla {AZAMI_SATIR} satır olabilir.")
    return [{b: _hucre(s[i]) if i < len(s) else "" for i, b in enumerate(basliklar) if b} for s in veri]


def _xlsx(icerik: bytes) -> list[list[object]]:
    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        wb = openpyxl.load_workbook(io.BytesIO(icerik), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as e:
        raise TopolojiHata(400, "Dosya okunamadı: CSV veya XLSX dosyası seçin.") from e
    try:
        satirlar: list[list[object]] = []
        for r in wb.worksheets[0].iter_rows(values_only=True):
            if not satirlar and not any(_hucre(v) for v in r):
                continue  # ustteki bos satirlar atlanir
            satirlar.append(list(r))
            if len(satirlar) > AZAMI_SATIR + 1:
                break
        return satirlar
    finally:
        wb.close()


def _csv(icerik: bytes) -> list[list[object]]:
    try:
        metin = icerik.decode("utf-8-sig")
    except UnicodeDecodeError:
        metin = icerik.decode("latin-1")  # yalniz eski ANSI dosyalar icin son care
    if "\x00" in metin:
        raise TopolojiHata(400, "Dosya okunamadı: CSV veya XLSX dosyası seçin.")
    return [list(s) for s in csv.reader(io.StringIO(metin), delimiter=";")]


def analiz(icerik: bytes) -> dict:
    satirlar = tablo_oku(icerik)
    basliklar = list(satirlar[0].keys()) if satirlar else []
    kolon = {k: kolon_bul(basliklar, k) for k in KOLON_TAKMA_ADLARI}
    if not kolon["loc"]:
        raise TopolojiHata(400, "Lokasyon kolonu bulunamadı (Lokasyon, Lokasyon_Adi, Location, Site).")

    def deger(satir: dict[str, str], k: str) -> str:
        return satir.get(kolon[k], "") if kolon[k] else ""

    gruplar: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for sira, s in enumerate(satirlar):
        lok = deger(s, "loc")
        if lok and lok.lower() != "nan":
            gruplar.setdefault(lok, []).append((sira, s))

    dugumler: dict[str, dict] = {BULUT: {"id": BULUT, "tur": "bulut", "etiket": "Turkcell BB", "lokasyon": "", "il": ""}}
    kenarlar: dict[tuple[str, str], dict] = {}
    spof: list[dict] = []

    def kenar(a: str, b: str, altyapi: str, etiket: str, yedek: bool) -> None:
        if (a, b) not in kenarlar and (b, a) not in kenarlar:
            kenarlar[(a, b)] = {"kaynak": a, "hedef": b, "altyapi": altyapi, "etiket": etiket, "yedek": yedek, "renk": KABLO_RENKLERI.get(altyapi, "#7F8C8D")}

    for lok in sorted(gruplar):
        satir_listesi = gruplar[lok]
        il = deger(satir_listesi[0][1], "il")
        bb_altyapi: dict[str, set[str]] = {}
        for sira, s in satir_listesi:
            altyapi, oncelik = altyapi_bul(deger(s, "devre_alt"))
            yedek = oncelik == "backup"
            me_ip, rtr_ip, bb = deger(s, "me_ip"), deger(s, "rtr_ip"), deger(s, "bb_host")
            bb_kisa = bb.split(".")[0]
            if bb_kisa:
                bb_altyapi.setdefault(bb_kisa, set()).add(altyapi)
            sw = f"SW_{lok}_{me_ip or f'noSW_{sira}'}"
            rt = f"R_{lok}_{rtr_ip or f'noRT_{sira}'}"
            dugumler.setdefault(rt, {"id": rt, "tur": "router", "etiket": rtr_ip, "lokasyon": lok, "il": il})
            if altyapi in ("4.5G", "xDSL"):
                kenar(BULUT, rt, altyapi, bb_kisa or altyapi, yedek)
            else:
                dugumler.setdefault(sw, {"id": sw, "tur": "switch", "etiket": me_ip, "lokasyon": lok, "il": il})
                kenar(BULUT, sw, altyapi, bb_kisa or altyapi, yedek)
                kenar(sw, rt, "LAN", "LAN", False)
        for bb, kume in sorted(bb_altyapi.items()):
            if len(kume) >= 2:
                spof.append({"lokasyon": lok, "bb": bb, "altyapilar": sorted(kume)})

    sayac: dict[str, int] = {}
    adlar: dict[str, str] = {}
    for d in dugumler.values():
        if d["tur"] == "bulut" or not d["il"] or _katla(d["il"]) == "BILINMIYOR":
            continue
        anahtar = _katla(d["il"])
        sayac[anahtar] = sayac.get(anahtar, 0) + 1
        adlar.setdefault(anahtar, d["il"])
    sehirler = [
        {"il": _KOORDINAT[a][0], "adet": n, "enlem": _KOORDINAT[a][1][0], "boylam": _KOORDINAT[a][1][1]}
        for a, n in sorted(sayac.items(), key=lambda x: (-x[1], x[0]))
        if a in _KOORDINAT
    ]
    return {
        "spof": bool(spof),
        "spof_noktalari": spof,
        "dugumler": list(dugumler.values()),
        "kenarlar": list(kenarlar.values()),
        "sehirler": sehirler,
        "konumsuz_iller": sorted(adlar[a] for a in sayac if a not in _KOORDINAT),
        "kolonlar": {k: v for k, v in kolon.items() if v},
        "satir": len(satirlar),
        "lokasyon": len(gruplar),
        "renkler": KABLO_RENKLERI,
    }
