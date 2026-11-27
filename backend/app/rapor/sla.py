# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Aylik rapora yuklenen SLA Excel'i (OneDesk ciktisi): grafikler, aylik seriler ve donem sayilari.

Uretim karsiligi: blueprints/customer_bp.py upload_excel, _gomulu_grafikler, _monthly_series, _kapanis_aylari.
Farklar:
- Rapora YALNIZ kapanan Alarm/Sikayet/Talep adet grafikleri ve yanlarinda ilk mudahale / cozum sure ortalamalari girer
  (kullanici karari 2026-10-11). Dosyaya gomulu gorseller (pasta grafikler vb.) KULLANILMAZ; grafik 'Kapanis Ayi'
  pivotlarinin serisinden tarayicida cizilir (matplotlib yok).
- Dosya saklanir: rapor gonderilirken ileti ekine otomatik girer. Yer: TAMLIFE_REPORT_DIR/sla/<musteri>/<yil>-<ay>.*
  Ayni donemde yeniden yukleme oncekinin yerine gecer. Ayni kayitta iletiye eklenecek ek dosyalar ('dosyalar', <yil>-<ay>-ekler/
  klasorunde). 'ekler' (eski elle eklenen grafik gorselleri) yalniz okunur: 2026-11-19 kullanici grafik ekleme / ice alma
  bolumunu kaldirdi; trafik grafikleri ReportDB sayisal verisinden panelde uretilecek.
