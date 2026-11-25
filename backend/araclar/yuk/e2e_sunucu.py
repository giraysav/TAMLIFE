"""Playwright oturum dusme testleri icin gecici panel (bos DB + derlenmis arayuz) ve DB'yi disaridan degistiren komutlar.

  python -m araclar.yuk.e2e_sunucu sunucu --dizin <gecici> --port 8198      DB kurar, e2e.admin/e2e.uye acar, uvicorn'u calistirir
  python -m araclar.yuk.e2e_sunucu degistir --dizin <gecici> pasif e2e.uye  hesabi pasife ceker (baska surecten, panel acikken)
  ... degistir ... rol e2e.admin TeamMember | sil e2e.uye | rolsuz e2e.uye | sifirla  (rolsuz: role sutunu bosaltilir = rol kaydi silindi)

Parola E2E_PAROLA ortam degiskeninden (varsayilan sabit test parolasi; yalniz bu gecici DB'de gecerli). Canli DB'ye dokunmaz.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from araclar.yuk.ornek import BACKEND, bos_db_kur

KULLANICILAR = (("e2e.admin", "admin"), ("e2e.uye", "TeamMember"))
VARSAYILAN_PAROLA = "E2e-test-parolasi-2026"


def _db(dizin: Path) -> Path:
    return dizin / "yuk.db"


def hazirla(dizin: Path) -> None:
    if _db(dizin).exists():
        _db(dizin).unlink()
    bos_db_kur(dizin)
    sifirla(dizin)


def sifirla(dizin: Path) -> None:
    """Iki test hesabini bastan acar (onceki testin pasif/rol/silme degisikligi kalmaz)."""
    from app.kullanicilar import parola_ozeti

    ozet = parola_ozeti(os.environ.get("E2E_PAROLA", VARSAYILAN_PAROLA))
    with sqlite3.connect(_db(dizin), timeout=30) as b:
        b.executemany("DELETE FROM app_user WHERE username = ?", [(ad,) for ad, _ in KULLANICILAR])
        for ad, rol in KULLANICILAR:
            b.execute(
                "INSERT INTO app_user (username, display_name, role, is_admin, active, is_ad_user, ad_domain, password_hash, first_name, last_name,"
                " phone, company, address, website) VALUES (?, ?, ?, ?, 1, 0, '', ?, '', '', '', '', '', '')",
                (ad, ad, rol, rol == "admin", ozet),
            )


def degistir(dizin: Path, islem: str, ad: str, deger: str = "") -> None:
    """Baska bir surecin (hesap.py, DBA, isci) yaptigi degisikligin benzeri: dogrudan SQLite, panel sureci haberdar degil."""
    sql = {
        "pasif": ("UPDATE app_user SET active = 0 WHERE username = ?", (ad,)),
        "aktif": ("UPDATE app_user SET active = 1 WHERE username = ?", (ad,)),
        "rol": ("UPDATE app_user SET role = ?, is_admin = ? WHERE username = ?", (deger, deger == "admin", ad)),
        "rolsuz": ("UPDATE app_user SET role = '', is_admin = 0 WHERE username = ?", (ad,)),
        "sil": ("DELETE FROM app_user WHERE username = ?", (ad,)),
    }[islem]
    with sqlite3.connect(_db(dizin), timeout=30) as b:
        assert b.execute(*sql).rowcount == 1, f"{ad} bulunamadi"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    alt = p.add_subparsers(dest="komut", required=True)
    s = alt.add_parser("sunucu")
    s.add_argument("--dizin", type=Path, required=True)
    s.add_argument("--port", type=int, default=8198)
    d = alt.add_parser("degistir")
    d.add_argument("--dizin", type=Path, required=True)
    d.add_argument("islem", choices=("pasif", "aktif", "rol", "rolsuz", "sil", "sifirla"))
    d.add_argument("ad", nargs="?", default="")
    d.add_argument("deger", nargs="?", default="")
    a = p.parse_args()
    if a.komut == "degistir":
        sifirla(a.dizin) if a.islem == "sifirla" else degistir(a.dizin, a.islem, a.ad, a.deger)
        return 0
    if a.port in (8117, 443):
        print("8117/443 canli paneldir.")
        return 2
    hazirla(a.dizin)
    (a.dizin / "yok.env").write_text("", encoding="utf-8")
    temel = {k: v for k, v in os.environ.items() if not k.upper().startswith(("TAMLIFE_", "AD_", "ORACLE_"))}
    ortam = {
        **temel,
        "TAMLIFE_ENV": "dev",
        "TAMLIFE_ENV_DOSYASI": str(a.dizin / "yok.env"),
        "TAMLIFE_DATABASE_URL": f"sqlite:///{_db(a.dizin).as_posix()}",
        "TAMLIFE_KULLANICI_DB_DIZINI": str(a.dizin / "kullanicilar"),
        "TAMLIFE_LOG_DIR": str(a.dizin / "log"),
        "TAMLIFE_BACKUP_DIR": str(a.dizin / "yedek"),
        "TAMLIFE_STATIC_DIR": str((BACKEND.parent / "ekran-react" / "dist").resolve()),
        "TAMLIFE_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "TAMLIFE_COOKIE_SECURE": "false",
        "AD_ENABLED": "false",
    }
    komut = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(a.port), "--no-proxy-headers", "--log-level", "warning"]
    return subprocess.call(komut, cwd=BACKEND, env=ortam)


if __name__ == "__main__":
    sys.exit(main())
