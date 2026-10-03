"""Bes SQLite dosyasi ve kisi dosyasi.

Parola, tuz, hash ve sertifika yolu bu modulden gecmez ve veritabanina yazilmaz.
Musteri satiri kopyalanmaz. Oracle acilmaz.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

KOK = Path(r"D:\Project\TAMLIFE_v3.5")
VERI = KOK / "veri"
GELEN = VERI / "gelen"
KULLANICI_KLASOR = VERI / "users"

ADLAR = ("shared", "system", "realtime", "security", "backup")

_SEMALAR = {
    "shared": """
        CREATE TABLE IF NOT EXISTS modul (
            id TEXT PRIMARY KEY,
            ad TEXT NOT NULL,
            anahtar TEXT NOT NULL,
            sira INTEGER NOT NULL,
            yalniz_admin INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS rol (
            ad TEXT PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS rol_modul (
            rol TEXT NOT NULL,
            modul_id TEXT NOT NULL,
            PRIMARY KEY (rol, modul_id)
        );
        CREATE TABLE IF NOT EXISTS musteri (
            id INTEGER PRIMARY KEY,
            tam_id TEXT,
            ad TEXT,
            aktif INTEGER NOT NULL DEFAULT 1
        );
    """,
    "system": """
        CREATE TABLE IF NOT EXISTS ice_aktarim (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad TEXT NOT NULL,
            yol TEXT NOT NULL,
            zaman TEXT NOT NULL,
            satir INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS olay (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            zaman TEXT NOT NULL,
            tur TEXT NOT NULL,
            mesaj TEXT NOT NULL
        );
    """,
    "realtime": """
        CREATE TABLE IF NOT EXISTS is_kaydi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tur TEXT NOT NULL,
            durum TEXT NOT NULL,
            zaman TEXT NOT NULL,
            sahip TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS skor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            musteri_id INTEGER,
            puan REAL,
            zaman TEXT NOT NULL,
            veren TEXT NOT NULL
        );
    """,
    "security": """
        CREATE TABLE IF NOT EXISTS giris (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            zaman TEXT NOT NULL,
            kullanici TEXT NOT NULL,
            sonuc TEXT NOT NULL,
            neden TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS yetki_red (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            zaman TEXT NOT NULL,
            kullanici TEXT NOT NULL,
            yol TEXT NOT NULL
        );
    """,
    "backup": """
        CREATE TABLE IF NOT EXISTS yedek (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kaynak TEXT NOT NULL,
            hedef TEXT NOT NULL,
            zaman TEXT NOT NULL,
            durum TEXT NOT NULL
        );
    """,
}

_KISI_SEMA = """
    CREATE TABLE IF NOT EXISTS profil (
        anahtar TEXT PRIMARY KEY,
        deger TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS notlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zaman TEXT NOT NULL,
        metin TEXT NOT NULL
    );
"""

_AD = re.compile(r"[^A-Za-z0-9._-]+")


def yol(ad: str) -> Path:
    if ad not in ADLAR:
        raise KeyError(ad)
    return VERI / f"{ad}.db"


def baglan(ad: str) -> sqlite3.Connection:
    bag = sqlite3.connect(str(yol(ad)), timeout=10)
    bag.row_factory = sqlite3.Row
    bag.execute("PRAGMA busy_timeout = 5000")
    return bag


def hazirla() -> dict[str, Path]:
    """Bos dosyalari ve tablolari acar. Var olan satira dokunmaz, disaridan kopyalamaz."""
    VERI.mkdir(parents=True, exist_ok=True)
    GELEN.mkdir(parents=True, exist_ok=True)
    KULLANICI_KLASOR.mkdir(parents=True, exist_ok=True)
    sonuc: dict[str, Path] = {}
    for ad, sql in _SEMALAR.items():
        hedef = yol(ad)
        bag = sqlite3.connect(str(hedef))
        try:
            bag.executescript(sql)
            bag.commit()
        finally:
            bag.close()
        sonuc[ad] = hedef
    return sonuc


def _temiz_ad(ad: str) -> str:
    temiz = _AD.sub("_", (ad or "").strip()).strip("._")[:80]
    return temiz or "adsiz"


def kullanici_yolu(ad: str) -> Path:
    return KULLANICI_KLASOR / f"{_temiz_ad(ad)}.db"


def kullanici_ac(ad: str, profil: dict[str, str] | None = None) -> Path:
    """Giris aninda kisi dosyasini acar. Parola alani kabul etmez."""
    if profil:
        for anahtar in profil:
            dusuk = anahtar.lower()
            if any(parca in dusuk for parca in ("parola", "password", "hash", "salt", "sertifika", "secret")):
                raise ValueError("gizli_alan")
    KULLANICI_KLASOR.mkdir(parents=True, exist_ok=True)
    hedef = kullanici_yolu(ad)
    bag = sqlite3.connect(str(hedef))
    try:
        bag.executescript(_KISI_SEMA)
        if profil:
            for anahtar, deger in profil.items():
                bag.execute(
                    "INSERT INTO profil (anahtar, deger) VALUES (?, ?) "
                    "ON CONFLICT(anahtar) DO UPDATE SET deger = excluded.deger",
                    (anahtar, str(deger)),
                )
        bag.commit()
    finally:
        bag.close()
    return hedef


def modul_var() -> bool:
    bag = baglan("shared")
    try:
        row = bag.execute("SELECT 1 FROM modul LIMIT 1").fetchone()
        return row is not None
    finally:
        bag.close()


def modul_yaz(kayitlar: list[tuple]) -> None:
    if modul_var():
        return
    bag = baglan("shared")
    try:
        bag.executemany(
            "INSERT INTO modul (id, ad, anahtar, sira, yalniz_admin) VALUES (?, ?, ?, ?, ?)",
            kayitlar,
        )
        bag.commit()
    finally:
        bag.close()


def rol_var() -> bool:
    bag = baglan("shared")
    try:
        return bag.execute("SELECT 1 FROM rol LIMIT 1").fetchone() is not None
    finally:
        bag.close()


def rol_harita(sira: list[str]) -> dict[str, list[str]]:
    bag = baglan("shared")
    try:
        adlar = [r["ad"] for r in bag.execute("SELECT ad FROM rol ORDER BY ad")]
        sonuc = {ad: [] for ad in adlar}
        for row in bag.execute("SELECT rol, modul_id FROM rol_modul"):
            sonuc.setdefault(row["rol"], []).append(row["modul_id"])
        for ad, liste in list(sonuc.items()):
            secili = set(liste)
            sonuc[ad] = [m for m in sira if m in secili]
        return sonuc
    finally:
        bag.close()


def rol_yaz(harita: dict[str, list[str]], sira: list[str]) -> dict[str, list[str]]:
    bag = baglan("shared")
    try:
        bag.execute("DELETE FROM rol_modul")
        bag.execute("DELETE FROM rol")
        temiz: dict[str, list[str]] = {}
        for ad, liste in harita.items():
            bag.execute("INSERT INTO rol (ad) VALUES (?)", (ad,))
            secili = set(liste)
            sirali = [m for m in sira if m in secili]
            for modul_id in sirali:
                bag.execute(
                    "INSERT INTO rol_modul (rol, modul_id) VALUES (?, ?)",
                    (ad, modul_id),
                )
            temiz[ad] = sirali
        bag.commit()
        return temiz
    finally:
        bag.close()


def ice_ekle(ad: str, yol_metin: str, zaman: str, satir: int) -> int:
    bag = baglan("system")
    try:
        imlec = bag.execute(
            "INSERT INTO ice_aktarim (ad, yol, zaman, satir) VALUES (?, ?, ?, ?)",
            (ad, yol_metin, zaman, satir),
        )
        bag.commit()
        return int(imlec.lastrowid or 0)
    finally:
        bag.close()


def ice_liste(limit: int = 20) -> list[dict]:
    bag = baglan("system")
    try:
        rows = bag.execute(
            "SELECT id, ad, yol, zaman, satir FROM ice_aktarim ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        bag.close()


def giris_yaz(zaman: str, kullanici: str, sonuc: str, neden: str) -> None:
    bag = baglan("security")
    try:
        bag.execute(
            "INSERT INTO giris (zaman, kullanici, sonuc, neden) VALUES (?, ?, ?, ?)",
            (zaman, kullanici[:120], sonuc[:40], neden[:200]),
        )
        bag.commit()
    finally:
        bag.close()


def yetki_red_yaz(zaman: str, kullanici: str, yol_metin: str) -> None:
    bag = baglan("security")
    try:
        bag.execute(
            "INSERT INTO yetki_red (zaman, kullanici, yol) VALUES (?, ?, ?)",
            (zaman, (kullanici or "")[:120], yol_metin[:200]),
        )
        bag.commit()
    finally:
        bag.close()


def say(ad: str, tablo: str) -> int:
    if not re.fullmatch(r"[a-z_]+", tablo):
        raise ValueError("tablo")
    bag = baglan(ad)
    try:
        row = bag.execute(f"SELECT COUNT(*) AS n FROM {tablo}").fetchone()
        return int(row["n"])
    finally:
        bag.close()
def profil_oku(ad: str) -> dict[str, str]:
    hedef = kullanici_yolu(ad)
    if not hedef.is_file():
        return {}
    bag = sqlite3.connect(str(hedef))
    bag.row_factory = sqlite3.Row
    try:
        rows = bag.execute("SELECT anahtar, deger FROM profil").fetchall()
        return {str(r["anahtar"]): str(r["deger"]) for r in rows}
    except sqlite3.Error:
        return {}
    finally:
        bag.close()