Ham satir saklanmaz; yalniz dosyanin kendisi (ek olarak gidecek) ve ozet. Tum verinin analizi: rapor/sla_analiz.py.
"""

from __future__ import annotations

import io
import json
import math
import mimetypes
import os
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.dil import m
from app.ortak import UygulamaHatasi, eslestirme_anahtari

AZAMI_EXCEL = 30 * 1024 * 1024
AZAMI_ACIK = 400 * 1024 * 1024  # zip icindeki toplam acik boyut (zip bombasina karsi)
AZAMI_EK_DOSYA = 20 * 1024 * 1024
AZAMI_EK_TOPLAM = 25 * 1024 * 1024  # Exchange ileti siniri altinda kalsin
EN_FAZLA_EK_DOSYA = 10
# Calistirilabilir/betik turleri ileti ekine konmaz (Outlook da engeller; alici tarafinda risk).
YASAK_UZANTILAR = {
    ".exe",
    ".bat",
    ".cmd",
    ".com",
    ".scr",
    ".pif",
    ".msi",
    ".msp",
    ".dll",
    ".js",
    ".jse",
    ".vbs",
    ".vbe",
    ".wsf",
    ".wsh",
    ".ps1",
    ".psm1",
    ".hta",
    ".lnk",
    ".reg",
    ".jar",
    ".cpl",
    ".inf",
    ".sh",
}
ANALIZ_SATIRI = 5000
KATEGORILER = (("alarm", "Alarm"), ("sikayet", "Şikayet"), ("talep", "Talep"))
KATEGORI_EN = {"alarm": "Alarm", "sikayet": "Complaint", "talep": "Request"}
BEKLENEN_SAYFALAR = ("Alarm Detay", "Şikayet Detay", "Talep Detay", "Alarm Analiz", "Şikayet Analiz", "Talep Analiz")


class SlaHata(UygulamaHatasi):
    pass


def _k(metin: object) -> str:
    return eslestirme_anahtari(metin or "")


# --- seriler ---------------------------------------------------------------------------------------
def ay_kodu(deger: object) -> str:
    """'YYYY-MM' (tarih bicimli hucre de olur); degilse hucre metni."""
    if isinstance(deger, datetime) or hasattr(deger, "strftime"):
        return deger.strftime("%Y-%m")  # type: ignore[union-attr]
    return str(deger).strip()


def sayi(deger: object) -> float | None:
    """Sayi degilse None (0 DEGIL): 'no data returned' grafikte sahte sifir olmasin."""
    if isinstance(deger, bool) or not isinstance(deger, int | float):
        return None
    deger = float(deger)
    return deger if math.isfinite(deger) else None


def _hucre(satirlar: list[tuple], satir: int, sutun: int) -> object:
    """1 tabanli; aralik disi None."""
    if satir < 1 or satir > len(satirlar):
        return None
    dizi = satirlar[satir - 1]
    return dizi[sutun - 1] if 0 < sutun <= len(dizi) else None


def aylik_seri(
    satirlar: list[tuple], ay_satiri: int, ay_sutunu: int, anahtar: str, aralik: int = 4
) -> tuple[list[str], list[float | None]]:
    """'Kapanis Ayi' basliginin sagindaki sutunlarda `anahtar` gecen basligin altindaki ay/deger serisi (Total haric)."""
    deger_sutunu = next(
        (c for c in range(ay_sutunu + 1, ay_sutunu + 1 + aralik) if _k(anahtar) in _k(_hucre(satirlar, ay_satiri, c))), None
    )
    if deger_sutunu is None:
        return [], []
    aylar: list[str] = []
    degerler: list[float | None] = []
    satir = ay_satiri + 1
    while satir <= len(satirlar):
        ay = _hucre(satirlar, satir, ay_sutunu)
        if ay is None:
            break
        if _k(ay) != "total":
            aylar.append(ay_kodu(ay))
            degerler.append(sayi(_hucre(satirlar, satir, deger_sutunu)))
        satir += 1
    return aylar, degerler


def _kapanis_aylari(satirlar: list[tuple]) -> list[str]:
    if not satirlar:
        return []
    sutun = next((i for i, v in enumerate(satirlar[0], start=1) if v and _k("Kapanış Ayı") in _k(v)), None)
    if sutun is None:
        return []
    return [ay_kodu(r[sutun - 1]) for r in satirlar[1:] if len(r) >= sutun and r[sutun - 1]]


def _musteri_adlari(satirlar: list[tuple]) -> set[str]:
    """Detay sayfasinin 'Musteri Adi' sutunundaki unvanlar (baslik ilk satir). Yalniz bilgi: yuklemeyi kisitlamaz (2026-11-02)."""
    if not satirlar:
        return set()
    sutun = next((i for i, v in enumerate(satirlar[0]) if v and _k("Müşteri Adı") == _k(v)), None)
    if sutun is None:
        return set()
    return {str(r[sutun]).strip() for r in satirlar[1:] if len(r) > sutun and r[sutun] and str(r[sutun]).strip()}


def _baslik(kategori: str, tur: str, dil: str) -> str:
    ad = dict(KATEGORILER)[kategori]
    if dil == "en":
        en = KATEGORI_EN[kategori]
        return f"Monthly Closed {en} Count" if tur == "adet" else f"Monthly Closed {en} First Response and Resolution Time Averages"
    return f"Aylık Kapanan {ad} Adetleri" if tur == "adet" else f"Aylık Kapanan {ad} İlk Müdahale ve Çözüm Süre Ortalamaları"


def _sayfa_satirlari(ws: Any, sinir: int | None = None) -> list[tuple]:
    satirlar = []
    for i, satir in enumerate(ws.iter_rows(values_only=True)):
        if sinir is not None and i >= sinir:
            break
        satirlar.append(tuple(satir))
    return satirlar


def analiz(veri: bytes, yil: int, ay: int) -> dict:
    """Dosyadan grafik listesi ve donem sayilari. Okunamayan dosyada 400."""
    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException

    if len(veri) > AZAMI_EXCEL:
        raise SlaHata(400, m("Dosya çok büyük (en fazla 30 MB).", "File too large (max 30 MB)."))
    hata = m(
        "Dosya geçerli bir .xlsx değil ya da beklenen yapıda değil.",
        "The file is not a valid .xlsx or does not have the expected structure.",
    )
    try:
        z = zipfile.ZipFile(io.BytesIO(veri))
        if sum(b.file_size for b in z.infolist()) > AZAMI_ACIK:
            raise SlaHata(400, hata)
        wb = openpyxl.load_workbook(io.BytesIO(veri), read_only=True, data_only=True)
    except SlaHata:
        raise
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as exc:
        raise SlaHata(400, hata) from exc
    try:
        sayfalar = list(wb.sheetnames)
        anahtar = {_k(s): s for s in sayfalar}
        grafikler: list[dict] = []
        for kategori, ad in KATEGORILER:
            sayfa = anahtar.get(_k(f"{ad} Analiz"))
            if sayfa is None:
                continue
            satirlar = _sayfa_satirlari(wb[sayfa], ANALIZ_SATIRI)
            bulunan: set[str] = set()
            for satir_no, dizi in enumerate(satirlar[:12], start=1):
                for sutun_no, deger in enumerate(dizi, start=1):
                    if not deger or _k("Kapanış Ayı") not in _k(deger):
                        continue
                    ust = _hucre(satirlar, satir_no - 1, sutun_no)
                    pivot = str(ust).strip() if ust else ""
                    if "adet" not in bulunan:
                        aylar, adet = aylik_seri(satirlar, satir_no, sutun_no, "adedi")
                        if aylar:
                            bulunan.add("adet")
                            grafikler.append(_grafik(kategori, "adet", pivot, aylar, {"adet": adet}))
                    if "sure" not in bulunan:
                        aylar, cozum = aylik_seri(satirlar, satir_no, sutun_no, "çözüm süresi")
                        _, ilk = aylik_seri(satirlar, satir_no, sutun_no, "ilk müdahale")
                        if aylar:
                            bulunan.add("sure")
                            grafikler.append(_grafik(kategori, "sure", pivot, aylar, {"ilk": ilk or [], "cozum": cozum}))
        hedef = f"{yil}-{ay:02d}"
        sayilar: dict[str, dict] = {}
        dosya_aylari: set[str] = set()
        musteriler: set[str] = set()
        for kategori, ad in KATEGORILER:
            sayfa = anahtar.get(_k(f"{ad} Detay"))
            if sayfa is None:
                continue
            satirlar = _sayfa_satirlari(wb[sayfa])
            kapanis = _kapanis_aylari(satirlar)
            musteriler |= _musteri_adlari(satirlar)
            dosya_aylari.update(k for k in kapanis if re.fullmatch(r"\d{4}-\d{2}", k))
            sayilar[kategori] = {"donem": sum(1 for k in kapanis if k == hedef), "toplam": max(len(satirlar) - 1, 0)}
    finally:
        wb.close()
    return {
        "sayfalar": sayfalar,
        "bulunan": [s for s in BEKLENEN_SAYFALAR if _k(s) in anahtar],
        "eksik": [s for s in BEKLENEN_SAYFALAR if _k(s) not in anahtar],
        "grafikler": grafikler,
        "sayilar": sayilar,
        "dosya_donemi": max(dosya_aylari) if dosya_aylari else None,
        "donem": hedef,
        "musteriler": sorted(musteriler),
    }


def _grafik(kategori: str, tur: str, pivot: str, aylar: list[str], seriler: dict) -> dict:
    return {
        "anahtar": f"{kategori}-{tur}",
        "kategori": kategori,
        "tur": tur,
        "baslik": {"tr": _baslik(kategori, tur, "tr"), "en": _baslik(kategori, tur, "en")},
        "pivot": pivot,
        "gorsel": None,
        "aylar": aylar,
        "seriler": seriler,
    }


# --- depo ------------------------------------------------------------------------------------------
def _klasor(musteri_id: int) -> Path:
    from app.rapor.servis import rapor_klasoru

    return rapor_klasoru() / "sla" / str(int(musteri_id))


def _yollar(musteri_id: int, yil: int, ay: int) -> tuple[Path, Path]:
    kok = _klasor(musteri_id) / f"{int(yil)}-{int(ay):02d}"
    return kok.with_suffix(".xlsx"), kok.with_suffix(".json")


def _yaz_json(yol: Path, kayit: dict) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps(kayit, ensure_ascii=False), encoding="utf-8")
    os.replace(gecici, yol)


def oku(musteri_id: int, yil: int, ay: int) -> dict | None:
    _, js = _yollar(musteri_id, yil, ay)
    if not js.is_file():
        return None
    try:
        kayit = json.loads(js.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return kayit if isinstance(kayit, dict) else None


def ozet(kayit: dict | None) -> dict | None:
    """Taslakta gosterilen kisa bilgi (gorseller haric)."""
    if not kayit:
        return None
    dosya = kayit.get("dosya")
    return {
        "dosya": dosya.get("ad") if isinstance(dosya, dict) else None,
        "boyut": dosya.get("boyut") if isinstance(dosya, dict) else None,
        "zaman": kayit.get("zaman"),
        "yukleyen": kayit.get("yukleyen"),
        "grafik": len((kayit.get("analiz") or {}).get("grafikler") or []),
        "ek_gorsel": len(kayit.get("ekler") or []),
        "ek_dosya": len(kayit.get("dosyalar") or []),
    }


def _bos_kayit() -> dict:
    return {"dosya": None, "zaman": None, "yukleyen": None, "analiz": None, "ekler": [], "dosyalar": []}


def _kaydet_ya_da_sil(js: Path, kayit: dict) -> None:
    """SLA dosyasi, gorsel ve ek dosya kalmadiysa kayit silinir."""
    if not kayit.get("dosya") and not kayit.get("ekler") and not kayit.get("dosyalar"):
        js.unlink(missing_ok=True)
    else:
        _yaz_json(js, kayit)


def excel_yukle(musteri_id: int, yil: int, ay: int, veri: bytes, dosya_adi: str, yukleyen: str) -> dict:
    """Musteri unvani denetlenmez (2026-11-02 kullanici: "musteri eslesmesi kuralini kaldir, isteyen istedigi SLA excelini
    yuklesin"; 2026-10-26 unvan kurali kalkti). Gecerli kural yalniz analiz(): sayfalardan grafik, sayilar ve yorum."""
    sonuc = analiz(veri, yil, ay)
    xlsx, js = _yollar(musteri_id, yil, ay)
    xlsx.parent.mkdir(parents=True, exist_ok=True)
    onceki = oku(musteri_id, yil, ay) or {}
    gecici = xlsx.with_suffix(".xtmp")
    gecici.write_bytes(veri)
    os.replace(gecici, xlsx)
    ad = re.sub(r"[\\/:*?\"<>|\r\n]+", "_", os.path.basename(dosya_adi or "")).strip() or "SLA_Raporu.xlsx"
    if not ad.lower().endswith(".xlsx"):
        ad += ".xlsx"
    kayit = {
        "dosya": {"ad": ad[:150], "boyut": len(veri)},
        "zaman": datetime.now(UTC).isoformat(),
        "yukleyen": yukleyen[:120],
        "analiz": sonuc,
        "ekler": onceki.get("ekler") or [],
        "dosyalar": onceki.get("dosyalar") or [],
    }
    _yaz_json(js, kayit)
    return kayit


def excel_dosyasi(musteri_id: int, yil: int, ay: int) -> tuple[bytes, str] | None:
    """Ileti eki: (bayt, dosya adi). Kayit yoksa None."""
    xlsx, _ = _yollar(musteri_id, yil, ay)
    kayit = oku(musteri_id, yil, ay)
    if not xlsx.is_file() or not kayit or not isinstance(kayit.get("dosya"), dict):
        return None
    return xlsx.read_bytes(), str(kayit["dosya"].get("ad") or "SLA_Raporu.xlsx")


def excel_sil(musteri_id: int, yil: int, ay: int) -> dict:
    """SLA dosyasi silinir; ek dosyalar korunur."""
    xlsx, js = _yollar(musteri_id, yil, ay)
    kayit = oku(musteri_id, yil, ay) or _bos_kayit()
    xlsx.unlink(missing_ok=True)
    _kaydet_ya_da_sil(js, {**kayit, "dosya": None, "analiz": None})
    return {"silindi": True}


# --- iletiye eklenecek dosyalar --------------------------------------------------------------------
def _ek_klasoru(musteri_id: int, yil: int, ay: int) -> Path:
    return _klasor(musteri_id) / f"{int(yil)}-{int(ay):02d}-ekler"


def guvenli_ad(dosya_adi: str, varsayilan: str = "ek") -> str:
    ad = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", os.path.basename((dosya_adi or "").replace("\\", "/"))).strip(" .")
    return (ad or varsayilan)[:150]


def dosya_ekle(musteri_id: int, yil: int, ay: int, veri: bytes, dosya_adi: str, ekleyen: str) -> dict:
    """Rapor iletisine eklenecek dosya (sozlesme, tutanak vb.). Calistirilabilir turler reddedilir."""
    if not veri:
        raise SlaHata(400, m("Dosya seçilmedi.", "No file was selected."))
    if len(veri) > AZAMI_EK_DOSYA:
        raise SlaHata(400, m("Dosya çok büyük (en fazla 20 MB).", "File too large (max 20 MB)."))
    ad = guvenli_ad(dosya_adi)
    if Path(ad).suffix.lower() in YASAK_UZANTILAR:
        raise SlaHata(400, m("Bu dosya türü iletiye eklenemez.", "This file type cannot be attached to the message."))
    _, js = _yollar(musteri_id, yil, ay)
    kayit = oku(musteri_id, yil, ay) or _bos_kayit()
    dosyalar = list(kayit.get("dosyalar") or [])
    if len(dosyalar) >= EN_FAZLA_EK_DOSYA:
        raise SlaHata(
            400, m(f"En fazla {EN_FAZLA_EK_DOSYA} ek dosya eklenebilir.", f"At most {EN_FAZLA_EK_DOSYA} attachments can be added.")
        )
    if sum(int(d.get("boyut", 0)) for d in dosyalar) + len(veri) > AZAMI_EK_TOPLAM:
        raise SlaHata(400, m("Ek dosyaların toplamı 25 MB'ı aşamaz.", "Attachments cannot exceed 25 MB in total."))
    if any(str(d.get("ad", "")).lower() == ad.lower() for d in dosyalar):
        raise SlaHata(409, m("Aynı adlı bir ek dosya zaten var.", "An attachment with the same name already exists."))
    numara = max((int(d.get("no", 0)) for d in dosyalar), default=0) + 1
    klasor = _ek_klasoru(musteri_id, yil, ay)
    klasor.mkdir(parents=True, exist_ok=True)
    gecici = klasor / f"{numara}.tmp"
    gecici.write_bytes(veri)
    os.replace(gecici, klasor / str(numara))
    dosyalar.append(
        {
            "no": numara,
            "ad": ad,
            "boyut": len(veri),
            "tur": mimetypes.guess_type(ad)[0] or "application/octet-stream",
            "ekleyen": ekleyen[:120],
            "zaman": datetime.now(UTC).isoformat(),
        }
    )
    kayit["dosyalar"] = dosyalar
    _yaz_json(js, kayit)
    return {"no": numara}


def dosya_sil(musteri_id: int, yil: int, ay: int, numara: int) -> dict:
    _, js = _yollar(musteri_id, yil, ay)
    kayit = oku(musteri_id, yil, ay)
    dosyalar = list((kayit or {}).get("dosyalar") or [])
    kalan = [d for d in dosyalar if int(d.get("no", 0)) != numara]
    if kayit is None or len(kalan) == len(dosyalar):
        raise SlaHata(404, m("Dosya bulunamadı.", "File not found."))
    (_ek_klasoru(musteri_id, yil, ay) / str(int(numara))).unlink(missing_ok=True)
    kayit["dosyalar"] = kalan
    _kaydet_ya_da_sil(js, kayit)
    return {"silindi": numara}


def ek_dosyalari(musteri_id: int, yil: int, ay: int) -> list[tuple[bytes, str, str]]:
    """Ileti ekleri: (bayt, ad, MIME). Diskte olmayan kayit atlanir."""
    kayit = oku(musteri_id, yil, ay) or {}
    klasor = _ek_klasoru(musteri_id, yil, ay)
    sonuc = []
    for d in kayit.get("dosyalar") or []:
        yol = klasor / str(int(d.get("no", 0)))
        if yol.is_file():
            sonuc.append((yol.read_bytes(), str(d.get("ad") or "ek"), str(d.get("tur") or "application/octet-stream")))
    return sonuc
