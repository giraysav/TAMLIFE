"""Oracle kaynak katmani: uretim api_services.OracleSourceConfig + kutucuklar/veri/db_kaynak.py uyarlamasi.

- Anahtar adlari uretimle ayni (backend/.env): <ON EK>_ENABLED / _HOST / _PORT / _SERVICE_NAME / _USER / _PASSWORD / _TIMEOUT /
  _IMPORT_QUERY / _IMPORT_TIMEOUT; ortak ORACLE_CLIENT_DIR (Instant Client -> thick mod; eski 10G parola kaydi DPY-3015'i acar).
- python-oracledb TEMBEL yuklenir (_oracledb(); ad.py _ldap() kalibi): panel (web) sureci hic yuklemez, isci surec yalniz
  baglanirken yukler. Baglanti YALNIZ <ON EK>_ENABLED=true ve zorunlu anahtarlar doluyken acilir (_baglan zorlar).
- Sorgu yalniz koddan / .env'den gelir (arayuzden SQL yok); yalniz tek SELECT / WITH (sorgu_temizle). Hata metninde parola, adres,
  servis adi ve kullanici tasinmaz (hata_metni).
- Baglanti testi panelden AYRI surecte kosar: python -m app.tampon.oracle test <kaynak> (son satir JSON).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.external import SOURCES, Source, acik_mi, on_ek, oracle_eksikleri
from app.ortak import UygulamaHatasi

_log = logging.getLogger("tamlife.oracle")
BACKEND = Path(__file__).resolve().parents[2]
KAYNAKLAR: dict[str, Source] = {s.id: s for s in SOURCES if not s.id.endswith("_import")}
AZAMI_SORGU_UZUNLUGU = 20_000
BLOK = 2_000
_SORGU = re.compile(r"\s*(select|with)\b", re.IGNORECASE)
# Oracle / python-oracledb hata kodu -> yoneticiye anlasilir ipucu (uretim db_kaynak._IPUCLARI).
_IPUCLARI = (
    ("DPY-3015", ("Hesabın parola kaydı eski türde (10G); kurulumsuz sürücü açamıyor. Sunucuya Oracle Client kurulup "
                  ".env'e ORACLE_CLIENT_DIR yazılmalı ya da DBA parolayı yeniden atamalı.")),
    ("ORA-01017", "Kullanıcı adı ya da parola hatalı."),
    ("ORA-01045", "Hesabın veritabanına bağlanma yetkisi (CREATE SESSION) yok; DBA vermeli."),
    ("ORA-28000", "Hesap kilitli; DBA açmalı."),
    ("ORA-12514", "Servis adı (SERVICE_NAME) bulunamadı."),
    ("DPY-6001", "Servis adı (SERVICE_NAME) bulunamadı."),
    ("DPY-6005", "Sunucuya bağlanılamadı (servis adı, adres ya da port hatalı olabilir)."),
    ("ORA-12541", "Dinleyiciye ulaşılamadı (adres / port)."),
    ("ORA-00918", "Sorguda aynı adlı iki sütun var; sütunlara ayrı takma ad (alias) verin."),
)  # fmt: skip
_PAROLA = re.compile(r"(?i)(password|parola|pwd)\s*[=:]\s*\S+")
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_ALAN = re.compile(r"(?i)\b(host|service_name|service|user)(\s*=\s*|\s+)([^\s)\],;]+)")
_istemci_kilit = threading.Lock()
_istemci_denendi = False


class OracleHata(UygulamaHatasi):
    """Yoneticiye gosterilecek kaynak / baglanti hatasi (uretim db_kaynak.DbHatasi)."""

    def __init__(self, mesaj: str, kod: int = 400) -> None:
        super().__init__(kod, mesaj)


def _oracledb() -> Any:
    """python-oracledb tembel yuklenir (testler bu noktayi taklit eder)."""
    import oracledb

    return oracledb


def istemci_hazirla(oracledb: Any) -> None:
    """ORACLE_CLIENT_DIR doluysa thick moda gecer (surec basina bir kez). Yukleme hatasi baglantiyi ENGELLEMEZ: thin'e duser,
    hata gunluge yazilir (uretim oracle_istemcisi_hazirla)."""
    global _istemci_denendi
    klasor = os.environ.get("ORACLE_CLIENT_DIR", "").strip()
    if not klasor:
        return
    with _istemci_kilit:
        if _istemci_denendi:
            return
        _istemci_denendi = True
        try:
            oracledb.init_oracle_client(lib_dir=klasor)
        except Exception:  # noqa: BLE001 - istemci yoksa/bozuksa thin modda devam
            _log.warning("Oracle Client yuklenemedi (ORACLE_CLIENT_DIR); thin modda devam ediliyor", exc_info=True)


def _tam_sayi(anahtar: str, varsayilan: int) -> int:
    try:
        return int(os.environ.get(anahtar, "").strip() or varsayilan)
    except ValueError:
        return varsayilan


class OracleKaynak:
    """Tek Oracle kaynaginin .env ayarlari (uretim OracleSourceConfig). Degerler yalniz baglanirken kullanilir, disari verilmez."""

    def __init__(self, kaynak: Source) -> None:
        on = on_ek(kaynak)
        self.kaynak, self.prefix = kaynak, on
        self.ENABLED = acik_mi(kaynak.enabled_key)
        self.HOST = os.environ.get(f"{on}_HOST", "").strip()
        self.PORT = _tam_sayi(f"{on}_PORT", 1521)
        self.SERVICE_NAME = os.environ.get(f"{on}_SERVICE_NAME", "").strip()
        self.USER = os.environ.get(f"{on}_USER", "").strip()
        self.PASSWORD = os.environ.get(f"{on}_PASSWORD", "")
        self.TIMEOUT = _tam_sayi(f"{on}_TIMEOUT", 10)
        self.IMPORT_QUERY = os.environ.get(f"{on}_IMPORT_QUERY", "")
        self.IMPORT_TIMEOUT = _tam_sayi(f"{on}_IMPORT_TIMEOUT", 300)

    def eksikler(self) -> list[str]:
        return oracle_eksikleri(self.kaynak)

    def gizliler(self) -> tuple[str, ...]:
        """Hata metninden maskelenecek degerler (adres, servis, kullanici, parola)."""
        return tuple(v for v in (self.PASSWORD, self.HOST, self.SERVICE_NAME, self.USER) if len(v) >= 3)

    def _baglan(self, oracledb: Any) -> Any:
        if not self.ENABLED:
            raise OracleHata(f"Kaynak kapalı ({self.kaynak.enabled_key}=true değil).", 409)
        eksik = self.eksikler()
        if eksik:
            raise OracleHata("Bağlantı ayarı eksik: " + ", ".join(eksik))
        istemci_hazirla(oracledb)
        return oracledb.connect(
            user=self.USER, password=self.PASSWORD, dsn=f"{self.HOST}:{self.PORT}/{self.SERVICE_NAME}", tcp_connect_timeout=self.TIMEOUT
        )

    def baglanti_testi(self) -> Any:
        """SELECT 1 FROM DUAL -> 1. Yalniz baglanti + oturum; tablo okunmaz."""
        oracledb = _oracledb()
        with self._baglan(oracledb) as conn:
            conn.call_timeout = self.TIMEOUT * 1000
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM DUAL")
                return cur.fetchone()[0]

    def akis(self, sorgu: str, limit: int, blok: int = BLOK) -> Iterator[list[Any]]:
        """Once sutun adlari, sonra blok blok satirlar (bellekte tum sonuc tutulmaz). CLOB/BLOB metin/bayt gelir. En fazla `limit` satir."""
        oracledb = _oracledb()

        def _tip(cursor: Any, meta: Any) -> Any:
            if meta.type_code is oracledb.DB_TYPE_CLOB or meta.type_code is oracledb.DB_TYPE_NCLOB:
                return cursor.var(oracledb.DB_TYPE_LONG, arraysize=cursor.arraysize)
            if meta.type_code is oracledb.DB_TYPE_BLOB:
                return cursor.var(oracledb.DB_TYPE_LONG_RAW, arraysize=cursor.arraysize)
            return None

        sarmal = f"SELECT * FROM ({sorgu}) WHERE ROWNUM <= :kaynak_limit"
        binds: dict[str, Any] = {"kaynak_limit": int(limit)}
        if ":customer_no" in sorgu.lower():
            binds["customer_no"] = None  # tum musteriler (sorgu "(:customer_no IS NULL OR ...)" yazar)
        with self._baglan(oracledb) as conn:
            conn.call_timeout = self.IMPORT_TIMEOUT * 1000
            conn.outputtypehandler = _tip
            with conn.cursor() as cur:
                cur.arraysize = blok
                cur.execute(sarmal, binds)
                yield [d[0] for d in cur.description]
                while True:
                    satirlar = cur.fetchmany(blok)
                    if not satirlar:
                        return
                    yield satirlar


def ayar(anahtar: str) -> OracleKaynak:
    if anahtar not in KAYNAKLAR:
        raise OracleHata("Bu kaynak bir Oracle kaynağı değil.", 404)
    return OracleKaynak(KAYNAKLAR[anahtar])


def sorgu_temizle(sorgu: str | None) -> str:
    """Yalniz tek SELECT / WITH. Bos ya da gecersizse OracleHata."""
    s = (sorgu or "").strip().rstrip(";").strip()
    if not s:
        raise OracleHata("İçeri alma sorgusu tanımlı değil (.env: *_IMPORT_QUERY).")
    if len(s) > AZAMI_SORGU_UZUNLUGU:
        raise OracleHata("İçeri alma sorgusu çok uzun.")
    if not _SORGU.match(s) or ";" in s:
        raise OracleHata("İçeri alma sorgusu yalnız tek bir SELECT / WITH ifadesi olabilir.")
    return s


def maskele(metin: str, gizliler: tuple[str, ...] = ()) -> str:
    for g in sorted(gizliler, key=len, reverse=True):
        metin = re.sub(re.escape(g), "***", metin, flags=re.IGNORECASE)
    metin = _PAROLA.sub(lambda m: f"{m.group(1)}=***", metin)
    return _ALAN.sub(lambda m: f"{m.group(1)}{m.group(2)}***", _IPV4.sub("***", metin))


def hata_metni(hata: BaseException, gizliler: tuple[str, ...] = ()) -> tuple[str, str]:
    """Hata -> (kisa mesaj, ipucu). Yalniz hata kodu ve ilk satir (kirpilmis); parola, adres, servis adi, kullanici maskeli."""
    ham = str(hata.args[0] if hata.args else hata) if str(hata) else type(hata).__name__
    ilk = maskele((ham.splitlines() or [type(hata).__name__])[0], gizliler)[:220]
    return ilk, next((m for kod, m in _IPUCLARI if kod in ilk), "")


def deger(v: Any) -> Any:
    """Oracle degeri -> JSON'a yazilabilir deger (Decimal sayiya, tarih metne, bos metin None; uretim db_kaynak.deger + ham_depo.hucre)."""
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S") if (v.hour or v.minute or v.second) else v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).hex()[:200]
    if isinstance(v, str):
        return v.strip() or None
    return v if v is None or isinstance(v, (int, float, bool)) else str(v)


