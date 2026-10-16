"""SQLite kilit backtest: panel + isci (ReportDB) + denetim yazicisi ayni dosyaya yazar. WAL ve busy_timeout olmadan
uzun yazma 5 sn sonra 'database is locked' (500) verir, okuma da EXCLUSIVE kilitte bekler."""

from __future__ import annotations

import sqlite3
import threading
import time

from sqlalchemy import func, select

from app.db import engine, oturum
from app.models import AuditEvent
from app.ortak import simdi
from tests.conftest import login_ok


def _dosya() -> str:
    return str(engine().url.database)


def _kilitle(sure: float, kip: str = "IMMEDIATE") -> threading.Thread:
    hazir = threading.Event()

    def tut() -> None:
        b = sqlite3.connect(_dosya(), timeout=0, isolation_level=None)
        b.execute(f"BEGIN {kip}")
        b.execute("INSERT INTO audit_event (at, actor, action, outcome, module_key, detail) VALUES ('2026-01-01', 'isci', 'kilit', 'allow', '', '')")
        hazir.set()
        time.sleep(sure)
        b.execute("COMMIT")
        b.close()

    t = threading.Thread(target=tut, daemon=True)
    t.start()
    assert hazir.wait(5)
    return t


def test_panel_dosyasi_wal_ve_bekleme_suresiyle_acilir(client):
    with engine().connect() as b:
        assert b.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert b.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000
        assert b.exec_driver_sql("PRAGMA synchronous").scalar() == 1


def test_yazma_kilidi_6_sn_surse_de_istek_bekler_ve_basarir(client):
    hdr = login_ok(client)
    t = _kilitle(6.0)
    bas = time.monotonic()
    r = client.put("/api/v1/session/profile", json={"phone": "+90 532 000 00 00"}, headers=hdr)
    gecen = time.monotonic() - bas
    t.join()
    assert r.status_code == 200, r.text
    assert gecen >= 5.0


def test_exclusive_yazma_surerken_okuma_beklemez(client):
    login_ok(client)
    client.get("/api/v1/musteri")
    t = _kilitle(3.0, "EXCLUSIVE")
    bas = time.monotonic()
    r = client.get("/api/v1/musteri")
    gecen = time.monotonic() - bas
    t.join()
    assert r.status_code == 200 and gecen < 1.5, gecen


def test_eszamanli_yazicilar_kayip_ve_hata_uretmez(client):
    hatalar: list[BaseException] = []

    def yaz(n: int) -> None:
        try:
            for i in range(25):
                with oturum() as db:
                    db.add(AuditEvent(at=simdi(), actor=f"t{n}", action="yuk", outcome="allow", detail=str(i)))
                    db.commit()
        except BaseException as h:  # noqa: BLE001
            hatalar.append(h)

    iplikler = [threading.Thread(target=yaz, args=(n,)) for n in range(8)]
    for t in iplikler:
        t.start()
    for t in iplikler:
        t.join()
    assert not hatalar, hatalar[:1]
    with oturum() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "yuk")) == 200
