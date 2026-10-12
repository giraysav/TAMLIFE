"""Alembic zinciri: bos DB'de `upgrade head` modelle (models.Base) birebir ayni semayi kurar, `downgrade base` temizler.

Model degisip revizyon yazilmazsa test_zincir_modelle_esit fark listesiyle kirilir. PostgreSQL denemesi icin
TAMLIFE_TEST_PG_URL (bos bir veritabani, ornek postgresql+psycopg://localhost:5432/tamlife_test) verilir; yoksa atlanir.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.models import Base

KOK = Path(__file__).resolve().parents[1]


def _ayar(url: str) -> Config:
    ayar = Config(str(KOK / "alembic.ini"))
    ayar.set_main_option("script_location", str(KOK / "alembic"))
    ayar.set_main_option("sqlalchemy.url", url)
    return ayar


def _fark(url: str) -> list:
    motor = create_engine(url)
    try:
        with motor.connect() as b:
            return compare_metadata(MigrationContext.configure(b), Base.metadata)
    finally:
        motor.dispose()


def _tablolar(url: str) -> set[str]:
    motor = create_engine(url)
    try:
        return set(inspect(motor).get_table_names()) - {"alembic_version"}
    finally:
        motor.dispose()


def _zinciri_dene(url: str) -> None:
    command.upgrade(_ayar(url), "head")
    assert _fark(url) == []
    assert _tablolar(url) == set(Base.metadata.tables)
    command.downgrade(_ayar(url), "base")
    assert _tablolar(url) == set()


def test_zincir_modelle_esit(tmp_path):
    _zinciri_dene(f"sqlite:///{(tmp_path / 'zincir.db').as_posix()}")


def test_0001_sonrasi_eklenenler_sonraki_revizyonlarda(tmp_path):
    """0001 donmus semadir: 0002-0004'un ekledigi sutun/tablolar 0001'de yoktur, kendi revizyonlarinda gelir."""
    url = f"sqlite:///{(tmp_path / 'adim.db').as_posix()}"
    command.upgrade(_ayar(url), "0001_baslangic")
    motor = create_engine(url)
    try:
        bakis = inspect(motor)
        assert {"is_ad_user", "ad_domain", "password_hash"}.isdisjoint(c["name"] for c in bakis.get_columns("app_user"))
        assert "old_score" not in {c["name"] for c in bakis.get_columns("score_history")}
        assert not bakis.has_table("urun_tutar_ozet") and not bakis.has_table("app_setting")
    finally:
        motor.dispose()
    command.upgrade(_ayar(url), "head")
    assert _fark(url) == []


def test_eski_create_all_veritabani_yukselir(tmp_path):
    """Eski 0001 (create_all) ile kurulmus DB: 0001'de damgali, tum tablolar var; 0002-0004 cakismadan gecer."""
    url = f"sqlite:///{(tmp_path / 'eski.db').as_posix()}"
    motor = create_engine(url)
    Base.metadata.create_all(motor)
    with motor.begin() as b:
        b.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        b.execute(text("INSERT INTO alembic_version VALUES ('0001_baslangic')"))
    motor.dispose()
    command.upgrade(_ayar(url), "head")
    assert _fark(url) == []


@pytest.mark.skipif(not os.environ.get("TAMLIFE_TEST_PG_URL"), reason="TAMLIFE_TEST_PG_URL yok")
def test_zincir_postgresql():
    url = os.environ["TAMLIFE_TEST_PG_URL"]
    _zinciri_dene(url)
    command.upgrade(_ayar(url), "head")
    motor = create_engine(url)
    try:
        with motor.begin() as b:  # boolean server_default PostgreSQL'de gecerli olmali
            b.execute(text("INSERT INTO app_user (username, display_name, role, is_admin, active) VALUES ('pg', 'PG', 'TeamMember', false, true)"))
            assert b.execute(text("SELECT is_ad_user, ad_domain FROM app_user")).one() == (False, "")
    finally:
        motor.dispose()
    command.downgrade(_ayar(url), "base")
