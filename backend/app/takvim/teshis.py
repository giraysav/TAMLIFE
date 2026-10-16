"""Takvim senkron teshisi (2026-10-15 kullanici bildirimi: "personelin girdigi gunler admin tarafinda gorunmuyor"). YALNIZ OKUR.

  python -m app.takvim.teshis

Her panel kullanicisi icin: hesap (rol, admin, etkin), TAM Takvim'de satiri olup olmadigi (personel kurali), takvim dosyasinin
yolu ve icindeki kayit sayisi / ilk-son gun. Hicbir hesaba ait olmayan takvim dosyalari ayrica listelenir (girisi baska adla
yapilan kisi). Kisi dosyalari salt okunur acilir (sqlite mode=ro): dosya olusturmaz, sema eklemez.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from sqlalchemy import select

from app.config import env_dosyasi_yukle
from app.db import kullanici_dizini, kullanici_dosyalari, kullanici_dosyasi, oturum
from app.kullanicilar import personel_mi
from app.models import AppUser


def dosya_ozeti(dosya: Path) -> tuple[int, str | None, str | None]:
    """(kayit sayisi, ilk gun, son gun); tablo yoksa (0, None, None)."""
    with sqlite3.connect(f"{dosya.resolve().as_uri()}?mode=ro", uri=True) as b:
        if not b.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='calendar_day'").fetchone():
            return 0, None, None
        sayi, ilk, son = b.execute("SELECT COUNT(*), MIN(day), MAX(day) FROM calendar_day").fetchone()
        return int(sayi), ilk, son


def rapor() -> list[str]:
    satirlar = [f"Takvim klasoru: {kullanici_dizini()}", ""]
    with oturum() as db:
        kullanicilar = list(db.scalars(select(AppUser).order_by(AppUser.username)))
    sahipli: set[Path] = set()
    satirlar.append("KULLANICI | GORUNEN AD | ROL | ADMIN | ETKIN | TAM TAKVIMDE | DOSYA | KAYIT | ILK GUN | SON GUN")
    for u in kullanicilar:
        dosya = kullanici_dosyasi(u.username)
        sahipli.add(dosya.resolve())
        sayi, ilk, son = dosya_ozeti(dosya) if dosya.is_file() else (0, None, None)
        satirlar.append(
            " | ".join(
                str(x)
                for x in (
                    u.username,
                    u.display_name or "-",
                    u.role or "-",
                    "evet" if u.is_admin else "hayir",
                    "hayir" if u.active is False else "evet",
                    "evet" if personel_mi(u) else "HAYIR",
                    dosya.name if dosya.is_file() else "YOK",
                    sayi,
                    ilk or "-",
                    son or "-",
                )
            )
        )
    sahipsiz = [d for d in kullanici_dosyalari() if d.resolve() not in sahipli]
    satirlar += ["", f"Hesabi olmayan takvim dosyalari: {len(sahipsiz)}"]
    for d in sahipsiz:
        sayi, ilk, son = dosya_ozeti(d)
        satirlar.append(f"  {d.name} | kayit {sayi} | {ilk or '-'} .. {son or '-'}")
    return satirlar


def main() -> int:
    env_dosyasi_yukle()  # backend/.env: panel DB adresi (yuklenmezse varsayilan PostgreSQL'e gider, 2026-10-15 sunucuda goruldu)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    print("\n".join(rapor()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
