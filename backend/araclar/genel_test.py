"""Incident diagnostics and isolated regression/load tests. Never restarts production."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener
import re

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
EXTERNAL_PREFIXES = ("TAMLIFE_", "AD_", "ORACLE_", "REPORTDB_", "ONENTDB_", "GALAPAGOS", "URUNTUTAR_", "ANTHROPIC_", "OPENAI_", "AZURE_OPENAI_")


def test_environment(sandbox: Path, source=None) -> dict[str, str]:
    """No deployment configuration or database can be inherited by tests."""
    env = {k: v for k, v in (os.environ if source is None else source).items()
           if not k.upper().startswith(EXTERNAL_PREFIXES) and k.upper() not in {"PYTHONPATH", "PYTHONHOME", "PYTEST_ADDOPTS"}}
    sandbox.mkdir(parents=True, exist_ok=True)
    env.update({
        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1",
        "TAMLIFE_ENV": "test", "TAMLIFE_ENV_DOSYASI": str(sandbox / "not-present.env"),
        "TAMLIFE_DATABASE_URL": "sqlite:///" + (sandbox / "test.db").as_posix(),
        "TAMLIFE_LOG_DIR": str(sandbox / "logs"), "TAMLIFE_BACKUP_DIR": str(sandbox / "backups"),
        "AD_ENABLED": "false", "ORACLE_REPORTDB_ENABLED": "false",
        "ONENTDB_DB_ENABLED": "false", "GALAPAGOSDB_DB_ENABLED": "false",
    })
    return env


def sqlite_check(path: Path, seconds: float = 5) -> dict:
    if not path.is_file():
        return {"status": "FAIL", "detail": "SQLite file missing"}
    deadline = time.monotonic() + seconds
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        rows = conn.execute("PRAGMA quick_check(1)").fetchall()
        return {"status": "PASS" if rows == [("ok",)] else "FAIL",
                "detail": "SQLite quick_check: " + ("ok" if rows == [("ok",)] else "integrity error")}


def configured_db(root: Path) -> Path | None:
    """Read only the DB location; never collect or output secret values."""
    value = os.environ.get("TAMLIFE_DATABASE_URL")
    env_path = Path(os.environ.get("TAMLIFE_ENV_DOSYASI") or root / "backend/.env")
    if value is None and env_path.is_file():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, item = line.strip().partition("=")
            if sep and key.strip() == "TAMLIFE_DATABASE_URL":
                value = item.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                break
    if not value or not value.startswith("sqlite:///"):
        return None
    name = value[len("sqlite:///"):]
    if not name or name == ":memory:" or "?" in name:
        return None
    path = Path(name)
    return path if path.is_absolute() else root / "backend" / path


def terminate_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    else:
        import signal
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=20)


class Report:
    def __init__(self, path: Path):
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        self.items: list[dict] = []

    def add(self, name: str, status: str, detail, **extra):
        self.items.append({"name": name, "status": status, "detail": detail, **extra})
        self.save()
        print(f"[{status}] {name}", flush=True)

    @property
    def exit_code(self):
        if any(x["status"] == "FAIL" for x in self.items):
            return 1
        return 2 if any(x["status"] == "INCOMPLETE" for x in self.items) else 0

    def save(self):
        data = {"exit_code": self.exit_code, "checks": self.items}
        temp = self.path / "sonuc.tmp"
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path / "sonuc.json")
        lines = ["# TAMLIFE test raporu", "", f"Cikis kodu: {self.exit_code}", "",
                 "| Kontrol | Durum | Aciklama |", "|---|---|---|"]
        for item in self.items:
            detail = json.dumps(item["detail"], ensure_ascii=False) if not isinstance(item["detail"], str) else item["detail"]
            lines.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ")
                                          for x in (item["name"], item["status"], detail)) + " |")
        (self.path / "rapor.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def command(self, name, command, cwd, env, timeout=900, static=False):
        log = self.path / (name + ".log")
        start = time.monotonic()
        try:
            with log.open("wb") as stream:
                kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
                process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                           stdout=stream, stderr=subprocess.STDOUT, **kwargs)
                try:
                    code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    terminate_tree(process)
                    self.add(name, "FAIL", "Timed out; only the test process tree was stopped", log=log.name)
                    return None
                except BaseException:
                    terminate_tree(process)
                    raise
            status = "PASS" if code == 0 else ("WARN" if static and code == 1 else "FAIL")
            if static:
                try:
                    findings = json.loads(log.read_text(encoding="utf-8"))
                    if not isinstance(findings, list):
                        raise ValueError("Scanner did not return findings")
                except (ValueError, OSError):
                    self.add(name, "INCOMPLETE", "Static scanner unavailable or output invalid", log=log.name)
                    return None
            self.add(name, status, f"exit={code}; log={log.name}", elapsed_seconds=round(time.monotonic()-start, 2))
            return code
        except (OSError, subprocess.SubprocessError) as exc:
            self.add(name, "INCOMPLETE", type(exc).__name__, log=log.name)
            return None


def health(report: Report):
    opener = build_opener(ProxyHandler({}))
    for name, url in (("http-health", "http://127.0.0.1:8117/api/v1/health"),
                      ("https-health", "https://tamlife/api/v1/health")):
        try:
            with opener.open(url, timeout=5) as response:
                body = json.loads(response.read(8192))
                valid = response.status == 200 and body.get("data", {}).get("service") == "tamlife"
                report.add(name, "PASS" if valid else "FAIL", "HTTP " + str(response.status))
        except (OSError, URLError, HTTPError, ValueError) as exc:
            report.add(name, "FAIL", type(exc).__name__)
    try:
        db = configured_db(ROOT)
        result = sqlite_check(db) if db else {"status": "INCOMPLETE", "detail": "No supported SQLite location configured"}
        report.add("database-read-only", **result)
    except (OSError, sqlite3.Error) as exc:
        report.add("database-read-only", "FAIL", type(exc).__name__)
    space = shutil.disk_usage(ROOT)
    report.add("disk", "PASS" if space.free > 1024**3 else "WARN",
               {"free_gib": round(space.free / 1024**3, 2), "used_percent": round(space.used / space.total * 100, 1)})
    if os.name == "nt":
        ps = """$ErrorActionPreference='Stop'
