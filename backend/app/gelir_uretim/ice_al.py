# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Excel ice aktarma: kaynak tablo (kullanicinin "Gelir Faydasi" Excel'i) -> onizleme -> uygulama.

  onizleme(db, veri, dosya)  : dosyayi okur, her satiri ayristirir, hicbir sey yazmaz.
  uygula(db, user, veri, ...) : AYNI dosyayi yeniden okuyup yalniz YENI satirlari ekler (tek islem; commit cagirana aittir).

Kurallar:
  - Sutunlar basliga gore bulunur (Turkce harf/buyuk-kucuk farksiz); yalniz "Isin ozeti" zorunludur. Basliksiz sutun, "Proje/calisma bitis"
    sutunundan hemen sonra gelen ve "yil ici gelir" metni tasiyan sutun olarak (K) okunur.
  - Tek hucreli satir bolum basligidir ("... Insiyatifler" -> kayit turu inisiyatif); ondan once kayitlar proje sayilir. Bos satirlar atlanir.
  - "Ilgili TAM" , & - ve ; / ile bolunur, adlar yalniz etkin TAM personeliyle eslesir (Turkce harf/buyuk-kucuk farksiz);
    eslesmeyenler "Diger kisiler"e yazilir. Yonetici ve admin hesaplari eslesmez.
  - Ayni tur + baslik zaten kayitliysa satir "var", dosyada daha once geciyorsa "tekrar" sayilir ve eklenmez: ikinci yukleme hicbir sey eklemez.
  - Sayiya cevrilemeyen metin kaybolmaz: not alanlarinda durur, onizlemede uyari olarak gorunur (ayrintilar ayristir.py).
    Tek istisna: fayda/not hucresinin TAMAMI 'yok', '-', 'n/a' ise bos sayilir (bilgi tasimaz).
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dil import m
from app.gelir_uretim import servis
from app.gelir_uretim.ayristir import (
    Tarih,
    baslik_anahtari,
    baslik_haritasi,
    bolum_turu,
    bos_isareti,
    durum_cikar,
    katla,
    kisi_bol,
    saat_ayristir,
    tarih_ayristir,
    tutar_ayristir,
    yil_ici_ayristir,
    yillik_saat_ayristir,
)
from app.gelir_uretim.models import RevenueBenefit
from app.kullanicilar import ad_soyad, kullanici_kaydi, personel
from app.models import AppUser
from app.ortak import iso, simdi
from app.session import Principal
from app.tampon import ice_aktarma_gecmisi

AZAMI_BAYT = 5 * 1024 * 1024
AZAMI_ACIK = 100 * 1024 * 1024  # zip icindeki toplam acik boyut (zip bombasina karsi)
EN_COK_SATIR = 500
OKUNAN_SATIR_SINIRI = 5000  # sondaki bos satirlar sonsuz dolasmasin
SUTUN_SINIRI = 40
GEREKLI_BASLIK = "baslik"
ISTENEN_SUTUNLAR = ("tam", "baslik", "durum", "yol", "aciklama", "musteri", "gelir", "verimlilik", "yillik_saat", "baslangic", "bitis")
SUTUN_ADLARI = {
    "tam": ("İlgili TAM", "Responsible TAM"),
    "baslik": ("İşin özeti", "Work summary"),
    "durum": ("Güncel durum", "Current status"),
    "yol": ("Yol Haritası", "Roadmap"),
    "yillik_saat": ("Yıllık verimlilik faydası", "Yearly efficiency benefit"),
    "aciklama": ("Detaylı açıklaması", "Description"),
    "musteri": ("Etkilenen müşteri", "Affected customers"),
    "gelir": ("Aylık gelir faydası", "Monthly revenue benefit"),
    "verimlilik": ("Verimlilik faydası", "Efficiency benefit"),
    "baslangic": ("Başlangıç tarihi", "Start date"),
    "bitis": ("Bitiş tarihi", "End date"),
}
FAYDA_ADLARI = {
    "gelir": "gelir", "revenue": "gelir", "tasarruf": "tasarruf", "saving": "tasarruf", "savings": "tasarruf", "verimlilik": "verimlilik", "efficiency": "verimlilik",
}  # fmt: skip


