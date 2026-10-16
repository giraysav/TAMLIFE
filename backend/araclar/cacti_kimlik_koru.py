"""Yerel Cacti kimlik bakimi. Sir ve sifreli degerler ciktiya yazilmaz."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rapor.cacti_kimlik import KULLANICI_ANAHTARI, PAROLA_ANAHTARI, coz, koru

ACIK_ANAHTARLAR = ("TAMLIFE_CACTI_USERNAME", "TAMLIFE_CACTI_PASSWORD")


def _alanlar(icerik: str) -> dict[str, str]:
    sonuc = {}
    for satir in icerik.splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        anahtar, deger = (s.strip() for s in satir.split("=", 1))
        if len(deger) >= 2 and deger[0] == deger[-1] and deger[0] in "\"'":
            deger = deger[1:-1]
        sonuc[anahtar.upper()] = deger
    return sonuc


def _ayni_acl(kaynak: Path, hedef: Path) -> None:
    """Temp dosyasina daha veri yazmadan mevcut env DACL'sini uygular."""
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.GetFileSecurityW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
    adv.GetFileSecurityW.restype = ctypes.c_int
    adv.SetFileSecurityW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p]
    adv.SetFileSecurityW.restype = ctypes.c_int
    boyut = ctypes.c_uint32()
    adv.GetFileSecurityW(str(kaynak), 4, None, 0, ctypes.byref(boyut))
    if not boyut.value:
        raise OSError("ACL")
    buf = ctypes.create_string_buffer(boyut.value)
    if not adv.GetFileSecurityW(str(kaynak), 4, buf, boyut.value, ctypes.byref(boyut)):
        raise OSError("ACL")
    if not adv.SetFileSecurityW(str(hedef), 4 | 0x80000000, buf):
        raise OSError("ACL")


def kaydet(yol: Path, sifreli: dict[str, str]) -> None:
    kullanici, parola = coz(sifreli[KULLANICI_ANAHTARI]), coz(sifreli[PAROLA_ANAHTARI])
    if not kullanici.strip() or not parola.strip():
        raise ValueError("Kimlik bos")
    ilk = yol.read_bytes()
    metin = ilk.decode("utf-8-sig")
    sonlar = "\r\n" if "\r\n" in metin else "\n"
    degerler = {**{k: "" for k in ACIK_ANAHTARLAR}, **sifreli}
    satirlar, gorulen = [], set()
    for satir in metin.splitlines(keepends=True):
        temiz = satir.strip()
        ad = temiz.split("=", 1)[0].strip().upper() if "=" in temiz and not temiz.startswith("#") else ""
        if ad in degerler:
            # Tum yinelenen acik alanlar da bosaltilir.
            bitis = "\r\n" if satir.endswith("\r\n") else "\n" if satir.endswith("\n") else ""
            satirlar.append(ad + "=" + degerler[ad] + bitis)
            gorulen.add(ad)
        else:
            satirlar.append(satir)
    yeni = "".join(satirlar)
    for ad, deger in degerler.items():
        if ad not in gorulen:
            if yeni and not yeni.endswith("\n"):
                yeni += sonlar
            yeni += ad + "=" + deger + sonlar
    kontrol = _alanlar(yeni)
    if any(kontrol.get(k) for k in ACIK_ANAHTARLAR):
        raise ValueError("Acik alan")
    if coz(kontrol[KULLANICI_ANAHTARI]) != kullanici or coz(kontrol[PAROLA_ANAHTARI]) != parola:
        raise ValueError("Dogrulama")
    veri = (b"\xef\xbb\xbf" if ilk.startswith(b"\xef\xbb\xbf") else b"") + yeni.encode("utf-8")
    fd, gecici_ad = tempfile.mkstemp(prefix=".env.cacti-", suffix=".tmp", dir=yol.parent)
    gecici = Path(gecici_ad)
    try:
        os.close(fd)
        _ayni_acl(yol, gecici)
        with gecici.open("wb") as dosya:
            dosya.write(veri)
            dosya.flush()
            os.fsync(dosya.fileno())
        if yol.read_bytes() != ilk:
            raise ValueError("Dosya eszamanli degisti; yeniden deneyin")
        os.replace(gecici, yol)
    finally:
        gecici.unlink(missing_ok=True)


def env_gecir(yol: Path) -> None:
    degerler = _alanlar(yol.read_text(encoding="utf-8-sig"))
    kullanici, parola = (degerler.get(k, "") for k in ACIK_ANAHTARLAR)
    if kullanici and parola:
        sifreli = {KULLANICI_ANAHTARI: koru(kullanici), PAROLA_ANAHTARI: koru(parola)}
    elif degerler.get(KULLANICI_ANAHTARI) and degerler.get(PAROLA_ANAHTARI) and not kullanici and not parola:
        sifreli = {k: degerler[k] for k in (KULLANICI_ANAHTARI, PAROLA_ANAHTARI)}
    else:
        raise ValueError("Eksik kimlik; yerel kimlik penceresini kullanin")
    kaydet(yol, sifreli)


def main() -> int:
    try:
        if os.name != "nt":
            raise ValueError("Windows gerekli")
        kimlik = subprocess.check_output(["whoami"], text=True, creationflags=subprocess.CREATE_NO_WINDOW).strip()
        if kimlik.casefold() != "turkcell\\tamlifeadlog":
            raise ValueError("Calisma hesabi farkli")
        yol = Path(__file__).resolve().parents[1] / ".env"
        if sys.argv[1:] == ["--kontrol"]:
            degerler = _alanlar(yol.read_text(encoding="utf-8-sig"))
            if any(degerler.get(k) for k in ACIK_ANAHTARLAR):
                raise ValueError("Acik kimlik var")
            for ad in (KULLANICI_ANAHTARI, PAROLA_ANAHTARI):
                coz(degerler[ad])
            print("Cacti kimlik kontrolu: acik metin yok; DPAPI cozum basarili.")
            return 0
        if sys.argv[1:] == ["--env-gecir"]:
            env_gecir(yol)
        elif sys.argv[1:] == ["--sifreli-girdi"]:
            sifreli = json.loads(sys.stdin.read(200000))
            if not isinstance(sifreli, dict) or set(sifreli) != {KULLANICI_ANAHTARI, PAROLA_ANAHTARI}:
                raise ValueError("Girdi")
            kaydet(yol, sifreli)
        else:
            raise ValueError("Secenek")
        print("Cacti kimligi DPAPI CurrentUser ile korundu; acik metin alanlar bos.")
        return 0
    except Exception:  # noqa: BLE001 -- CLI must never disclose secret input in a traceback.
        # No exception details: they must not disclose input, env or ciphertext.
        print(
            "Cacti kimligi korunamadi. Hesabi, profil/DPAPI ve dosya erisimini kontrol edin; kimlik penceresini yeniden kullanin.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