Get-ScheduledTask | Where-Object {$_.TaskName -match 'TAMLIFE|TAM_Life|ReportDB'} |
 ForEach-Object {$i=Get-ScheduledTaskInfo -TaskName $_.TaskName; [pscustomobject]@{task=$_.TaskName;state=[string]$_.State;user=$_.Principal.UserId;logon=[string]$_.Principal.LogonType;last_result=$i.LastTaskResult}} | ConvertTo-Json
"""
        report.command("windows-tasks", ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                       ROOT, os.environ.copy(), timeout=45)
        try:
            tasks = json.loads((report.path / "windows-tasks.log").read_text(encoding="utf-8-sig"))
            if isinstance(tasks, dict):
                tasks = [tasks]
            for name in ("TAMLIFE_v35_Panel", "TAMLIFE_v35_TLS_Vekil"):
                task = next((x for x in tasks if x["task"] == name), None)
                valid = bool(task and task["state"] == "Running" and task["user"].split("\\")[-1].upper() == "TAMLIFEADLOG")
                report.add(name, "PASS" if valid else "FAIL", task or "Task missing")
            for name in ("TAMLIFE-Watch", "TAMLIFE-Watch-Health"):
                if any(x["task"] == name for x in tasks) and not Path("E:/TAMLIFE_Watch/run.bat").exists():
                    report.add(name, "WARN", "Task target E:/TAMLIFE_Watch/run.bat missing")
        except (OSError, ValueError, TypeError, KeyError):
            report.add("task-details", "INCOMPLETE", "Task snapshot unavailable")
        runtime_ps = """$ErrorActionPreference='Stop'
