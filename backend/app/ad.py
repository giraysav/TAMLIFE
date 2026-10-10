"""AD/LDAPS dogrulamasi. Eski servisle (ad_service.py) ayni kurallar, ayni AD_* anahtarlari, ayni sebep kodlari.

- Yalniz ldaps:// (TLS 1.2, sertifika dogrulamasi zorunlu; kurum CA'si AD_CA_CERT_FILE). Duz ldap:// acilista reddedilir.
- Servis hesabi yok: bind kullanicinin kendi UPN'i ve parolasiyla (SIMPLE). Parola saklanmaz, gunluge yazilmaz.
- Rol AD'den gelmez; app_user.role (panel DB). AD yalniz "bu kisi bu parolayla dogrulandi" der.
- Es zamanli bind 3, baglanti/yanit suresi 5/10 sn: yanit vermeyen DC istekleri kilitlemesin.
- AD_ENABLED=false (varsayilan) iken ldap3 hic yuklenmez. Yerel dev girisi (TAMLIFE_LOCAL_*) yalniz dev/test.
Tani: `python -m app.ad` (DNS -> TCP -> TLS/sertifika; --bind ile tek seferlik bind, parola sorulur, DB'ye yazmaz).
"""

from __future__ import annotations

import hmac
import ssl
import sys
import threading
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import urlparse

from app.config import Settings, get_settings

BAGLANTI_SURESI = 5
YANIT_SURESI = 10
ESZAMANLI_BIND = 3
SIRA_BEKLEME = 2
_bind_sirasi = threading.BoundedSemaphore(ESZAMANLI_BIND)


@dataclass(frozen=True)
class DirectoryUser:
    username: str
    role: str
    is_admin: bool


def _acik(deger: str) -> bool:
    return deger.strip().lower() == "true"


def etkin() -> bool:
    return _acik(get_settings().ad_enabled)


def izinli_alanlar(a: Settings) -> list[str]:
    alan = a.ad_domain.strip().lower()
    liste = [x.strip().lower() for x in a.ad_izinli_alanlar.split(",") if x.strip()]
    return liste + [alan] if alan and alan not in liste else liste


def ayar_dogrula() -> None:
    """AD aciksa ayar tutarli mi; degilse uygulama ACILMAZ (sessizce guvensiz calismaktan iyidir)."""
    a = get_settings()
    if not _acik(a.ad_enabled):
        return
    if not a.ad_server.strip().lower().startswith("ldaps://") or not _acik(a.ad_use_ssl):
        raise RuntimeError("AD_SERVER 'ldaps://' ile baslamali ve AD_USE_SSL=true olmali.")
    if a.ad_alan_kontrolu.strip().lower() not in ("izle", "zorunlu"):
        raise RuntimeError("AD_ALAN_KONTROLU 'izle' veya 'zorunlu' olmalidir.")
    if a.ad_kimlik_kontrolu.strip().lower() not in ("izle", "zorunlu"):
        raise RuntimeError("AD_KIMLIK_KONTROLU 'izle' veya 'zorunlu' olmalidir.")
    if a.ad_izinli_gruplar.strip() and not a.ad_arama_koku.strip():
        raise RuntimeError("AD_IZINLI_GRUPLAR doluysa AD_ARAMA_KOKU zorunludur.")
    _ldap()  # paket eksikse acilista soyle (giriste degil)


def domain_ayristir(girdi: str) -> tuple[str, str]:
    """'ad', 'ad@alan', 'ALAN\\ad' -> (kisa ad, alan). Alan yoksa AD_DOMAIN."""
    girdi = (girdi or "").strip()
    if "@" in girdi:
        kisa, alan = girdi.rsplit("@", 1)
        return kisa.strip(), alan.strip()
    if "\\" in girdi:
        alan, kisa = girdi.split("\\", 1)
        return kisa.strip(), alan.strip()
    return girdi, get_settings().ad_domain.strip()


def _oturum_adi(girdi: str) -> str:
    """Bind adi: yazilan UPN/ALAN\\ad oldugu gibi; kisa ad ise kisa@AD_DOMAIN."""
    girdi = (girdi or "").strip()
    if "@" in girdi or "\\" in girdi:
        return girdi
    alan = get_settings().ad_domain.strip()
    return f"{girdi}@{alan}" if alan else girdi


