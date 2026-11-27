"""Test ortami: gecici SQLite, AD kapali, canli kaynaklara (Oracle / PostgreSQL / AD) baglanti YOK.

Ortam degiskenleri app import edilmeden ONCE yazilir; env_dosyasi_yukle() var olan degeri ezmedigi icin backend/.env'deki canli
ayarlar (AD_ENABLED=true, kaynak adresleri) testlere sizmaz. Calistirma (backend klasorunden):  ..\\.venv\\Scripts\\python -m pytest
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

_KOK = Path(tempfile.mkdtemp(prefix="tamlife_test_"))
os.environ.update(
    {
        "TAMLIFE_ENV": "test",
        "TAMLIFE_DATABASE_URL": f"sqlite:///{(_KOK / 'panel.db').as_posix()}",
        "TAMLIFE_KULLANICI_DB_DIZINI": str(_KOK / "kullanicilar"),
        "TAMLIFE_LOG_DIR": str(_KOK / "log"),
        "TAMLIFE_BACKUP_DIR": str(_KOK / "yedek"),
        "TAMLIFE_STATIC_DIR": "",
        "TAMLIFE_TRUSTED_PROXIES": "",
        "TAMLIFE_ALLOWED_ORIGINS": "",
        "TAMLIFE_ALLOWED_HOSTS": "testserver,127.0.0.1,localhost",
        "TAMLIFE_LOCAL_USER": "",
        "TAMLIFE_LOCAL_PASSWORD": "",
        "TAMLIFE_COOKIE_SECURE": "false",
        "AD_ENABLED": "false",
        "AD_ROL_KONTROLU": "kapali",
    }
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app import musteri_alani  # noqa: E402
from app import session as oturum_deposu  # noqa: E402
from app.db import engine, oturum  # noqa: E402
from app.kullanicilar import parola_ozeti  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import (  # noqa: E402
    AppSetting, AppUser, AuditEvent, Base, Customer, CustomerCi, OnedeskRecord, ReportCircuit, ReportCircuitData, ReportCmdb, UserNotification,
)
from app.musteri import erken_uyari  # noqa: E402
from app.ortak import simdi  # noqa: E402
from app.security import limiter  # noqa: E402

PAROLA = "Dogru-Parola-123"
ORIGIN = "http://testserver"


@pytest.fixture(scope="session", autouse=True)
def _sema() -> Iterator[None]:
    Base.metadata.create_all(engine())
    yield


@pytest.fixture(autouse=True)
def _temiz() -> Iterator[None]:
    """Her test bos tablolarla baslar; giris sinirlayici, oturumlar ve Erken Uyari onbellegi sifirlanir."""
    jeton = musteri_alani.ayarla(musteri_alani.VARSAYILAN)
    musteri_alani._alan.set(musteri_alani.TUMU)  # Customer silmesi alana suzulmesin (Toptan kartlari da silinsin)
    try:
        with oturum() as db:
            for tablo in (UserNotification, ReportCircuitData, ReportCircuit, ReportCmdb, CustomerCi, AppSetting, OnedeskRecord, AuditEvent, Customer, AppUser):
                db.execute(delete(tablo))
            db.commit()
    finally:
        musteri_alani.geri_al(jeton)
    limiter.reset()
    oturum_deposu._STORE.clear()
    erken_uyari._onbellek = None
    yield


def kullanici_ekle(ad: str, rol: str = "TeamMember") -> int:
    with oturum() as db:
        u = AppUser(username=ad, role=rol, is_admin=rol == "admin", active=True, password_hash=parola_ozeti(PAROLA))
        db.add(u)
        db.commit()
        return u.id


def musteri_ekle(ad: str, *, sahip: int | None = None, ust: int | None = None, segment: str = "SA") -> int:
    with oturum() as db:
        c = Customer(external_key=ad.lower(), name=ad, segment=segment, owner_id=sahip, parent_id=ust, modul="musteri")
        db.add(c)
        db.commit()
        return c.id


def kayit_ekle(musteri: int | None, tur: str, *, gun_once: float, durum: str = "closed", kapanis_gun_once: float | None = None,
               ci: str = "", kategori: str = "AVAILABILITY", adet: int = 1) -> None:  # fmt: skip
    an = simdi()
    with oturum() as db:
        for _ in range(adet):
            db.add(OnedeskRecord(
                kind=tur, customer_id=musteri, status=durum, location=ci, category=kategori, source="temip" if tur == "alarm" else "onedesk",
                opened_at=an - timedelta(days=gun_once),
                closed_at=None if durum == "open" else an - timedelta(days=kapanis_gun_once if kapanis_gun_once is not None else max(gun_once - 0.5, 0)),
            ))  # fmt: skip
        db.commit()


@pytest.fixture()
def istemci() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=ORIGIN) as c:
        yield c


def giris(c: TestClient, ad: str, parola: str = PAROLA):
    """Basarili giriste CSRF basligini istemciye yazar (arayuzun yaptigi gibi)."""
    r = c.post("/api/v1/session/login", json={"username": ad, "password": parola}, headers={"Origin": ORIGIN})
    if r.status_code == 200:
        from app.config import get_settings

        jeton = c.cookies.get(get_settings().csrf_cookie_name)
        c.headers.update({"x-csrf-token": jeton or "", "Origin": ORIGIN})
    return r
