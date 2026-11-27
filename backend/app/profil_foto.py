# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Profil fotografi (2026-10-15 kullanici istegi: hesap kartindaki bas harf dairesine kisi kendi fotografini ekleyip kaydeder; yukleme
profil sayfasindan). Dosya `<panel DB klasoru>/profil_foto/<kullanici>.jpg` (kisinin takvim dosyasi gibi; DB'ye yazilmaz, sema yok).
Arayuz resmi 256 px kare JPEG'e kucultup ham govde olarak gonderir; sunucu JPEG imzasini ve boyutu dener (yeni bagimlilik yok)."""

from __future__ import annotations

import os
from pathlib import Path

from app.db import kullanici_dizini, kullanici_dosyasi
from app.dil import m
from app.ortak import UygulamaHatasi

AZAMI_BAYT = 512 * 1024  # 256 px JPEG ~20-60 KB; sinir elle gonderilen buyuk dosyayi keser


def dizin() -> Path:
    return kullanici_dizini().parent / "profil_foto"


def dosya(kullanici: str) -> Path:
    return dizin() / f"{kullanici_dosyasi(kullanici).stem}.jpg"  # ad kullanici dosyasiyla ayni kuralla temizlenir


def surum(kullanici: str) -> int | None:
    """Arayuzun onbellegi kirmasi icin degisim zamani (ms); fotograf yoksa None."""
    yol = dosya(kullanici)
    return yol.stat().st_mtime_ns // 1_000_000 if yol.is_file() else None


def oku(kullanici: str) -> bytes | None:
    yol = dosya(kullanici)
    return yol.read_bytes() if yol.is_file() else None


def kaydet(kullanici: str, veri: bytes) -> int:
    if len(veri) < 100 or not veri.startswith(b"\xff\xd8\xff") or not veri.rstrip(b"\x00")[-2:] == b"\xff\xd9":
        raise UygulamaHatasi(400, m("Fotoğraf JPEG olmalı.", "The photo must be a JPEG."))
    yol = dosya(kullanici)
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    gecici.write_bytes(veri)
    os.replace(gecici, yol)  # yarim yazilmis dosya gosterilmez
    return surum(kullanici) or 0


def sil(kullanici: str) -> bool:
    yol = dosya(kullanici)
    if not yol.is_file():
        return False
    yol.unlink()
    return True
