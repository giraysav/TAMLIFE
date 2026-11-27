"""Veritabani gocleri: bos bir veritabanina 0001'den son surume kadar zincir kesintisiz uygulanir ve modelle uyusur."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

BACKEND = Path(__file__).resolve().parents[1]


def test_tum_gocler_bos_veritabanina_uygulanir(tmp_path):
    hedef = tmp_path / "goc.db"
    ortam = {**os.environ, "TAMLIFE_DATABASE_URL": f"sqlite:///{hedef.as_posix()}"}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=ortam, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    motor = sa.create_engine(f"sqlite:///{hedef.as_posix()}")
    with motor.connect() as b:
        surum = b.execute(sa.text("select version_num from alembic_version")).scalar()
    denetci = sa.inspect(motor)
    from app.models import Base

    eksik = {t for t in Base.metadata.tables if t not in denetci.get_table_names()}
    assert surum and not eksik, (surum, eksik)
    assert "ip" in {c["name"] for c in denetci.get_columns("audit_event")}
    motor.dispose()