def _onizleme_satiri(no: int, durum: str, tur: str, baslik: str, uyarilar: list[str], **alanlar: object) -> dict:
    """Onizleme satiri: her satirda ayni anahtarlar bulunur (arayuz eksik alan beklemez)."""
    return {
        "satir": no, "durum": durum, "kind": tur, "title": baslik, "status": "", "benefit_type": "", "people": [], "other_people": "",
        "revenue_amount": None, "revenue_currency": "TRY", "revenue_period": "ay", "revenue_note": "", "year_revenue": None,
        "hours_per_month": None, "hours_per_year": None, "start_date": None, "end_date": None, "uyarilar": uyarilar, **alanlar,
    }  # fmt: skip


@dataclass
class SatirPlani:
    satir: int
    durum: str  # yeni | var | tekrar | hatali
    kayit: dict | None
    kisi_idleri: list[int]
    onizleme: dict


@dataclass
class Plan:
    dosya: str
    sayfa: str
    baslik_satiri: int
    satirlar: list[SatirPlani] = field(default_factory=list)
    uyarilar: list[str] = field(default_factory=list)

    def sayilar(self) -> dict:
        sonuc = {"toplam": len(self.satirlar), "yeni": 0, "var": 0, "tekrar": 0, "hatali": 0}
        for s in self.satirlar:
            sonuc[s.durum] += 1
        return sonuc


# --- dosya okuma -------------------------------------------------------------------------------------------------
def _bos(deger: object) -> bool:
    return deger is None or (isinstance(deger, str) and not deger.strip())


