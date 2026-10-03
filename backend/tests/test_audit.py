"""403 bir audit satiri ekler. Satirda pin, totp, cerez yok."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.core.audit import write
from app.data.gateway import session_factory
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def _prepare(tmp_path: Path, monkeypatch) -> tuple[TestClient, object]:
    db_file = tmp_path / "audit.db"
    url = "sqlite:///" + db_file.as_posix()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    monkeypatch.setenv("TAMLIFE_ENV", "test")
    monkeypatch.setenv("TAMLIFE_DATABASE_URL", url)
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", "member-audit")
    monkeypatch.setenv("TAMLIFE_LOCAL_PASSWORD", secrets.token_urlsafe(18))
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    client = TestClient(create_app())
    csrf = client.cookies.get("tamlife_csrf") or client.get("/api/v1/csrf") and client.cookies.get("tamlife_csrf")
    login = client.post(
        "/api/v1/session",
        json={"username": "member-audit", "password": __import__("os").environ["TAMLIFE_LOCAL_PASSWORD"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert login.status_code == 200
    return client, create_engine(url)


def test_denied_adds_one_row_without_secrets(tmp_path: Path, monkeypatch) -> None:
    client, engine = _prepare(tmp_path, monkeypatch)
    names = [col["name"] for col in inspect(engine).get_columns("audit_event")]
    print("AUDIT_COLUMNS " + ",".join(names))
    assert "pin_code" not in names
    assert "totp_secret" not in names
    assert "cookie" not in names
    before = engine.connect().execute(text("select count(*) from audit_event")).scalar()
    denied = client.get("/api/v1/modules/utilizasyon")
    assert denied.status_code == 403
    after = engine.connect().execute(text("select count(*) from audit_event")).scalar()
    assert before == 0
    assert after == before + 1
    row = engine.connect().execute(text("select action, module, result, path, detail from audit_event")).one()
    blob = " ".join("" if part is None else str(part) for part in row).lower()
    assert "pin" not in blob
    assert "totp" not in blob
    assert "cookie" not in blob
    assert row.action == "denied"
    assert row.module == "utilizasyon"
    factory = session_factory(engine)
    with pytest.raises(ValueError):
        write(
            factory,
            actor_id=1,
            action="denied",
            module="utilizasyon",
            target_id=None,
            result="denied",
            path="/api/v1/modules/utilizasyon",
            detail={"pin_code": "no"},
        )
    stayed = engine.connect().execute(text("select count(*) from audit_event")).scalar()
    assert stayed == 1
