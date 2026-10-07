"""Kaynaklar: tampona veri getiren yollar. Bugun: CSV yukleme ve ornek veri (yalniz gelistirme).

Oracle kaynaklari (ReportDB, Onent, Urun-Tutar) AYNI arayuzde gorunur ama canli baglanti KAPALIDIR (app.external.connect).
Acilacagi gun: ayri bir isci surec kaynaktan SELECT calistirip satirlari depo.ice_al'a verir; panel sureci Oracle'a baglanmaz
(uretimde de boyleydi: native surucu web surecine yuklenmez).
"""

from __future__ import annotations

import csv
import io
import os
import random
import re
from collections import Counter
from collections.abc import Iterator
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.external import SOURCES
from app.models import Customer, IngestBatch
from app.ortak import UygulamaHatasi, iso
from app.tampon import depo
from app.tampon.eslestirme import musteri_anahtarlari

ORNEK = "ornek"
CSV_ON_EK = "csv_"
_AYRACLAR = (";", ",", "\t", "|")
_SLUG = re.compile(r"[^a-z0-9]+")


_ASCII = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iIsSgGuUoOcC")


def kaynak_anahtari(ad: str) -> str:
    """Yukleme kaynak adi -> 'csv_<slug>' (en fazla 40 karakter); bos/gecersizse 'csv_dosya'."""
    slug = _SLUG.sub("_", ad.translate(_ASCII).lower()).strip("_")
    return (CSV_ON_EK + (slug or "dosya"))[:40]


def _metne_cevir(veri: bytes) -> str:
    for kodlama in ("utf-8-sig", "cp1254"):
        try:
            return veri.decode(kodlama)
        except UnicodeDecodeError:
            continue
    return veri.decode("latin-1")


def _basliklari_tekillestir(ham: list[str]) -> list[str]:
    sonuc, sayac = [], Counter[str]()
    for i, h in enumerate(ham, 1):
        ad = h.strip() or f"Sütun {i}"
        sayac[ad] += 1
        sonuc.append(ad if sayac[ad] == 1 else f"{ad} ({sayac[ad]})")
    return sonuc


def csv_oku(veri: bytes) -> tuple[list[str], Iterator[list[Any]]]:
    """(basliklar, satir ureteci). Kodlama (UTF-8/Windows-1254) ve ayrac (; , TAB |) kendiliginden bulunur."""
    metin = _metne_cevir(veri)
    ilk = next((s for s in metin.splitlines() if s.strip()), "")
    ayrac = max(_AYRACLAR, key=ilk.count) if any(a in ilk for a in _AYRACLAR) else ","
    okuyucu = csv.reader(io.StringIO(metin, newline=""), delimiter=ayrac)
    for ham in okuyucu:
        if any(h.strip() for h in ham):
            while ham and not ham[-1].strip():
                ham.pop()
            basliklar = _basliklari_tekillestir(ham)
            break
    else:
        raise UygulamaHatasi(400, "Dosyada başlık satırı yok.")
    if len(basliklar) < 2:
        raise UygulamaHatasi(400, "En az iki sütun gerekir (ayraç ';' ',' sekme ya da '|' olmalı).")

    def satirlar() -> Iterator[list[Any]]:
        for ham in okuyucu:
            if ham:  # bos satir ([]); yalniz ayraclardan olusan satirlari ice_al eler
                yield [(h.strip() or None) for h in ham]

    return basliklar, satirlar()


def _oracle_durum() -> list[dict[str, Any]]:
    cikti = []
    for s in SOURCES:
        if s.id.endswith("_import"):
            continue
        onek = s.enabled_key.rsplit("_ENABLED", 1)[0]
        acik = bool(os.environ.get(s.enabled_key, "").strip())
        eksik = [
            f"{onek}_{a}"
            for a in ("HOST", "PORT", "SERVICE_NAME", "USER", "PASSWORD")
            if acik and not os.environ.get(f"{onek}_{a}", "").strip()
        ]
        cikti.append(
            {
                "anahtar": s.id,
                "ad": s.label,
                "tur": "oracle",
                "hazir": False,
                "neden": "Canlı bağlantı bu sürümde kapalı (ayrı işçi süreç ve sorgu sözleşmesi bekleniyor).",
                "yapilandirma": "eksik" if eksik else ("tamam" if acik else "kapalı"),
                "eksik": eksik,
            }
        )
    return cikti


