# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Excel hucre metinlerinin guvenli ayristirilmasi: tutar, saat, yil ici gelir, tarih, durum, kisi adlari, baslik haritasi.

Saf fonksiyonlar: veritabani, istek dili ve saat yok (bugun parametre olarak gelir). Sonuclar kod/anlam tasir; kullaniciya
gorunen cumleleri ice_al.py uretir.

Ilke (kullanici karari): TAHMIN YOK. Sayiya guvenle cevrilemeyen ya da belirsiz her metin OLDUGU GIBI nota gider:
  - birden fazla sayi / para birimi / donem iceren metin ayristirilmaz;
  - tutarda donem (/ay, aylik, yillik, tek seferlik) zorunludur; donemsiz "2,1 M TL" aylik sayilmaz;
  - tek virgullu uc haneli "318,500" binlik mi ondalik mi belli degildir: carpan (K/M/bin) yoksa ayristirilmaz;
  - kur cevirisi, adamgun->saat gibi donusumler yapilmaz.
Carpanlar (K, M, bin, milyon) Decimal ile uygulanir: 88,2 KTL tam 88200 olur, kayan nokta hatasi girmez.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

AZAMI_NOT = 500
PARA_BIRIMLERI = ("TRY", "USD", "EUR")
DONEMLER = ("ay", "yil", "tek_sefer")

_TR_HARF = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def katla(metin: object) -> str:
    """Karsilastirma icin: Turkce harfler ASCII, kucuk harf, bolunmez bosluk -> bosluk. UZUNLUK KORUNUR (konumlar asil metinle ayni)."""
    cikti: list[str] = []
    for harf in str(metin if metin is not None else "").replace("\xa0", " ").translate(_TR_HARF):
        k = harf.lower()
        cikti.append(k if len(k) == 1 else harf)
    return "".join(cikti)


def _temiz(metin: object) -> str:
    return re.sub(r"\s+", " ", str(metin if metin is not None else "").replace("\xa0", " ")).strip()


def _sayisal_mi(deger: object) -> bool:
    return isinstance(deger, (int, float, Decimal)) and not isinstance(deger, bool)


def _kirp(metin: str, sinir: int = AZAMI_NOT) -> str:
    metin = metin.strip()
    return metin if len(metin) <= sinir else metin[: sinir - 1].rstrip() + "…"


_BOS_ISARETLERI = frozenset({"yok", "yoktur", "-", "--", "–", "—", "n/a"})


def bos_isareti(metin: object) -> bool:
    """Hucrenin TAMAMI 'yok', '-', 'n/a' gibi bir 'deger yok' isaretiyse True: bilgi tasimaz, nota yazilmaz.
    'ek gelir yok' gibi cumleler isaret degildir (oldugu gibi nota gider)."""
    return katla(_temiz(metin)).rstrip(". ") in _BOS_ISARETLERI


# --- sayi ----------------------------------------------------------------------------------------------------------
_BINLIK_NOKTA = re.compile(r"^\d{1,3}(\.\d{3})+$")
_BINLIK_VIRGUL = re.compile(r"^\d{1,3}(,\d{3}){2,}$")


