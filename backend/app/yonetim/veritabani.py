# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""DB yonetimi: motor/surum/boyut, tablo sayilari, butunluk, TAM yedek (SQLite cevrimici yedek + dosyalar + SHA-256 manifest).

Geri yukleme panelden YAPILMAZ: yikici bir islemdir ve panelin kendisini durdurmayi gerektirir. Ayri, SIFRELI ve onayli bir adim olarak
yedek klasorundeki ROLLBACK\\GERI_DON.bat ile yapilir (kurulum\\yedek_geri_don.ps1; 2026-10-21). Yedek dogrulama (salt okuma) panelde vardir.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import Connection, Engine, make_url

from app import ariza
from app.config import get_settings
from app.db import kullanici_dizini, kullanici_dosyalari
from app.models import TABLE_OWNER, Base, KullaniciBase
from app.ortak import UygulamaHatasi, iso, simdi

YEDEK_AD = re.compile(r"^tamlife_\d{8}_\d{6}\.db$")
GERI_DON_KLASORU = "ROLLBACK"
SIFRE_DOSYASI = "sifre.hash"  # PBKDF2 ozeti (parola DEGIL); kurulum\yedek_kur.ps1 koyar, panel yazmaz
GERI_DON_DOSYALARI = {"yedek_geri_don.ps1": "geri_don.ps1", "yedek_geri_don.bat": "GERI_DON.bat"}  # kurulum\ -> ROLLBACK\


def sqlite_yolu(url: str | None = None) -> Path | None:
    """Dosya tabanli SQLite ise mutlak yol; bellek ici / baska motor ise None."""
    adres = make_url(url or get_settings().database_url)
    if adres.get_backend_name() != "sqlite" or not adres.database or adres.database == ":memory:":
        return None
    return Path(adres.database).resolve()


