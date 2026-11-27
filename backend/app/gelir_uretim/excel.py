# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Excel rapor: kullanicinin "Gelir Faydasi" Excel'inin 13 sutunu (ayni sira ve basliklar) + fayda turu; ikinci sayfa Ozet (toplamlar ve suzgec).
Yalniz ONAYLI isler (servis.tum_kayitlar). Ilk sayfa ice_al ile yeniden okunabilir.

Metin hucreleri formul sayilmaz (veri_tipi 's'); kontrol karakterleri temizlenir. Dil: dosya her zaman Turkce (kaynak tablo Turkce).
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.gelir_uretim import servis
from app.gelir_uretim.ayristir import durum_oneki
from app.gelir_uretim.models import RevenueBenefit
from app.models import AppUser

BASLIKLAR = (
    "İlgili TAM",
    "İşin özeti",
    "Güncel durum",
    "Yol Haritası",
    "Detaylı açıklaması",
    "Hangi müşteri/müşterileri etkilediği",
    "Aylık gelir faydası (TL/ay)",
    "Yıllık gelir faydası (TL/12 ay)",
    "Aylık verimlilik faydası (saat efor kazancı/ay)",
    "Yıllık verimlilik faydası (saat efor kazancı/12 ay)",
    "Ek açıklamalar",
    "Proje/çalışma başlangıç tarihi",
    "Proje/çalışma bitiş tarihi",
    "Fayda türü",
)
GENISLIKLER = (28, 42, 40, 40, 60, 28, 24, 20, 28, 20, 40, 16, 16, 14)
TARIH_SUTUNLARI = (12, 13)
SAYI_SUTUNLARI = (8, 10)
OZET_SAYFASI = "Özet"
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


def _baslik_hucresi(hucre) -> None:
    hucre.font = Font(bold=True, color="FFFFFF")
    hucre.fill = PatternFill("solid", fgColor="1F3A5F")
    hucre.alignment = Alignment(vertical="center", wrap_text=True)


def _para_toplami(toplamlar: dict[str, float]) -> str:
    return " + ".join(f"{sayi_metni(v)} {PARA_ETIKETLERI[p]}" for p, v in toplamlar.items()) or "0"


def _ozet_sayfasi(kitap: Workbook, kayitlar: list[RevenueBenefit], suzgec: dict) -> None:
    o = servis.ozet_hesapla(kayitlar, len(kayitlar))
    sayfa = kitap.create_sheet(OZET_SAYFASI)
    sayfa.column_dimensions["A"].width = 44
    sayfa.column_dimensions["B"].width = 40
    _yaz(sayfa, 1, 1, "Gelir Faydası Sağlanan İşler raporu").font = Font(bold=True, size=13)
    etiketler = {"q": "Arama", "tur": "Tür", "durum": "Durum", "fayda": "Fayda türü", "tam": "TAM", "yil": "Yıl"}
    secili = [f"{etiketler[k]}: {v}" for k, v in suzgec.items() if v not in (None, "") and k in etiketler]
    satirlar = (
        ("Rapor tarihi", date.today()),
        ("Kapsam", "Onaylı işler" + (" · " + ", ".join(secili) if secili else " (tümü)")),
        ("İş sayısı", o["is_sayisi"]),
        *((DURUM_ETIKETLERI[d], o["durum_sayilari"][d]) for d in servis.DURUMLAR),
        ("Aylık gelir faydası (iptaller hariç)", _para_toplami(o["aylik_gelir"])),
        ("Yıllık tutar girilen gelir", _para_toplami(o["yillik_gelir"])),
        ("Tek seferlik gelir", _para_toplami(o["tek_seferlik_gelir"])),
        ("Yıllık gelir faydası (TL/12 ay)", o["yil_ici_gelir"]),
        ("Aylık verimlilik faydası (saat)", o["aylik_saat"]),
        ("Yıllık verimlilik faydası (saat)", o["yillik_saat"]),
    )
    for i, (ad, deger) in enumerate(satirlar, start=3):
        _baslik_hucresi(_yaz(sayfa, i, 1, ad))
        hucre = _yaz(sayfa, i, 2, deger)
        if isinstance(deger, date):
            hucre.number_format = "dd.mm.yyyy"
        elif isinstance(deger, float):
            hucre.number_format = "#,##0.00"
        hucre.alignment = Alignment(horizontal="left")


def excel_olustur(db: Session, **suzgec: object) -> bytes:
    kitap = Workbook()
    sayfa = kitap.active
    sayfa.title = SAYFA_ADI
    for sutun, (baslik, genislik) in enumerate(zip(BASLIKLAR, GENISLIKLER, strict=True), start=1):
        _baslik_hucresi(_yaz(sayfa, 1, sutun, baslik))
        sayfa.column_dimensions[get_column_letter(sutun)].width = genislik
    sayfa.freeze_panes = "A2"
    satir = 2
    bolum_yazildi = False
    kayitlar = servis.tum_kayitlar(db, **suzgec)
    for r, kisiler in kayitlar:
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
            r.roadmap,
            r.description,
            r.customers,
            tutar_metni(r),
            r.year_revenue,
            saat_metni(r),
            r.hours_per_year,
            r.extra_note,
            r.start_date,
            r.end_date,
            FAYDA_ETIKETLERI[r.benefit_type],
        )
        for sutun, deger in enumerate(degerler, start=1):
            hucre = _yaz(sayfa, satir, sutun, deger)
            hucre.alignment = Alignment(vertical="top", wrap_text=sutun not in (*TARIH_SUTUNLARI, *SAYI_SUTUNLARI, len(BASLIKLAR)))
            if sutun in TARIH_SUTUNLARI and deger is not None:
                hucre.number_format = "dd.mm.yyyy"
            elif sutun in SAYI_SUTUNLARI and deger is not None:
                hucre.number_format = "#,##0.00"
        satir += 1
    tam = db.get(AppUser, suzgec["tam"]) if suzgec.get("tam") else None
    _ozet_sayfasi(kitap, [r for r, _ in kayitlar], {**suzgec, "tam": servis.kisi_adi(tam) if tam else suzgec.get("tam")})
    veri = io.BytesIO()
    kitap.save(veri)
    return veri.getvalue()
