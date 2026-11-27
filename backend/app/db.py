# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Veritabani katmani: tek ortak panel DB'si + kullanici basina SQLite dosyasi. Import baglanti acmaz.

panel     : TAMLIFE_DATABASE_URL (PostgreSQL; SQLite yalniz dev/test ya da TAMLIFE_SQLITE_IZIN) -> models.Base, Alembic ile.
kullanici : <TAMLIFE_KULLANICI_DB_DIZINI>/<kullanici>.db -> models.KullaniciBase (takvim gunleri, gelir kayitlari).
            Dosya ilk acilista olusur; tablolar create_all(checkfirst) ile eklenir, Alembic gerekmez. Modele sonradan eklenen
            bos olabilen sutunlari eski dosyalara _eksik_sutunlari_ekle ekler.
Kullanici dosyasindaki kayitlarin disariya verilen kimligi dosyalar arasi tekildir: app_user.id * KIMLIK_CARPANI + yerel id.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable, Iterator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app import musteri_alani
from app.config import get_settings
from app.models import KullaniciBase

musteri_alani.kur()  # Customer sorgulari istegin musteri alanina suzulur (Toptan / Baglantili Araclar ayri kartlar)

KIMLIK_CARPANI = 1_000_000
SQLITE_BEKLEME_SN = 30
# SQLite havuzu sinirsiz tasar (10 kalici): istek, bagimlilikta (require_user) aldigi baglantiyi uc govdesi icin is parcacigi
# beklerken de tutar; tavanli havuzda baglanti bekleyen is parcaciklari ile is parcacigi bekleyen baglantilar birbirini
# pool_timeout (30 sn) boyunca kilitliyordu: varsayilan 5+10'da 100 eszamanlida %61 zaman asimi, 10+110'da 300 eszamanlida 31-61 sn
# (tests/test_yuk_ornek.py). SQLite baglantisi bir dosya tutamacidir; tasan baglanti iade edilince kapanir.
SQLITE_HAVUZ = 10
_ENGINES: dict[str, Engine] = {}
_HAZIR: set[str] = set()  # sema kurulmus kullanici dosyalari
_LOCK = threading.Lock()
_SEMA_KILIDI = threading.Lock()


def _sqlite_ayarla(baglanti, _kayit) -> None:  # type: ignore[no-untyped-def]
    """WAL: yazma surerken okuma bloklanmaz (panel + isci ayni dosya). busy_timeout: kilitte hemen 'database is locked' yerine bekler."""
    imlec = baglanti.cursor()
    imlec.execute(f"PRAGMA busy_timeout={SQLITE_BEKLEME_SN * 1000}")
    imlec.execute("PRAGMA journal_mode=WAL")
    imlec.execute("PRAGMA synchronous=NORMAL")
    imlec.close()


def _motor_kur(url: str) -> Engine:
    if url.startswith("sqlite"):
        motor = create_engine(
            url, pool_pre_ping=True, pool_size=SQLITE_HAVUZ, max_overflow=-1,
            connect_args={"timeout": SQLITE_BEKLEME_SN},
        )
        event.listen(motor, "connect", _sqlite_ayarla)
        return motor
    # PostgreSQL erisilemezse istek dakikalarca beklemesin: 3 sn'de hata (arka plan yazicilar ve saglik kontrolu de buna guvenir).
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3})


def panel_url() -> str:
    ayar = get_settings()
    url = ayar.database_url
    if not (url.startswith("postgresql") or (url.startswith("sqlite") and (ayar.env in {"dev", "test"} or ayar.sqlite_izin))):
        raise RuntimeError("panel database must be PostgreSQL (sqlite only in dev/test or TAMLIFE_SQLITE_IZIN=true)")
    return url


def engine(url: str | None = None) -> Engine:
    """Adres basina tek motor; panel adresi yalniz ilk kurulumda denetlenir."""
    hedef = url or get_settings().database_url
    with _LOCK:
        if hedef not in _ENGINES:
            _ENGINES[hedef] = _motor_kur(hedef if url else panel_url())
        return _ENGINES[hedef]


def dispose_engines() -> None:
    """Testler: motorlari ve hazir kullanici dosyasi kaydini sifirlar (her test kendi gecici veritabanini kullanir)."""
    with _LOCK:
        for e in _ENGINES.values():
            e.dispose()
        _ENGINES.clear()
        _HAZIR.clear()


