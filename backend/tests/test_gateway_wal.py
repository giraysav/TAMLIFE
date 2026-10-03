"""Panel store does not enable SQLite WAL."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.data.gateway import make_engine


def test_journal_mode_wal(tmp_path: Path) -> None:
    db_file = tmp_path / "gateway.db"
    engine = make_engine("sqlite:///" + db_file.as_posix())
    with engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar()
    assert mode != "wal"
    assert mode == "delete"
    assert not str(db_file).lower().endswith("sirket.db")
