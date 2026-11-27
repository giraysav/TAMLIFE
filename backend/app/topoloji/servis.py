# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""TopoMaker: devre envanterinden (CSV/XLSX) ag topolojisi, SPoF tespiti ve il bazli cihaz dagilimi.

Uretim kutucuklar/topoloji (engine.py + servis.py) is kurali tasindi; pandas/networkx/folium yerine duz Python. Sunucu HTML
uretmez: dugum/kenar/il listesi JSON doner, cizim istemcide SVG ile yapilir (hava bosluklu ortamda CDN/karo gerekmez).
Dosya saklanmaz, veritabanina yazilmaz; analiz istek bitince unutulur.

Uretimden bilincli farklar:
  - Bos hucre 'nan' metni olarak dugum adina girmez (uretimde 'SW_<lok>_nan' olusuyordu); bos IP noSW_/noRT_ yedek adini alir.
  - Lokasyon kolonu bulunamazsa bos grafik yerine anlasilir hata doner.
  - Il adi Turkce buyuk harfe cevrilerek eslenir ('istanbul', 'ISTANBUL', 'İstanbul' ayni ildir).
  - Her devre ayri kenar olarak korunur; tek devre, ortak BB, ortak erisim cihazi ve ortak musteri router'i ayri risklerdir.
  - XLSX acilmis boyutu ve CSV/XLSX satir-kolon sinirlari ayrıştırma sirasinda uygulanir.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile

from app.ortak import UygulamaHatasi

AZAMI_BAYT = 10 * 1024 * 1024
AZAMI_SATIR = 5000
AZAMI_SUTUN = 100
AZAMI_ACILMIS_BAYT = 64 * 1024 * 1024
AZAMI_ZIP_UYESI = 1000
AZAMI_FIZIKSEL_SATIR = 50_000
BULUT = "ISP_CLOUD"

KABLO_RENKLERI = {
    "SOL Fiber": "#1A6FA6", "SOL RL": "#1A6FA6", "TT Fiber": "#B03A2E", "TT RL": "#B03A2E", "TTME": "#B03A2E",
    "xDSL": "#E67E22", "RL": "#8E44AD", "4.5G": "#6C3483", "Fiber/RL": "#1A6FA6", "Bilinmiyor": "#64748B", "LAN": "#7F8C8D",
}

