# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Sutun profili: yol ustunde (satirlar bellekte biriktirilmez) doluluk, farkli deger, baskin tip, en sik degerler."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence

from app.tampon.eslestirme import sayi

FARKLI_AZAMI = 5_000  # sutun basina izlenen farkli deger (bellek siniri)
_TARIH = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$|^\d{2}[./]\d{2}[./]\d{4}([ ]\d{2}:\d{2}(:\d{2})?)?$")
_TAM = re.compile(r"^[+-]?\d+$")


def tip_tahmin(deger: object) -> str:
    metin = str(deger).strip()
    if _TAM.match(metin):
        return "tam sayı"
    if _TARIH.match(metin):
        return "tarih"
    if sayi(metin) is not None and re.search(r"\d", metin) and not re.search(r"[A-Za-z]", metin):
        return "sayı"
    return "metin"


class Profil:
    def __init__(self, basliklar: Sequence[str]) -> None:
        self.basliklar = list(basliklar)
        n = len(self.basliklar)
        self.dolu = [0] * n
        self.sayac: list[Counter[str]] = [Counter() for _ in range(n)]
        self.tip: list[Counter[str]] = [Counter() for _ in range(n)]
        self.tasti = [False] * n

    def ekle(self, satirlar: Iterable[Sequence[object]]) -> None:
        for satir in satirlar:
            for i, deger in enumerate(satir[: len(self.basliklar)]):
                if deger is None or deger == "":
                    continue
                self.dolu[i] += 1
                anahtar = str(deger)
                self.tip[i][tip_tahmin(anahtar)] += 1
                sayac = self.sayac[i]
                if anahtar in sayac:
                    sayac[anahtar] += 1
                elif len(sayac) < FARKLI_AZAMI:
                    sayac[anahtar] = 1
                else:
                    self.tasti[i] = True

    def sonuc(self, ornek: int = 5) -> list[dict[str, object]]:
        return [
            {
                "sutun": ad,
                "dolu": self.dolu[i],
                "farkli": f"{FARKLI_AZAMI}+" if self.tasti[i] else len(self.sayac[i]),
                "tip": self.tip[i].most_common(1)[0][0] if self.tip[i] else "-",
                "en_sik": [[deger, adet] for deger, adet in self.sayac[i].most_common(ornek)],
            }
            for i, ad in enumerate(self.basliklar)
        ]