def oturum() -> Session:
    """Panel DB oturumu (istek disi kullanim: arka plan yazici, ariza kaydi, ornek veri). `with oturum() as db:`"""
    return Session(engine(), autoflush=False)


def yazma_kilidi(db: Session) -> None:
    """SQLite'ta yazma islemini OKUMADAN once baslatir (BEGIN IMMEDIATE; kilit doluysa busy_timeout bekler). pysqlite islemi ilk
    DML'de actigi icin "satir yok mu? ekle" deseninde iki yazici ayni bos sonucu gorup UNIQUE'e carpiyordu. PostgreSQL'de islem yok."""
    baglanti = db.connection()
    if baglanti.dialect.name == "sqlite" and not baglanti.connection.dbapi_connection.in_transaction:  # type: ignore[union-attr]
        baglanti.exec_driver_sql("BEGIN IMMEDIATE")


def get_db() -> Iterator[Session]:
    """Istek basina panel oturumu. Commit endpointte acikca yapilir; hata olursa kapanista geri alinir."""
    with oturum() as db:
        yield db


# --- kullanici dosyalari ----------------------------------------------------------------------------
def _eksik_sutunlari_ekle(motor: Engine) -> None:
    """create_all mevcut tabloya dokunmaz; modele sonradan eklenen sutunlari eski kullanici dosyalarina ekler.
    Yalniz bos olabilen (nullable) sutun eklenir; zorunlu sutun icin bu yol yetmez, hata verir."""
    mevcut = inspect(motor)
    with motor.begin() as baglanti:
        for tablo in KullaniciBase.metadata.sorted_tables:
            var = {s["name"] for s in mevcut.get_columns(tablo.name)}
            for sutun in tablo.columns:
                if sutun.name in var:
                    continue
                if not sutun.nullable:
                    raise RuntimeError(f"{tablo.name}.{sutun.name}: kullanici dosyasina zorunlu sutun eklenemez, sutunu nullable yapin")
                baglanti.exec_driver_sql(f'ALTER TABLE "{tablo.name}" ADD COLUMN "{sutun.name}" {sutun.type.compile(dialect=motor.dialect)}')


def kullanici_dizini() -> Path:
    """Ayar bos ise SQLite panel dosyasinin yanindaki kullanicilar/, PostgreSQL'de var/kullanicilar."""
    ayar = get_settings()
    if ayar.kullanici_db_dizini:
        return Path(ayar.kullanici_db_dizini).resolve()
    url = ayar.database_url
    return ((Path(url.split(":///", 1)[1]).parent if url.startswith("sqlite") else Path("var")) / "kullanicilar").resolve()


def kullanici_dosyasi(kullanici: str) -> Path:
    ad = re.sub(r"[^a-z0-9._-]", "_", kullanici.strip().lower()).strip(".") or "_"
    return kullanici_dizini() / f"{ad}.db"


def kullanici_oturumu(kullanici: str) -> Session:
    """Kisinin kendi SQLite dosyasi; yoksa olusturulur. `with kullanici_oturumu(ad) as k:`"""
    dosya = kullanici_dosyasi(kullanici)
    motor = engine(f"sqlite:///{dosya.as_posix()}")
    if str(dosya) not in _HAZIR:
        with _SEMA_KILIDI:
            if str(dosya) not in _HAZIR:
                dosya.parent.mkdir(parents=True, exist_ok=True)
                KullaniciBase.metadata.create_all(motor)
                _eksik_sutunlari_ekle(motor)
                _HAZIR.add(str(dosya))
    return Session(motor, autoflush=False)


def mevcut_oturumlar(kullanicilar: Iterable[str]) -> Iterator[tuple[str, Session]]:
    """Dosyasi olan kullanicilar icin sirayla oturum; okuma dosya olusturmaz."""
    for ad in kullanicilar:
        if kullanici_dosyasi(ad).is_file():
            with kullanici_oturumu(ad) as k:
                yield ad, k


def kullanici_dosyalari() -> list[Path]:
    """Mevcut kullanici dosyalari (yedek, butunluk, tablo sayimi)."""
    return sorted(kullanici_dizini().glob("*.db"))


def dis_kimlik(uid: int, yerel: int) -> int:
    return uid * KIMLIK_CARPANI + yerel


def kimlik_coz(kimlik: int) -> tuple[int, int]:
    """(app_user.id, yerel id)"""
    return divmod(kimlik, KIMLIK_CARPANI)
