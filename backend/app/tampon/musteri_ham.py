"""Ham Musteri Verisi: musteri kartinin alan katalogu, dosya okuma (.xlsx / .csv), sablon ve bicim tanima.

Uretim karsiligi: kutucuklar/veri/musteri_sablon.py (katalog, takma adlar, cati/istirak genis bicimi, uyum raporu, sablon) ve
musteri_no.py. Kartlara aktarim musteri_aktar.py'dedir (once onizleme, sonra onayli uygulama, geri alma).

Dosya bicimi kullanicinin dosyasina uyar: sayfa ve baslik satiri sabit degildir. Okuma her sayfanin ilk ARAMA_SATIRI satirinda
katalog basliklarini en cok tutan satiri baslik sayar (ust bilgi / bos satirlar atlanir); en iyi tutan sayfa secilir.
Baslik eslesmesi harf / bosluk / I-İ farkini gozetmez; takma adlar (TAKMA_ADLAR) baska sistemlerin liste dosyalarini tanir.
Ornek / uydurma deger yoktur: dolu sablon yalniz panelde kayitli gercek kart degerlerinden uretilir.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dil import m
from app.models import AppUser, Customer, CustomerTeam
from app.musteri.servis import ILETISIM_ALANLARI, SEGMENTLER
from app.ortak import UygulamaHatasi, eslestirme_anahtari, tr_kucuk

KAYNAK = "musteri_ham"
SAYFA = "Müşteri Kartı"
DOSYA_ADI = "TAM_Musteri_Ham_Veri_Sablonu.xlsx"
AZAMI_TAMSAYI = 1_000_000_000
ARAMA_SATIRI = 15  # baslik satiri bu kadar satir icinde aranir


@dataclass(frozen=True)
class Alan:
    """Katalog satiri. anahtar: kod icin kisa ad; baslik: dosya sutun basligi; kolon: Customer/CustomerTeam sutunu."""

    anahtar: str
    grup: str
    baslik: str
    tip: str  # metin | secim | tamsayi | tutar | evet_hayir | eposta | gsm | kisi | cati | musteri_no
    azami: int | None
    zorunlu: bool
    kart: str
    kural: str


_ILETISIM_BASLIKLARI = {
    "sales_manager": "Satış Yöneticisi",
    "presales_manager": "Presales",
    "tac_name": "TAC Adı",
    "tac_gsm": "TAC GSM",
    "tac_email": "TAC E-posta",
    "sol_kmt_name": "SOL KMT Adı",
    "sol_kmt_gsm": "SOL KMT GSM",
    "sol_kmt_email": "SOL KMT E-posta",
    "mobil_kmt_name": "Mobil KMT Adı",
    "mobil_kmt_gsm": "Mobil KMT GSM",
    "mobil_kmt_email": "Mobil KMT E-posta",
    "mobil_kmt_detail": "Mobil KMT Notu",
}


def _iletisim_alani(anahtar: str) -> Alan:
    etiket, azami = ILETISIM_ALANLARI[anahtar]
    tip = "eposta" if anahtar.endswith("_email") else "gsm" if anahtar.endswith("_gsm") else "metin"
    kural = {
        "eposta": "Geçerli e-posta adresi (ad@alanadi.uzanti).",
        "gsm": "Yalnız rakam, +, boşluk, - ve parantez.",
        "metin": f"En fazla {azami} karakter.",
    }[tip]
    return Alan(anahtar, "iletisim", _ILETISIM_BASLIKLARI.get(anahtar, etiket), tip, azami, False, f"Ekip & İletişim › {etiket}", kural)


def _sayac(anahtar: str, baslik: str, kart: str, kural: str) -> Alan:
    return Alan(anahtar, "operasyon", baslik, "tamsayi", None, False, kart, kural)


# Sira = sutun sirasi = kartin okunus sirasi.
ALANLAR: tuple[Alan, ...] = (
    Alan(
        "unvan",
        "kimlik",
        "Müşteri Ünvanı",
        "metin",
        150,
        True,
        "Kimlik › Müşteri Ünvanı",
        "Satırın kartla eşleşme anahtarı (Müşteri No yoksa). Büyük/küçük harf ve boşluk farkı yok sayılır.",
    ),
    Alan(
        "cati",
        "kimlik",
        "Çatı Müşteri Ünvanı",
        "cati",
        150,
        False,
        "Kimlik › Çatı müşteri",
        "Yalnız iştirak satırlarında: bağlı olduğu çatı müşterinin ünvanı. Boş = çatı müşteri.",
    ),
    Alan(
        "tam", "kimlik", "Sorumlu TAM", "kisi", 120, False, "Kimlik › Sorumlu TAM", "Panel kullanıcısının adı soyadı ya da kullanıcı adı."
    ),
    Alan(
        "customer_no",
        "kimlik",
        "Müşteri No",
        "musteri_no",
        200,
        False,
        "Kimlik › Müşteri No",
        "Yalnız rakam; aynı müşterinin birden çok numarası virgülle ayrılır. Kartta kayıtlı numara silinmez, yenisi eklenir.",
    ),
    Alan("ncst", "kimlik", "Müşteri NCST", "metin", 50, False, "Kimlik › Müşteri NCST", "En fazla 50 karakter."),
    Alan("segment", "kimlik", "Segment", "secim", 100, False, "Kimlik › Segment", "Şunlardan biri: " + ", ".join(SEGMENTLER) + "."),
    Alan("sector", "kimlik", "Sektör", "metin", 100, False, "Kimlik › Sektör", "En fazla 100 karakter."),
    Alan("envanter", "kimlik", "Envanter", "tamsayi", None, False, "Kimlik › Envanter", "0 ile 1.000.000.000 arası tam sayı."),
    Alan("ft_hacim", "kimlik", "FT Hacim", "tutar", 100, False, "Operasyon › FT Hacim", "Karttaki gösterimle 1.234,56 ₺ ya da sayı."),
    Alan("tam_ft", "kimlik", "TAM FT", "tutar", 100, False, "Operasyon › TAM FT", "Karttaki gösterimle 1.234,56 ₺ ya da sayı."),
    Alan(
        "ayri_rapor",
        "kimlik",
        "Ayrı Aylık Rapor",
        "evet_hayir",
        None,
        False,
        "Kimlik › Ayrı aylık rapor",
        "Yalnız iştirak satırlarında: Evet = kendi aylık raporu var, Hayır = çatısının raporuna dahil.",
    ),
    _sayac("alarm_count", "Alarm Sayısı", "Operasyon › Alarm", "Açık alarm adedi (tam sayı ≥ 0)."),
    _sayac("sikayet_count", "Şikayet Sayısı", "Operasyon › Şikayet", "Açık şikayet adedi (tam sayı ≥ 0)."),
    _sayac("talep_count", "Talep Sayısı", "Operasyon › Talep", "Açık talep adedi (tam sayı ≥ 0)."),
    _sayac("alarm_closed_count", "Kapanan Alarm Sayısı", "Operasyon › Alarm (yıl içi kapanan)", "Yıl içinde kapanan alarm adedi."),
    _sayac("sikayet_closed_count", "Kapanan Şikayet Sayısı", "Operasyon › Şikayet (yıl içi kapanan)", "Yıl içinde kapanan şikayet adedi."),
    _sayac("talep_closed_count", "Kapanan Talep Sayısı", "Operasyon › Talep (yıl içi kapanan)", "Yıl içinde kapanan talep adedi."),
    *(_iletisim_alani(a) for a in ILETISIM_ALANLARI),
)  # 2026-10-26: "Cacti Adresleri" alani kalkti (aylik rapor grafikleri yalniz elle)
ALAN = {a.anahtar: a for a in ALANLAR}

# sablon alani -> Customer sutunu (iletisim alanlari CustomerTeam'de, ayni adla)
KOLON = {
    "customer_no": "customer_no",
    "ncst": "ncst",
    "segment": "segment",
    "sector": "sector",
    "envanter": "inventory_count",
    "ft_hacim": "ft_volume",
    "tam_ft": "tam_ft",
    "ayri_rapor": "separate_report",
    "alarm_count": "alarm_count",
    "sikayet_count": "complaint_count",
    "talep_count": "request_count",
    "alarm_closed_count": "alarm_closed_count",
    "sikayet_closed_count": "complaint_closed_count",
    "talep_closed_count": "request_closed_count",
    "tam": "owner_id",
    "cati": "parent_id",
}

# Baska sistemlerin liste dosyalari: ayni alanin farkli basliklari (harf / bosluk / noktalama farki gozetilmez).
TAKMA_ADLAR: dict[str, tuple[str, ...]] = {
    "unvan": ("Müşteri Adı", "Müşteri", "Müşteri Ünvan", "Ünvan", "Firma", "Firma Adı", "Kurum", "Kurum Adı"),
    "tam": ("TAM Temsilcisi", "TAM", "TAM Adı", "Sorumlu"),
    "customer_no": ("Müşteri Numarası", "Müşteri Kodu", "Customer No"),
    "ncst": ("NCST",),
    "sector": ("Sektör Adı",),
    "envanter": ("Envanter Sayısı", "Envanter Adedi"),
    "sales_manager": ("Satış Yöneticisi Adı", "Satış Müdürü"),
    "tac_name": ('TAC "AD SOYAD"', "TAC Ad Soyad", "TAC"),
}
LISTE_BICIMI_ALANLARI = ("customer_no", "tam", "unvan")

# Iceri alinan alanlar = sablondaki sutunlar (2026-10-15 kullanici sablonu). Katalogun geri kalani (NCST, envanter, FT, sayaclar,
# Cacti, ayri rapor) bu dosyadan OKUNMAZ: o basliklar dosyada olsa da "taninmayan sutun" sayilir, karta dokunulmaz.
ICE_ALINAN: tuple[str, ...] = ("tam", "unvan", "cati", "customer_no", "segment", "sector", *ILETISIM_ALANLARI)

# Sablon sutunlari (sira, baslik, Excel genisligi): cati / istirak genis bicimi, musteri basina degil (cati, istirak) cifti basina satir.
SABLON: tuple[tuple[str, float | None], ...] = (
    ("Sorumlu TAM", 24),
    ("Çatı Müşteri Ünvanı", 18.86),
    ("Çatı Müşteri No", 16),
    ("Çatı_to_İştirak Müşteri No", 24.57),
    ("İştirak Müşteri Ünvanı", 25),
    ("İştirak Müşteri No", 18),
    ("Segment", 16),
    ("Sektör", None),
    *((_ILETISIM_BASLIKLARI[a], {"sales_manager": 22, "presales_manager": 16, "tac_email": 17, "sol_kmt_email": 21, "mobil_kmt_name": 19,
                                 "mobil_kmt_email": 23, "mobil_kmt_detail": 20}.get(a)) for a in ILETISIM_ALANLARI),
)  # fmt: skip  # bu uc alan takma adlarla varsa dosya bir "musteri / TAM listesi"dir

_BASLIK_SONEKI = re.compile(r"\s*\*+\s*$")  # 'Müşteri Ünvanı *' zorunlu isareti


def _anahtar(baslik: object) -> str:
    return eslestirme_anahtari(_BASLIK_SONEKI.sub("", str(baslik or "")))


def _takma_anahtar(baslik: object) -> str:
    """Takma ad karsilastirmasi: noktalama / bosluk da yok sayilir ('TAC "AD SOYAD"' = 'TAC Ad Soyad')."""
    return re.sub(r"[^0-9a-zçğıöşü]", "", _anahtar(baslik))


_TANIMLI = {_anahtar(a.baslik): a.anahtar for a in ALANLAR if a.anahtar in ICE_ALINAN}
_TAKMA = {_takma_anahtar(a.baslik): a.anahtar for a in ALANLAR if a.anahtar in ICE_ALINAN}
_TAKMA.update({_takma_anahtar(ad): alan for alan, adlar in TAKMA_ADLAR.items() if alan in ICE_ALINAN for ad in adlar})


def baslik_alani(baslik: object) -> str | None:
    """Dosya basligi -> katalog alan anahtari (sablon basligi, yoksa takma ad) ya da None."""
    return _TANIMLI.get(_anahtar(baslik)) or _TAKMA.get(_takma_anahtar(baslik))


# --- Musteri No: bir kartta birden cok numara (uretim musteri_no.py) ---------------------------------------------
_NO_AYRAC = re.compile(r"[,;/\n]+")


def _no_metne(deger: object) -> str:
    if deger is None or isinstance(deger, bool):
        return ""
    if isinstance(deger, float) and deger.is_integer():
        deger = int(deger)  # Excel sayisal hucre: 22135503.0
    return str(deger)


def no_parcalar(deger: object) -> list[str]:
    return [p.strip() for p in _NO_AYRAC.split(_no_metne(deger)) if p.strip()]


def no_anahtar(numara: object) -> str:
    """Karsilastirma anahtari: yalniz rakam, bastaki sifirlar atilir ('' = numara degil)."""
    return re.sub(r"\D", "", _no_metne(numara)).lstrip("0")


def numaralar(deger: object) -> list[str]:
    sonuc, gorulen = [], set()
    for p in no_parcalar(deger):
        n = re.sub(r"\D", "", p)
        k = n.lstrip("0")
        if k and k not in gorulen:
            gorulen.add(k)
            sonuc.append(n)
    return sonuc


def no_anahtarlari(deger: object) -> list[str]:
    return [no_anahtar(n) for n in numaralar(deger)]


def no_ekle(mevcut: object, yeni: Iterable[str]) -> tuple[list[str], list[str]]:
    """Mevcut numaralarin USTUNE yenileri ekler (hicbiri silinmez). Donus: (birlesik liste, eklenenler)."""
    eski = numaralar(mevcut)
    var = {no_anahtar(n) for n in eski}
    eklenen = []
    for n in yeni:
        k = no_anahtar(n)
        if k and k not in var:
            var.add(k)
            eklenen.append(n)
    return eski + eklenen, eklenen


# --- Cati / istirak "genis" bicimi ------------------------------------------------------------------------------
# Her satir bir (cati, istirak) cifti: 'Cati Musteri Unvani | Cati Musteri No | Cati_to_Istirak | Istirak Musteri Unvani |
# Istirak Musteri No | Sorumlu TAM | ...'; standart 'Musteri Unvani' sutunu yoktur. Musteri basina tek satirlik standart bicime
# cevrilip ayni aktarim akisina girer: cati TEK kez gelir, istirak 'Cati_to_Istirak' (bos ise satirin Cati Musteri No'su)
# numarali catinin altina eklenir. Sorumlu TAM catiya da istiraga da yazilir; diger sutunlar satir istirak tasiyorsa istiragin.
_GENIS = {
    "cati_unvan": ("Çatı Müşteri Ünvanı", "Çatı Müşteri Adı", "Çatı Ünvan", "Çatı"),
    "cati_no": ("Çatı Müşteri No", "Çatı No"),
    "cati_to": ("Çatı_to_İştirak Müşteri No", "Çatı_to_İştirak", "Çatı to İştirak"),
    "istirak_unvan": ("İştirak Müşteri Ünvanı", "İştirak Müşteri Adı", "İştirak Ünvan", "İştirak"),
    "istirak_no": ("İştirak Müşteri No", "İştirak No"),
}


def _genis_sutunlar(basliklar: Sequence[object]) -> dict[str, int | None] | None:
    anahtar: dict[str, int] = {}
    for i, b in enumerate(basliklar):
        anahtar.setdefault(_takma_anahtar(b), i)
    if any(baslik_alani(b) == "unvan" for b in basliklar):
        return None
    sutun = {ad: next((anahtar[_takma_anahtar(x)] for x in adlar if _takma_anahtar(x) in anahtar), None) for ad, adlar in _GENIS.items()}
    return None if sutun["cati_unvan"] is None or sutun["istirak_unvan"] is None else sutun


def genis_bicim_mi(basliklar: Sequence[object]) -> bool:
    return _genis_sutunlar(basliklar) is not None


def _genis_ek(basliklar: Sequence[object], sutun: dict[str, int | None]) -> list[int]:
    kimlik = {i for i in sutun.values() if i is not None}
    return [i for i in range(len(basliklar)) if i not in kimlik]


def _bos(v: object) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _tek(v: object) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return "" if v is None else " ".join(str(v).split())


def genis_donustur(basliklar: Sequence[str], satirlar: Iterable[Sequence[object]]) -> tuple[list[str], list[list[Any]], list[int]]:
    """-> (standart basliklar, standart satirlar, kaynak satir numaralari 1 tabanli). Genis bicim degilse girdi aynen doner."""
    liste = [list(r) for r in satirlar]
    sutun = _genis_sutunlar(basliklar)
    if sutun is None:
        return list(basliklar), liste, list(range(1, len(liste) + 1))
    ek = _genis_ek(basliklar, sutun)
    tam_k = next((k for k, i in enumerate(ek) if baslik_alani(basliklar[i]) == "tam"), None)

    def al(r: list[Any], ad: str) -> object:
        i = sutun[ad]
        return r[i] if i is not None and i < len(r) else None

    catilar: list[dict[str, Any]] = []
    no_ile: dict[str, dict[str, Any]] = {}
    unvan_ile: dict[str, dict[str, Any]] = {}
    istirakler: list[dict[str, Any]] = []
    for sira, r in enumerate(liste, 1):
        c_unvan, c_no = _tek(al(r, "cati_unvan")), _tek(al(r, "cati_no"))
        i_unvan, i_no = _tek(al(r, "istirak_unvan")), _tek(al(r, "istirak_no"))
        deger = [r[i] if i < len(r) else None for i in ek]
        link = _tek(al(r, "cati_to")) or c_no
        c_no = c_no or link
        g = None
        if c_unvan:
            g = next((no_ile[k] for k in no_anahtarlari(c_no) if k in no_ile), None) or unvan_ile.get(eslestirme_anahtari(c_unvan))
            if g is None:
                g = {"unvan": c_unvan, "nolar": [], "ek": [None] * len(ek), "sira": sira}
                catilar.append(g)
            unvan_ile.setdefault(eslestirme_anahtari(c_unvan), g)
            for n in numaralar(c_no):
                if no_anahtar(n) not in no_ile:
                    g["nolar"].append(n)
                no_ile.setdefault(no_anahtar(n), g)
            if i_unvan:  # istirak satiri: catiya yalniz Sorumlu TAM
                if tam_k is not None and _bos(g["ek"][tam_k]) and not _bos(deger[tam_k]):
                    g["ek"][tam_k] = deger[tam_k]
            else:  # yalniz cati satiri: ilk dolu deger catinin
                for k, v in enumerate(deger):
                    if _bos(g["ek"][k]) and not _bos(v):
                        g["ek"][k] = v
        if i_unvan:
            istirakler.append({"unvan": i_unvan, "no": i_no, "ek": deger, "link": no_anahtarlari(link), "cati": g, "sira": sira})

    altlar: dict[int, list[dict[str, Any]]] = {id(g): [] for g in catilar}
    yetim: list[dict[str, Any]] = []
    for it in istirakler:
        hedef = next((no_ile[k] for k in it["link"] if k in no_ile), None) or it["cati"]
        (altlar[id(hedef)] if hedef is not None else yetim).append(it)
    cikti: list[list[Any]] = []
    kaynak: list[int] = []
    for g in catilar:
        cikti.append([g["unvan"], "", ", ".join(g["nolar"]), *g["ek"]])
        kaynak.append(g["sira"])
        for it in altlar[id(g)]:
            cikti.append([it["unvan"], g["unvan"], it["no"], *it["ek"]])
            kaynak.append(it["sira"])
    for it in yetim:  # bagli cati bulunamadi: bagimsiz musteri
        cikti.append([it["unvan"], "", it["no"], *it["ek"]])
        kaynak.append(it["sira"])
    standart = [ALAN["unvan"].baslik, ALAN["cati"].baslik, ALAN["customer_no"].baslik] + [str(basliklar[i]) for i in ek]
    return standart, cikti, kaynak


def sutun_haritasi(basliklar: Sequence[object]) -> dict[str, int]:
    """Dosya basliklari -> {alan: sutun sirasi}. Katalog disi sutun yok sayilir; ayni alan iki kez gelirse ilki."""
    harita: dict[str, int] = {}
    for i, b in enumerate(basliklar):
        alan = baslik_alani(b)
        if alan and alan not in harita:
            harita[alan] = i
    return harita


def uyum_raporu(basliklar: Sequence[object]) -> dict[str, Any]:
    """Dosya basliklarinin katalogla karsilastirmasi (ekranda 'dosya taninmasi')."""
    genis = genis_bicim_mi(basliklar)
    if genis:
        basliklar = genis_donustur([str(b) for b in basliklar], [])[0]
    harita = sutun_haritasi(basliklar)
    alanlar = [a for a in ALANLAR if a.anahtar in ICE_ALINAN]
    eksik = [a.baslik for a in alanlar if a.anahtar not in harita]
    fazla = [str(b) for b in basliklar if baslik_alani(b) is None]
    zorunlu_eksik = [a.baslik for a in alanlar if a.zorunlu and a.anahtar not in harita]
    takma = any(_anahtar(b) not in _TANIMLI and baslik_alani(b) for b in basliklar)
    bicim = "genis" if genis else ("liste" if takma and all(a in harita for a in LISTE_BICIMI_ALANLARI) else "sablon")
    return {
        "toplam": len(alanlar),
        "eslesen": len(harita),
        "alanlar": [{"sutun": str(basliklar[i]), "alan": ALAN[a].baslik} for a, i in sorted(harita.items(), key=lambda x: x[1])],
        "eksik": eksik,
        "fazla": fazla,
        "zorunlu_eksik": zorunlu_eksik,
        "uyumlu": not zorunlu_eksik,
        "bicim": bicim,
    }


# --- Dosya okuma --------------------------------------------------------------------------------------------------
def _hucre(v: object) -> object:
    if isinstance(v, datetime):
        return v.date().isoformat() if v.time() == time(0) else v.isoformat(sep=" ", timespec="minutes")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def _puan(satir: Sequence[object]) -> int:
    """Bir satirin baslik olma puani: katalogda taninan farkli alan sayisi (genis bicim kimlik sutunlari dahil)."""
    alanlar = {baslik_alani(h) for h in satir if not _bos(h)} - {None}
    genis = _genis_sutunlar([h for h in satir if not _bos(h)]) if any(not _bos(h) for h in satir) else None
    return len(alanlar) + (sum(1 for v in genis.values() if v is not None) if genis else 0)


def tablo_bul(satirlar: list[list[object]]) -> tuple[int, list[str], list[list[object]]] | None:
    """Ilk ARAMA_SATIRI satirda en yuksek puanli satir baslik; -> (puan, basliklar, veri satirlari) ya da None."""
    en_iyi: tuple[int, int] | None = None
    for i, satir in enumerate(satirlar[:ARAMA_SATIRI]):
        p = _puan(satir)
        if p and (en_iyi is None or p > en_iyi[0]):
            en_iyi = (p, i)
    if en_iyi is None:
        return None
    puan, i = en_iyi
    ham = list(satirlar[i])
    while ham and _bos(ham[-1]):
        ham.pop()
    basliklar, sayac = [], {}
    for k, h in enumerate(ham, 1):
        ad = _tek(h) or f"Sütun {k}"
        sayac[ad] = sayac.get(ad, 0) + 1
        basliklar.append(ad if sayac[ad] == 1 else f"{ad} ({sayac[ad]})")
    veri = [list(r[: len(basliklar)]) for r in satirlar[i + 1 :] if any(not _bos(h) for h in r[: len(basliklar)])]
    return puan, basliklar, veri


def _xlsx_sayfalari(veri: bytes) -> list[tuple[str, list[list[object]]]]:
    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        wb = openpyxl.load_workbook(io.BytesIO(veri), read_only=True, data_only=True)
    except (InvalidFileException, OSError, KeyError, ValueError) as e:
        raise UygulamaHatasi(
            400, m("Excel dosyası okunamadı (.xlsx bekleniyor).", "Could not read the Excel file (.xlsx expected).")
        ) from e
    try:
        return [(ws.title, [[_hucre(v) for v in r] for r in ws.iter_rows(values_only=True)]) for ws in wb.worksheets]
    finally:
        wb.close()


def _csv_satirlari(veri: bytes) -> list[list[object]]:
    for kodlama in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            metin = veri.decode(kodlama)
            break
        except UnicodeDecodeError:
            continue
    ilk = next((s for s in metin.splitlines() if s.strip()), "")
    ayrac = max((";", ",", "\t", "|"), key=ilk.count) if any(a in ilk for a in ";,\t|") else ","
    return [[_hucre(h) for h in r] for r in csv.reader(io.StringIO(metin, newline=""), delimiter=ayrac)]


def dosya_oku(veri: bytes, dosya: str = "") -> dict[str, Any]:
    """.xlsx (PK imzasi) ya da .csv -> {'sayfa', 'basliklar', 'satirlar'}. Birden cok sayfa varsa katalogu en cok tutan secilir."""
    if not veri:
        raise UygulamaHatasi(400, m("Dosya boş.", "The file is empty."))
    if veri[:2] == b"PK":
        sayfalar = _xlsx_sayfalari(veri)
    elif dosya.lower().endswith((".xlsx", ".xlsm")):
        raise UygulamaHatasi(400, m("Excel dosyası okunamadı (.xlsx bekleniyor).", "Could not read the Excel file (.xlsx expected)."))
    else:
        sayfalar = [("", _csv_satirlari(veri))]
    adaylar = []
    for ad, satirlar in sayfalar:
        bulunan = tablo_bul(satirlar)
        if bulunan:
            on_sayfa = 1 if _anahtar(ad) == _anahtar(SAYFA) else 0
            adaylar.append((bulunan[0], on_sayfa, ad, bulunan[1], bulunan[2]))
    if not adaylar:
        raise UygulamaHatasi(
            400,
            m(
                "Dosyada müşteri kartı sütunları bulunamadı (örn. Çatı Müşteri Ünvanı, İştirak Müşteri Ünvanı, Sorumlu TAM). Şablonu indirip ona göre doldurun.",
                "No customer card columns found in the file (e.g. Çatı Müşteri Ünvanı, İştirak Müşteri Ünvanı, Sorumlu TAM). Download the template and fill it in.",
            ),
        )
    _, _, ad, basliklar, satirlar = max(adaylar, key=lambda a: (a[0], a[1]))
    return {"sayfa": ad, "basliklar": basliklar, "satirlar": satirlar}


# --- Mevcut kart degerleri ----------------------------------------------------------------------------------------
def kisi_adi(k: AppUser | None) -> str:
    return (k.display_name or k.username) if k else ""


def iletisim_kayitlari(db: Session) -> dict[int, CustomerTeam]:
    return {k.customer_id: k for k in db.scalars(select(CustomerTeam))}


def kart_degerleri(c: Customer, kayit: CustomerTeam | None, adlar: dict[int, str], kisiler: dict[int, AppUser]) -> dict[str, Any]:
    """Bir musterinin karttaki degerleri, katalog anahtarlariyla. Sablon doldurma ve onizleme ayni degerleri kullanir."""
    deger: dict[str, Any] = {
        "unvan": c.name,
        "cati": adlar.get(c.parent_id, "") if c.parent_id else "",
        "tam": kisi_adi(kisiler.get(c.owner_id)) if c.owner_id else "",
        "customer_no": c.customer_no or "",
        "ncst": c.ncst or "",
        "segment": c.segment or "",
        "sector": c.sector or "",
        "envanter": c.inventory_count or 0,
        "ft_hacim": c.ft_volume or "",
        "tam_ft": c.tam_ft or "",
        "ayri_rapor": ("Evet" if c.separate_report else "Hayır") if c.parent_id else "",
        "alarm_count": c.alarm_count or 0,
        "sikayet_count": c.complaint_count or 0,
        "talep_count": c.request_count or 0,
        "alarm_closed_count": c.alarm_closed_count or 0,
        "sikayet_closed_count": c.complaint_closed_count or 0,
        "talep_closed_count": c.request_closed_count or 0,
    }
    for a in ILETISIM_ALANLARI:
        deger[a] = (getattr(kayit, a, None) or "") if kayit else ""
    return deger


def sablon_satirlari(db: Session) -> list[list[Any]]:
    """Dolu sablon: SABLON sirasinda; her cati bir satir (istirak sutunlari bos), ardindan her istiraki catisiyla bir satir."""
    musteriler = list(db.scalars(select(Customer)))
    kisiler = {u.id: u for u in db.scalars(select(AppUser))}
    kayitlar = iletisim_kayitlari(db)
    tum = {c.id: c for c in musteriler}
    cocuklar: dict[int, list[Customer]] = {}
    for c in musteriler:
        if c.parent_id in tum:
            cocuklar.setdefault(c.parent_id, []).append(c)

    def satir(c: Customer, cati: Customer | None) -> list[Any]:
        kayit = kayitlar.get(c.id)
        tam = kisi_adi(kisiler.get(c.owner_id)) if c.owner_id else ""
        kimlik = [cati.name, cati.customer_no or "", "", c.name, c.customer_no or ""] if cati else [c.name, c.customer_no or "", "", "", ""]
        iletisim = [(getattr(kayit, a, None) or "") if kayit else "" for a in ILETISIM_ALANLARI]
        return [tam, *kimlik, c.segment or "", c.sector or "", *iletisim]

    sonuc: list[list[Any]] = []
    for kok in sorted((c for c in musteriler if c.parent_id not in tum), key=lambda c: tr_kucuk(c.name or "")):
        sonuc.append(satir(kok, None))
        sonuc.extend(satir(c, kok) for c in sorted(cocuklar.get(kok.id, []), key=lambda c: tr_kucuk(c.name or "")))
    return sonuc


# --- Sablon (.xlsx) -----------------------------------------------------------------------------------------------
def _yaz(ws: Any, satir: int, sutun: int, deger: object) -> Any:
    h = ws.cell(row=satir, column=sutun, value=deger)
    if isinstance(deger, str) and deger.startswith("="):
        h.data_type = "s"  # musteri verisi formul olarak yorumlanmasin
    return h


def sablon_olustur(db: Session, dolu: bool = False) -> bytes:
    """.xlsx baytlari, kullanicinin verdigi sablonla ayni (2026-10-15): tek sayfa, koyu mavi baslik, filtreli, C2'den sabit.
    dolu=False: yalniz basliklar; dolu=True: paneldeki kartlarin GERCEK degerleriyle (ornek / uydurma deger yok)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Color, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = SAYFA
    dolgu = PatternFill("solid", fgColor=Color(theme=4, tint=-0.4999))  # Vurgu 1, %50 koyu
    for sutun, (baslik, genislik) in enumerate(SABLON, 1):
        h = _yaz(ws, 1, sutun, baslik)
        h.font = Font(bold=True, color="FFFFFF")
        h.fill = dolgu
        h.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if genislik:
            ws.column_dimensions[get_column_letter(sutun)].width = genislik
    ws.row_dimensions[1].height = 33.95
    ws.freeze_panes = "C2"
    for i, satir in enumerate(sablon_satirlari(db) if dolu else [], 2):
        for sutun, deger in enumerate(satir, 1):
            if deger not in ("", None):
                _yaz(ws, i, sutun, deger)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(SABLON))}{max(ws.max_row, 2)}"  # baslik satirinda filtre (kullanici sablonundaki gibi)
    cikti = io.BytesIO()
    wb.save(cikti)
    return cikti.getvalue()