IL_KOORDINAT = {
    "ADANA": (37.0000, 35.3213), "ANKARA": (39.9334, 32.8597), "ANTALYA": (36.8969, 30.7133),
    "BURSA": (40.1824, 29.0671), "DİYARBAKIR": (37.9144, 40.2306), "ERZURUM": (39.9043, 41.2679),
    "ESKİŞEHİR": (39.7767, 30.5206), "GAZİANTEP": (37.0662, 37.3833), "İSTANBUL": (41.0082, 28.9784),
    "İZMİR": (38.4192, 27.1287), "KAYSERİ": (38.7312, 35.4787), "KOCAELİ": (40.8533, 29.8815),
    "KONYA": (37.8667, 32.4833), "MERSİN": (36.8121, 34.6415), "SAMSUN": (41.2867, 36.3300),
    "TRABZON": (41.0015, 39.7178), "ŞANLIURFA": (37.1591, 38.7969),
    "ADIYAMAN": (37.7648, 38.2786), "AFYONKARAHİSAR": (38.7507, 30.5567), "AĞRI": (39.7191, 43.0503),
    "AMASYA": (40.6499, 35.8353), "ARTVİN": (41.1828, 41.8183), "AYDIN": (37.8560, 27.8416),
    "BALIKESİR": (39.6484, 27.8826), "BİLECİK": (40.0567, 30.0665), "BİNGÖL": (38.8853, 40.4983),
    "BİTLİS": (38.4006, 42.1095), "BOLU": (40.5760, 31.5788), "BURDUR": (37.4613, 30.0665),
    "ÇANAKKALE": (40.1553, 26.4142), "ÇANKIRI": (40.6013, 33.6134), "ÇORUM": (40.5506, 34.9556),
    "DENİZLİ": (37.7765, 29.0864), "DÜZCE": (40.8438, 31.1565), "EDİRNE": (41.6771, 26.5557),
    "ELAZIĞ": (38.6810, 39.2264), "ERZİNCAN": (39.7500, 39.5000), "GİRESUN": (40.9128, 38.3895),
    "GÜMÜŞHANE": (40.4386, 39.5086), "HAKKARİ": (37.5744, 43.7408), "HATAY": (36.2025, 36.1606),
    "IĞDIR": (39.8880, 44.0048), "ISPARTA": (37.7648, 30.5566), "KAHRAMANMARAŞ": (37.5753, 36.9228),
    "KARABÜK": (41.2061, 32.6204), "KARAMAN": (37.1759, 33.2287), "KARS": (40.6013, 43.0975),
    "KASTAMONU": (41.3887, 33.7827), "KIRIKKALE": (39.8468, 33.5153), "KIRKLARELİ": (41.7333, 27.2167),
    "KIRŞEHİR": (39.1425, 34.1709), "KİLİS": (36.7184, 37.1212), "KÜTAHYA": (39.4167, 29.9833),
    "MALATYA": (38.3552, 38.3095), "MANİSA": (38.6191, 27.4289), "MARDİN": (37.3212, 40.7245),
    "MUĞLA": (37.2153, 28.3636), "MUŞ": (38.9462, 41.7539), "NEVŞEHİR": (38.6244, 34.7239),
    "NİĞDE": (37.9667, 34.6833), "ORDU": (40.9839, 37.8764), "OSMANİYE": (37.0742, 36.2478),
    "RİZE": (41.0201, 40.5234), "SAKARYA": (40.7569, 30.3781), "SİİRT": (37.9333, 41.9500),
    "SİNOP": (42.0231, 35.1531), "SİVAS": (39.7477, 37.0179), "ŞIRNAK": (37.4187, 42.4918),
    "TEKİRDAĞ": (40.9833, 27.5167), "TOKAT": (40.3167, 36.5500), "TUNCELİ": (39.1079, 39.5401),
    "UŞAK": (38.6823, 29.4082), "VAN": (38.4891, 43.4089), "YALOVA": (40.6550, 29.2769),
    "YOZGAT": (39.8200, 34.8044), "ZONGULDAK": (41.4564, 31.7987), "AKSARAY": (38.3687, 34.0370),
    "BARTIN": (41.6344, 32.3375), "BATMAN": (37.8812, 41.1351), "BAYBURT": (40.2552, 40.2249),
    "ARDAHAN": (41.1105, 42.7022),
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
    metin = unicodedata.normalize("NFKD", str(deger).casefold())
    metin = "".join(harf for harf in metin if not unicodedata.combining(harf))
    metin = metin.translate(str.maketrans("ıþð", "isg"))
    return " ".join(re.sub(r"[^\w]+|_", " ", metin).split())


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
    """Altyapi metnini siniflandirir; bos veya tanimsiz deger varsayim yapmak yerine Bilinmiyor doner."""
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
    return "Bilinmiyor", "unknown"


_KOORDINAT = {_katla(ad): (ad, k) for ad, k in IL_KOORDINAT.items()}


def _hucre(deger: object) -> str:
    if deger is None:
        return ""
    if isinstance(deger, float) and deger.is_integer():
        deger = int(deger)
    return str(deger).strip()


def tablo_oku(icerik: bytes) -> list[dict[str, str]]:
    """XLSX ya da UTF-8/Windows-1254 CSV'yi sinirli ve benzersiz baslikli satirlara donusturur."""
    if not icerik:
        raise TopolojiHata(400, "Dosya seçilmedi.")
    if icerik[:4] == b"PK\x03\x04":
        satirlar = _xlsx(icerik)
    else:
        satirlar = _csv(icerik)
    if not satirlar or not any(b for b in satirlar[0]):
        raise TopolojiHata(400, "Dosyada başlık satırı bulunamadı.")
    basliklar = [_hucre(b) for b in satirlar[0]]
    if len(basliklar) > AZAMI_SUTUN:
        raise TopolojiHata(400, f"Dosya en fazla {AZAMI_SUTUN} kolon olabilir.")
    tekrar = sorted({b for b in basliklar if b and sum(_normal(x) == _normal(b) for x in basliklar if x) > 1})
    if tekrar:
        raise TopolojiHata(400, "Aynı isimli kolonlar birden fazla kullanılamaz: " + ", ".join(tekrar))
    veri = [s for s in satirlar[1:] if any(_hucre(h) for h in s)]
    if len(veri) > AZAMI_SATIR:
        raise TopolojiHata(400, f"Dosya en fazla {AZAMI_SATIR} satır olabilir.")
    return [{b: _hucre(s[i]) if i < len(s) else "" for i, b in enumerate(basliklar) if b} for s in veri]


def _xlsx(icerik: bytes) -> list[list[object]]:
    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        with zipfile.ZipFile(io.BytesIO(icerik)) as arsiv:
            uyeler = arsiv.infolist()
            acilmis = sum(u.file_size for u in uyeler)
            if len(uyeler) > AZAMI_ZIP_UYESI or acilmis > AZAMI_ACILMIS_BAYT:
                raise TopolojiHata(400, "XLSX dosyasının açılmış boyutu güvenli sınırı aşıyor.")
            if any(u.file_size > 1024 * 1024 and u.compress_size and u.file_size / u.compress_size > 250 for u in uyeler):
                raise TopolojiHata(400, "XLSX dosyasının sıkıştırma oranı güvenli sınırı aşıyor.")
        wb = openpyxl.load_workbook(io.BytesIO(icerik), read_only=True, data_only=True)
    except TopolojiHata:
        raise
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as e:
        raise TopolojiHata(400, "Dosya okunamadı: CSV veya XLSX dosyası seçin.") from e
    try:
        satirlar: list[list[object]] = []
        for fiziksel, r in enumerate(wb.worksheets[0].iter_rows(values_only=True), start=1):
            if fiziksel > AZAMI_FIZIKSEL_SATIR:
                raise TopolojiHata(400, "XLSX dosyasında çok fazla boş veya biçimlendirilmiş satır var.")
            if not satirlar and not any(_hucre(v) for v in r):
                continue  # ustteki bos satirlar atlanir
            if not any(_hucre(v) for v in r):
                continue
            if len(r) > AZAMI_SUTUN:
                raise TopolojiHata(400, f"Dosya en fazla {AZAMI_SUTUN} kolon olabilir.")
            satirlar.append(list(r))
            if len(satirlar) > AZAMI_SATIR + 1:
                break
        return satirlar
    except TopolojiHata:
        raise
    except Exception as e:
        raise TopolojiHata(400, "XLSX dosyası okunurken hata oluştu.") from e
    finally:
        wb.close()


def _csv(icerik: bytes) -> list[list[object]]:
    try:
        metin = icerik.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            metin = icerik.decode("cp1254")
        except UnicodeDecodeError:
            metin = icerik.decode("latin-1")  # son care; eski Bati Avrupa ANSI
    if "\x00" in metin:
        raise TopolojiHata(400, "Dosya okunamadı: CSV veya XLSX dosyası seçin.")
    # Satir siniri okurken uygulanir (tumunu listeye almak siniri asan dosyayi da bellege aliyordu); bos satir sayilmaz.
    satirlar: list[list[object]] = []
    dolu = 0
    ilk = next((satir for satir in metin.splitlines() if satir.strip()), "")
    ayrac = max((";", ",", "\t"), key=lambda a: ilk.count(a))
    try:
        for s in csv.reader(io.StringIO(metin), delimiter=ayrac):
            if len(s) > AZAMI_SUTUN:
                raise TopolojiHata(400, f"Dosya en fazla {AZAMI_SUTUN} kolon olabilir.")
            if any(len(_hucre(h)) > 32_768 for h in s):
                raise TopolojiHata(400, "CSV dosyasında izin verilenden uzun bir alan var.")
            if not any(_hucre(h) for h in s):
                continue
            satirlar.append(list(s))
            dolu += 1
            if dolu > AZAMI_SATIR + 1:
                break
    except csv.Error as e:
        raise TopolojiHata(400, "CSV dosyası okunamadı; alan veya tırnak yapısını kontrol edin.") from e
    return satirlar


def analiz(icerik: bytes) -> dict:
    satirlar = tablo_oku(icerik)
    basliklar = list(satirlar[0].keys()) if satirlar else []
    kolon = {k: kolon_bul(basliklar, k) for k in KOLON_TAKMA_ADLARI}
    if not kolon["loc"]:
        raise TopolojiHata(400, "Lokasyon kolonu bulunamadı (Lokasyon, Lokasyon_Adi, Location, Site).")

    def deger(satir: dict[str, str], k: str) -> str:
        return satir.get(kolon[k], "") if kolon[k] else ""

    gruplar: dict[str, dict] = {}
    for sira, s in enumerate(satirlar):
        lok = deger(s, "loc")
        if lok and lok.lower() != "nan":
            grup = gruplar.setdefault(_katla(lok), {"ad": lok, "satirlar": []})
            grup["satirlar"].append((sira, s))
    if not gruplar:
        raise TopolojiHata(400, "Dosyada dolu bir lokasyon kaydı bulunamadı.")

    dugumler: dict[str, dict] = {BULUT: {"id": BULUT, "tur": "bulut", "etiket": "Turkcell BB", "lokasyon": "", "il": ""}}
    kenarlar: list[dict] = []
    spof: list[dict] = []
    uyarilar: list[str] = []

    def kenar(kimlik: str, a: str, b: str, altyapi: str, etiket: str, yedek: bool, devre: str) -> None:
        kenarlar.append({
            "id": kimlik, "kaynak": a, "hedef": b, "altyapi": altyapi, "etiket": etiket,
            "yedek": yedek, "devre": devre, "renk": KABLO_RENKLERI.get(altyapi, "#7F8C8D"),
        })

    for grup in sorted(gruplar.values(), key=lambda g: _katla(g["ad"])):
        lok = grup["ad"]
        satir_listesi = grup["satirlar"]
        iller = [deger(s, "il") for _, s in satir_listesi if deger(s, "il")]
        il = iller[0] if iller else ""
        if len({_katla(i) for i in iller}) > 1:
            uyarilar.append(f"{lok}: birden fazla il bilgisi bulundu; ilk değer kullanıldı.")
        devreler: dict[str, dict] = {}
        for sira, s in satir_listesi:
            altyapi, oncelik = altyapi_bul(deger(s, "devre_alt"))
            yedek = oncelik == "backup"
            me_ip, rtr_ip, bb = deger(s, "me_ip"), deger(s, "rtr_ip"), deger(s, "bb_host")
            bb_kisa = bb.split(".")[0]
            devre = deger(s, "c_no_primary") or deger(s, "ci") or f"Satır {sira + 2}"
            devre_anahtari = _katla(devre) if (deger(s, "c_no_primary") or deger(s, "ci")) else f"SATIR_{sira}"
            sw = f"SW_{lok}_{me_ip or f'noSW_{sira}'}"
            rt = f"R_{lok}_{rtr_ip or f'noRT_{sira}'}"
            dugumler.setdefault(rt, {"id": rt, "tur": "router", "etiket": rtr_ip, "lokasyon": lok, "il": il})
            if altyapi in ("4.5G", "xDSL"):
                kenar(f"K{sira}:WAN", BULUT, rt, altyapi, bb_kisa or altyapi, yedek, devre)
                erisim_dugumu = ""
            else:
                dugumler.setdefault(sw, {"id": sw, "tur": "switch", "etiket": me_ip, "lokasyon": lok, "il": il})
                kenar(f"K{sira}:WAN", BULUT, sw, altyapi, bb_kisa or altyapi, yedek, devre)
                kenar(f"K{sira}:LAN", sw, rt, "LAN", "LAN", False, devre)
                erisim_dugumu = me_ip
            devreler.setdefault(devre_anahtari, {
                "ad": devre, "bb": bb_kisa, "erisim": erisim_dugumu, "router": rtr_ip, "altyapi": altyapi,
            })

        kayitlar = list(devreler.values())
        if len(kayitlar) < 2:
            tek = kayitlar[0] if kayitlar else {"ad": "—", "bb": "—", "altyapi": "Bilinmiyor"}
            spof.append({
                "lokasyon": lok, "bb": tek["bb"] or "—", "altyapilar": [tek["altyapi"]],
                "neden": "tek_devre", "devreler": [tek["ad"]],
            })
        for alan, neden in (("bb", "ortak_bb"), ("erisim", "ortak_erisim"), ("router", "ortak_router")):
            ortaklar: dict[str, list[dict]] = {}
            for kayit in kayitlar:
                if kayit[alan]:
                    ortaklar.setdefault(kayit[alan], []).append(kayit)
            for ortak, ayni in sorted(ortaklar.items()):
                if len(ayni) < 2:
                    continue
                spof.append({
                    "lokasyon": lok, "bb": ortak, "altyapilar": sorted({k["altyapi"] for k in ayni}),
                    "neden": neden, "devreler": [k["ad"] for k in ayni],
                })
        if any(k["altyapi"] == "Bilinmiyor" for k in kayitlar):
            uyarilar.append(f"{lok}: altyapısı belirlenemeyen devre var.")
        if any(not k["bb"] for k in kayitlar):
            uyarilar.append(f"{lok}: BB router bilgisi eksik devre var; uç ayrışması tam doğrulanamadı.")

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
        "kenarlar": kenarlar,
        "sehirler": sehirler,
        "konumsuz_iller": sorted(adlar[a] for a in sayac if a not in _KOORDINAT),
        "kolonlar": {k: v for k, v in kolon.items() if v},
        "satir": len(satirlar),
        "lokasyon": len(gruplar),
        "degerlendirme": "riskli" if spof else "sinirli",
        "uyarilar": uyarilar,
        "renkler": KABLO_RENKLERI,
    }