$os=Get-CimInstance Win32_OperatingSystem
$listener=Get-NetTCPConnection -LocalPort 8117 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$panel=$null
if($listener){$p=Get-Process -Id $listener.OwningProcess; $panel=[pscustomobject]@{pid=$p.Id;rss_mb=[math]::Round($p.WorkingSet64/1MB,1);cpu_seconds=$p.CPU;threads=$p.Threads.Count;started=$p.StartTime.ToString('o')}}
$events=@(Get-WinEvent -FilterHashtable @{LogName='Application';StartTime=(Get-Date).AddHours(-2);Level=1,2} -MaxEvents 20 -ErrorAction SilentlyContinue | Select-Object @{n='time';e={$_.TimeCreated.ToString('o')}},Id,ProviderName)
[pscustomobject]@{memory_total_mb=[math]::Round($os.TotalVisibleMemorySize/1024);memory_free_mb=[math]::Round($os.FreePhysicalMemory/1024);panel=$panel;recent_error_events=$events} | ConvertTo-Json -Depth 4
"""
        report.command("windows-runtime", ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", runtime_ps],
                       ROOT, os.environ.copy(), timeout=45)
    counts = Counter()
    for path in (ROOT / "backend/var/logs/uygulama.log", ROOT / "backend/var/logs/isci.log", ROOT / "var/log/canli_panel.log"):
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size-262144))
            counts.update(re.findall(r"(?:ORA|DPY|DPI)-\d+|TL-[A-Z]+-\d+", stream.read().decode("utf-8", errors="replace")))
    report.add("historical-error-codes", "INFO", dict(counts))  # no raw log messages or credentials


def junit(report: Report, name: str):
    path = report.path / (name + ".xml")
    if not path.is_file():
        report.add(name + "-coverage", "INCOMPLETE", "JUnit report missing; test execution not confirmed")
        return
    try:
        tree = ET.parse(path).getroot()
        suites = list(tree.iter("testsuite"))
        totals = {key: sum(int(s.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
        status = "FAIL" if totals["failures"] or totals["errors"] or not totals["tests"] else ("INCOMPLETE" if totals["skipped"] else "PASS")
        report.add(name + "-coverage", status, totals)
    except (OSError, ValueError, ET.ParseError) as exc:
        report.add(name + "-coverage", "INCOMPLETE", type(exc).__name__)


def suites(report: Report, mode: str, python: str, timeout: int):
    env = test_environment(report.path / "sandbox")
    if mode in {"tam", "backend"}:
        report.command("backend", [python, "-m", "pytest", "tests", "-m", "not yuk", "-v", "-o", "faulthandler_timeout=120", "--tb=short",
                       "-p", "no:cacheprovider", "--junitxml", str(report.path / "backend.xml")], BACKEND, env, timeout)
        junit(report, "backend")
        report.command("security-static", [python, "-m", "ruff", "check", "app", "araclar",
                       "--select", "S", "--output-format", "json"], BACKEND, env, timeout=90, static=True)
    if mode in {"tam", "arayuz"}:
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        node = shutil.which("node")
        cli = Path(npm).parent / "node_modules/npm/bin/npm-cli.js" if npm else Path("/nonexistent")
        if not node or not cli.is_file():
            report.add("frontend", "INCOMPLETE", "Node/npm CLI not found; nothing installed automatically")
        else:
            for name, args in (
                ("frontend-lint", ["run", "lint"]),
                ("frontend-test", ["run", "test", "--", "--maxWorkers=2"]),
                ("frontend-build", ["run", "build", "--", "--outDir", str(report.path / "ui-build"), "--emptyOutDir"]),
            ):
                report.command(name, [node, str(cli), *args], ROOT / "ekran-react", env, timeout)
    if mode in {"tam", "yuk"}:
        report.command("load", [python, "-m", "pytest", "tests/test_yuk_ornek.py", "-m", "yuk", "-q", "-s",
                       "--tb=short", "-p", "no:cacheprovider", "--junitxml", str(report.path / "load.xml")], BACKEND, env, timeout)
        junit(report, "load")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("hizli", "backend", "arayuz", "yuk", "tam"), default="hizli")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    parent = ROOT / "var/test"
    parent.mkdir(parents=True, exist_ok=True)
    lock = (parent / "genel-test.lock").open("a+b")
    try:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Another diagnostic run is active.", file=sys.stderr)
        lock.close()
        return 2
    path = parent / ("rapor-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    report = Report(path)
    print("REPORT " + str(path), flush=True)
    try:
        health(report)
        if args.mode != "hizli":
            suites(report, args.mode, args.python, args.timeout)
    except KeyboardInterrupt:
        report.add("interrupted", "INCOMPLETE", "Interrupted by operator")
    except Exception as exc:
        report.add("runner", "INCOMPLETE", type(exc).__name__)
    finally:
        report.save()
        lock.close()
    print("REPORT " + str(path / "rapor.md"), flush=True)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
