"""Oracle kaynak katmani: uretim api_services.OracleSourceConfig + kutucuklar/veri/db_kaynak.py uyarlamasi.

- Anahtar adlari uretimle ayni (backend/.env): <ON EK>_ENABLED / _HOST / _PORT / _SERVICE_NAME / _USER / _PASSWORD / _TIMEOUT /
  _IMPORT_TIMEOUT (cagri zaman asimi); ortak ORACLE_CLIENT_DIR (Instant Client -> thick mod; eski 10G parola kaydi DPY-3015'i acar).
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
KOLEKSIYON_TIPI = "SYS.ODCIVARCHAR2LIST"  # Oracle'in herkese acik VARRAY(32767) OF VARCHAR2(4000) tipi
KOLEKSIYON_AZAMI = 32_767


class MetinListesi(list):
    """Bind degeri olarak metin listesi: akis() baglantida SYS.ODCIVARCHAR2LIST nesnesine cevirir; sorguda
    "... IN (SELECT COLUMN_VALUE FROM TABLE(:ad))". Uzun liste SQL metnine gomulmez (sorgu kisa kalir, ayristirma ucuz)."""
_SORGU = re.compile(r"\s*(select|with)\b", re.IGNORECASE)
# Oracle / python-oracledb hata kodu -> yoneticiye anlasilir ipucu (uretim db_kaynak._IPUCLARI).
_IPUCLARI = (
    ("DPY-3015", ("Hesabın parola kaydı eski türde (10G); kurulumsuz sürücü açamıyor. Sunucuya Oracle Client kurulup "
                  ".env'e ORACLE_CLIENT_DIR yazılmalı ya da DBA parolayı yeniden atamalı.")),
    ("ORA-20099", ("Parola doğru ve oturum açıldı; ancak veritabanının giriş tetikleyicisi bu DB kullanıcısı, işletim sistemi kullanıcısı ve "
                   "makine için erişimi reddetti. Parola sıfırlamak çözmez; DBA'dan bu erişim için izin istenmeli.")),
    ("ORA-04088", "Veritabanının giriş tetikleyicisi hata verdi (parola sorunu değil); DBA'dan erişim izni istenmeli."),
    ("ORA-01017", "Kullanıcı adı ya da parola hatalı."),
    ("ORA-28001", "Parolanın süresi dolmuş; DBA ya da hesap sahibi yeni parola atamalı."),
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

    def akis(self, sorgu: str, limit: int, blok: int = BLOK, parametreler: dict[str, Any] | None = None) -> Iterator[list[Any]]:
        """Once sutun adlari, sonra blok blok satirlar (bellekte tum sonuc tutulmaz). CLOB/BLOB metin/bayt gelir. En fazla `limit` satir.
        parametreler: koddan gelen sorgunun bind degerleri (:ad); kullanici metni sorguya HIC birlestirilmez."""
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
        binds.update(parametreler or {})
        with self._baglan(oracledb) as conn:
            conn.call_timeout = self.IMPORT_TIMEOUT * 1000
            conn.outputtypehandler = _tip
            listeler = [k for k, v in binds.items() if isinstance(v, MetinListesi)]
            if listeler:
                tip = conn.gettype(KOLEKSIYON_TIPI)
                for k in listeler:
                    if len(binds[k]) > KOLEKSIYON_AZAMI:
                        raise OracleHata("Bind listesi çok uzun.")
                    binds[k] = tip.newobject(list(binds[k]))
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
        raise OracleHata("Sorgu boş.")
    if len(s) > AZAMI_SORGU_UZUNLUGU:
        raise OracleHata("Sorgu çok uzun.")
    if not _SORGU.match(s) or ";" in s:
        raise OracleHata("Sorgu yalnız tek bir SELECT / WITH ifadesi olabilir.")
    return s


def maskele(metin: str, gizliler: tuple[str, ...] = ()) -> str:
    for g in sorted(gizliler, key=len, reverse=True):
        metin = re.sub(re.escape(g), "***", metin, flags=re.IGNORECASE)
    metin = _PAROLA.sub(lambda m: f"{m.group(1)}=***", metin)
    return _ALAN.sub(lambda m: f"{m.group(1)}{m.group(2)}***", _IPV4.sub("***", metin))


def hata_metni(hata: BaseException, gizliler: tuple[str, ...] = ()) -> tuple[str, str]:
    """Hata -> (kisa mesaj, ipucu). Yalniz hata kodu ve ilk satir (kirpilmis); parola, adres, servis adi, kullanici maskeli.
    Ipucu tum metindeki kodlara bakar (giris tetikleyicisi hatasinda ORA-20099 ilk satirda degil, ORA-00604 altindadir)."""
    ham = str(hata.args[0] if hata.args else hata) if str(hata) else type(hata).__name__
    ilk = maskele((ham.splitlines() or [type(hata).__name__])[0], gizliler)[:220]
    return ilk, next((m for kod, m in _IPUCLARI if kod in ham), "")


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
    """Ekran icin (DEGER degil, yalniz anahtar adlari): acik mi, eksikler, hazir mi."""
    a = ayar(anahtar)
    eksik = a.eksikler() if a.ENABLED else []
    return {
        "acik": a.ENABLED,
        "eksik": eksik,
        "hazir": a.ENABLED and not eksik,
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


def bilgiler(anahtar: str) -> dict[str, Any]:
    """Kurum Baglantilari karti (yalniz admin): AD karti gibi sunucu, port, servis adi ve kullanici gorunur (kullanici karari
    2026-10-11); parola ASLA verilmez, yalniz var/yok."""
    a = ayar(anahtar)
    d = durum(anahtar)
    return {
        "sunucu": a.HOST,
        "port": a.PORT,
        "servis": a.SERVICE_NAME,
        "kullanici": a.USER,
        "parola": bool(a.PASSWORD),
        "zaman_asimi": a.TIMEOUT,
        "oracle_istemci": d["oracle_istemci"],
    }


def erisim_adimlari(anahtar: str) -> list[dict[str, str]]:
    """AD erisim testiyle ayni kalip: ayar -> DNS -> TCP -> Oracle oturumu (SELECT 1 FROM DUAL, AYRI surecte); ilk kirilan halkada
    durur. Adim: {'adim', 'durum' ('ok'|'hata'), 'baslik', 'ayrinti'}. Ipucunda sunucu adi yazilir (AD testi gibi); IP ve parola yazilmaz."""
    a = ayar(anahtar)
    adimlar: list[dict[str, str]] = []

    def ekle(adim: str, durum_: str, baslik: str, ayrinti: str = "") -> list[dict[str, str]]:
        adimlar.append({"adim": adim, "durum": durum_, "baslik": baslik, "ayrinti": ayrinti})
        return adimlar

    if not a.ENABLED:
        return ekle("ayar", "hata", f"{a.kaynak.enabled_key}=true değil", "backend/.env içindeki satırı true yapıp paneli yeniden başlatın.")
    eksik = a.eksikler()
    if eksik:
        return ekle("ayar", "hata", "Bağlantı ayarı eksik", ", ".join(eksik))
    ekle("ayar", "ok", "Ayarlar tamam", f"port {a.PORT} · zaman aşımı {a.TIMEOUT} sn" + (" · Oracle Client (thick)" if os.environ.get("ORACLE_CLIENT_DIR", "").strip() else ""))
    if not ag_adimlari(ekle, a.HOST, a.PORT, a.TIMEOUT, "güvenlik duvarı / VPN"):
        return adimlar
    sonuc = baglanti_testi(anahtar)
    ekle("oturum", "ok" if sonuc["ok"] else "hata", "Oracle oturumu (SELECT 1 FROM DUAL)", "\n".join(x for x in (sonuc["mesaj"], sonuc["ipucu"]) if x))
    return adimlar


def ag_adimlari(ekle: Any, host: str, port: int, timeout: int, ipucu: str) -> bool:
    """Erisim testlerinin ortak DNS -> TCP halkalari (Oracle ve PostgreSQL). Kirilirsa adimi yazar ve False doner."""
    import socket

    try:
        adres = {x[4][0] for x in socket.getaddrinfo(host, None)}
        ekle("dns", "ok", "Sunucu adı çözüldü", f"{len(adres)} adres")
    except OSError as exc:
        ekle("dns", "hata", "Sunucu adı çözülemedi", f"{type(exc).__name__}\nnslookup {host}")
        return False
    try:
        socket.create_connection((host, port), timeout=max(1, min(timeout, 5))).close()
        ekle("tcp", "ok", f"Porta ulaşıldı ({port})")
    except OSError as exc:
        ekle("tcp", "hata", f"Porta ulaşılamadı ({port})", f"{type(exc).__name__}\nTest-NetConnection {host} -Port {port} · {ipucu}")
        return False
    return True


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
