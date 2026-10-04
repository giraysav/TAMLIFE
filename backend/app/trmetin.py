"""Turkce metin yardimcilari (uretim extensions.py ve _cekirdek/ortak.py'den)."""

from __future__ import annotations

MONTH_LABELS_TR = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
    7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık",
}  # fmt: skip
MONTH_LABELS_EN = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}  # fmt: skip


def tr_kucuk(metin: object) -> str:
    """Turkce'ye uygun kucultme: 'I' -> 'i' degil, dotsuz i; 'I' ve 'i' ayri harftir."""
    return str(metin).replace("İ", "i").replace("I", "ı").lower()


def eslestirme_anahtari(metin: object) -> str:
    """Karsilastirma anahtari: I/i-dotsuz farki ve fazla bosluk yok sayilir."""
    return " ".join(tr_kucuk(metin).replace("ı", "i").split())


def ay_adi(ay: int, dil: str = "tr") -> str:
    return (MONTH_LABELS_EN if dil == "en" else MONTH_LABELS_TR).get(ay, str(ay))
