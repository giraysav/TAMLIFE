"""Sunucu metinlerinin dili: arayuz her istekte 'X-Dil: tr|en' basligini gonderir; yoksa Turkce.

Is katmani dili parametre olarak tasimaz: m("Türkçe", "English") istegin diline gore birini dondurur. Dil, istek basinda
ContextVar'a yazilir (DilAraKatmani); senkron uclar threadpool'da calissa da baglam kopyalandigi icin ayni deger okunur.
Musteri verisi (unvan, kisi adi, yuklenen dosyanin hucreleri) cevrilmez; yalniz panelin kendi metinleri.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

DILLER = ("tr", "en")
BASLIK = b"x-dil"
_dil: ContextVar[str] = ContextVar("tamlife_dil", default="tr")


def secili() -> str:
    return _dil.get()


def ingilizce() -> bool:
    return _dil.get() == "en"


def m(tr: str, en: str) -> str:
    """Istegin dilindeki metin."""
    return en if _dil.get() == "en" else tr


def ayarla(dil: str) -> Any:
    """Testler ve isci surecler icin: dili elle ayarlar; donen jeton ContextVar.reset ile geri alinir."""
    return _dil.set(dil if dil in DILLER else "tr")


def geri_al(jeton: Any) -> None:
    _dil.reset(jeton)


class DilAraKatmani:
    """Saf ASGI ara katmani: 'X-Dil' basligini okur (yalniz tr/en kabul edilir)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        deger = next((v for k, v in scope.get("headers") or [] if k == BASLIK), b"tr").decode("latin-1").strip().lower()
        jeton = _dil.set(deger if deger in DILLER else "tr")
        try:
            await self.app(scope, receive, send)
        finally:
            _dil.reset(jeton)
