# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
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



@pytest.mark.parametrize("satir", [0, 1])
def test_0010_radar_prospect_yalniz_bossa_kalkar(tmp_path, satir):
    url = f"sqlite:///{(tmp_path / 'radar.db').as_posix()}"
    command.upgrade(_ayar(url), "0009_gelir_uretim")
    motor = create_engine(url)
    try:
        with motor.begin() as b:
            for i in range(satir):
                b.execute(text("INSERT INTO radar_prospect (id, name, stage) VALUES (:i, 'x', 'y')"), {"i": i + 1})
        command.upgrade(_ayar(url), "head")
        assert inspect(motor).has_table("radar_prospect") is bool(satir)
        command.downgrade(_ayar(url), "0009_gelir_uretim")
        assert inspect(motor).has_table("radar_prospect")
    finally:
        motor.dispose()

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


def test_0011_gelir_onay_eski_kayitlar_onayli(tmp_path):
    """Mevcut Gelir Faydasi kayitlari onay akisina 'onayli' girer (canli veri ve sunum degismez); geri alma satiri korur."""
    url = f"sqlite:///{(tmp_path / 'gelir.db').as_posix()}"
    command.upgrade(_ayar(url), "0010_radar_prospect_kaldir")
    motor = create_engine(url)
    try:
        with motor.begin() as b:
            b.execute(
                text(
                    "INSERT INTO revenue_benefit (id, kind, benefit_type, title, status, status_note, description, customers, revenue_currency,"
                    " revenue_period, revenue_note, hours_note, extra_note, other_people, created_by, created_at, updated_by, updated_at)"
                    " VALUES (1, 'proje', 'gelir', 'Alfa', 'devam', '', '', '', 'TRY', 'ay', '', '', '', '', 'x', '2026-01-01', 'x', '2026-01-01')"
                )
            )
        command.upgrade(_ayar(url), "head")
        with motor.connect() as b:
            assert b.execute(text("SELECT approval, roadmap, approval_note, hours_per_year, created_by_id FROM revenue_benefit")).one() == ("onayli", "", "", None, None)
        command.downgrade(_ayar(url), "0010_radar_prospect_kaldir")
        assert "approval" not in {c["name"] for c in inspect(motor).get_columns("revenue_benefit")}
        with motor.connect() as b:
            assert b.execute(text("SELECT title FROM revenue_benefit")).scalar() == "Alfa"
    finally:
        motor.dispose()
