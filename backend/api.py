"""TAMLIFE API. Uc dosya: api.py, depo.py, ayar.json.

Rotalar ekran-react ile ayni kalir. Parola ve sertifika yolu yalniz ayar.json.
Oracle acilmaz. Uretim klasoru okunmaz.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import re
import socket
import sqlite3
import ssl
import sys
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, session

sys.path.insert(0, str(Path(__file__).resolve().parent))
import depo

AYAR_YOL = Path(__file__).resolve().with_name("ayar.json")
ESKI = Path(r"D:\Project\TAMLIFE_v3.5\backend-api")
MASKE = "********"
SLOTLAR = (
    {"id": "oracle_reportdb", "ad": "ORACLE REPORTDB"},
    {"id": "ikinci_kaynak", "ad": "ikinci kaynak"},
)
MODUL_ANAHTAR = {
    "takvim": "takvim_ozet",
    "sunum": "sunum",
    "radar": "radar",
    "musteri": "musteri",
    "rapor": "rapor",
    "proje": "proje",
    "onedesk": "onedesk",
    "toptan": "toptan",
    "sms": "tamsms",
    "apn": "tamapn",
    "gelir": "gelir_uretim",
    "izin": "takvim",
    "baglantili": "baglantili",
    "utilizasyon": "utilizasyon",
}
MODUL_AD = {
    "ozet": "TAM Ozet",
    "takvim": "TAM Takvim",
    "sunum": "TAM Sunum",
    "radar": "Musteri Radar",
    "musteri": "Musteri Yonetimi",
    "rapor": "Gonderilen Aylik Rapor",
    "proje": "Takip Edilen Projeler",
    "onedesk": "OneDesk",
    "toptan": "TAM Toptan",
    "sms": "TAM SMS",
    "apn": "TAM APN",
    "gelir": "Gelir Uretim",
    "izin": "Takvim yonetimi",
    "baglantili": "Baglantili Araclar",
    "utilizasyon": "TAM Utilizasyon",
}
YALNIZ_ADMIN = {"utilizasyon"}
MODUL_IDLER = ("ozet", *tuple(MODUL_ANAHTAR))
AD_BAGLANTI_SURESI = 5
AD_YANIT_SURESI = 10
AD_ESZAMANLI_BIND = 3
AD_SIRA_BEKLEME = 2
_bind_sirasi = threading.BoundedSemaphore(AD_ESZAMANLI_BIND)


def _simdi() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _oku_json(yol: Path):
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return veri if isinstance(veri, dict) else None


def _temiz_metin(deger, limit: int = 200) -> str:
    if deger is None:
        return ""
    return str(deger).replace("\r", " ").replace("\n", " ").strip()[:limit]


def _bos_slot(slot: dict) -> dict:
    return {
        "id": slot["id"],
        "ad": slot["ad"],
        "host": "",
        "port": 1521,
        "service": "",
        "user": "",
        "password": "",
    }


def _bos_ayar() -> dict:
    return {
        "yerel_admin": {
            "username": "admin",
            "full_name": "Yerel test admin",
            "algo": "pbkdf2_sha256",
            "iter": 200000,
            "salt_hex": "",
            "hash_hex": "",
        },
        "dev_admin": [],
        "ad": {
            "enabled": False,
            "server": "",
            "domain": "",
            "use_ssl": True,
            "ca_cert_file": "",
            "izinli_alanlar": "",
            "alan_kontrolu": "zorunlu",
            "kimlik_kontrolu": "izle",
            "izinli_gruplar": "",
            "arama_koku": "",
            "otomatik_ac": True,
        },
        "sertifika": {"ad_ca": ""},
        "baglantilar": [_bos_slot(slot) for slot in SLOTLAR],
    }


def _hash_aktar(ayar: dict) -> None:
    eski = _oku_json(ESKI / "yerel_kullanici.json")
    if not eski or eski.get("algo") != "pbkdf2_sha256":
        return
    try:
        tur = int(eski.get("iter") or 0)
    except (TypeError, ValueError):
        return
    ayar["yerel_admin"] = {
        "username": (eski.get("username") or "admin").strip() or "admin",
        "full_name": eski.get("full_name") or "Yerel test admin",
        "algo": "pbkdf2_sha256",
        "iter": tur,
        "salt_hex": str(eski.get("salt_hex") or ""),
        "hash_hex": str(eski.get("hash_hex") or ""),
    }


def _dev_aktar(ayar: dict) -> None:
    eski = _oku_json(ESKI / "dev_kullanici.json")
    if not eski:
        return
    adlar: list[str] = []
    for kayit in eski.get("kullanicilar") or []:
        if not isinstance(kayit, dict) or kayit.get("is_admin") is not True:
            continue
        ad = (kayit.get("username") or "").strip().lower()
        if ad and ad not in adlar:
            adlar.append(ad)
    if adlar:
        ayar["dev_admin"] = adlar


def _baglanti_aktar(ayar: dict, gelen: dict) -> None:
    gelen_slot = {}
    for kayit in gelen.get("baglantilar") or []:
        if isinstance(kayit, dict) and kayit.get("id"):
            gelen_slot[str(kayit["id"])] = kayit
    for slot in ayar["baglantilar"]:
        eski = gelen_slot.get(slot["id"]) or {}
        slot["host"] = _temiz_metin(eski.get("host"))
        try:
            port = int(eski.get("port") or 1521)
        except (TypeError, ValueError):
            port = 1521
        slot["port"] = port if 1 <= port <= 65535 else 1521
        slot["service"] = _temiz_metin(eski.get("service"))
        slot["user"] = _temiz_metin(eski.get("user"))
        slot["password"] = str(eski.get("password") or "")


def _kaydet(ayar: dict) -> None:
    AYAR_YOL.write_text(json.dumps(ayar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ayar_yukle() -> dict:
    ayar = _bos_ayar()
    if not AYAR_YOL.is_file():
        _hash_aktar(ayar)
        _dev_aktar(ayar)
        eski = _oku_json(ESKI / "ayar.json")
        if eski:
            _baglanti_aktar(ayar, eski)
        _kaydet(ayar)
        return ayar
    gelen = _oku_json(AYAR_YOL) or {}
    yerel = gelen.get("yerel_admin") if isinstance(gelen.get("yerel_admin"), dict) else {}
    ayar["yerel_admin"].update({k: yerel.get(k, ayar["yerel_admin"].get(k)) for k in ayar["yerel_admin"]})
    if isinstance(gelen.get("dev_admin"), list):
        ayar["dev_admin"] = [str(a).strip().lower() for a in gelen["dev_admin"] if str(a).strip()]
    ad = gelen.get("ad") if isinstance(gelen.get("ad"), dict) else {}
    for anahtar in ayar["ad"]:
        if anahtar in ad:
            ayar["ad"][anahtar] = ad[anahtar]
    sert = gelen.get("sertifika") if isinstance(gelen.get("sertifika"), dict) else {}
    if "ad_ca" in sert:
        ayar["sertifika"]["ad_ca"] = str(sert.get("ad_ca") or "")
    _baglanti_aktar(ayar, gelen)
    return ayar


def yerel_dene(username: str, password: str, ayar: dict) -> str:
    kayit = ayar.get("yerel_admin") or {}
    ad = (kayit.get("username") or "").strip()
    if not ad or username != ad:
        return "yok"
    if kayit.get("algo") != "pbkdf2_sha256":
        return "red"
    try:
        salt = bytes.fromhex(str(kayit.get("salt_hex") or ""))
        beklenen = bytes.fromhex(str(kayit.get("hash_hex") or ""))
        tur = int(kayit.get("iter") or 0)
    except (TypeError, ValueError):
        return "red"
    if tur < 1 or not salt or not beklenen:
        return "red"
    gelen = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, tur)
    if hmac.compare_digest(gelen, beklenen):
        return "ok"
    return "red"


def _izin_acik(izin: dict, grup: str, anahtar: str) -> bool:
    kutu = izin.get(grup)
    if not isinstance(kutu, dict):
        return False
    return bool(kutu.get(anahtar))


def modul_acik(anahtar: str, *, admin: bool, yonetici: bool, izin: dict) -> bool:
    if admin:
        return True
    if anahtar in YALNIZ_ADMIN:
        return False
    if yonetici:
        return True
    if _izin_acik(izin, "modules", anahtar) or _izin_acik(izin, "dashboard_cards", anahtar):
        return True
    if anahtar in ("tamsms", "tamapn") and _izin_acik(izin, "dashboard_cards", "ictapn"):
        return True
    kartlar = izin.get("dashboard_cards")
    if anahtar == "baglantili" and (not isinstance(kartlar, dict) or "baglantili" not in kartlar):
        return True
    return False


def _modul_sirasi(secili: set[str], *, hepsi: bool) -> list[str]:
    if hepsi:
        return list(MODUL_IDLER)
    temiz = {m for m in secili if m in MODUL_IDLER}
    temiz.add("ozet")
    return [m for m in MODUL_IDLER if m in temiz]


def varsayilan_roller() -> dict[str, list[str]]:
    hepsi = list(MODUL_IDLER)
    yonetici = ["ozet"]
    uye = ["ozet"]
    for modul_id, anahtar in MODUL_ANAHTAR.items():
        if modul_acik(anahtar, admin=False, yonetici=True, izin={}):
            yonetici.append(modul_id)
        if modul_acik(anahtar, admin=False, yonetici=False, izin={}):
            uye.append(modul_id)
    return {"admin": hepsi, "TeamMngr": yonetici, "TeamMember": uye}


def _rol_listesi(ham) -> list[str] | None:
    if not isinstance(ham, list):
        return None
    return _modul_sirasi({m for m in ham if isinstance(m, str)}, hepsi=False)


def roller_oku() -> dict[str, list[str]]:
    taban = varsayilan_roller()
    if depo.rol_var():
        kayit = depo.rol_harita(list(MODUL_IDLER))
        for ad in ("TeamMngr", "TeamMember"):
            if ad in kayit:
                taban[ad] = kayit[ad]
    taban["admin"] = list(MODUL_IDLER)
    return taban


def roller_kaydet(govde: dict) -> dict[str, list[str]]:
    if not isinstance(govde, dict):
        raise ValueError("govde")
    kaynak = govde.get("roller") if isinstance(govde.get("roller"), dict) else govde
    if not isinstance(kaynak, dict):
        raise ValueError("govde")
    mevcut = roller_oku()
    degisti = False
    for ad in ("TeamMngr", "TeamMember"):
        if ad not in kaynak:
            continue
        liste = _rol_listesi(kaynak.get(ad))
        if liste is None:
            raise ValueError(ad)
        mevcut[ad] = liste
        degisti = True
    if not degisti:
        raise ValueError("rol")
    mevcut["admin"] = list(MODUL_IDLER)
    return depo.rol_yaz(mevcut, list(MODUL_IDLER))


def _haritadan(rol_adi: str) -> list[str] | None:
    if not depo.rol_var():
        return None
    harita = roller_oku()
    if rol_adi == "teammngr":
        return list(harita["TeamMngr"])
    if rol_adi == "teammember":
        return list(harita["TeamMember"])
    return None


def gorunen(*, oturum: bool, username: str | None, is_admin: bool, role: str | None, izin: dict | None, dev_admin: set[str]) -> dict:
    ad = (username or "").strip().lower()
    dev = bool(oturum and ad and ad in dev_admin)
    rol_adi = (role or "").strip().lower()
    admin = bool(oturum and (is_admin or dev or rol_adi == "admin"))
    yonetici = bool(oturum and not admin and rol_adi == "teammngr")
    izin = izin if isinstance(izin, dict) else {}
    kayitli = _haritadan(rol_adi) if oturum and not admin else None
    if admin:
        moduller = list(MODUL_IDLER)
    elif kayitli is not None:
        moduller = list(kayitli)
    else:
        moduller = ["ozet"]
        if oturum:
            for modul_id, anahtar in MODUL_ANAHTAR.items():
                if modul_acik(anahtar, admin=admin, yonetici=yonetici, izin=izin):
                    moduller.append(modul_id)
    return {"oturum": bool(oturum), "admin": admin, "moduller": moduller, "menu": {"rol": admin, "admin": admin}}


def _tohum() -> None:
    depo.hazirla()
    if not depo.modul_var():
        kayitlar = []
        for sira, modul_id in enumerate(MODUL_IDLER):
            anahtar = MODUL_ANAHTAR.get(modul_id, modul_id)
            kayitlar.append((modul_id, MODUL_AD.get(modul_id, modul_id), anahtar, sira, int(anahtar in YALNIZ_ADMIN)))
        depo.modul_yaz(kayitlar)
    if depo.rol_var():
        return
    harita = varsayilan_roller()
    eski = _oku_json(ESKI / "roller.json")
    kaynak = None
    if isinstance(eski, dict):
        kaynak = eski.get("roller") if isinstance(eski.get("roller"), dict) else eski
    if isinstance(kaynak, dict):
        for ad in ("TeamMngr", "TeamMember"):
            liste = _rol_listesi(kaynak.get(ad)) if ad in kaynak else None
            if liste is not None:
                harita[ad] = liste
    harita["admin"] = list(MODUL_IDLER)
    depo.rol_yaz(harita, list(MODUL_IDLER))


def herkese_acik(ayar: dict) -> dict:
    slotlar = []
    for slot in ayar["baglantilar"]:
        gizli = bool(slot.get("password"))
        slotlar.append({
            "id": slot["id"],
            "ad": slot["ad"],
            "host": slot["host"],
            "port": slot["port"],
            "service": slot["service"],
            "user": slot["user"],
            "parola": MASKE if gizli else "",
            "parola_var": gizli,
        })
    return {"sqlite": str(depo.VERI), "baglantilar": slotlar}


def _slot_bul(ayar: dict, slot_id: str) -> dict:
    for slot in ayar["baglantilar"]:
        if slot["id"] == slot_id:
            return slot
    raise KeyError(slot_id)


def ayar_guncelle(slot_id: str, alanlar: dict) -> dict:
    if not isinstance(alanlar, dict):
        raise ValueError("govde")
    ayar = ayar_yukle()
    slot = _slot_bul(ayar, slot_id)
    if "host" in alanlar:
        slot["host"] = _temiz_metin(alanlar.get("host"))
    if "port" in alanlar:
        try:
            port = int(alanlar.get("port"))
        except (TypeError, ValueError):
            raise ValueError("port")
        if not 1 <= port <= 65535:
            raise ValueError("port")
        slot["port"] = port
    if "service" in alanlar:
        slot["service"] = _temiz_metin(alanlar.get("service"))
    if "user" in alanlar:
        slot["user"] = _temiz_metin(alanlar.get("user"))
    if "password" in alanlar and alanlar.get("password") is not None:
        metin = str(alanlar.get("password"))
        if metin and metin != MASKE:
            slot["password"] = metin
    _kaydet(ayar)
    return herkese_acik(ayar_yukle())


def tcp_dene(slot_id: str, timeout: float = 3.0) -> dict:
    ayar = ayar_yukle()
    slot = _slot_bul(ayar, slot_id)
    host = slot["host"]
    port = int(slot["port"])
    if not host:
        return {"ulasti": False, "neden": "host_yok", "host": "", "port": port}
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"ulasti": True, "host": host, "port": port}
    except OSError as exc:
        return {"ulasti": False, "host": host, "port": port, "neden": type(exc).__name__}


def veri_agaci(ayar: dict) -> dict:
    slotlar = {slot["id"]: slot for slot in ayar["baglantilar"]}

    def tanimli(slot: dict) -> bool:
        return bool(slot.get("host") and slot.get("service") and slot.get("user") and slot.get("password"))

    rapor = tanimli(slotlar.get("oracle_reportdb") or {})
    ikinci = tanimli(slotlar.get("ikinci_kaynak") or {})
    return {
        "baslik": "Veri agaci",
        "dugumler": [{
            "id": "onedesk",
            "ad": "OneDesk",
            "cocuklar": [
                {"id": "oracle_reportdb", "ad": "Oracle REPORTDB", "tur": "realtime", "tanimli": rapor, "durum": "tanimli" if rapor else "degil"},
                {"id": "ikinci_kaynak", "ad": "ikinci kaynak", "tur": "realtime", "tanimli": ikinci, "durum": "tanimli" if ikinci else "degil"},
            ],
        }],
    }


def _guvenli_ad(ad: str) -> str:
    ad = Path(ad or "dosya.csv").name
    ad = re.sub(r"[^A-Za-z0-9._-]+", "_", ad).strip("._") or "dosya"
    if not ad.lower().endswith(".csv"):
        ad += ".csv"
    return ad[:120]


def _satir_say(icerik: bytes) -> int:
    metin = icerik.decode("utf-8-sig", errors="replace")
    sayi = 0
    for row in csv.reader(io.StringIO(metin)):
        if any(str(hucre).strip() for hucre in row):
            sayi += 1
    return sayi


def ice_al(ad: str, icerik: bytes) -> dict:
    if not icerik:
        raise ValueError("bos")
    if len(icerik) > 20 * 1024 * 1024:
        raise ValueError("buyuk")
    if b"\x00" in icerik:
        raise ValueError("csv_degil")
    if not str(ad or "").lower().endswith(".csv"):
        raise ValueError("csv_degil")
    depo.hazirla()
    simdi = datetime.now().astimezone()
    zaman = simdi.isoformat(timespec="seconds")
    dosya_ad = simdi.strftime("%Y%m%d_%H%M%S") + "_" + _guvenli_ad(ad)
    hedef = depo.GELEN / dosya_ad
    hedef.write_bytes(icerik)
    satir = _satir_say(icerik)
    kayit_id = depo.ice_ekle(Path(ad).name[:200], str(hedef), zaman, satir)
    return {"id": kayit_id, "ad": Path(ad).name, "yol": str(hedef), "zaman": zaman, "satir": satir}


class _AD:
    def __init__(self, ayar: dict):
        ad = ayar.get("ad") or {}
        sert = ayar.get("sertifika") or {}
        self.ENABLED = str(ad.get("enabled", False)).strip().lower() in ("1", "true", "evet", "yes")
        self.SERVER = str(ad.get("server") or "")
        self.DOMAIN = str(ad.get("domain") or "")
        self.USE_SSL = str(ad.get("use_ssl", True)).strip().lower() not in ("0", "false", "hayir", "no")
        self.CA_CERT_FILE = str(ad.get("ca_cert_file") or sert.get("ad_ca") or "").strip()
        ham = ad.get("izinli_alanlar") or ""
        if isinstance(ham, list):
            liste = [str(a).strip().lower() for a in ham if str(a).strip()]
        else:
            liste = [a.strip().lower() for a in str(ham).split(",") if a.strip()]
        domain = self.DOMAIN.lower()
        if domain and domain not in liste:
            liste.append(domain)
        self.IZINLI_ALANLAR = liste
        self.ALAN_KONTROLU = str(ad.get("alan_kontrolu") or "zorunlu").strip().lower()
        self.KIMLIK_KONTROLU = str(ad.get("kimlik_kontrolu") or "izle").strip().lower()
        grup = ad.get("izinli_gruplar") or ""
        if isinstance(grup, list):
            self.IZINLI_GRUPLAR = [str(g).strip() for g in grup if str(g).strip()]
        else:
            self.IZINLI_GRUPLAR = [g.strip() for g in str(grup).split(",") if g.strip()]
        self.ARAMA_KOKU = str(ad.get("arama_koku") or "").strip()

    def domain_ayristir(self, kullanici_girdisi: str) -> tuple[str, str]:
        if not kullanici_girdisi:
            return "", ""
        girdi = kullanici_girdisi.strip()
        if "@" in girdi:
            kisa_ad, domain = girdi.rsplit("@", 1)
            return kisa_ad.strip(), domain.strip()
        if "\\" in girdi:
            domain, kisa_ad = girdi.split("\\", 1)
            return kisa_ad.strip(), domain.strip()
        return girdi, self.DOMAIN

    def _oturum_adi(self, kullanici_girdisi: str) -> str:
        girdi = (kullanici_girdisi or "").strip()
        if not girdi:
            return ""
        if "@" in girdi or "\\" in girdi:
            return girdi
        return f"{girdi}@{self.DOMAIN}" if self.DOMAIN else girdi

    def dogrula(self) -> str | None:
        if not self.ENABLED:
            return None
        if not self.SERVER.strip().lower().startswith("ldaps://") or not self.USE_SSL:
            return "ad_ayar_ldaps"
        if self.ALAN_KONTROLU not in ("izle", "zorunlu"):
            return "ad_ayar_alan"
        if self.KIMLIK_KONTROLU not in ("izle", "zorunlu"):
            return "ad_ayar_kimlik"
        if self.IZINLI_GRUPLAR and not self.ARAMA_KOKU:
            return "ad_ayar_grup"
        return None

    def _server(self):
        from ldap3 import NONE, Server, Tls

        if not self.SERVER.strip().lower().startswith("ldaps://") or not self.USE_SSL:
            raise ValueError("plain_ldap")
        tls_kw = {"validate": ssl.CERT_REQUIRED, "version": ssl.PROTOCOL_TLSv1_2}
        if self.CA_CERT_FILE:
            tls_kw["ca_certs_file"] = self.CA_CERT_FILE
        return Server(self.SERVER, use_ssl=True, tls=Tls(**tls_kw), get_info=NONE, connect_timeout=AD_BAGLANTI_SURESI)

    @staticmethod
    def _gercek_kisa_ad(conn):
        try:
            kimlik = conn.extend.standard.who_am_i()
        except Exception:
            return None
        if isinstance(kimlik, bytes):
            kimlik = kimlik.decode("utf-8", "replace")
        if not isinstance(kimlik, str):
            return None
        kimlik = kimlik.strip()
        if kimlik.lower().startswith("u:"):
            kimlik = kimlik[2:]
        if "\\" not in kimlik:
            return None
        return kimlik.split("\\", 1)[1].strip().lower() or None

    def _grup(self, conn, kisa_ad: str):
        if not self.IZINLI_GRUPLAR:
            return True, None
        if not self.ARAMA_KOKU:
            return False, "ad_grup_yapilandirma"
        from ldap3.utils.conv import escape_filter_chars

        for grup in self.IZINLI_GRUPLAR:
            filtre = "(&(objectClass=user)(sAMAccountName={})(memberOf={}))".format(
                escape_filter_chars(kisa_ad), escape_filter_chars(grup)
            )
            if conn.search(self.ARAMA_KOKU, filtre, attributes=["distinguishedName"], size_limit=1) and conn.entries:
                return True, None
        return False, "ad_grup_izinsiz"

    def dene(self, username: str, password: str) -> tuple[bool, str]:
        if not self.ENABLED:
            return False, "ad_kapali"
        sorun = self.dogrula()
        if sorun:
            return False, sorun
        if not username or not password:
            return False, "eksik_bilgi"
        kisa_ad, domain = self.domain_ayristir(username)
        if not kisa_ad:
            return False, "eksik_bilgi"
        domain_kucuk = domain.lower() if domain else ""
        alan_disi = bool(domain_kucuk and self.IZINLI_ALANLAR and domain_kucuk not in self.IZINLI_ALANLAR)
        if alan_disi and self.ALAN_KONTROLU == "zorunlu":
            return False, f"alan_izinsiz: {domain_kucuk}"
        if not _bind_sirasi.acquire(timeout=AD_SIRA_BEKLEME):
            return False, "ad_mesgul"
        try:
            from ldap3 import SIMPLE, Connection
            from ldap3.core.exceptions import LDAPSocketOpenError

            server = self._server()
            conn = Connection(
                server, user=self._oturum_adi(username), password=password,
                authentication=SIMPLE, receive_timeout=AD_YANIT_SURESI,
            )
            if conn.bind():
                try:
                    gercek_ad = self._gercek_kisa_ad(conn)
                    grup_ok, grup_sebep = self._grup(conn, kisa_ad)
                finally:
                    conn.unbind()
                if gercek_ad and gercek_ad != kisa_ad.lower() and self.KIMLIK_KONTROLU == "zorunlu":
                    return False, f"ad_kimlik_uyusmuyor: {gercek_ad}"
                if not grup_ok:
                    return False, grup_sebep or "ad_grup_izinsiz"
                if alan_disi:
                    return False, f"ad_onayladi_alan_disi:{domain_kucuk}"
                return True, "ad_onayladi"
            try:
                conn.unbind()
            except Exception:
                pass
            return False, "ad_reddetti"
        except Exception as exc:
            ad = type(exc).__name__
            try:
                from ldap3.core.exceptions import LDAPSocketOpenError
                if isinstance(exc, LDAPSocketOpenError):
                    ad = "LDAPSocketOpenError"
            except Exception:
                pass
            return False, f"ad_ulasilamadi: {ad}"
        finally:
            _bind_sirasi.release()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or os.urandom(32).hex()
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["JSON_AS_ASCII"] = False
    app.config["MAX_CONTENT_LENGTH"] = 21 * 1024 * 1024
    ayar_yukle()
    _tohum()

    @app.before_request
    def _on_kontrol():
        if request.method == "OPTIONS" and request.path.startswith("/api/"):
            return ("", 204)

    @app.after_request
    def _cors(resp):
        origin = request.headers.get("Origin") or ""
        if origin in ("http://127.0.0.1:5173", "http://localhost:5173"):
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            resp.headers["Vary"] = "Origin"
        return resp

    def _kullanici():
        uid = session.get("user_id")
        if not uid:
            return None
        return {
            "id": uid,
            "username": session.get("username"),
            "full_name": session.get("full_name"),
            "is_admin": bool(session.get("is_admin")),
            "role": session.get("role"),
        }

    def _admin() -> bool:
        if not session.get("user_id"):
            return False
        if session.get("is_admin"):
            return True
        return (session.get("role") or "").strip().lower() == "admin"

    def _red(yol: str):
        depo.yetki_red_yaz(_simdi(), session.get("username") or "", yol)
        return jsonify(status="error", message="Bu islem icin yonetici yetkisi gereklidir."), 403

    @app.get("/")
    def kok():
        html = (
            "<!doctype html><html lang=\"tr\"><meta charset=\"utf-8\">"
            "<title>TAMLIFE API</title><body><p>TAMLIFE API ayakta.</p>"
            "<p>Arayuz: <a href=\"http://127.0.0.1:5173/\">http://127.0.0.1:5173/</a></p>"
            "</body></html>"
        )
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.get("/api/saglik")
    def saglik():
        dosyalar = {ad: depo.yol(ad).is_file() for ad in depo.ADLAR}
        return jsonify(durum="ok" if all(dosyalar.values()) else "eksik", veritabani=dosyalar, oracle="acilmadi")

    @app.post("/api/giris")
    def giris():
        govde = request.get_json(silent=True) or {}
        username = (govde.get("username") or "").strip()
        password = govde.get("password") or ""
        if not username or not password:
            return jsonify(status="error", message="Kullanici adi ve parola gerekli."), 400
        ayar = ayar_yukle()
        yerel = yerel_dene(username, password, ayar)
        if yerel == "red":
            depo.giris_yaz(_simdi(), username, "red", "yerel_red")
            return jsonify(status="error", message="Giris onaylanmadi.", neden="yerel_red"), 401
        if yerel == "ok":
            kisi = ayar["yerel_admin"]
            depo.kullanici_ac(kisi["username"], {
                "username": kisi["username"],
                "full_name": kisi.get("full_name") or "Yerel test admin",
                "role": "admin",
                "is_admin": "1",
            })
            session.clear()
            session["user_id"] = "yerel-admin"
            session["username"] = kisi["username"]
            session["full_name"] = kisi.get("full_name") or "Yerel test admin"
            session["is_admin"] = True
            session["role"] = "admin"
            session["yerel_test"] = True
            session.permanent = True
            depo.giris_yaz(_simdi(), kisi["username"], "ok", "yerel_test")
            return jsonify(status="success", neden="yerel_test", kullanici={
                "id": "yerel-admin",
                "username": kisi["username"],
                "full_name": session["full_name"],
                "is_admin": True,
                "role": "admin",
            })
        ad = _AD(ayar)
        ok, neden = ad.dene(username, password)
        if not ok:
            depo.giris_yaz(_simdi(), username, "red", neden)
            return jsonify(status="error", message="Giris onaylanmadi.", neden=neden), 401
        kisa, _alan = ad.domain_ayristir(username)
        depo.kullanici_ac(kisa)
        profil = depo.profil_oku(kisa)
        if "role" not in profil:
            depo.kullanici_ac(kisa, {"username": kisa, "full_name": kisa, "role": "TeamMember", "is_admin": "0"})
            profil = depo.profil_oku(kisa)
        rol = profil.get("role") or "TeamMember"
        admin = profil.get("is_admin") == "1" or rol.strip().lower() == "admin"
        session.clear()
        session["user_id"] = kisa
        session["username"] = profil.get("username") or kisa
        session["full_name"] = profil.get("full_name") or kisa
        session["is_admin"] = admin
        session["role"] = "admin" if admin else rol
        session.permanent = True
        depo.giris_yaz(_simdi(), kisa, "ok", neden)
        return jsonify(status="success", neden=neden, kullanici={
            "id": kisa,
            "username": session["username"],
            "full_name": session["full_name"],
            "is_admin": admin,
            "role": session["role"],
        })

    @app.post("/api/cikis")
    def cikis():
        session.clear()
        resp = jsonify(status="success", oturum=False)
        resp.delete_cookie(
            app.config.get("SESSION_COOKIE_NAME", "session"),
            path=app.config.get("SESSION_COOKIE_PATH") or "/",
            domain=app.config.get("SESSION_COOKIE_DOMAIN"),
            secure=bool(app.config.get("SESSION_COOKIE_SECURE", False)),
            httponly=bool(app.config.get("SESSION_COOKIE_HTTPONLY", True)),
            samesite=app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
        )
        return resp

    @app.get("/api/yetkiler")
    def yetkiler():
        kullanici = _kullanici()
        ayar = ayar_yukle()
        dev = {a for a in ayar.get("dev_admin") or [] if isinstance(a, str)}
        if not kullanici:
            return jsonify(gorunen(oturum=False, username=None, is_admin=False, role=None, izin=None, dev_admin=dev))
        return jsonify(gorunen(
            oturum=True,
            username=kullanici.get("username"),
            is_admin=bool(kullanici.get("is_admin")),
            role=kullanici.get("role"),
            izin=None,
            dev_admin=dev,
        ))

    @app.get("/api/roller")
    def roller_get():
        if not _admin():
            return _red("/api/roller")
        return jsonify(status="success", roller=roller_oku())

    @app.post("/api/roller")
    def roller_post():
        if not _admin():
            return _red("/api/roller")
        govde = request.get_json(silent=True) or {}
        try:
            kayit = roller_kaydet(govde)
        except ValueError:
            return jsonify(status="error", message="Gecersiz rol listesi."), 400
        return jsonify(status="success", roller=kayit)

    @app.get("/api/admin/kapi")
    def admin_kapi():
        kullanici = _kullanici()
        if not kullanici:
            return jsonify(status="error", message="Oturum bulunamadi, lutfen giris yapin."), 401
        if not session.get("is_admin"):
            return _red("/api/admin/kapi")
        return jsonify(status="success", admin=True, kullanici=kullanici["username"])

    @app.get("/api/admin/veri-agaci")
    def admin_veri_agaci():
        return jsonify(status="success", agac=veri_agaci(ayar_yukle()))

    @app.get("/api/admin/baglantilar")
    def admin_baglantilar():
        if not _admin():
            return _red("/api/admin/baglantilar")
        return jsonify(status="success", **herkese_acik(ayar_yukle()))

    @app.post("/api/admin/baglantilar/<slot_id>")
    def admin_baglanti_kaydet(slot_id):
        if not _admin():
            return _red("/api/admin/baglantilar")
        govde = request.get_json(silent=True) or {}
        try:
            acik = ayar_guncelle(slot_id, govde)
        except KeyError:
            return jsonify(status="error", message="Baglanti bulunamadi."), 404
        except ValueError:
            return jsonify(status="error", message="Gecersiz baglanti alani."), 400
        return jsonify(status="success", **acik)

    @app.post("/api/admin/baglantilar/<slot_id>/dene")
    def admin_baglanti_dene(slot_id):
        if not _admin():
            return _red("/api/admin/baglantilar")
        try:
            sonuc = tcp_dene(slot_id)
        except KeyError:
            return jsonify(status="error", message="Baglanti bulunamadi."), 404
        return jsonify(status="success", sonuc=sonuc)

    @app.get("/api/admin/ice-aktar")
    def admin_ice_liste():
        if not _admin():
            return _red("/api/admin/ice-aktar")
        return jsonify(status="success", kayitlar=depo.ice_liste())

    @app.post("/api/admin/ice-aktar")
    def admin_ice_aktar():
        if not _admin():
            return _red("/api/admin/ice-aktar")
        dosya = request.files.get("dosya")
        if dosya is None or not dosya.filename:
            return jsonify(status="error", message="CSV dosyasi gerekli."), 400
        if not str(dosya.filename).lower().endswith(".csv"):
            return jsonify(status="error", message="Yalniz CSV kabul edilir."), 400
        try:
            kayit = ice_al(dosya.filename, dosya.read())
        except ValueError:
            return jsonify(status="error", message="CSV okunamadi."), 400
        return jsonify(status="success", kayit=kayit)

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("KEMIK_PORT", "8119"))
    print(f"dinleniyor {port}", flush=True)
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)