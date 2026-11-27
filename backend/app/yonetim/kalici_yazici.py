# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Denetim olaylarinin KALICI yazimi: istegi BEKLETMEZ, veritabani kapaliyken girisi/islemi dusurmez.

Neden kuyruk: olayi istek icinde senkron yazmak, veritabani erisilemezken her girisi baglanti zaman asimi kadar bekletir
(testte gozlendi). Burada olay once bellek kuyruguna girer (hep, aninda); arka plan iplik toplu yazar. Yazilamazsa olaylar
kuyrukta kalir (en fazla AZAMI) ve BEKLEME_SN boyunca yeniden denenmez (devre kesici). Okuma yolu (Yonetim > Gunlukler)
once bosalt(zorla=True) cagirir: yonetici her zaman son olaylari gorur.

Test ortami (env=test): iplik yok; olay cagiran iplikte hemen yazilmaya calisilir (deterministik).
"""

from __future__ import annotations

import atexit
import logging
import threading
import time
from collections import deque
from typing import Any

from app.config import get_settings
from app.models import AuditEvent
from app.ortak import simdi

_log = logging.getLogger("tamlife.denetim")


class KaliciYazici:
    AZAMI = 5000  # bellekte bekleyebilecek olay (asilirsa en eskiler dusurulur)
    ARALIK_SN = 1.0
    BEKLEME_SN = 30.0

    def __init__(self) -> None:
        self._bekleyen: deque[dict[str, Any]] = deque()
        self._liste_kilidi = threading.Lock()
        self._yazma_kilidi = threading.Lock()
        self._iplik: threading.Thread | None = None
        self._sonraki = 0.0
        self._uyari_verildi = False
        self.dusen = 0

    def __call__(self, satir: dict[str, str]) -> None:
        olay = {**satir, "_at": simdi()}
        with self._liste_kilidi:
            self._bekleyen.append(olay)
            while len(self._bekleyen) > self.AZAMI:
                self._bekleyen.popleft()
                self.dusen += 1
        if get_settings().env == "test":
            self.bosalt()
        else:
            self._iplik_baslat()

    def bekleyen(self) -> int:
        with self._liste_kilidi:
            return len(self._bekleyen)

    def bosalt(self, zorla: bool = False) -> int:
        """Bekleyenleri tek islemde yazar. zorla: devre kesiciyi yok say. Donus: yazilan adet (0 = yazilamadi/bos)."""
        with self._yazma_kilidi:
            if not zorla and time.monotonic() < self._sonraki:
                return 0
            with self._liste_kilidi:
                toplu = list(self._bekleyen)
                self._bekleyen.clear()
            if not toplu:
                return 0
            try:
                from app.db import oturum

                with oturum() as db:
                    db.add_all(AuditEvent(at=o["_at"], **{k: v for k, v in o.items() if k != "_at"}) for o in toplu)
                    db.commit()
            except Exception:  # noqa: BLE001 - DB kapali/kilitli: olaylar kuyrukta kalir, istek etkilenmez
                with self._liste_kilidi:
                    self._bekleyen.extendleft(reversed(toplu))
                    while len(self._bekleyen) > self.AZAMI:
                        self._bekleyen.popleft()
                        self.dusen += 1
                self._sonraki = time.monotonic() + self.BEKLEME_SN
                if not self._uyari_verildi:
                    self._uyari_verildi = True
                    _log.warning("denetim olaylari kalici yazilamadi; %s sn sonra yeniden denenecek", int(self.BEKLEME_SN), exc_info=True)
                return 0
            self._uyari_verildi = False
            return len(toplu)

    def _iplik_baslat(self) -> None:
        if self._iplik is not None and self._iplik.is_alive():
            return
        with self._liste_kilidi:
            if self._iplik is not None and self._iplik.is_alive():
                return
            self._iplik = threading.Thread(target=self._dongu, name="denetim-yazici", daemon=True)
            self._iplik.start()

    def _dongu(self) -> None:
        while True:
            time.sleep(self.ARALIK_SN)
            try:
                self.bosalt()
            except Exception:  # noqa: BLE001 - iplik hicbir kosulda olmemeli
                _log.warning("denetim yazici dongusu hata verdi", exc_info=True)

    def sifirla(self) -> None:
        """Yalniz testler: bekleyenleri at, devre kesiciyi sifirla (testler arasi sizinti olmasin)."""
        with self._liste_kilidi:
            self._bekleyen.clear()
        self._sonraki, self._uyari_verildi, self.dusen = 0.0, False, 0


yazici = KaliciYazici()
atexit.register(lambda: yazici.bosalt(zorla=True))