def sayi_degeri(jeton: str, carpanli: bool = False) -> Decimal | None:
    """Turkce bicimli sayi jetonu -> Decimal; belirsiz/gecersizse None.

    "88,2" -> 88.2 | "118.425" -> 118425 | "1.234,56" -> 1234.56 | "2.2" -> 2.2 | "1,234,567" -> 1234567.
    "318,500" (tek virgul + 3 hane) yalniz carpanli yazimda ("5,148 M") ondaliktir; carpansizsa belirsizdir -> None.
    """
    jeton = jeton.strip().rstrip(".,")
    if not re.fullmatch(r"\d[\d.,]*", jeton):
        return None
    try:
        if "." in jeton and "," in jeton:
            if re.fullmatch(r"\d{1,3}(\.\d{3})+,\d+", jeton):  # 1.234,56 (TR)
                return Decimal(jeton.replace(".", "").replace(",", "."))
            if re.fullmatch(r"\d{1,3}(,\d{3})+\.\d+", jeton):  # 1,234.56 (EN)
                return Decimal(jeton.replace(",", ""))
            return None
        if "," in jeton:
            if re.fullmatch(r"\d+,\d{1,2}", jeton):
                return Decimal(jeton.replace(",", "."))
            if re.fullmatch(r"\d+,\d{3}", jeton):
                return Decimal(jeton.replace(",", ".")) if carpanli else None
            if _BINLIK_VIRGUL.match(jeton):
                return Decimal(jeton.replace(",", ""))
            return None
        if "." in jeton:
            if _BINLIK_NOKTA.match(jeton):
                return Decimal(jeton.replace(".", ""))
            if re.fullmatch(r"\d+\.\d{1,2}", jeton):
                return Decimal(jeton)
            return None
        return Decimal(jeton)
    except InvalidOperation:
        return None


_CARPANLAR = (
    ("milyar", Decimal(10**9), None),
    ("milyon", Decimal(10**6), None),
    ("bin", Decimal(1000), None),
    ("mtl", Decimal(10**6), "TRY"),
    ("ktl", Decimal(1000), "TRY"),
    ("m", Decimal(10**6), None),
    ("k", Decimal(1000), None),
)
_CARPAN_DESENI = re.compile(r"\s*(" + "|".join(c[0] for c in _CARPANLAR) + r")(?![a-z])")
_SAYI_JETONU = re.compile(r"\d[\d.,]*")
_ADET_DESENI = re.compile(r"(?:\d|euro|eur|avro|usd|dolar|tl|\$|€|₺)\s*(?P<adet>[x×*]\s*(?P<n>\d+)(?:\s*adet)?)(?![a-z0-9])")

_PARA_DESENLERI = (
    ("USD", re.compile(r"\$|(?<![a-z])(?:usd|dolar)(?![a-z])")),
    ("EUR", re.compile(r"€|(?<![a-z])(?:euro|eur|avro)(?![a-z])")),
    ("TRY", re.compile(r"₺|(?<![a-z])(?:tl|try|lira)(?![a-z])")),
)
_DONEM_DESENLERI = (
    ("tek_sefer", re.compile(r"tek\s*seferlik|tek\s*sefer|tek\s*defa|bir\s*kerelik|one[\s-]*time")),
    ("yil", re.compile(r"/\s*yil(?![a-z])|yillik|yilda|(?<![a-z])yil(?![a-z])|/\s*year|annual")),
    ("ay", re.compile(r"/\s*ay(?![a-z])|aylik|ayda|(?<![a-z])ay(?![a-z])|/\s*month|monthly")),
)
_SAAT_DESENI = re.compile(r"(?<![a-z])(?:saat|hours?|hrs?)(?![a-z])")


def _bosalt(kat: str, aralik: tuple[int, int]) -> str:
    a, b = aralik
    return kat[:a] + " " * (b - a) + kat[b:]


def _artik(asil: str, araliklar: list[tuple[int, int]]) -> str:
    """Asil metinden taninan parcalar (araliklar) cikarildiktan kalan metin; uclardaki ayrac/noktalama temizlenir."""
    parcalar: list[str] = []
    onceki = 0
    for a, b in sorted(araliklar):
        if a > onceki:
            parcalar.append(asil[onceki:a])
        onceki = max(onceki, b)
    parcalar.append(asil[onceki:])
    kalan = re.sub(r"\(\s*\)", " ", " ".join(parcalar))
    kalan = re.sub(r"\s+", " ", kalan).strip(" \t\n/-–—:;,+")
    kalan = kalan.lstrip(".").strip()
    return kalan if re.search(r"[^\W_]", kalan) else ""


# --- tutar (F sutunu) ----------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Tutar:
    """miktar None ise ayristirilamadi: metin `ek`te durur. neden: '' (tamam/bos) | sayi_yok | coklu | donem_yok | sayi_belirsiz."""

    miktar: float | None = None
    para: str = "TRY"
    donem: str = "ay"
    ek: str = ""
    neden: str = ""


