"""Uygulama dosya gunlugu: donen dosya (5 MB x 5), istegi BEKLETMEZ (QueueHandler + QueueListener).

Hata aninda 'ne oldu' sorusunun cevabi konsol penceresinde kalmasin: ariza kayit numarasiyla yigin izi buradan bulunur.
Kurulamazsa uygulama durmaz (konsol gunlugu surer).
"""

from __future__ import annotations

import atexit
import logging
import logging.handlers
import queue
import re
from pathlib import Path

from app.config import get_settings
from app.ortak import UygulamaHatasi

DOSYA = "uygulama.log"
BICIM = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
KUYRUK_BAYT = 512 * 1024  # her okumada dosyanin yalniz sonu
_KAYIT = re.compile(r"^[0-9a-f]{8}$")
_YENI_SATIR = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
_dinleyici: logging.handlers.QueueListener | None = None


def _durdur() -> None:
    """Cikista kuyrugu bosaltir; dinleyici zaten durdurulmussa (testler) sessizce gecer."""
    dinleyici = _dinleyici
    if dinleyici is not None and getattr(dinleyici, "_thread", None) is not None:
        dinleyici.stop()


def klasor() -> Path:
    ayar = get_settings().log_dir.strip()
    if ayar:
        return Path(ayar)
    return Path(__file__).resolve().parents[2] / "var" / "logs"


def kur() -> bool:
    """'tamlife' gunlukcusune (bir kez) kuyruklu dosya yazici baglar. Donus: kuruldu mu."""
    global _dinleyici
    kok = logging.getLogger("tamlife")
    if getattr(kok, "_tamlife_dosya", False):
        return True
    try:
        yer = klasor()
        yer.mkdir(parents=True, exist_ok=True)
        dosya = logging.handlers.RotatingFileHandler(yer / DOSYA, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8", delay=True)
        dosya.setFormatter(logging.Formatter(BICIM))
        kuyruk: queue.SimpleQueue = queue.SimpleQueue()
        _dinleyici = logging.handlers.QueueListener(kuyruk, dosya, respect_handler_level=True)
        _dinleyici.start()
        atexit.register(_durdur)
        kok.addHandler(logging.handlers.QueueHandler(kuyruk))
        kok.setLevel(logging.INFO)
        kok._tamlife_dosya = True  # type: ignore[attr-defined]
        return True
    except Exception:
        logging.getLogger(__name__).warning("dosya gunlugu kurulamadi; yalniz konsola yazilacak", exc_info=True)
        return False


def oku(kayit: str = "", satir: int = 200) -> dict[str, object]:
    """Gunlugun sonu. kayit (8 hane hex) verilirse o ariza kaydinin satirlari + yigin izi; yoksa son satirlar."""
    kayit = kayit.strip().lower()
    if kayit and not _KAYIT.match(kayit):
        raise UygulamaHatasi(400, "Kayıt numarası 8 haneli onaltılık olmalı.")
    satir = max(10, min(int(satir), 1000))
    yol = klasor() / DOSYA
    if not yol.is_file():
        return {"dosya": DOSYA, "var": False, "satirlar": []}
    with yol.open("rb") as f:
        f.seek(0, 2)
        boyut = f.tell()
        f.seek(max(0, boyut - KUYRUK_BAYT))
        metin = f.read().decode("utf-8", errors="replace")
    satirlar = metin.splitlines()
    if boyut > KUYRUK_BAYT and satirlar:
        satirlar = satirlar[1:]  # kesilen ilk satir
    if kayit:
        secili: list[str] = []
        icinde = False
        for s in satirlar:
            if _YENI_SATIR.match(s):
                icinde = f"[kayit {kayit}]" in s
            if icinde:
                secili.append(s)
        satirlar = secili
    return {"dosya": DOSYA, "var": True, "satirlar": satirlar[-satir:]}
