"""DB yonetimi: motor/surum/boyut, tablo sayilari, butunluk, yedek (SQLite cevrimici yedek).

Geri yukleme bu surumde YOK: yikici bir islemdir (uretimde denetim izi, AD kullanicilari, oturumlar icin ozel kurallari vardi);
ayri, onayli bir adim olarak tasarlanacak (docs/yonetim-ve-tampon-tasarimi.md, Faz E). Yedek dogrulama (salt okuma) vardir.
"""

from __future__ import annotations

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
from app.models import TABLE_OWNER, Base
from app.ortak import UygulamaHatasi, iso, simdi

YEDEK_AD = re.compile(r"^tamlife_\d{8}_\d{6}\.db$")


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


def _sqlite_kontrol(yol: Path) -> str:
    baglanti = sqlite3.connect(f"{yol.as_uri()}?mode=ro", uri=True)
    try:
        return str(baglanti.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        baglanti.close()


def yedek_al(kullanici: str) -> dict[str, Any]:
    """SQLite cevrimici yedek (calisirken guvenli): ayri dosyaya kopyalar, butunlugunu dogrular, eskileri budar."""
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
        src = sqlite3.connect(f"{kaynak.as_uri()}?mode=ro", uri=True)
        dst = sqlite3.connect(str(hedef))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        sonuc = _sqlite_kontrol(hedef)
        if sonuc != "ok":
            hedef.unlink(missing_ok=True)
            raise UygulamaHatasi(500, "Yedek bütünlük kontrolünden geçemedi; dosya silindi.")
    except UygulamaHatasi:
        raise
    except (OSError, sqlite3.Error) as hata:
        hedef.unlink(missing_ok=True)
        kayit = ariza.kaydet("TL-YDK-01", exc=hata, kaynak="yedek", kullanici=kullanici)
        raise UygulamaHatasi(500, ariza.mesaj("TL-YDK-01", kayit)) from hata
    for eski in yedekler()[get_settings().backup_keep :]:
        (yer / eski["ad"]).unlink(missing_ok=True)
    return {"ad": ad, "boyut_bayt": hedef.stat().st_size, "butunluk": sonuc}


def yedek_dogrula(ad: str) -> dict[str, Any]:
    """Yedek dosyasini salt okuma ile dogrular (geri yuklemez)."""
    if not YEDEK_AD.match(ad):
        raise UygulamaHatasi(400, "Geçersiz yedek adı.")
    yol = yedek_dizini() / ad
    if not yol.is_file():
        raise UygulamaHatasi(404, "Yedek bulunamadı.")
    try:
        sonuc = _sqlite_kontrol(yol)
    except sqlite3.Error as hata:
        return {"ad": ad, "butunluk": f"okunamadı ({type(hata).__name__})", "tamam": False}
    return {"ad": ad, "butunluk": sonuc, "tamam": sonuc == "ok"}


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
        "yedek": {
            "dizin": str(yedek_dizini()),
            "desteklenir": yol is not None,
            "saklanan": get_settings().backup_keep,
            "adet": len(liste),
            "liste": liste[:20],
        },
    }