def _carpan_ve_para(kat: str, jeton_son: int) -> tuple[Decimal, str | None, tuple[int, int] | None]:
    bulunan = _CARPAN_DESENI.match(kat, jeton_son)
    if not bulunan:
        return Decimal(1), None, None
    kelime = bulunan.group(1)
    for ad, deger, para in _CARPANLAR:
        if ad == kelime:
            return deger, para, bulunan.span(1)
    return Decimal(1), None, None


def _tutar_cozumle(metin: str, donem_zorunlu: bool) -> tuple[Decimal | None, str, str, list[tuple[int, int]], str, int]:
    """Tek tutar cikarir: (miktar, para, donem, taninan_araliklar, neden, adet). miktar None ise neden dolu."""
    kat = katla(metin)
    aralik: list[tuple[int, int]] = []
    adet = 1
    adetler = list(_ADET_DESENI.finditer(kat))
    if len(adetler) > 1:
        return None, "TRY", "ay", [], "coklu", 1
    if adetler:
        adet = int(adetler[0].group("n"))
        aralik.append(adetler[0].span("adet"))
        kat = _bosalt(kat, adetler[0].span("adet"))
    jetonlar = list(_SAYI_JETONU.finditer(kat))
    if not jetonlar:
        return None, "TRY", "ay", [], "sayi_yok", 1
    if len(jetonlar) > 1:
        return None, "TRY", "ay", [], "coklu", 1
    jeton = jetonlar[0]
    carpan, carpan_parasi, carpan_araligi = _carpan_ve_para(kat, jeton.end())
    taban = sayi_degeri(jeton.group(), carpanli=carpan_araligi is not None)
    if taban is None:
        return None, "TRY", "ay", [], "sayi_belirsiz", 1
    aralik.append(jeton.span())
    if carpan_araligi:
        aralik.append(carpan_araligi)
        kat = _bosalt(kat, carpan_araligi)
    paralar: dict[str, tuple[int, int]] = {}
    for kod, desen in _PARA_DESENLERI:
        for b in desen.finditer(kat):
            paralar.setdefault(kod, b.span())
            aralik.append(b.span())
    if carpan_parasi:
        paralar.setdefault(carpan_parasi, carpan_araligi or (0, 0))
    if len(paralar) > 1:
        return None, "TRY", "ay", [], "coklu", 1
    para = next(iter(paralar), "TRY")
    donemler: dict[str, int] = {}
    for kod, desen in _DONEM_DESENLERI:
        for b in desen.finditer(kat):
            donemler[kod] = donemler.get(kod, 0) + 1
            aralik.append(b.span())
    if len(donemler) > 1:
        return None, "TRY", "ay", [], "coklu", 1
    donem = next(iter(donemler), "")
    if not donem and donem_zorunlu:
        return None, para, "ay", [], "donem_yok", 1
    return taban * carpan * adet, para, donem, aralik, "", adet


def tutar_ayristir(deger: object) -> Tutar:
    """F sutunu: "88,2 KTL/ay", "1250,75 $ / ay", "900 eurox4 adet (tek seferlik)", "140bin ₺ / Aylık" ... Donem zorunludur."""
    if deger is None or (isinstance(deger, str) and not deger.strip()):
        return Tutar()
    if _sayisal_mi(deger):
        deger = Decimal(str(deger))
        return Tutar(miktar=float(deger), donem="ay") if deger >= 0 else Tutar(ek=_kirp(str(deger)), neden="sayi_belirsiz")
    metin = _temiz(deger)
    if not re.search(r"[^\W_]", metin):
        return Tutar()
    miktar, para, donem, aralik, neden, adet = _tutar_cozumle(metin, donem_zorunlu=True)
    if miktar is None:
        return Tutar(ek=_kirp(metin), neden=neden)
    artik = _artik(metin, aralik)
    ek = metin if adet > 1 else artik  # adetle carpildiysa hesabin gorunmesi icin asil metin kalir
    return Tutar(miktar=float(miktar), para=para, donem=donem, ek=_kirp(ek))