def durumlar(db: Session) -> list[dict[str, Any]]:
    """Kaynak listesi + her kaynagin son partisi ve parti sayisi."""
    ayar = get_settings()
    liste: list[dict[str, Any]] = [
        {"anahtar": "csv", "ad": "CSV yükleme", "tur": "dosya", "hazir": True, "neden": "", "yapilandirma": "tamam", "eksik": []},
    ]
    if ayar.env in {"dev", "test"}:
        liste.append(
            {
                "anahtar": ORNEK,
                "ad": "Örnek veri (yalnız geliştirme)",
                "tur": "ornek",
                "hazir": True,
                "neden": "",
                "yapilandirma": "tamam",
                "eksik": [],
            }
        )
    liste.extend(_oracle_durum())
    anahtarlar = db.scalars(select(IngestBatch.source_key).distinct()).all()
    for k in anahtarlar:
        if k.startswith(CSV_ON_EK) and not any(x["anahtar"] == k for x in liste):
            liste.append(
                {
                    "anahtar": k,
                    "ad": f"CSV · {k[len(CSV_ON_EK) :]}",
                    "tur": "dosya",
                    "hazir": True,
                    "neden": "",
                    "yapilandirma": "tamam",
                    "eksik": [],
                }
            )
    for kaynak in liste:
        son = db.scalars(
            select(IngestBatch).where(IngestBatch.source_key == kaynak["anahtar"]).order_by(IngestBatch.id.desc()).limit(1)
        ).first()
        sayi = db.scalar(select(func.count()).select_from(IngestBatch).where(IngestBatch.source_key == kaynak["anahtar"])) or 0
        kaynak["parti_sayisi"] = sayi
        kaynak["son"] = (
            None
            if son is None
            else {"id": son.id, "durum": son.status, "satir": son.row_count, "zaman": iso(son.received_at), "hata": son.error}
        )
    return liste


def ornek_parti(db: Session, kullanici: str) -> IngestBatch:
    """Yerel ornek veri: panelde Musteri No'su dolu kartlardan turetilmis OLAY satirlari (alarm/sikayet/talep, acik/kapali) +
    kartlarda olmayan birkac numara. Deterministik (ayni kartlar -> ayni veri). Yalniz dev/test; gercek musteri verisi degildir."""
    if get_settings().env not in {"dev", "test"}:
        raise UygulamaHatasi(404, "Örnek veri yalnız geliştirme ortamında üretilir.")
    rng = random.Random(20261007)
    numaralar: list[tuple[str, str]] = []
    for no, ad in db.execute(select(Customer.customer_no, Customer.name).where(Customer.customer_no.isnot(None)).limit(60)):
        anahtarlar = musteri_anahtarlari(no)
        if anahtarlar:
            numaralar.append((anahtarlar[0].zfill(8), ad))
    ek = [(f"9{rng.randint(1000000, 9999999)}", f"Kartı olmayan müşteri {i}") for i in range(1, 4)]
    if not numaralar:
        numaralar = [(f"1{rng.randint(1000000, 9999999)}", f"Örnek müşteri {i}") for i in range(1, 13)]
    basliklar = ["Müşteri No", "Müşteri Ünvanı", "Kayıt Türü", "Durum", "Açılış"]
    satirlar: list[list[Any]] = []
    for no, ad in numaralar + ek:
        for tur, azami in (("Alarm", 6), ("Şikayet", 3), ("Talep", 3)):
            for _ in range(rng.randint(0, azami)):
                durum = rng.choice(("Açık", "Kapalı", "Kapalı"))
                satirlar.append(
                    [
                        no,
                        ad,
                        tur,
                        durum,
                        f"2026-{rng.randint(1, 10):02d}-{rng.randint(1, 28):02d} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00",
                    ]
                )
    if not satirlar:
        satirlar.append([numaralar[0][0], numaralar[0][1], "Alarm", "Açık", "2026-10-01 09:00:00"])
    parti = depo.parti_olustur(db, ORNEK, "Örnek veri (yerel üretim, gerçek değil)", kullanici)
    return depo.ice_al(db, parti, basliklar, satirlar)
