"""Turkcell'li Takvimi (2026-10-15 kullanicinin yukledigi "2026 Turkcell'li Takvimi" gorselinden): tum ekipte ayni olan gunler.

Gunler kisinin dosyasina yazilmaz; kaydi olmayan gun bu tablodan gelir (takvim.servis._gunler). Kisi o gune kendi kaydini girerse
(ornegin tatilde calisti) kendi kaydi gecerlidir. Durum kodlari takvim.servis.DURUMLAR ile ayni:
  resmi_tatil   sari  "Resmi tatil"
  arife_tatili + sirket_izni  yari sari yari mavi "0,5 gun resmi tatil + 0,5 gun izin": gun ikiye bolunur (status2), izin 0,5
  sirket_izni   mavi  "Sirket tatili" (izin sayiminda 1)
Yeni yil eklemek icin ayni bicimde bir sozluk yazin.
"""

from __future__ import annotations

from datetime import date

_2026: dict[str, tuple[str, str] | tuple[str, str, str]] = {
    "01-01": ("resmi_tatil", "Yılbaşı"),
    "01-02": ("sirket_izni", "Şirket tatili"),
    "03-19": ("arife_tatili", "Ramazan Bayramı Arifesi", "sirket_izni"),
    "03-20": ("resmi_tatil", "Ramazan Bayramı 1. Gün"),
    "03-21": ("resmi_tatil", "Ramazan Bayramı 2. Gün"),
    "03-22": ("resmi_tatil", "Ramazan Bayramı 3. Gün"),
    "04-23": ("resmi_tatil", "Ulusal Egemenlik ve Çocuk Bayramı"),
    "04-24": ("sirket_izni", "Şirket tatili"),
    "05-01": ("resmi_tatil", "Emek ve Dayanışma Günü"),
    "05-19": ("resmi_tatil", "Gençlik ve Spor Bayramı"),
    "05-25": ("sirket_izni", "Şirket tatili"),
    "05-26": ("arife_tatili", "Kurban Bayramı Arifesi", "sirket_izni"),
    "05-27": ("resmi_tatil", "Kurban Bayramı 1. Gün"),
    "05-28": ("resmi_tatil", "Kurban Bayramı 2. Gün"),
    "05-29": ("resmi_tatil", "Kurban Bayramı 3. Gün"),
    "05-30": ("resmi_tatil", "Kurban Bayramı 4. Gün"),
    "07-13": ("sirket_izni", "Şirket tatili"),
    "07-14": ("sirket_izni", "Şirket tatili"),
    "07-15": ("resmi_tatil", "Demokrasi ve Milli Birlik Günü"),
    "07-16": ("sirket_izni", "Şirket tatili"),
    "07-17": ("sirket_izni", "Şirket tatili"),
    "08-24": ("sirket_izni", "Şirket tatili"),
    "08-25": ("sirket_izni", "Şirket tatili"),
    "08-26": ("sirket_izni", "Şirket tatili"),
    "08-27": ("sirket_izni", "Şirket tatili"),
    "08-28": ("sirket_izni", "Şirket tatili"),
    "08-30": ("resmi_tatil", "Zafer Bayramı"),
    "10-28": ("arife_tatili", "Cumhuriyet Bayramı Öncesi", "sirket_izni"),
    "10-29": ("resmi_tatil", "Cumhuriyet Bayramı"),
    "10-30": ("sirket_izni", "Şirket tatili"),
}

# gun -> (durum, aciklama, ikinci yari durumu ya da None)
KURUM_GUNLERI: dict[date, tuple[str, str, str | None]] = {date.fromisoformat(f"2026-{g}"): (d[0], d[1], d[2] if len(d) > 2 else None) for g, d in _2026.items()}


def kurum_gunu(gun: date) -> tuple[str, str, str | None] | None:
    """(durum, aciklama, durum2) ya da None."""
    return KURUM_GUNLERI.get(gun)


def varsayilan_durum(gun: date) -> tuple[str, str | None]:
    """Kisinin kaydi yokken gunun (durum, durum2): kurum gunu ya da ('calisiyor', None) (hafta sonu arayuzde ayrica gosterilir)."""
    k = KURUM_GUNLERI.get(gun)
    return (k[0], k[2]) if k else ("calisiyor", None)


def aralik(bas: date, son: date) -> list[tuple[date, str, str, str | None]]:
    return [(g, d, a, d2) for g, (d, a, d2) in sorted(KURUM_GUNLERI.items()) if bas <= g <= son]
