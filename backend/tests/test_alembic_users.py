"""Upgrade sonrasi users kolon listesi. pin_code ve totp_secret yok."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[1]


def test_users_columns_after_upgrade(tmp_path: Path, capsys) -> None:
    db_file = tmp_path / "schema.db"
    url = "sqlite:///" + db_file.as_posix()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    names = [col["name"] for col in inspect(engine).get_columns("users")]
    print("COLUMNS " + ",".join(names))
    captured = capsys.readouterr()
    assert "pin_code" not in names
    assert "totp_secret" not in names
    assert "username" in names
    assert "role" in names
    assert captured.out.strip().startswith("COLUMNS ")
    assert set(inspect(engine).get_table_names()) == {"alembic_version", "users", "audit_event"}
