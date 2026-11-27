# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Diagnostic tool: production isolation, honest failures, read-only checks and cleanup."""
import json
import os
import sqlite3
import sys

import pytest

from araclar.genel_test import Report, configured_db, junit, sqlite_check
from araclar.genel_test import test_environment as isolated_env
from araclar.yuk.ornek import rss_mb


def test_external_configuration_cannot_leak_into_test_process(tmp_path):
    source = {"PATH": "keep", "TAMLIFE_DATABASE_URL": "sqlite:///production.db",
              "TAMLIFE_LOCAL_PASSWORD": "never-copy", "AD_ENABLED": "true",
              "ORACLE_REPORTDB_PASSWORD": "never-copy", "URUNTUTAR_DB_PASSWORD": "never-copy",
              "PYTHONPATH": "untrusted", "PYTEST_ADDOPTS": "--lf"}
    env = isolated_env(tmp_path, source)
    assert env["PATH"] == "keep"
    assert env["AD_ENABLED"] == env["ORACLE_REPORTDB_ENABLED"] == "false"
    assert str(tmp_path) in env["TAMLIFE_ENV_DOSYASI"]
    assert "production.db" not in env["TAMLIFE_DATABASE_URL"]
    assert "never-copy" not in json.dumps(env)
    assert "PYTHONPATH" not in env and "PYTEST_ADDOPTS" not in env


def test_sqlite_check_is_read_only_and_detects_corruption(tmp_path):
    db = tmp_path / "sample with space.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE sample (value TEXT)")
        conn.execute("INSERT INTO sample VALUES ('unchanged')")
    before = db.read_bytes()
    assert sqlite_check(db)["status"] == "PASS"
    assert db.read_bytes() == before
    db.write_bytes(b"this is not SQLite")
    with pytest.raises(sqlite3.DatabaseError):
        sqlite_check(db)
    assert sqlite_check(tmp_path / "missing.db")["status"] == "FAIL"


def test_database_location_matches_first_definition_and_environment_precedence(tmp_path, monkeypatch):
    monkeypatch.delenv("TAMLIFE_DATABASE_URL", raising=False)
    monkeypatch.delenv("TAMLIFE_ENV_DOSYASI", raising=False)
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / ".env").write_text("TAMLIFE_DATABASE_URL='sqlite:///var/one.db'\nTAMLIFE_DATABASE_URL=sqlite:///wrong.db\n", encoding="utf-8")
    assert configured_db(tmp_path) == backend / "var/one.db"
    monkeypatch.setenv("TAMLIFE_DATABASE_URL", "postgresql://hidden")
    assert configured_db(tmp_path) is None


def test_failed_step_does_not_prevent_remaining_checks(tmp_path):
    report = Report(tmp_path)
    assert report.command("bad", [sys.executable, "-c", "raise SystemExit(7)"], tmp_path, os.environ.copy()) == 7
    assert report.command("good", [sys.executable, "-c", "print('ok')"], tmp_path, os.environ.copy()) == 0
    assert report.exit_code == 1
    assert [x["status"] for x in report.items] == ["FAIL", "PASS"]
    assert json.loads((tmp_path / "sonuc.json").read_text())["exit_code"] == 1


def test_timeout_stops_owned_child_and_records_failure(tmp_path):
    report = Report(tmp_path)
    pid = tmp_path / "child.pid"
    code = "import os,time; from pathlib import Path; Path(" + repr(str(pid)) + ").write_text(str(os.getpid())); time.sleep(20)"
    assert report.command("timeout", [sys.executable, "-c", code], tmp_path, os.environ.copy(), timeout=1) is None
    assert report.exit_code == 1
    assert "Timed out" in report.items[0]["detail"]


def test_missing_executable_and_invalid_scanner_are_not_success(tmp_path):
    report = Report(tmp_path)
    report.command("missing", [str(tmp_path / "does-not-exist.exe")], tmp_path, os.environ.copy())
    assert report.exit_code == 2
    report.command("scanner", [sys.executable, "-c", "raise SystemExit(1)"], tmp_path, os.environ.copy(), static=True)
    assert report.items[-1]["status"] == "INCOMPLETE"


def test_skipped_tests_and_missing_junit_are_incomplete(tmp_path):
    report = Report(tmp_path)
    junit(report, "missing")
    (tmp_path / "unit.xml").write_text('<testsuites><testsuite tests="5" failures="0" errors="0" skipped="1"/></testsuites>')
    junit(report, "unit")
    assert report.exit_code == 2
    assert report.items[-1]["detail"]["skipped"] == 1


@pytest.mark.skipif(sys.platform not in ("win32", "linux"), reason="RSS supported on Windows/Linux")
def test_process_rss_is_measured_in_real_megabytes():
    # Regression: wrong Windows DWORD layout reported ~0.16 MB for an entire Python process.
    assert rss_mb(os.getpid()) > 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows venv child process regression")
def test_windows_load_instance_measures_and_stops_its_child_tree(tmp_path):
    import subprocess
    import time

    from araclar.yuk.ornek import Ornek

    ready = tmp_path / "ready"
    payload = "import time; from pathlib import Path; data=bytearray(48*1024*1024); Path(" + repr(str(ready)) + ").write_text('ready'); time.sleep(30)"
    process = subprocess.Popen([sys.executable, "-c", payload])
    instance = Ornek(8199, tmp_path, surec=process)
    try:
        for _ in range(100):
            if ready.exists():
                break
            time.sleep(0.05)
        assert ready.exists()
        assert instance.rss_mb() > 48  # the launcher alone is ~11 MB; its actual interpreter must be included
    finally:
        instance.durdur()
    assert process.poll() is not None
