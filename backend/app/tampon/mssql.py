# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""MSSQL dis kaynagi: devre trafik olcumleri (2026-11-27; yetki 2026-11-27 geldi, bkz. app.rapor.loe_trafik).

Ayarlar backend/.env: MSSQL_LOE_ENABLED (yalniz 'true' acar), _HOST, _PORT (1433), _DBNAME (virgulle birden cok veritabani; trafik
tablolari loe_reporting_bb / _int / _vrf'te ayri ayri durur), _USER, _PASSWORD, _TIMEOUT (10 sn), _IMPORT_TIMEOUT (sorgu, 900 sn).
SQL kimlik dogrulamasi (Windows girisi sunucuda reddediliyor). Surucu: Windows'un yerlesik "SQL Server" ODBC surucusu + pyodbc; yalniz
baglanirken yuklenir (panel yalniz Kurum Baglantilari testinde, veri cekimi isci surecinde). Yalniz SELECT; parola ekrana ASLA.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.ortak import UygulamaHatasi
from app.tampon.oracle import ag_adimlari, maskele

KAYNAK = "mssql_loe"
ETIKET = "LOE TRAFİK"
ON_EK = "MSSQL_LOE"
ENABLED_KEY = f"{ON_EK}_ENABLED"
ZORUNLU = ("HOST", "DBNAME", "USER", "PASSWORD")
SURUCU = "SQL Server"  # Windows yerlesik ODBC surucusu (ayri kurulum gerekmez)
_VT_ADI = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")


class MssqlHata(UygulamaHatasi):
    def __init__(self, mesaj: str, kod: int = 400) -> None:
        super().__init__(kod, mesaj)


def _tam_sayi(anahtar: str, varsayilan: int) -> int:
    try:
        return int(os.environ.get(anahtar, "").strip() or varsayilan)
    except ValueError:
        return varsayilan


class MssqlKaynak:
    def __init__(self) -> None:
        self.ENABLED = os.environ.get(ENABLED_KEY, "").strip().lower() == "true"
        self.HOST = os.environ.get(f"{ON_EK}_HOST", "").strip()
        self.PORT = _tam_sayi(f"{ON_EK}_PORT", 1433)
        self.DBNAME = os.environ.get(f"{ON_EK}_DBNAME", "").strip()
        self.USER = os.environ.get(f"{ON_EK}_USER", "").strip()
        self.PASSWORD = os.environ.get(f"{ON_EK}_PASSWORD", "")
        self.TIMEOUT = max(1, min(_tam_sayi(f"{ON_EK}_TIMEOUT", 10), 60))
        self.SORGU_SN = max(10, min(_tam_sayi(f"{ON_EK}_IMPORT_TIMEOUT", 900), 3600))

    @property
    def veritabanlari(self) -> list[str]:
        """Gecerli adlar (sorguya USE [ad] olarak girer; yalniz harf / rakam / alt cizgi)."""
        return [v for v in (p.strip() for p in self.DBNAME.split(",")) if _VT_ADI.match(v)]

    def eksikler(self) -> list[str]:
        eksik = [f"{ON_EK}_{ad}" for ad in ZORUNLU if not getattr(self, ad).strip()]
        if self.DBNAME.strip() and not self.veritabanlari:
            eksik.append(f"{ON_EK}_DBNAME (geçersiz ad)")
        return eksik

    def hazir(self) -> bool:
        return self.ENABLED and not self.eksikler()

    def gizliler(self) -> tuple[str, ...]:
        return tuple(v for v in (self.PASSWORD, self.HOST, self.USER) if len(v) >= 3)

    @contextmanager
    def baglan(self) -> Iterator[Any]:
        """Otomatik onayli, zaman asimli ODBC oturumu (yalniz SELECT calistirilir)."""
        if not self.ENABLED:
            raise MssqlHata(f"Kaynak kapalı ({ENABLED_KEY}=true değil).", 409)
        if eksik := self.eksikler():
            raise MssqlHata("Bağlantı ayarı eksik: " + ", ".join(eksik))
        import pyodbc

        conn = pyodbc.connect(
            f"DRIVER={{{SURUCU}}};SERVER={self.HOST},{self.PORT};UID={self.USER};PWD={{{self.PASSWORD.replace('}', '}}')}}};APP=TAMLIFE",
            timeout=self.TIMEOUT, autocommit=True, readonly=True,
        )  # fmt: skip
        conn.timeout = self.SORGU_SN
        try:
            yield conn
        finally:
            conn.close()


def ayar() -> MssqlKaynak:
    return MssqlKaynak()


def hata_metni(hata: BaseException, gizliler: tuple[str, ...]) -> str:
    ham = str(hata) or type(hata).__name__
    return maskele((ham.splitlines() or [type(hata).__name__])[0], gizliler)[:220]


def durum() -> dict[str, Any]:
    a = ayar()
    eksik = a.eksikler() if a.ENABLED else []
    return {"acik": a.ENABLED, "eksik": eksik, "hazir": a.ENABLED and not eksik, "state": "disabled" if not a.ENABLED else ("incomplete" if eksik else "ready")}  # fmt: skip


def bilgiler() -> dict[str, Any]:
    """Kurum Baglantilari karti (yalniz admin): sunucu, port, veritabanlari, kullanici; parola yalniz tanimli mi."""
    a = ayar()
    return {"sunucu": a.HOST, "port": a.PORT, "veritabani": ", ".join(a.veritabanlari), "kullanici": a.USER, "parola": bool(a.PASSWORD),
            "zaman_asimi": a.TIMEOUT}  # fmt: skip


def erisim_adimlari() -> list[dict[str, str]]:
    """Oracle / PostgreSQL testiyle ayni kalip: ayar -> DNS -> TCP -> oturum + her veritabaninda okuma izni; ilk kirilan halkada durur."""
    a = ayar()
    adimlar: list[dict[str, str]] = []

    def ekle(adim: str, durum_: str, baslik: str, ayrinti: str = "") -> list[dict[str, str]]:
        adimlar.append({"adim": adim, "durum": durum_, "baslik": baslik, "ayrinti": ayrinti})
        return adimlar

    if not a.ENABLED:
        return ekle("ayar", "hata", f"{ENABLED_KEY}=true değil", "backend/.env içindeki satırı true yapıp paneli yeniden başlatın.")
    if eksik := a.eksikler():
        return ekle("ayar", "hata", "Bağlantı ayarı eksik", ", ".join(eksik))
    ekle("ayar", "ok", "Ayarlar tamam", f"port {a.PORT} · {len(a.veritabanlari)} veritabanı · zaman aşımı {a.TIMEOUT} sn")
    if not ag_adimlari(ekle, a.HOST, a.PORT, a.TIMEOUT, "güvenlik duvarı izni gerekir"):
        return adimlar
    try:
        with a.baglan() as conn:
            cur = conn.cursor()
            surum = cur.execute("SELECT CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(40))").fetchone()[0]
            erisimler = [(v, cur.execute("SELECT HAS_DBACCESS(?)", v).fetchone()[0]) for v in a.veritabanlari]
        kapali = [v for v, e in erisimler if e != 1]
        if kapali:
            ekle("oturum", "hata", "MSSQL oturumu açıldı, veritabanı erişimi eksik", "erişim yok: " + ", ".join(kapali))
        else:
            ekle("oturum", "ok", "MSSQL oturumu (salt okunur) ve veritabanı erişimi", f"SQL Server {surum} · {len(erisimler)} veritabanı okunabilir")
    except Exception as e:  # noqa: BLE001 - surucu / kimlik / ag hatasi kisa mesajla
        ekle("oturum", "hata", "MSSQL oturumu", hata_metni(e, a.gizliler()))
    return adimlar