# --- saat (G sutunu) -----------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Saat:
    saat: float | None = None
    ek: str = ""
    neden: str = ""  # '' | sayi_yok | coklu | birim | donem_yok | sayi_belirsiz


def saat_ayristir(deger: object) -> Saat:
    """G sutunu: "36 Saat / Ay" -> 36. Yalniz SAAT/ay kabul edilir; adamgun, TL, donemsiz saat ayristirilmaz (nota gider)."""
    if deger is None or (isinstance(deger, str) and not deger.strip()):
        return Saat()
    if _sayisal_mi(deger):
        sayi = Decimal(str(deger))
        return Saat(saat=float(sayi)) if sayi >= 0 else Saat(ek=_kirp(str(deger)), neden="sayi_belirsiz")
    metin = _temiz(deger)
    if not re.search(r"[^\W_]", metin):
        return Saat()
    kat = katla(metin)
    jetonlar = list(_SAYI_JETONU.finditer(kat))
    if not jetonlar:
        return Saat(ek=_kirp(metin), neden="sayi_yok")
    if len(jetonlar) > 1:
        return Saat(ek=_kirp(metin), neden="coklu")
    saat_bulundu = _SAAT_DESENI.search(kat)
    para_var = any(d.search(kat) for _, d in _PARA_DESENLERI) or _CARPAN_DESENI.match(kat, jetonlar[0].end()) is not None
    if not saat_bulundu or para_var:
        return Saat(ek=_kirp(metin), neden="birim")
    taban = sayi_degeri(jetonlar[0].group())
    if taban is None:
        return Saat(ek=_kirp(metin), neden="sayi_belirsiz")
    donemler = {kod for kod, d in _DONEM_DESENLERI if d.search(kat)}
    if donemler != {"ay"}:
        return Saat(ek=_kirp(metin), neden="donem_yok")
    aralik = [jetonlar[0].span(), saat_bulundu.span()] + [b.span() for _, d in _DONEM_DESENLERI for b in d.finditer(kat)]
    return Saat(saat=float(taban), ek=_kirp(_artik(metin, aralik)))


def yillik_saat_ayristir(deger: object) -> Saat:
    """"Yillik verimlilik faydasi (saat efor kazanci/12 ay)": "432 saat", "432 saat/yil", "432 saat / 12 ay" -> 432. Sayi hucresi oldugu gibi.
    Aylik (/ay) ya da tek seferlik yazilmis, para birimli ya da saatsiz metin ayristirilmaz (nota gider)."""
    if deger is None or (isinstance(deger, str) and not deger.strip()):
        return Saat()
    if _sayisal_mi(deger):
        sayi = Decimal(str(deger))
        return Saat(saat=float(sayi)) if sayi >= 0 else Saat(ek=_kirp(str(deger)), neden="sayi_belirsiz")
    metin = _temiz(deger)
    if not re.search(r"[^\W_]", metin):
        return Saat()
    kat = katla(metin)
    on_iki = re.search(r"(?<![\d.,])12\s*ay(?![a-z])", kat)
    if on_iki:
        kat = _bosalt(kat, on_iki.span())
    jetonlar = list(_SAYI_JETONU.finditer(kat))
    if not jetonlar:
        return Saat(ek=_kirp(metin), neden="sayi_yok")
    if len(jetonlar) > 1:
        return Saat(ek=_kirp(metin), neden="coklu")
    saat_bulundu = _SAAT_DESENI.search(kat)
    para_var = any(d.search(kat) for _, d in _PARA_DESENLERI) or _CARPAN_DESENI.match(kat, jetonlar[0].end()) is not None
    if not saat_bulundu or para_var:
        return Saat(ek=_kirp(metin), neden="birim")
    taban = sayi_degeri(jetonlar[0].group())
    if taban is None:
        return Saat(ek=_kirp(metin), neden="sayi_belirsiz")
    if {kod for kod, d in _DONEM_DESENLERI if d.search(kat)} - {"yil"}:
        return Saat(ek=_kirp(metin), neden="donem_yok")
    aralik = [jetonlar[0].span(), saat_bulundu.span(), *([on_iki.span()] if on_iki else [])]
    aralik += [b.span() for _, d in _DONEM_DESENLERI for b in d.finditer(kat)]
    return Saat(saat=float(taban), ek=_kirp(_artik(metin, aralik)))