def excel_oku(veri: bytes) -> tuple[str, int, dict[str, int], list[tuple[int, list[object]]]]:
    """(sayfa, baslik_satiri, baslik_haritasi, [(excel_satir_no, hucreler)]) -- ilk basligi bulunan sayfa. Hata: 400/413."""
    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException

    okunamadi = m("Excel dosyası okunamadı. .xlsx biçiminde bir dosya seçin.", "The Excel file could not be read. Choose an .xlsx file.")
    if not veri:
        raise servis.GelirUretimHata(400, m("Dosya seçilmedi.", "No file selected."))
    try:
        if sum(b.file_size for b in zipfile.ZipFile(io.BytesIO(veri)).infolist()) > AZAMI_ACIK:
            raise ValueError("boyut")
        kitap = openpyxl.load_workbook(io.BytesIO(veri), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as exc:
        raise servis.GelirUretimHata(400, okunamadi) from exc
    try:
        for sayfa in kitap.worksheets:
            if hasattr(sayfa, "reset_dimensions"):
                sayfa.reset_dimensions()  # bazi uretecler boyutu yanlis yazar: tum satirlar okunsun
            satirlar: list[tuple[int, list[object]]] = []
            for no, hucreler in enumerate(sayfa.iter_rows(values_only=True), start=1):
                if no > OKUNAN_SATIR_SINIRI:
                    break
                satirlar.append((no, list(hucreler)[:SUTUN_SINIRI]))
            for i, (no, hucreler) in enumerate(satirlar[:15]):
                harita = baslik_haritasi(hucreler)
                if GEREKLI_BASLIK in harita and len(harita) >= 3:
                    govde = [(n, h) for n, h in satirlar[i + 1 :] if not all(_bos(x) for x in h)]
                    # Basliksiz yil ici gelir sutunu (K): bitisten hemen sonraki, basligi bos sutun
                    if "yil_ici" not in harita:
                        sonraki = max(harita.values()) + 1
                        if sonraki < len(hucreler) + 1 and (sonraki >= len(hucreler) or _bos(hucreler[sonraki])):
                            harita["yil_ici"] = sonraki
                    if len(govde) > EN_COK_SATIR + 20:
                        raise servis.GelirUretimHata(
                            413, m(f"Dosyada en fazla {EN_COK_SATIR} satır olabilir.", f"The file can have at most {EN_COK_SATIR} rows.")
                        )
                    return sayfa.title, no, harita, govde
        raise servis.GelirUretimHata(
            400,
            m(
                "Başlık satırı bulunamadı: ‘İşin özeti’ sütunu olan bir tablo gerekli.",
                "No header row found: a table with a ‘Work summary’ (İşin özeti) column is required.",
            ),
        )
    finally:
        kitap.close()


# --- hucre yardimcilari ------------------------------------------------------------------------------------------
def _metin(deger: object) -> str:
    if deger is None:
        return ""
    if isinstance(deger, datetime):
        return deger.date().isoformat()
    if isinstance(deger, date):
        return deger.isoformat()
    if isinstance(deger, float) and deger.is_integer():
        return str(int(deger))
    return str(deger).replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ").strip()


def _al(hucreler: list[object], harita: dict[str, int], anahtar: str) -> object:
    i = harita.get(anahtar)
    return hucreler[i] if i is not None and i < len(hucreler) else None


def _fayda_hucresi(hucreler: list[object], harita: dict[str, int], anahtar: str) -> object:
    """Fayda ve not sutunlari (F, G, H, K): hucrenin tamami 'yok', '-' gibi bir 'deger yok' isaretiyse bos sayilir (nota yazilmaz, uyari uretmez)."""
    deger = _al(hucreler, harita, anahtar)
    return None if bos_isareti(_metin(deger)) else deger


def _anahtar(ad: str) -> str:
    return " ".join(katla(ad).split())


def kisi_dizini(kisiler: list[AppUser]) -> dict[str, list[AppUser]]:
    """Ad anahtari -> kisiler. Her kisi 'gorunen ad', 'ad soyad' ve 'soyad ad' anahtarlariyla bulunur."""
    dizin: dict[str, list[AppUser]] = {}
    for k in kisiler:
        ad, soyad = ad_soyad(k)
        for aday in {_anahtar(k.display_name or ""), _anahtar(f"{ad} {soyad}"), _anahtar(f"{soyad} {ad}")}:
            if aday and k not in dizin.setdefault(aday, []):
                dizin[aday].append(k)
    return dizin


def _kisalt(metin: str, sinir: int, etiket: tuple[str, str], uyarilar: list[str]) -> str:
    if len(metin) <= sinir:
        return metin
    uyarilar.append(m(f"‘{etiket[0]}’ {sinir} karaktere kısaltıldı.", f"‘{etiket[1]}’ was shortened to {sinir} characters."))
    return metin[: sinir - 1].rstrip() + "…"


def _fayda_turu(f_metni: str, tutar_var: bool, saat_var: bool, acik: str | None) -> str:
    """Acik 'Fayda turu' sutunu varsa o; yoksa F metninden: gelir > verimlilik > tasarruf sozcugu; tutar yok + saat varsa verimlilik; aksi gelir."""
    if acik:
        return acik
    kat = katla(f_metni)
    if "gelir" in kat:
        return "gelir"
    if "verimlili" in kat:  # verimlilik, verimliliğe, verimliliği
        return "verimlilik"
    if "tasarruf" in kat:
        return "tasarruf"
    if not tutar_var and saat_var:
        return "verimlilik"
    return "gelir"


# --- plan ----------------------------------------------------------------------------------------------------------
def plan_olustur(
    dosya: str,
    sayfa: str,
    baslik_satiri: int,
    harita: dict[str, int],
    satirlar: list[tuple[int, list[object]]],
    kisiler: list[AppUser],
    mevcut: set[tuple[str, str]],
    bugun: date,
) -> Plan:
    plan = Plan(dosya=dosya, sayfa=sayfa, baslik_satiri=baslik_satiri)
    eksik = [m(*SUTUN_ADLARI[k]) for k in ISTENEN_SUTUNLAR if k not in harita]
    if eksik:
        plan.uyarilar.append(m("Bulunamayan sütunlar (boş sayıldı): ", "Columns not found (treated as empty): ") + ", ".join(eksik))
    dizin = kisi_dizini(kisiler)
    dosyada: set[tuple[str, str]] = set()
    tur = "proje"
    baslik_sutunu = harita[GEREKLI_BASLIK]
    for no, hucreler in satirlar:
        dolu = [i for i, h in enumerate(hucreler) if not _bos(h)]
        if len(dolu) == 1 and dolu[0] != baslik_sutunu:
            yeni_tur = bolum_turu(hucreler[dolu[0]])
            if yeni_tur:
                tur = yeni_tur
            else:
                plan.uyarilar.append(
                    m(
                        f"Satır {no}: bölüm başlığı türü anlaşılamadı (‘{_metin(hucreler[dolu[0]])[:60]}’); önceki tür sürdürüldü.",
                        f"Row {no}: the section heading type could not be determined (‘{_metin(hucreler[dolu[0]])[:60]}’); the previous type was kept.",
                    )
                )
            continue
        uyarilar: list[str] = []
        baslik = _kisalt(_metin(_al(hucreler, harita, GEREKLI_BASLIK)), servis.METIN_ALANLARI["title"][2], ("Başlık", "Title"), uyarilar)
        if not baslik:
            hata = [m("‘İşin özeti’ boş: satır eklenmez.", "‘Work summary’ is empty: the row is skipped.")]
            plan.satirlar.append(SatirPlani(no, "hatali", None, [], _onizleme_satiri(no, "hatali", tur, "", hata)))
            continue

        # kisiler
        idler: list[int] = []
        adlar: list[str] = []
        eslesmeyen: list[str] = []
        belirsiz: list[str] = []
        for ad in kisi_bol(_metin(_al(hucreler, harita, "tam"))):
            adaylar = dizin.get(_anahtar(ad), [])
            if len(adaylar) == 1:
                if adaylar[0].id not in idler:
                    idler.append(adaylar[0].id)
                    adlar.append(servis.kisi_adi(adaylar[0]))
            else:
                (belirsiz if adaylar else eslesmeyen).append(ad)
        diger = ", ".join(eslesmeyen + belirsiz)
        if eslesmeyen:
            uyarilar.append(
                m(
                    f"TAM eşleşmedi, ‘Diğer kişiler’e yazıldı: {', '.join(eslesmeyen)}",
                    f"No TAM account matched; written to ‘Other people’: {', '.join(eslesmeyen)}",
                )
            )
        if belirsiz:
            uyarilar.append(
                m(
                    f"Birden fazla TAM ile eşleşti, ‘Diğer kişiler’e yazıldı: {', '.join(belirsiz)}",
                    f"Matched more than one TAM account; written to ‘Other people’: {', '.join(belirsiz)}",
                )
            )
        diger = _kisalt(diger, servis.METIN_ALANLARI["other_people"][2], ("Diğer kişiler", "Other people"), uyarilar)

        # tutar / saat / yil ici gelir
        f_ham = _fayda_hucresi(hucreler, harita, "gelir")
        tutar = tutar_ayristir(f_ham)
        if tutar.neden in {"coklu", "donem_yok", "sayi_belirsiz"}:
            uyarilar.append(
                m(
                    "Gelir tutarı sayıya çevrilemedi (birden fazla sayı, dönem yok ya da belirsiz biçim); metin ‘Tutar notu’na yazıldı.",
                    "The revenue amount could not be converted to a number (several numbers, no period or unclear format); the text was kept in the amount note.",
                )
            )
        saat = saat_ayristir(_fayda_hucresi(hucreler, harita, "verimlilik"))
        if saat.neden in {"coklu", "birim", "donem_yok", "sayi_belirsiz"}:
            uyarilar.append(
                m(
                    "Verimlilik faydası saate çevrilemedi (yalnızca ‘saat/ay’ sayılır); metin ‘Efor notu’na yazıldı.",
                    "The efficiency benefit could not be converted to hours (only ‘hours/month’ counts); the text was kept in the effort note.",
                )
            )
        yil_ici = yil_ici_ayristir(_fayda_hucresi(hucreler, harita, "yil_ici"))
        ek_parcalar = [_metin(_fayda_hucresi(hucreler, harita, "ek"))]
        yil_saat = yillik_saat_ayristir(_fayda_hucresi(hucreler, harita, "yillik_saat"))
        if yil_saat.saat is None and yil_saat.ek:
            uyarilar.append(
                m(
                    "Yıllık verimlilik faydası saate çevrilemedi; metin ‘Ek açıklamalar’a yazıldı.",
                    "The yearly efficiency benefit could not be converted to hours; the text was kept in the additional notes.",
                )
            )
            ek_parcalar.append(f"Yıllık verimlilik (Excel): {yil_saat.ek}")
        elif yil_saat.ek:
            ek_parcalar.append(f"Yıllık verimlilik notu: {yil_saat.ek}")
        yil_ici_ham = _metin(_fayda_hucresi(hucreler, harita, "yil_ici"))
        if yil_ici.tutar is None and yil_ici_ham:
            uyarilar.append(
                m(
                    "Yıl içi gelir sayıya çevrilemedi; metin ‘Ek açıklamalar’a yazıldı.",
                    "The in-year revenue could not be converted to a number; the text was kept in the additional notes.",
                )
            )
            ek_parcalar.append(f"Yıl içi gelir (Excel): {yil_ici_ham}")
        elif yil_ici.ek:
            ek_parcalar.append(f"Yıl içi gelir notu: {yil_ici.ek}")

        # tarihler
        baslangic = tarih_ayristir(_al(hucreler, harita, "baslangic"))
        bitis = tarih_ayristir(_al(hucreler, harita, "bitis"), son=True)
        bitis_tarihi = bitis.tarih
        if baslangic.tarih and bitis_tarihi and bitis_tarihi < baslangic.tarih:
            uyarilar.append(m("Bitiş tarihi başlangıçtan önce: bitiş alınmadı.", "The end date is before the start date: it was not taken."))
            bitis = Tarih(isaret=bitis.isaret, ek=f"{bitis_tarihi.isoformat()} (başlangıçtan önce olduğu için alınmadı)")
            bitis_tarihi = None
        if baslangic.ek:
            ek_parcalar.append(f"Başlangıç tarihi notu: {baslangic.ek}")
        if bitis.ek:
            ek_parcalar.append(f"Bitiş tarihi notu: {bitis.ek}")
        ek_not = _kisalt("\n".join(p for p in ek_parcalar if p), servis.METIN_ALANLARI["extra_note"][2], ("Ek açıklamalar", "Additional notes"), uyarilar)

        durum_metni = _metin(_al(hucreler, harita, "durum"))
        durum = durum_cikar(durum_metni, baslangic, bitis, bugun)
        acik_fayda = FAYDA_ADLARI.get(_anahtar(_metin(_al(hucreler, harita, "fayda_turu")))) if "fayda_turu" in harita else None
        kayit = {
            "kind": tur,
            "benefit_type": _fayda_turu(_metin(f_ham), tutar.miktar is not None, saat.saat is not None, acik_fayda),
            "title": baslik,
            "status": durum,
            "status_note": _kisalt(durum_metni, servis.METIN_ALANLARI["status_note"][2], ("Güncel durum", "Current status"), uyarilar),
            "description": _kisalt(_metin(_al(hucreler, harita, "aciklama")), servis.METIN_ALANLARI["description"][2], ("Detaylı açıklama", "Description"), uyarilar),
            "customers": _kisalt(_metin(_al(hucreler, harita, "musteri")), servis.METIN_ALANLARI["customers"][2], ("Etkilenen müşteriler", "Affected customers"), uyarilar),
            "revenue_amount": tutar.miktar,
            "revenue_currency": tutar.para,
            "revenue_period": tutar.donem,
            "revenue_note": tutar.ek,
            "year_revenue": yil_ici.tutar,
            "hours_per_month": saat.saat,
            "hours_note": saat.ek,
            "hours_per_year": yil_saat.saat,
            "roadmap": _kisalt(_metin(_al(hucreler, harita, "yol")), servis.METIN_ALANLARI["roadmap"][2], ("Yol haritası", "Roadmap"), uyarilar),
            "extra_note": ek_not,
            "start_date": baslangic.tarih,
            "end_date": bitis_tarihi,
            "other_people": diger,
        }
        anahtar = (tur, baslik_anahtari(baslik))
        if anahtar in dosyada:
            durum_kodu = "tekrar"
            uyarilar.append(m("Aynı tür ve başlık dosyada daha önce geçiyor: satır eklenmez.", "The same type and title appear earlier in the file: the row is skipped."))
        elif anahtar in mevcut:
            durum_kodu = "var"
            uyarilar.append(m("Aynı tür ve başlıkta kayıt zaten var: satır eklenmez.", "A record with the same type and title already exists: the row is skipped."))
        else:
            durum_kodu = "yeni"
        dosyada.add(anahtar)
        plan.satirlar.append(
            SatirPlani(
                no,
                durum_kodu,
                kayit if durum_kodu == "yeni" else None,
                idler,
                _onizleme_satiri(
                    no, durum_kodu, tur, baslik, uyarilar,
                    status=durum, benefit_type=kayit["benefit_type"], people=adlar, other_people=diger,
                    revenue_amount=tutar.miktar, revenue_currency=tutar.para, revenue_period=tutar.donem, revenue_note=tutar.ek,
                    year_revenue=yil_ici.tutar, hours_per_month=saat.saat, hours_per_year=yil_saat.saat,
                    start_date=baslangic.tarih.isoformat() if baslangic.tarih else None,
                    end_date=bitis_tarihi.isoformat() if bitis_tarihi else None,
                ),
            )
        )
        if len(plan.satirlar) > EN_COK_SATIR:
            raise servis.GelirUretimHata(413, m(f"Dosyada en fazla {EN_COK_SATIR} satır olabilir.", f"The file can have at most {EN_COK_SATIR} rows."))
    return plan


def plan_hazirla(db: Session, veri: bytes, dosya: str) -> Plan:
    sayfa, baslik_satiri, harita, satirlar = excel_oku(veri)
    mevcut = {(r.kind, baslik_anahtari(r.title)) for r in db.scalars(select(RevenueBenefit))}
    return plan_olustur(dosya, sayfa, baslik_satiri, harita, satirlar, personel(db), mevcut, simdi().date())


def onizleme(db: Session, veri: bytes, dosya: str) -> dict:
    """Hicbir sey yazmaz. Satirlar: durum yeni | var | tekrar | hatali, ayristirilan alanlar ve uyarilar."""
    plan = plan_hazirla(db, veri, dosya)
    return {
        "dosya": plan.dosya,
        "sayfa": plan.sayfa,
        "baslik_satiri": plan.baslik_satiri,
        "plan": plan.sayilar(),
        "uyarilar": plan.uyarilar,
        "satirlar": [s.onizleme for s in plan.satirlar],
    }


def uygula(db: Session, user: Principal, veri: bytes, dosya: str) -> dict:
    """Yalniz 'yeni' satirlari ekler (commit etmez: cagiran tek islemde onaylar). Sayilari dondurur."""
    plan = plan_hazirla(db, veri, dosya)
    yapan = servis.kisi_adi(kullanici_kaydi(db, user))
    olusan: list[RevenueBenefit] = []
    for s in plan.satirlar:
        if s.durum == "yeni" and s.kayit is not None:
            olusan.append(servis.ekle(db, yapan, servis.temizle(s.kayit), s.kisi_idleri))
    sayilar = {**plan.sayilar(), "eklendi": len(olusan)}
    if olusan:  # 2026-11-01: aktarim Import > Ice aktarma gecmisi'nden geri alinabilir (sonradan duzenlenen kayit korunur)
        ice_aktarma_gecmisi.kaydet(db, "gelir_uretim", dosya, yapan, sayilar, {"kayitlar": [{"id": r.id, "zaman": iso(r.updated_at)} for r in olusan]})
    return {**sayilar, "uyarilar": plan.uyarilar}
