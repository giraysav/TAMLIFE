"""Yaris kosullari (race condition): ayni kayda eszamanli yazma. Barrier ile tum is parcaciklari ayni anda baslar.

Yama 54 oncesi: ayni gune eszamanli ilk takvim yazmasi (iki sekme / cift tiklama) UNIQUE(day) ile 500 veriyordu (yuk testinde
100 eszamanlida gozlendi); 16 is parcacigiyla ilk iki test her kosuda kiriliyordu. Cozum: db.yazma_kilidi (BEGIN IMMEDIATE).
"""

from __future__ import annotations

import threading

from sqlalchemy import func, select

from app.db import kullanici_oturumu
from app.models import CalendarDay
from app.takvim import servis
from tests.conftest import login_ok

ISCI = 16


def _ayni_anda(is_) -> list[BaseException]:
    engel, hatalar = threading.Barrier(ISCI), []

    def kos(n: int) -> None:
        engel.wait()
        try:
            is_(n)
        except BaseException as h:  # noqa: BLE001
            hatalar.append(h)

    iplikler = [threading.Thread(target=kos, args=(n,)) for n in range(ISCI)]
    for t in iplikler:
        t.start()
    for t in iplikler:
        t.join()
    return hatalar


def test_ayni_gune_eszamanli_ilk_yazma_tek_satir_hatasiz(client):
    login_ok(client)
    for gun in ("2026-04-01", "2026-04-02", "2026-04-03"):  # her tur yeni gun: hep "satir yok" yarisi
        hatalar = _ayni_anda(lambda n, g=gun: servis.gun_kaydet("admin", {"tarih": g, "durum": "calisiyor", "online": n + 1, "yuzyuze": 0}))
        assert not hatalar, hatalar[:1]
    with kullanici_oturumu("admin") as k:
        assert k.scalar(select(func.count()).select_from(CalendarDay)) == 3


def test_toplu_atama_ile_tek_gun_yazmasi_yarisi(client):
    login_ok(client)

    def is_(n: int) -> None:
        if n % 2:
            servis.toplu_kaydet("admin", {"baslangic": "2026-05-04", "bitis": "2026-05-08", "durum": "yillik_izin"})
        else:
            servis.gun_kaydet("admin", {"tarih": "2026-05-06", "durum": "calisiyor", "online": 2, "yuzyuze": 0})

    assert not _ayni_anda(is_)
    with kullanici_oturumu("admin") as k:
        assert k.scalar(select(func.count()).select_from(CalendarDay).where(CalendarDay.day == __import__("datetime").date(2026, 5, 6))) == 1


def test_profil_eszamanli_yazma_kaybolmaz_ve_hata_vermez(client):
    hdr = login_ok(client)
    r = _ayni_anda(lambda n: client.put("/api/v1/session/profile", json={"phone": f"+90 532 000 00 {n:02d}"}, headers=hdr).raise_for_status())
    assert not r, r[:1]
    assert client.get("/api/v1/session/me").json()["data"]["profile"]["phone"].startswith("+90 532 000 00")