# --- yil ici gelir (K sutunu) --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class YilIci:
    tutar: float | None = None
    ek: str = ""
    neden: str = ""  # '' | sayi_yok | coklu | para | sayi_belirsiz


_YIL_ETIKETI = re.compile(r"(?:19|20)\d{2}\s*yil(?:i|\s)\s*ici\s*(?:gelir\w*)?\s*[:=-]?|(?:19|20)\d{2}\s*yil(?:i|lik)?\s*gelir\w*\s*[:=-]?")


def yil_ici_ayristir(deger: object) -> YilIci:
    """K sutunu: "2026 yılı içi gelir: 1 MTL" -> 1.000.000 (TL). Etiket sayilmaz; donem aranmaz; TL disi para birimi ayristirilmaz."""
    if deger is None or (isinstance(deger, str) and not deger.strip()):
        return YilIci()
    if _sayisal_mi(deger):
        sayi = Decimal(str(deger))
        return YilIci(tutar=float(sayi)) if sayi >= 0 else YilIci(ek=_kirp(str(deger)), neden="sayi_belirsiz")
    metin = _temiz(deger)
    kat = katla(metin)
    etiket = _YIL_ETIKETI.search(kat)
    aralik: list[tuple[int, int]] = []
    if etiket:
        aralik.append(etiket.span())
        kat = _bosalt(kat, etiket.span())
    jetonlar = list(_SAYI_JETONU.finditer(kat))
    if not jetonlar:
        return YilIci(ek=_kirp(metin), neden="sayi_yok")
    if len(jetonlar) > 1:
        return YilIci(ek=_kirp(metin), neden="coklu")
    carpan, carpan_parasi, carpan_araligi = _carpan_ve_para(kat, jetonlar[0].end())
    taban = sayi_degeri(jetonlar[0].group(), carpanli=carpan_araligi is not None)
    if taban is None:
        return YilIci(ek=_kirp(metin), neden="sayi_belirsiz")
    aralik.append(jetonlar[0].span())
    if carpan_araligi:
        aralik.append(carpan_araligi)
        kat = _bosalt(kat, carpan_araligi)
    paralar = {kod for kod, d in _PARA_DESENLERI if d.search(kat)}
    if carpan_parasi:
        paralar.add(carpan_parasi)
    if paralar - {"TRY"}:
        return YilIci(ek=_kirp(metin), neden="para")
    aralik += [b.span() for _, d in _PARA_DESENLERI for b in d.finditer(kat)]
    return YilIci(tutar=float(taban * carpan), ek=_kirp(_artik(metin, aralik)))


# --- tarih (I / J sutunlari) ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Tarih:
    """tarih: ayristirilan gun (None olabilir). isaret: metindeki durum ipucu (devam | baslamadi | tamamlandi | iptal | ''). ek: tarihe cevrilemeyen metin."""

    tarih: date | None = None
    isaret: str = ""
    ek: str = ""


_AYLAR = {
    "ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6, "temmuz": 7, "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}  # fmt: skip
_GUN_AY_YIL = re.compile(r"^\s*(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4})(?!\d)")
_ISO_TARIH = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_AY_YIL = re.compile(r"^\s*([a-z]+)\s+(\d{4})(?!\d)")
_DURUM_IPUCLARI = (
    ("iptal", re.compile(r"iptal|vazge[cç]|cancel")),
    ("tamamlandi", re.compile(r"^\W*(?:tamamland|bitti|kapand|completed|done)")),
    ("baslamadi", re.compile(r"^\W*(?:baslamad|baslanmad|baslamamis|baslanmamis|not started)")),
    ("devam", re.compile(r"^\W*(?:devam|surmekte|suruyor|in progress|ongoing)")),
)