def durum(anahtar: str) -> dict[str, Any]:
    """Ekran icin (DEGER degil, yalniz anahtar adlari): acik mi, eksikler, hazir mi, ice alma sorgusu gecerli mi."""
    a = ayar(anahtar)
    eksik = a.eksikler() if a.ENABLED else []
    try:
        sorgu_temizle(a.IMPORT_QUERY)
        sorgu_hata = None
    except OracleHata as e:
        sorgu_hata = e.mesaj
    return {
        "acik": a.ENABLED,
        "eksik": eksik,
        "hazir": a.ENABLED and not eksik,
        "sorgu_tamam": sorgu_hata is None,
        "sorgu_hata": sorgu_hata,
        "oracle_istemci": bool(os.environ.get("ORACLE_CLIENT_DIR", "").strip()),
    }


def baglanti_testi(anahtar: str, senkron: bool = False) -> dict[str, Any]:
    """{'ok', 'mesaj', 'ipucu'}. SELECT 1 FROM DUAL - yazmaz, tablo okumaz. Varsayilan AYRI surecte (surucu / Oracle Client web
    surecine yuklenmez); senkron=True ayri surecin kendisi ve testler icindir."""
    a = ayar(anahtar)
    if not a.ENABLED:
        return {"ok": False, "mesaj": f"Kaynak kapalı ({a.kaynak.enabled_key}=true değil).", "ipucu": ""}
    eksik = a.eksikler()
    if eksik:
        return {"ok": False, "mesaj": "Bağlantı ayarı eksik: " + ", ".join(eksik), "ipucu": ""}
    if not senkron:
        sonuc = _ayri_surecte_test(anahtar, a.TIMEOUT)
        return {**sonuc, "mesaj": maskele(sonuc["mesaj"], a.gizliler())}
    try:
        sonuc = a.baglanti_testi()
    except Exception as e:  # noqa: BLE001 - her surucu / ag hatasi kullaniciya kisa mesajla
        mesaj, ipucu = hata_metni(e, a.gizliler())
        _log.warning("%s baglanti testi basarisiz: %s", anahtar, mesaj)
        return {"ok": False, "mesaj": mesaj, "ipucu": ipucu}
    return {"ok": sonuc == 1, "mesaj": "SELECT 1 FROM DUAL → 1" if sonuc == 1 else "Beklenmeyen yanıt.", "ipucu": ""}


