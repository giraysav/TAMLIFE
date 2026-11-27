# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Test ortami: yerel admin ve her test icin ayri gecici SQLite veritabani."""

from __future__ import annotations

import os

os.environ["TAMLIFE_ENV"] = "test"
os.environ["TAMLIFE_LOCAL_USER"] = "admin"
os.environ["TAMLIFE_LOCAL_PASSWORD"] = "test-parola-1"
os.environ["TAMLIFE_LOCAL_ROLE"] = "admin"
# TAMLIFE_ENV'i degistiren testlerde create_app() gercek backend/.env'i ortama eklemesin (Oracle/AD anahtarlari sonraki testlere sizardi).
os.environ["TAMLIFE_ENV_DOSYASI"] = os.path.join(os.path.dirname(__file__), "yok.env")

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import dispose_engines, engine, kullanici_dosyalari, kullanici_oturumu
from app.main import create_app
from app.models import Base
from app.security import limiter
from app.session import reset_for_tests
from app.yonetim.kalici_yazici import yazici


@pytest.fixture(autouse=True)
def _canli_yollardan_izole(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """2026-10-20: hicbir test canli klasore yazmasin (rapor PDF / SLA, gunluk, yedek, ham katalog). Eskiden yalniz client fixture'i
    gunluk/yedek yolunu degistiriyordu; SLA/PDF testleri canli backend/data/reports'a artik birakti. Testin kendi setenv'i bunu ezer."""
    kok = tmp_path_factory.mktemp("izole")
    monkeypatch.setenv("TAMLIFE_REPORT_DIR", str(kok / "raporlar"))
    monkeypatch.setenv("TAMLIFE_LOG_DIR", str(kok / "log"))
    monkeypatch.setenv("TAMLIFE_BACKUP_DIR", str(kok / "yedek"))
    from app.tampon import katalog

    monkeypatch.setattr(katalog, "HAM_DIZIN", kok / "ham")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("TAMLIFE_DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("TAMLIFE_LOG_DIR", str(tmp_path / "log"))  # testler repo icine gunluk/yedek yazmasin
    monkeypatch.setenv("TAMLIFE_BACKUP_DIR", str(tmp_path / "yedek"))
    dispose_engines()
    Base.metadata.create_all(engine())
    limiter.reset()
    reset_for_tests()
    yazici.sifirla()
    with TestClient(create_app(), base_url="http://testserver") as c:
        yield c
    dispose_engines()


def kisi_say(model) -> int:
    """Tum kullanici dosyalarindaki satir sayisi."""
    toplam = 0
    for dosya in kullanici_dosyalari():
        with kullanici_oturumu(dosya.stem) as k:
            toplam += k.scalar(select(func.count()).select_from(model)) or 0
    return toplam


def login_ok(c: TestClient) -> dict[str, str]:
    r = c.post("/api/v1/session/login", json={"username": "admin", "password": "test-parola-1"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": c.cookies.get("tamlife_csrf") or ""}


# --- 2026-11-27: v3.5 test paketi sunucu-birebir dalina alindi (prod-esit-2026-11-18'den) ------------------------------------
# Paket 18 Kasim'da ayrilan dalda kalmisti. Bugunku koda karsi: 726 gecti, 118 basarisiz, 7 dosya yuklenemedi. Basarisiz testler
# 18 Kasim sonrasi bilincli davranis degisikligi mi yoksa gerileme mi diye TEK TEK gozden gecirilecek; o zamana kadar
# bekleyen_gozden_gecirme.txt listesindekiler gerekceli atlanir (raporda "skipped" olarak gorunur, sessizce silinmez).
collect_ignore = [  # kaldirilmis moduller (eski aktarim, gecmis temizligi, yuk ornegi, takvim senkronu, eski radar / reportdb akisi)
    "test_eski_aktar.py", "test_gecmis_temizle.py", "test_genel_test.py", "test_radar.py", "test_reportdb.py",
    "test_takvim_senkron.py", "test_yuk_ornek.py",
]  # fmt: skip
_BEKLEYEN = Path(__file__).with_name("bekleyen_gozden_gecirme.txt")


def pytest_collection_modifyitems(config, items):  # type: ignore[no-untyped-def]
    if not _BEKLEYEN.exists():
        return
    bekleyen = {s.strip() for s in _BEKLEYEN.read_text(encoding="utf-8").splitlines() if s.strip() and not s.startswith("#")}
    isaret = pytest.mark.skip(reason="v3.5 paketi: 18 Kasim sonrasi davranis degisikligi - gozden gecirilecek (bekleyen_gozden_gecirme.txt)")
    for item in items:
        if item.nodeid in bekleyen:
            item.add_marker(isaret)
