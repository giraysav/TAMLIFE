"""Eslestirme ve deger okuma yardimcilari (saf fonksiyonlar, veritabani yok).

Musteri No: bir kartta BIRDEN COK numara olabilir ('22499633, 22499634'); karsilastirma anahtari bastaki sifirlari
atilmis rakam dizisidir ('0012' = '12'). Eslesme musteri UNVANINDAN degil numaradan yapilir (unvan degisebilir).
"""

from __future__ import annotations

import math
import re

from app.ortak import normal

_AYRAC = re.compile(r"[,;/\n]+")
_BINLIK_NOKTA = re.compile(r"^\d{1,3}(\.\d{3})+$")


def _metne(deger: object) -> str:
    if deger is None or isinstance(deger, bool):
        return ""
    if isinstance(deger, float) and deger.is_integer():
        deger = int(deger)  # Excel/CSV sayisal hucre: 22135503.0
    return str(deger)


def anahtar(numara: object) -> str:
    """Karsilastirma anahtari: yalniz rakam, bastaki sifirlar atilir ('' = numara degil)."""
    return re.sub(r"\D", "", _metne(numara)).lstrip("0")


def musteri_anahtarlari(deger: object) -> list[str]:
    """Hucredeki / kartin alanindaki numaralarin anahtarlari (tekil, sirali)."""
    sonuc: list[str] = []
    for parca in _AYRAC.split(_metne(deger)):
        k = anahtar(parca)
        if k and k not in sonuc:
            sonuc.append(k)
    return sonuc


def alan_anahtarlari(alan: str, deger: object) -> list[str]:
    """Eslesme alanina gore anahtarlar: customer_no -> numara anahtarlari; ncst / name -> normalize metin."""
    if alan == "customer_no":
        return musteri_anahtarlari(deger)
    metin = normal(_metne(deger))
    return [metin] if metin else []


def sayi(deger: object) -> float | None:
    """Turkce bicime duyarli sayi: '1.234,56' / '1234,5' / '1.234' (binlik) / '12.5'. Okunamazsa None."""
    if deger is None or isinstance(deger, bool):
        return None
    if isinstance(deger, (int, float)):
        return float(deger) if math.isfinite(float(deger)) else None
    temiz = re.sub(r"[^\d.,\-+]", "", str(deger))
    if not temiz or temiz in "+-":
        return None
    if "," in temiz and "." in temiz:
        # sondaki ayrac ondaliktir
        ondalik = "," if temiz.rfind(",") > temiz.rfind(".") else "."
        binlik = "." if ondalik == "," else ","
        temiz = temiz.replace(binlik, "").replace(ondalik, ".")
    elif "," in temiz:
        temiz = temiz.replace(",", ".")
    elif _BINLIK_NOKTA.match(temiz.lstrip("+-")):
        temiz = temiz.replace(".", "")
    try:
        sonuc = float(temiz)
    except ValueError:
        return None
    return sonuc if math.isfinite(sonuc) else None


ISLECLER = ("esit", "esit_degil", "baslar", "icerir", "icermez", "dolu", "bos")
DEGERSIZ_ISLECLER = ("dolu", "bos")


def kosul_saglar(hucre: object, islec: str, deger: str) -> bool:
    """Tek kosul: metinler normalize edilir (buyuk/kucuk harf ve Turkce karakter farki yok sayilir)."""
    metin = normal(_metne(hucre))
    if islec == "dolu":
        return metin != ""
    if islec == "bos":
        return metin == ""
    hedef = normal(deger)
    if islec == "esit":
        return metin == hedef
    if islec == "esit_degil":
        return metin != hedef
    if islec == "baslar":
        return metin.startswith(hedef)
    if islec == "icerir":
        return hedef in metin
    if islec == "icermez":
        return hedef not in metin
    return False
