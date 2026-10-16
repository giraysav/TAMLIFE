"""Cacti kimligi: Windows DPAPI CurrentUser; acik metin .env destegi yok."""

from __future__ import annotations

import base64
import ctypes
import os

from app.ortak import UygulamaHatasi

KULLANICI_ANAHTARI = "TAMLIFE_CACTI_USERNAME_DPAPI"
PAROLA_ANAHTARI = "TAMLIFE_CACTI_PASSWORD_DPAPI"


class CactiKimlikHata(UygulamaHatasi):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(veri: bytes, *, ac: bool) -> bytes:
    if os.name != "nt":
        raise CactiKimlikHata(503, "Cacti kimliği Windows DPAPI gerektirir.")
    if not veri or len(veri) > 65536:
        raise CactiKimlikHata(503, "Cacti şifreli kimlik verisi geçersiz.")
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    blob_ptr = ctypes.POINTER(_Blob)
    crypt.CryptProtectData.argtypes = [blob_ptr, ctypes.c_wchar_p, blob_ptr, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, blob_ptr]
    crypt.CryptProtectData.restype = ctypes.c_int
    crypt.CryptUnprotectData.argtypes = [
        blob_ptr,
        ctypes.POINTER(ctypes.c_wchar_p),
        blob_ptr,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        blob_ptr,
    ]
    crypt.CryptUnprotectData.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    tampon = ctypes.create_string_buffer(veri)
    girdi = _Blob(len(veri), ctypes.cast(tampon, ctypes.POINTER(ctypes.c_ubyte)))
    cikti = _Blob()
    try:
        if ac:
            tamam = crypt.CryptUnprotectData(ctypes.byref(girdi), None, None, None, None, 1, ctypes.byref(cikti))
        else:
            # CRYPTPROTECT_UI_FORBIDDEN=1; LOCAL_MACHINE deliberately not used.
            tamam = crypt.CryptProtectData(ctypes.byref(girdi), "TAMLIFE Cacti", None, None, None, 1, ctypes.byref(cikti))
        if not tamam:
            raise CactiKimlikHata(
                503, "Cacti kimliği DPAPI ile açılamadı veya korunamadı. Servis hesabını ve Windows profilini kontrol edin."
            )
        return ctypes.string_at(cikti.pbData, cikti.cbData)
    finally:
        ctypes.memset(tampon, 0, ctypes.sizeof(tampon))
        if cikti.pbData:
            ctypes.memset(cikti.pbData, 0, cikti.cbData)
            kernel.LocalFree(cikti.pbData)


def koru(metin: str) -> str:
    if not metin or not metin.strip() or len(metin) > 16000:
        raise CactiKimlikHata(400, "Cacti kullanıcı adı veya parolası boş ya da geçersiz.")
    return base64.b64encode(_dpapi(metin.encode("utf-8"), ac=False)).decode("ascii")


def coz(sifreli: str) -> str:
    try:
        if len(sifreli) > 90000:
            raise ValueError
        veri = base64.b64decode(sifreli, validate=True)
        sonuc = _dpapi(veri, ac=True).decode("utf-8")
        if not sonuc or not sonuc.strip():
            raise ValueError
        return sonuc
    except (ValueError, UnicodeError):
        raise CactiKimlikHata(503, "Cacti şifreli kimlik verisi geçersiz.") from None


def hazir() -> bool:
    return bool(os.environ.get(KULLANICI_ANAHTARI, "").strip() and os.environ.get(PAROLA_ANAHTARI, "").strip())


def oku() -> tuple[str, str]:
    if not hazir():
        raise CactiKimlikHata(503, "Cacti korumalı LDAP hesabı tanımlanmamış. Yerel kimlik kurulum aracını çalıştırın.")
    # No plaintext fallback: a damaged protected value must not downgrade storage.
    return coz(os.environ[KULLANICI_ANAHTARI]), coz(os.environ[PAROLA_ANAHTARI])