def surum_head() -> str | None:
    """Kodun bekledigi Alembic surumu (betik dizininden)."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        kok = Path(__file__).resolve().parents[2]
        ayar = Config(str(kok / "alembic.ini"))
        ayar.set_main_option("script_location", str(kok / "alembic"))
        return ScriptDirectory.from_config(ayar).get_current_head()
    except Exception:  # noqa: BLE001 - betik dizini okunamazsa karsilastirma atlanir
        return None


def surum(baglanti: Connection) -> str | None:
    """Veritabaninda kayitli Alembic surumu (alembic_version yoksa None)."""
    if "alembic_version" not in inspect(baglanti).get_table_names():
        return None
    return baglanti.execute(text("SELECT version_num FROM alembic_version")).scalar()


def tablolar(baglanti: Connection) -> tuple[list[dict[str, Any]], list[str]]:
    """([{ad, modul, var, satir}], eksik tablo adlari). Satir sayisi yalniz tablo varsa."""
    mevcut = set(inspect(baglanti).get_table_names())
    satirlar, eksik = [], []
    for tablo in Base.metadata.sorted_tables:
        var = tablo.name in mevcut
        if not var:
            eksik.append(tablo.name)
        sayi = baglanti.execute(select(func.count()).select_from(tablo)).scalar_one() if var else None
        satirlar.append({"ad": tablo.name, "modul": TABLE_OWNER.get(tablo.name, "-"), "var": var, "satir": sayi})
    return satirlar, eksik


def kullanici_ozeti() -> list[dict[str, Any]]:
    """Kullanici basina dosyalar: ad, boyut, butunluk ve tablo satir sayilari."""
    cikti = []
    for yol in kullanici_dosyalari():
        baglanti = sqlite3.connect(f"{yol.as_uri()}?mode=ro", uri=True)
        try:
            mevcut = {r[0] for r in baglanti.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            satir = {t: baglanti.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in KullaniciBase.metadata.tables if t in mevcut}
            sonuc = str(baglanti.execute("PRAGMA quick_check").fetchone()[0])
        finally:
            baglanti.close()
        cikti.append({"kullanici": yol.stem, "boyut_bayt": boyut_bayt(yol), "butunluk": sonuc, "satirlar": satir})
    return cikti


def butunluk(baglanti: Connection) -> str | None:
    """SQLite quick_check sonucu ('ok' ya da ilk bulgu); diger motorlarda None."""
    if baglanti.dialect.name != "sqlite":
        return None
    return str(baglanti.exec_driver_sql("PRAGMA quick_check").scalar())


def boyut_bayt(yol: Path | None) -> int | None:
    if yol is None or not yol.is_file():
        return None
    return sum(p.stat().st_size for p in (yol, Path(f"{yol}-wal")) if p.is_file())


def yedek_dizini() -> Path:
    ayar = get_settings().backup_dir.strip()
    if ayar:
        return Path(ayar)
    yol = sqlite_yolu()
    return (yol.parent if yol else Path(__file__).resolve().parents[2] / "var") / "yedek"


def yedekler() -> list[dict[str, Any]]:
    yer = yedek_dizini()
    if not yer.is_dir():
        return []
    cikti = []
    for p in sorted((p for p in yer.iterdir() if YEDEK_AD.match(p.name)), key=lambda p: p.name, reverse=True):
        durum = p.stat()
        cikti.append({"ad": p.name, "boyut_bayt": durum.st_size, "zaman": iso(datetime.fromtimestamp(durum.st_mtime).astimezone())})
    return cikti


def _kopyala(kaynak: Path, hedef: Path) -> str:
    """SQLite cevrimici yedek (calisirken guvenli) + butunluk sonucu."""
    src = sqlite3.connect(f"{kaynak.as_uri()}?mode=ro", uri=True)
    dst = sqlite3.connect(str(hedef))
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode=DELETE")  # yedek WAL kipini miras alir: -wal/-shm artigi kalir, ilk acista dosya (ve SHA-256) degisir
    finally:
        dst.close()
        src.close()
    return _sqlite_kontrol(hedef)


def _sqlite_kontrol(yol: Path) -> str:
    baglanti = sqlite3.connect(f"{yol.as_uri()}?mode=ro", uri=True)
    try:
        return str(baglanti.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        baglanti.close()


def _rapor_dizini() -> Path:
    from app.rapor.servis import rapor_klasoru  # tembel: rapor paketi yonetim'in acilisina girmesin

    return rapor_klasoru()


def _foto_dizini() -> Path:
    return kullanici_dizini().parent / "profil_foto"


def _sha256(yol: Path) -> str:
    ozet = hashlib.sha256()
    with yol.open("rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""):
            ozet.update(parca)
    return ozet.hexdigest()


def _dizin_kopyala(kaynak: Path, hedef: Path) -> None:
    if kaynak.is_dir():
        shutil.copytree(kaynak, hedef, dirs_exist_ok=True)


def _manifest_yaz(yer: Path, ad: str, kullanici: str, kaynak: Path) -> None:
    """Yedegin tum dosyalarinin SHA-256'si ve geri donus hedefleri. Geri donus betigi (ROLLBACK) buna bakar: hash tutmayan yedekten donmez."""
    kok = yer / ad
    parcalar = [kok.with_suffix(".db"), _kisi_dizini(kok.with_suffix(".db")), _dosya_dizini(kok.with_suffix(".db"))]
    dosyalar = []
    for parca in parcalar:
        for p in [parca] if parca.is_file() else sorted(parca.rglob("*")) if parca.is_dir() else []:
            if p.is_file():
                dosyalar.append({"yol": p.relative_to(yer).as_posix(), "bayt": p.stat().st_size, "sha256": _sha256(p)})
    baglanti = sqlite3.connect(f"{kok.with_suffix('.db').as_uri()}?mode=ro", uri=True)
    try:
        alembic = baglanti.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.Error:
        alembic = None
    finally:
        baglanti.close()
    icerik = {
        "bicim": 1,
        "ad": ad,
        "zaman": iso(simdi()),
        "alan": kullanici,
        "alembic": alembic[0] if alembic else None,
        "hedefler": {
            "db": str(kaynak),
            "kullanici_dizini": str(kullanici_dizini()),
            "rapor_dizini": str(_rapor_dizini().resolve()),
            "foto_dizini": str(_foto_dizini().resolve()),
        },
        "dosyalar": dosyalar,
    }
    _manifest_yolu(kok.with_suffix(".db")).write_text(json.dumps(icerik, ensure_ascii=True, indent=1), encoding="ascii")


