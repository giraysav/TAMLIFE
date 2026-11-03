"""Ortak yardimcilar (paketler birbirini import etmez, ortak kod burada): yanit/hata bicimi, zaman, sayfalama, kimlik tipi, Turkce metin."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Annotated

from pydantic import Field

from app.dil import m

if TYPE_CHECKING:
    from starlette.requests import Request

EN_FAZLA_SAYFA_BASINA = 200
EN_BUYUK_KIMLIK = 2_147_483_647  # PostgreSQL INTEGER ile uyumlu; SQLite 64 bit sinirinin cok altinda
EN_BUYUK_SAYFA_NO = 1_000_000  # sayfa ofseti SQLite'a gider: sinirsiz olursa OverflowError

# Yol ve govde kimlikleri icin tek tip: sinir disi deger veritabanina varmadan 422 olur. Her int kimlik bunu kullanir.
KimlikTipi = Annotated[int, Field(ge=1, le=EN_BUYUK_KIMLIK)]


class UygulamaHatasi(Exception):
    """kod = HTTP durumu; mesaj yoneticiye gosterilir (sir/host/yol tasimaz)."""

    def __init__(self, kod: int, mesaj: str) -> None:
        super().__init__(mesaj)
        self.kod = kod
        self.mesaj = mesaj


def simdi() -> datetime:
    return datetime.now(UTC)


def rapor_donemi(an: date | datetime) -> tuple[int, int]:
    """Bir ayda gonderilen aylik rapor ONCEKI ayin raporudur: Ekim'de Eylul raporu (Ocak'ta onceki yilin Araligi)."""
    return (an.year, an.month - 1) if an.month > 1 else (an.year - 1, 12)


# Rapor uyumu (Genel Bakis / Ekip Ozeti) bu donemden itibaren sayilir. 2026-11-03 kullanici: "Ekim ayi atilan raporlar itibariyla
# hesaplanacak, yil basindan bugune olan kisimlari hesaplatma" (panelde ilk rapor donemi Ekim 2026; oncesi panelde yok).
RAPOR_UYUM_BASLANGICI = (2026, 10)


def rapor_uyum_aylari(an: date | datetime) -> list[int]:
    """Bu yil raporu beklenen aylar: tamamlanmis rapor donemleri (Ocak..son rapor ayi), RAPOR_UYUM_BASLANGICI'ndan oncesi haric.
    Ocak'ta (son donem onceki yilin Araligi) bos: yeni yilin beklentisi Subat'ta baslar."""
    yil, ay = rapor_donemi(an)
    if yil != an.year or (yil, ay) < RAPOR_UYUM_BASLANGICI:
        return []
    ilk = RAPOR_UYUM_BASLANGICI[1] if yil == RAPOR_UYUM_BASLANGICI[0] else 1
    return list(range(ilk, ay + 1))


def iso(zaman: datetime | None) -> str | None:
    """SQLite saat dilimi saklamaz: ofsetsiz deger UTC kabul edilir. Cikti 'Z' ekli ISO 8601."""
    if zaman is None:
        return None
    if zaman.tzinfo is None:
        zaman = zaman.replace(tzinfo=UTC)
    return zaman.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sayfa_bilgisi(sayfa: int, adet: int, toplam: int) -> tuple[int, int, int]:
    """(sayfa, atlanacak, adet): sayfa 1..son sayfa araligina kisitlanir."""
    adet = max(1, min(int(adet), EN_FAZLA_SAYFA_BASINA))
    son = max(1, -(-toplam // adet))
    sayfa = max(1, min(int(sayfa), son))
    return sayfa, (sayfa - 1) * adet, adet


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


def normal(metin: object) -> str:
    """Eslestirme icin: Turkce karakterler ASCII'ye, kucuk harf, tek bosluk (skor motoru ve tampon kullanir)."""
    tablo = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return re.sub(r"\s+", " ", str(metin or "").translate(tablo).lower()).strip()


def ok(veri: object) -> dict[str, object]:
    """Basari govdesi: {"status": "success", "data": ...} (API kontrati)."""
    return {"status": "success", "data": veri}


async def govde_oku(request: Request, sinir: int, mesaj: str = "") -> bytes:
    """Ham dosya govdesi (cok parcali form yok). Sinir hem bildirilen boyuta hem akisa uygulanir (yalan Content-Length/chunked); asimda 413."""
    mesaj = mesaj or m(f"Dosya çok büyük (en fazla {sinir // 1048576} MB).", f"File too large (max {sinir // 1048576} MB).")
    bildirilen = request.headers.get("content-length", "")
    if bildirilen.isdigit() and int(bildirilen) > sinir:
        raise UygulamaHatasi(413, mesaj)
    govde = bytearray()
    async for parca in request.stream():
        govde += parca
        if len(govde) > sinir:
            raise UygulamaHatasi(413, mesaj)
    return bytes(govde)