def _ldap() -> SimpleNamespace:
    """ldap3 tembel yuklenir: AD kapaliyken paket gerekmez (testler bu noktayi taklit eder)."""
    from ldap3 import NONE, SIMPLE, Connection, Server, Tls
    from ldap3.core.exceptions import LDAPSocketOpenError
    from ldap3.utils.conv import escape_filter_chars

    return SimpleNamespace(Server=Server, Connection=Connection, Tls=Tls, SIMPLE=SIMPLE, NONE=NONE, LDAPSocketOpenError=LDAPSocketOpenError, kacis=escape_filter_chars)


def _sunucu(lib: SimpleNamespace, a: Settings):
    if not a.ad_server.strip().lower().startswith("ldaps://") or not _acik(a.ad_use_ssl):
        raise ValueError("Plain LDAP (ldap://) is rejected for security reasons.")
    tls = {"validate": ssl.CERT_REQUIRED, "version": ssl.PROTOCOL_TLSv1_2}
    if a.ad_ca_cert_file.strip():
        tls["ca_certs_file"] = a.ad_ca_cert_file.strip()
    return lib.Server(a.ad_server.strip(), use_ssl=True, tls=lib.Tls(**tls), get_info=lib.NONE, connect_timeout=BAGLANTI_SURESI)


def _gercek_kisa_ad(conn) -> str | None:
    """Bind edilen hesabin sAMAccountName'i (Who Am I, RFC 4532; AD 'u:ALAN\\ad' doner) ya da None (karar verilemez)."""
    try:
        kimlik = conn.extend.standard.who_am_i()
    except Exception:  # noqa: BLE001 - sunucu desteklemiyor / zaman asimi
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


def _grup_uyeligi(lib: SimpleNamespace, conn, kisa_ad: str, a: Settings) -> tuple[bool, str | None]:
    gruplar = [g.strip() for g in a.ad_izinli_gruplar.split(";") if g.strip()]  # DN virgul icerir; eski servisin virgulle bolmesi DN'i parcaliyordu
    if not gruplar:
        return True, None
    kok = a.ad_arama_koku.strip()
    if not kok:
        return False, "ad_grup_yapilandirma"
    for grup in gruplar:
        filtre = f"(&(objectClass=user)(sAMAccountName={lib.kacis(kisa_ad)})(memberOf={lib.kacis(grup)}))"
        if conn.search(kok, filtre, attributes=["distinguishedName"], size_limit=1) and conn.entries:
            return True, None
    return False, "ad_grup_izinsiz"


def dogrula(kullanici: str, parola: str) -> tuple[bool, str]:
    """(dogrulandi mi, sebep kodu). Sebep denetim kaydina gider; kullaniciya hep ayni 'Giris reddedildi' doner."""
    a = get_settings()
    if not _acik(a.ad_enabled):
        return False, "ad_kapali"
    kisa_ad, alan = domain_ayristir(kullanici)
    if not kisa_ad or not parola:
        return False, "eksik_bilgi"
    alan = alan.lower()
    izinli = izinli_alanlar(a)
    alan_disi = bool(alan and izinli and alan not in izinli)
    if alan_disi and a.ad_alan_kontrolu.strip().lower() == "zorunlu":
        return False, f"alan_izinsiz: {alan}"
    if not _bind_sirasi.acquire(timeout=SIRA_BEKLEME):
        return False, "ad_mesgul"
    try:
        lib = _ldap()
        conn = lib.Connection(_sunucu(lib, a), user=_oturum_adi(kullanici), password=parola, authentication=lib.SIMPLE, receive_timeout=YANIT_SURESI)
        if not conn.bind():
            try:
                conn.unbind()  # basarisiz bind soketi acik birakmasin
            except Exception:  # noqa: BLE001, S110 - kapatma hatasi girisi etkilemez
                pass
            return False, "ad_reddetti"
        try:
            gercek = _gercek_kisa_ad(conn)
            grup_ok, grup_sebep = _grup_uyeligi(lib, conn, kisa_ad, a)
        finally:
            conn.unbind()
        if gercek and gercek != kisa_ad.lower() and a.ad_kimlik_kontrolu.strip().lower() == "zorunlu":
            return False, f"ad_kimlik_uyusmuyor: {gercek}"
        if not grup_ok:
            return False, grup_sebep or "ad_grup_izinsiz"
        if alan_disi:
            return False, f"ad_onayladi_alan_disi:{alan}"
        return True, "ad_onayladi" if not gercek or gercek == kisa_ad.lower() else f"ad_onayladi_kimlik_farkli:{gercek}"
    except Exception as exc:  # noqa: BLE001 - ag/sertifika/kutuphane: giris reddedilir, sebep kaydedilir
        return False, f"ad_ulasilamadi: {type(exc).__name__}"
    finally:
        _bind_sirasi.release()