def _geri_don_yaz(yer: Path) -> bool:
    """ROLLBACK klasorune geri donus betiklerini (kurulum\\yedek_geri_don.*) her yedekte tazeler. Sifre ozeti (sifre.hash) buraya
    YAZILMAZ: kurulumda bir kez konur (kurulum\\yedek_kur.ps1). Yazilamazsa yedek basarisiz sayilmaz."""
    sablon = Path(__file__).resolve().parents[3] / "kurulum"
    try:
        (yer / GERI_DON_KLASORU).mkdir(parents=True, exist_ok=True)
        for kaynak, hedef in GERI_DON_DOSYALARI.items():
            shutil.copyfile(sablon / kaynak, yer / GERI_DON_KLASORU / hedef)
    except OSError:
        return False
    return True


def yedek_al(kullanici: str) -> dict[str, Any]:
    """TAM yedek (<ad> = tamlife_<tarih>_<saat>): <ad>.db (panel DB) + <ad>_kullanicilar/ (kisi basina SQLite) + <ad>_dosyalar/ (aylik
    rapor arsivi, profil fotograflari) + <ad>.manifest.json (SHA-256 + geri donus hedefleri). Butunluk dogrulanir, eskiler budanir.
    Haric: .env/sirlar, ham katalog (var/ham, yeniden taranir), gunlukler. Geri donus panelden DEGIL, ROLLBACK\\geri_don.ps1 ile (sifreli)."""
    kaynak = sqlite_yolu()
    if kaynak is None:
        raise UygulamaHatasi(501, "Yedek yalnız dosya tabanlı SQLite için; PostgreSQL'de pg_dump kullanılır.")
    if not kaynak.is_file():
        raise UygulamaHatasi(404, "Veritabanı dosyası bulunamadı.")
    yer = yedek_dizini()
    ad = f"tamlife_{simdi().astimezone():%Y%m%d_%H%M%S}.db"
    hedef = yer / ad
    try:
        yer.mkdir(parents=True, exist_ok=True)
        sonuc = _kopyala(kaynak, hedef)
        kisiler = _kisi_dizini(hedef)
        for dosya in kullanici_dosyalari():
            kisiler.mkdir(exist_ok=True)
            if _kopyala(dosya, kisiler / dosya.name) != "ok":
                sonuc = f"{dosya.stem}: bozuk"
        if sonuc != "ok":
            _yedek_sil(hedef)
            raise UygulamaHatasi(500, "Yedek bütünlük kontrolünden geçemedi; dosya silindi.")
        _dizin_kopyala(_rapor_dizini(), _dosya_dizini(hedef) / "raporlar")
        _dizin_kopyala(_foto_dizini(), _dosya_dizini(hedef) / "profil_foto")
        _manifest_yaz(yer, hedef.stem, kullanici, kaynak)
    except UygulamaHatasi:
        raise
    except (OSError, sqlite3.Error) as hata:
        _yedek_sil(hedef)
        kayit = ariza.kaydet("TL-YDK-01", exc=hata, kaynak="yedek", kullanici=kullanici)
        raise UygulamaHatasi(500, ariza.mesaj("TL-YDK-01", kayit)) from hata
    for eski in yedekler()[get_settings().backup_keep :]:
        _yedek_sil(yer / eski["ad"])
    return {
        "ad": ad,
        "boyut_bayt": hedef.stat().st_size,
        "butunluk": sonuc,
        "kullanici_dosyasi": len(kullanici_dosyalari()),
        "geri_don_betigi": _geri_don_yaz(yer),
    }


def _kisi_dizini(yedek: Path) -> Path:
    return yedek.with_name(f"{yedek.stem}_kullanicilar")


def _dosya_dizini(yedek: Path) -> Path:
    return yedek.with_name(f"{yedek.stem}_dosyalar")


def _manifest_yolu(yedek: Path) -> Path:
    return yedek.with_name(f"{yedek.stem}.manifest.json")