def tarih_ayristir(deger: object, son: bool = False) -> Tarih:
    """I/J sutunu. datetime/date dogrudan; "6.08.2026 (...)" bastaki tarih; "Ağustos 2026" ayin ilk (son=True: son) gunu;
    "devam ediyor" / "başlamadı" / "Tamamlandı" / "iptal" durum ipucudur (tarih None); gerisi `ek` olarak kalir."""
    if isinstance(deger, datetime):
        return Tarih(tarih=deger.date())
    if isinstance(deger, date):
        return Tarih(tarih=deger)
    if deger is None:
        return Tarih()
    metin = _temiz(deger)
    if not metin:
        return Tarih()
    kat = katla(metin)
    bulunan = _GUN_AY_YIL.match(kat)
    if bulunan:
        gun, ay, yil = (int(x) for x in bulunan.groups())
    else:
        iso_bulunan = _ISO_TARIH.match(kat)
        if iso_bulunan:
            yil, ay, gun = (int(x) for x in iso_bulunan.groups())
            bulunan = iso_bulunan
    if bulunan:
        try:
            tarih = date(yil, ay, gun)
        except ValueError:
            return Tarih(ek=_kirp(metin))
        kalan = metin[bulunan.end() :].strip()
        return Tarih(tarih=tarih, ek=_kirp(kalan) if re.search(r"[^\W_]", kalan) else "")
    ay_yil = _AY_YIL.match(kat)
    if ay_yil and ay_yil.group(1) in _AYLAR:
        ay, yil = _AYLAR[ay_yil.group(1)], int(ay_yil.group(2))
        try:
            gun = calendar.monthrange(yil, ay)[1] if son else 1
            tarih = date(yil, ay, gun)
        except (ValueError, calendar.IllegalMonthError):
            return Tarih(ek=_kirp(metin))
        kalan = metin[ay_yil.end() :].strip()
        return Tarih(tarih=tarih, ek=_kirp(kalan) if re.search(r"[^\W_]", kalan) else "")
    for ad, desen in _DURUM_IPUCLARI:
        if desen.search(kat):
            kisa = bool(re.fullmatch(r"\W*(?:devam ediyor|devam|baslamadi|tamamlandi|iptal|iptal edildi)\W*", kat))
            return Tarih(isaret=ad, ek="" if kisa else _kirp(metin))
    return Tarih(ek=_kirp(metin))


# --- durum ---------------------------------------------------------------------------------------------------------
_C_ONEKLERI = (
    ("iptal", re.compile(r"^\W*iptal")),
    ("tamamlandi", re.compile(r"^\W*(?:tamamland|bitti|kapand|completed|done)")),
    ("baslamadi", re.compile(r"^\W*(?:baslamad|baslanmad|baslamamis|baslanmamis|not started)")),
    ("devam", re.compile(r"^\W*(?:devam|surmekte|suruyor|in progress|ongoing)")),
)


def durum_oneki(metin: object) -> str | None:
    """Metnin ILK sozcugu bir durum bildiriyorsa o durum (baslamadi | devam | tamamlandi | iptal), yoksa None. Cumle ortasindaki "tamamlandı" sayilmaz."""
    kat = katla(metin if metin is not None else "").lstrip()
    for ad, desen in _C_ONEKLERI:
        if desen.search(kat):
            return ad
    return None


def durum_cikar(guncel_durum: object, baslangic: Tarih, bitis: Tarih, bugun: date) -> str:
    """baslamadi | devam | tamamlandi | iptal. Oncelik: (1) "Güncel durum" metninin ILK sozcugu, (2) bitis sutunu ipucu, (3) baslangic sutunu ipucu,
    (4) gecmis bir bitis tarihi -> tamamlandi, aksi halde devam."""
    onek = durum_oneki(guncel_durum)
    if onek:
        return onek
    if bitis.isaret:
        return bitis.isaret
    if baslangic.isaret:
        return baslangic.isaret
    if bitis.tarih and bitis.tarih <= bugun:
        return "tamamlandi"
    return "devam"