class Directory:
    def configured(self) -> bool:
        """AD_ENABLED=true ve AD_SERVER + AD_DOMAIN dolu mu (yalniz doluluk; baglanti durumu ekrani)."""
        a = get_settings()
        return bool(_acik(a.ad_enabled) and a.ad_server.strip() and a.ad_domain.strip())

    def yerel(self, username: str, password: str) -> DirectoryUser | None:
        """Yalniz dev/test'te panel-yerel kullanici (TAMLIFE_LOCAL_*); uretimde her zaman None."""
        a = get_settings()
        if a.env not in {"dev", "test"} or not a.local_user or not a.local_password:
            return None
        user_ok = hmac.compare_digest(username.encode(), a.local_user.encode())
        pass_ok = hmac.compare_digest(password.encode(), a.local_password.encode())
        if not (user_ok and pass_ok):
            return None
        role = a.local_role or "TeamMember"
        return DirectoryUser(username=username, role=role, is_admin=role == "admin")


directory = Directory()


# --- tani (offline sunucuda: python -m app.ad [--bind]) -------------------------------------------
def _yaz(durum: str, baslik: str, ayrinti: str = "") -> None:
    print({"ok": "  [OK]   ", "hata": "  [HATA] ", "bilgi": "  [ ]    "}[durum] + baslik)
    for satir in ayrinti.splitlines():
        print("           " + satir)


def tani(bind: bool = False) -> int:
    """DNS -> TCP -> TLS/sertifika -> (istege bagli) bind; ilk kirilan halkayi adiyla soyler. 0 = saglam."""
    import getpass
    import socket

    from app.config import env_dosyasi_yukle

    env_dosyasi_yukle()
    try:
        ayar_dogrula()
    except (RuntimeError, ImportError) as exc:
        _yaz("hata", "Ayar gecersiz", str(exc))
        return 2
    a = get_settings()
    if not _acik(a.ad_enabled):
        _yaz("hata", "AD_ENABLED=true degil", "backend/.env icindeki AD_* satirlarini kontrol edin.")
        return 2
    adres = urlparse(a.ad_server.strip())
    host, port = adres.hostname or "", adres.port or 636
    try:
        _yaz("ok", f"DNS: {host}", ", ".join(sorted({x[4][0] for x in socket.getaddrinfo(host, None)})))
        socket.create_connection((host, port), timeout=BAGLANTI_SURESI).close()
        _yaz("ok", f"TCP: {host}:{port}")
    except OSError as exc:
        _yaz("hata", f"Ag: {host}:{port}", f"{type(exc).__name__}: {exc}\nTest-NetConnection {host} -Port {port}")
        return 2
    baglam = ssl.create_default_context()
    if a.ad_ca_cert_file.strip():
        try:
            baglam.load_verify_locations(a.ad_ca_cert_file.strip())
        except OSError as exc:
            _yaz("hata", "CA dosyasi okunamadi", f"{a.ad_ca_cert_file}\n{exc}")
            return 2
    try:
        with socket.create_connection((host, port), timeout=BAGLANTI_SURESI) as ham, baglam.wrap_socket(ham, server_hostname=host) as tls:
            sert = tls.getpeercert() or {}
            konu = dict(x[0] for x in sert.get("subject", ()))
            veren = dict(x[0] for x in sert.get("issuer", ()))
            _yaz("ok", "TLS ve sertifika dogrulandi", f"protokol: {tls.version()}\nkonu: {konu.get('commonName', '?')}\nveren: {veren.get('commonName', '?')}\nbitis: {sert.get('notAfter', '?')}")
    except ssl.SSLCertVerificationError as exc:
        _yaz("hata", "SERTIFIKA DOGRULANAMADI", f"{exc}\nKurum ara+kok CA zincirini .pem olarak AD_CA_CERT_FILE ile gosterin.")
        return 2
    except OSError as exc:
        _yaz("hata", "TLS el sikisma basarisiz", f"{type(exc).__name__}: {exc}")
        return 2
    if not bind:
        print("\nAg ve sertifika saglam. Bind testi icin: python -m app.ad --bind")
        return 0
    kullanici = input("AD kullanici adi (kisa ad / ad@alan / ALAN\\ad): ").strip()
    parola = getpass.getpass("AD parolasi (gizli): ")
    tamam, sebep = dogrula(kullanici, parola)
    parola = ""
    _yaz("ok" if tamam else "hata", f"Bind: {_oturum_adi(kullanici)}", sebep)
    return 0 if tamam else 1


if __name__ == "__main__":
    sys.exit(tani(bind="--bind" in sys.argv[1:]))