def _yedek_sil(yedek: Path) -> None:
    yedek.unlink(missing_ok=True)
    _manifest_yolu(yedek).unlink(missing_ok=True)
    shutil.rmtree(_kisi_dizini(yedek), ignore_errors=True)
    shutil.rmtree(_dosya_dizini(yedek), ignore_errors=True)


def manifest_sorunlari(yedek: Path) -> list[str] | None:
    """Manifestteki her dosyanin varligi ve SHA-256'si. Manifest yoksa None (eski bicim yedek); bos liste = sorunsuz."""
    yol = _manifest_yolu(yedek)
    if not yol.is_file():
        return None
    try:
        dosyalar = json.loads(yol.read_text(encoding="ascii"))["dosyalar"]
    except (OSError, ValueError, KeyError):
        return ["manifest okunamadı"]
    sorun = []
    for d in dosyalar:
        p = yedek.parent / d["yol"]
        if not p.is_file():
            sorun.append(f"eksik: {d['yol']}")
        elif _sha256(p) != d["sha256"]:
            sorun.append(f"özet uyuşmuyor: {d['yol']}")
    return sorun


def yedek_dogrula(ad: str) -> dict[str, Any]:
    """Yedegi salt okuma ile dogrular (geri yuklemez): SQLite butunlugu + manifestteki tum dosyalarin SHA-256'si."""
    if not YEDEK_AD.match(ad):
        raise UygulamaHatasi(400, "Geçersiz yedek adı.")
    yol = yedek_dizini() / ad
    if not yol.is_file():
        raise UygulamaHatasi(404, "Yedek bulunamadı.")
    try:
        sonuc = _sqlite_kontrol(yol)
        sorunlar = manifest_sorunlari(yol)
    except (sqlite3.Error, OSError) as hata:
        return {"ad": ad, "butunluk": f"okunamadı ({type(hata).__name__})", "tamam": False}
    if sorunlar:
        return {"ad": ad, "butunluk": "; ".join(sorunlar[:3]), "tamam": False}
    return {"ad": ad, "butunluk": sonuc, "tamam": sonuc == "ok", "manifest": sorunlar is not None}


def _ayni_disk(a: Path, b: Path) -> bool:
    """Iki yol ayni birimde mi (yedek veriyle ayni diskte durmasin uyarisi). Henuz olusmamis klasorde en yakin var olan ust klasore bakilir."""

    def birim(p: Path) -> int:
        while not p.exists() and p != p.parent:
            p = p.parent
        return os.stat(p).st_dev

    try:
        return birim(a.resolve()) == birim(b.resolve())
    except OSError:
        return False


def bilgi(motor: Engine) -> dict[str, Any]:
    url = make_url(get_settings().database_url)
    yol = sqlite_yolu()
    with motor.connect() as baglanti:
        satirlar, eksik = tablolar(baglanti)
        kayitli, hedef = surum(baglanti), surum_head()
        sonuc = butunluk(baglanti)
    liste = yedekler()
    disk = shutil.disk_usage(yol.parent) if yol else None
    return {
        "motor": url.get_backend_name(),
        "dosya": yol.name if yol else None,
        "boyut_bayt": boyut_bayt(yol),
        "disk_serbest_bayt": disk.free if disk else None,
        "surum": kayitli,
        "hedef_surum": hedef,
        "surum_uyumlu": None if kayitli is None or hedef is None else kayitli == hedef,
        "eksik_tablolar": eksik,
        "tablolar": satirlar,
        "toplam_satir": sum(int(t["satir"] or 0) for t in satirlar),
        "butunluk": sonuc,
        "kullanici_dosyalari": kullanici_ozeti(),
        "yedek": {
            "dizin": str(yedek_dizini()),
            "desteklenir": yol is not None,
            "saklanan": get_settings().backup_keep,
            "adet": len(liste),
            "liste": liste[:20],
            "ayni_disk": yol is not None and _ayni_disk(yedek_dizini(), yol.parent),
            "geri_donus": {
                "klasor": str(yedek_dizini() / GERI_DON_KLASORU),
                "betik": (yedek_dizini() / GERI_DON_KLASORU / "GERI_DON.bat").is_file(),
                "sifre": (yedek_dizini() / GERI_DON_KLASORU / SIFRE_DOSYASI).is_file(),
            },
        },
    }