# --- kisiler -------------------------------------------------------------------------------------------------------
_KISI_AYRACI = re.compile(r"\s*(?:,|&|;|/|\+|\n|\r|-|–|—)\s*|\s+ve\s+", re.IGNORECASE)


def kisi_bol(metin: object) -> list[str]:
    """"A, B & C - D ve E" -> ["A", "B", "C", "D", "E"]; bos/yinelenen parcalar atilir, ilk gorunum sirasi korunur."""
    cikti: list[str] = []
    gorulen: set[str] = set()
    for parca in _KISI_AYRACI.split(str(metin if metin is not None else "")):
        ad = _temiz(parca)
        anahtar = katla(ad)
        if len(ad) < 2 or anahtar in gorulen or not re.search(r"[^\W\d_]", ad):
            continue
        gorulen.add(anahtar)
        cikti.append(ad)
    return cikti


# --- baslik haritasi -----------------------------------------------------------------------------------------------
# Sira onemlidir: "Ek açıklamalar" 'aciklama'dan, "yıl içi gelir" 'gelir'den once yakalanir.
_BASLIK_KURALLARI = (
    ("yol", re.compile(r"yol harita|roadmap")),
    ("yillik_saat", re.compile(r"yillik verimlilik|yillik efor|yearly effort|yearly efficiency")),
    ("baslangic", re.compile(r"baslangic|start")),
    ("bitis", re.compile(r"bitis|(?<![a-z])end(?![a-z])")),
    ("yil_ici", re.compile(r"yil ici|yillik gelir|year revenue")),
    ("ek", re.compile(r"^ek(?![a-z])|(?<![a-z])ek aciklama|notlar")),
    ("fayda_turu", re.compile(r"fayda tur|benefit type")),
    ("verimlilik", re.compile(r"verimlilik|efficiency|efor")),
    ("gelir", re.compile(r"gelir|revenue")),
    ("musteri", re.compile(r"musteri|customer")),
    ("durum", re.compile(r"(?<![a-z])durum|status")),
    ("tam", re.compile(r"(?<![a-z])tam(?![a-z])|sorumlu|owner")),
    ("aciklama", re.compile(r"aciklama|detay|description")),
    ("baslik", re.compile(r"ozet|baslik|(?<![a-z])isin adi|(?<![a-z])is adi|title|summary")),
)


def baslik_haritasi(satir: list[object] | tuple[object, ...]) -> dict[str, int]:
    """Bir satirdaki basliklari alan anahtarlarina esler: {anahtar: sutun_indeksi}. Tanimsiz baslik atlanir; ilk eslesen sutun kazanir."""
    harita: dict[str, int] = {}
    for i, hucre in enumerate(satir):
        kat = katla(_temiz(hucre))
        if not kat:
            continue
        for anahtar, desen in _BASLIK_KURALLARI:
            if anahtar not in harita and desen.search(kat):
                harita[anahtar] = i
                break
    return harita


# --- bolum satiri --------------------------------------------------------------------------------------------------
_BOLUM_INISIYATIF = re.compile(r"insiyatif|inisiyatif|initiative|gelir art")
_BOLUM_PROJE = re.compile(r"(?<![a-z])proje|calisma|planli|(?<![a-z])isler(?![a-z])|projects?")


def bolum_turu(metin: object) -> str | None:
    """Bolum (tek hucreli) satir metninden kayit turu: inisiyatif | proje | None (taninmayan baslik)."""
    kat = katla(_temiz(metin))
    if _BOLUM_INISIYATIF.search(kat):
        return "inisiyatif"
    if _BOLUM_PROJE.search(kat):
        return "proje"
    return None


def baslik_anahtari(baslik: object) -> str:
    """Ayni is tespiti (tur + baslik): bosluk, buyuk/kucuk harf ve Turkce harf farki yok sayilir."""
    return re.sub(r"\s+", " ", katla(str(baslik if baslik is not None else ""))).strip()
