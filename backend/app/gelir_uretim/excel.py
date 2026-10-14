"""Excel disa aktarim: kaynak tablonun sutun duzeni (A-J) + yil ici gelir (K) + fayda turu (L). Cikti ice_al ile yeniden okunabilir.

Metin hucreleri formul sayilmaz (veri_tipi 's'); kontrol karakterleri temizlenir. Dil: dosya her zaman Turkce (kaynak tablo Turkce).
"""

from __future__ import annotations

import io
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.gelir_uretim import servis
from app.gelir_uretim.ayristir import durum_oneki
from app.gelir_uretim.models import RevenueBenefit

BASLIKLAR = (
    "İlgili TAM",
    "İşin özeti",
    "Güncel durum",
    "Detaylı açıklaması",
    "Hangi müşteri/müşterileri etkilediği",
    "Aylık gelir faydası (TL/ay)",
    "Aylık verimlilik faydası (saat efor kazancı/ay)",
    "Ek açıklamalar",
    "Proje/çalışma başlangıç tarihi",
    "Proje/çalışma bitiş tarihi",
    "Yıl içi gelir (TL)",
    "Fayda türü",
)
GENISLIKLER = (28, 42, 40, 60, 28, 24, 28, 40, 16, 16, 18, 14)
BOLUM_INISIYATIF = "Tam Gelir Artırıcı Aldığımız İnsiyatifler"
SAYFA_ADI = "Gelir Faydası"
DURUM_ETIKETLERI = {"baslamadi": "Başlamadı", "devam": "Devam ediyor", "tamamlandi": "Tamamlandı", "iptal": "İptal"}
FAYDA_ETIKETLERI = {"gelir": "Gelir", "tasarruf": "Tasarruf", "verimlilik": "Verimlilik"}
PARA_ETIKETLERI = {"TRY": "TL", "USD": "USD", "EUR": "EUR"}
DONEM_SONEKLERI = {"ay": "/ay", "yil": "/yıl", "tek_sefer": " (tek seferlik)"}


def sayi_metni(sayi: float) -> str:
    """88200.0 -> "88200"; 1250.75 -> "1250,75" (binlik ayraci yok: yeniden okunurken belirsizlik olmaz)."""
    return format(Decimal(str(sayi)).normalize(), "f").replace(".", ",")


def tutar_metni(r: RevenueBenefit) -> str:
    if r.revenue_amount is None:
        return r.revenue_note
    metin = f"{sayi_metni(r.revenue_amount)} {PARA_ETIKETLERI[r.revenue_currency]}{DONEM_SONEKLERI[r.revenue_period]}"
    return f"{metin} {r.revenue_note}".strip() if r.revenue_note else metin


def saat_metni(r: RevenueBenefit) -> str:
    if r.hours_per_month is None:
        return r.hours_note
    metin = f"{sayi_metni(r.hours_per_month)} saat/ay"
    return f"{metin} {r.hours_note}".strip() if r.hours_note else metin


def durum_metni(r: RevenueBenefit) -> str:
    """Durum sozcugu "Guncel durum" metninin basinda yoksa eklenir: yeniden okununca durum kaybolmaz."""
    if durum_oneki(r.status_note) == r.status:
        return r.status_note
    etiket = DURUM_ETIKETLERI[r.status]
    return f"{etiket}. {r.status_note}" if r.status_note else etiket


def _yaz(sayfa, satir: int, sutun: int, deger: object):
    if isinstance(deger, str):
        deger = ILLEGAL_CHARACTERS_RE.sub("", deger)
    hucre = sayfa.cell(row=satir, column=sutun, value=deger)
    if isinstance(deger, str):
        hucre.data_type = "s"  # "=..." ile baslayan metin formul olarak calismasin
    return hucre


def excel_olustur(db: Session) -> bytes:
    kitap = Workbook()
    sayfa = kitap.active
    sayfa.title = SAYFA_ADI
    for sutun, (baslik, genislik) in enumerate(zip(BASLIKLAR, GENISLIKLER, strict=True), start=1):
        hucre = _yaz(sayfa, 1, sutun, baslik)
        hucre.font = Font(bold=True, color="FFFFFF")
        hucre.fill = PatternFill("solid", fgColor="1F3A5F")
        hucre.alignment = Alignment(vertical="center", wrap_text=True)
        sayfa.column_dimensions[get_column_letter(sutun)].width = genislik
    sayfa.freeze_panes = "A2"
    satir = 2
    bolum_yazildi = False
    for r, kisiler in servis.tum_kayitlar(db):
        if r.kind == "inisiyatif" and not bolum_yazildi:
            satir += 1
            _yaz(sayfa, satir, 1, BOLUM_INISIYATIF).font = Font(bold=True)
            satir += 1
            bolum_yazildi = True
        adlar = [servis.kisi_adi(k) for k in kisiler] + ([r.other_people] if r.other_people else [])
        degerler = (
            ", ".join(adlar),
            r.title,
            durum_metni(r),
            r.description,
            r.customers,
            tutar_metni(r),
            saat_metni(r),
            r.extra_note,
            r.start_date,
            r.end_date,
            r.year_revenue,
            FAYDA_ETIKETLERI[r.benefit_type],
        )
        for sutun, deger in enumerate(degerler, start=1):
            hucre = _yaz(sayfa, satir, sutun, deger)
            hucre.alignment = Alignment(vertical="top", wrap_text=sutun not in (9, 10, 11, 12))
            if sutun in (9, 10) and deger is not None:
                hucre.number_format = "dd.mm.yyyy"
            elif sutun == 11 and deger is not None:
                hucre.number_format = "#,##0.00"
        satir += 1
    veri = io.BytesIO()
    kitap.save(veri)
    return veri.getvalue()