def _ayri_surecte_test(anahtar: str, timeout: int) -> dict[str, Any]:
    bayrak = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        p = subprocess.run(
            [sys.executable, "-m", "app.tampon.oracle", "test", anahtar],
            check=False,
            cwd=str(BACKEND),
            env=dict(os.environ),
            creationflags=bayrak,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=int(timeout) + 25,
        )
        satirlar = [s for s in (p.stdout or "").splitlines() if s.strip().startswith("{")]
        sonuc = json.loads(satirlar[-1])
        return {"ok": bool(sonuc.get("ok")), "mesaj": str(sonuc.get("mesaj") or "")[:300], "ipucu": str(sonuc.get("ipucu") or "")[:300]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "mesaj": "Bağlantı testi zaman aşımına uğradı.", "ipucu": "Adres / port ya da güvenlik duvarı kontrol edilmeli."}
    except (OSError, ValueError, IndexError):
        _log.warning("%s baglanti testi sureci sonuc vermedi", anahtar, exc_info=True)
        return {"ok": False, "mesaj": "Bağlantı testi çalıştırılamadı.", "ipucu": ""}


if __name__ == "__main__":  # python -m app.tampon.oracle test <kaynak> : son satir JSON (ASCII; konsol kod sayfasindan bagimsiz)
    from app.config import env_dosyasi_yukle

    env_dosyasi_yukle()
    if len(sys.argv) != 3 or sys.argv[1] != "test":
        print("Kullanim: python -m app.tampon.oracle test <" + "|".join(KAYNAKLAR) + ">")
        sys.exit(2)
    try:
        cikti = baglanti_testi(sys.argv[2], senkron=True)
    except OracleHata as e:
        cikti = {"ok": False, "mesaj": e.mesaj, "ipucu": ""}
    print(json.dumps(cikti))
