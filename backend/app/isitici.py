"""Onbellek isiticisi (2026-10-20 kullanici: "panelde asiri yavaslik var").

Agir ozetlerin ilk hesabi (Onedesk top10 ~1,5 sn, TEMIP eslesme gruplari ~5 sn, tanitimin depo olcumu ~4 sn) ilk ziyaretciyi bekletiyordu.
Panel acilinca ve ARALIK_SN'de bir arka planda cagrilir; her biri kendi onbellegini kullanir (veri degismediyse hesap yapmaz, ucuz).
Test ortaminda calismaz. Hata isiticiyi durdurmaz (gunluge yazilir).
"""

from __future__ import annotations

import logging
import threading

_log = logging.getLogger("tamlife.isitici")
ARALIK_SN = 60
_dur = threading.Event()


def tur() -> None:
    from app.db import oturum
    from app.onedesk.servis import top10
    from app.session import Principal
    from app.sunum import tanitim
    from app.tampon import temip_kayit

    with oturum() as db:
        top10(db, Principal("isitici", "TeamMngr", False))
        temip_kayit._gruplar(db)
        tanitim.depo_olcumu()
        db.rollback()


def _dongu() -> None:
    while not _dur.is_set():
        try:
            tur()
        except Exception:  # noqa: BLE001 - isitici panelin calismasini etkilemez
            _log.warning("onbellek isitma turu basarisiz", exc_info=True)
        _dur.wait(ARALIK_SN)


def baslat() -> None:
    _dur.clear()
    threading.Thread(target=_dongu, name="tamlife-isitici", daemon=True).start()


def durdur() -> None:
    _dur.set()
