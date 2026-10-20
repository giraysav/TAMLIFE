"""Yuk/stres testleri icin AYRI panel ornegi (yalniz standart kutuphane). Canli panele ve canli DB'ye dokunmaz.

Canli DB'nin (backend\\var\\dev.db) tutarli kopyasi SQLite backup API ile alinir (panel acikken dosyayi elle kopyalamak WAL
yuzunden tutarsiz kopya verir); ornek ayri portta, ayri gunluk/yedek klasoruyle, AD ve Oracle kapali, gercek .env OKUNMADAN
(TAMLIFE_ENV_DOSYASI bos dosyaya isaret eder) acilir. Giris: tek kullanimlik yerel yuk hesabi (admin rolu, yalniz bu ornekte).

  cd E:\\TAMLIFE_Dev\\TAMLIFE_v3.5\\backend
  ..\\.venv\\Scripts\\python.exe -m araclar.yuk.ornek --kaynak var\\dev.db --port 8199     (Ctrl+C ile kapanir, kopya silinir)
  ..\\.venv\\Scripts\\python.exe -m araclar.yuk.ornek --bos --port 8199                    (bos sema: alembic upgrade head)
"""

from __future__ import annotations

import argparse
import ctypes
import http.client
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def db_kopyala(kaynak: Path, hedef_dizin: Path) -> Path:
    """Panel DB'si ve yanindaki kullanicilar/*.db, SQLite backup API ile (okuyucu kilidi; canli yazmalari durdurmaz)."""
    hedef_dizin.mkdir(parents=True, exist_ok=True)
    hedef = hedef_dizin / "yuk.db"

    def yedekle(a: Path, b: Path) -> None:
        with sqlite3.connect(f"file:{a.as_posix()}?mode=ro", uri=True) as k, sqlite3.connect(b) as h:
            k.backup(h)
        h.close()
        k.close()

    yedekle(kaynak, hedef)
    kaynak_kul = kaynak.parent / "kullanicilar"
    if kaynak_kul.is_dir():
        (hedef_dizin / "kullanicilar").mkdir(exist_ok=True)
        for dosya in kaynak_kul.glob("*.db"):
            yedekle(dosya, hedef_dizin / "kullanicilar" / dosya.name)
    return hedef


def bos_db_kur(hedef_dizin: Path) -> Path:
    hedef_dizin.mkdir(parents=True, exist_ok=True)
    hedef = hedef_dizin / "yuk.db"
    ortam = {**os.environ, "TAMLIFE_ENV": "dev", "TAMLIFE_DATABASE_URL": f"sqlite:///{hedef.as_posix()}"}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=ortam, check=True, capture_output=True)
    return hedef


def rss_mb(pid: int) -> float:
    """Surecin yerlesik bellegi (MB). Linux /proc, Windows psapi (psutil gerekmez)."""
    if sys.platform.startswith("linux"):
        for satir in Path(f"/proc/{pid}/status").read_text().splitlines():
            if satir.startswith("VmRSS:"):
                return int(satir.split()[1]) / 1024
        return 0.0
    if sys.platform == "win32":

        from ctypes import wintypes

        class Sayac(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (ad, ctypes.c_size_t) for ad in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Sayac), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        tutamac = kernel.OpenProcess(0x1000 | 0x0010, False, pid)
        if not tutamac:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            s = Sayac()
            s.cb = ctypes.sizeof(s)
            if not psapi.GetProcessMemoryInfo(tutamac, ctypes.byref(s), s.cb):
                raise ctypes.WinError(ctypes.get_last_error())
            return s.WorkingSetSize / 1048576
        finally:
            kernel.CloseHandle(tutamac)
    return 0.0


def rss_agaci_mb(pid: int) -> float:
    """Windows venv launcher dahil yalniz bu surec agacinin toplam RSS'i."""
    if sys.platform != "win32":
        return rss_mb(pid)
    from ctypes import wintypes

    class Kayit(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Kayit)]
    kernel.Process32FirstW.restype = kernel.Process32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    parents = {}
    try:
        entry = Kayit()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            ok = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    owned = {pid}
    while True:
        expanded = owned | {child for child, parent in parents.items() if parent in owned}
        if expanded == owned:
            break
        owned = expanded
    total = 0.0
    for child in owned:
        try:
            total += rss_mb(child)
        except OSError:
            if child == pid:
                raise
    return total


@dataclass
class Ornek:
    port: int
    dizin: Path
    kullanici: str = "yuk.admin"
    parola: str = field(default_factory=lambda: secrets.token_urlsafe(18))
    surec: subprocess.Popen | None = None

    @property
    def db(self) -> Path:
        return self.dizin / "yuk.db"

    def ortam(self, ek: dict[str, str] | None = None) -> dict[str, str]:
        bos_env = self.dizin / "yok.env"
        bos_env.write_text("", encoding="utf-8")
        temel = {k: v for k, v in os.environ.items() if not k.upper().startswith(("TAMLIFE_", "AD_", "ORACLE_", "REPORTDB_", "ONENTDB_", "GALAPAGOS"))}
        return {
            **temel,
            "TAMLIFE_ENV": "dev",
            "TAMLIFE_ENV_DOSYASI": str(bos_env),
            "TAMLIFE_DATABASE_URL": f"sqlite:///{self.db.as_posix()}",
            "TAMLIFE_KULLANICI_DB_DIZINI": str(self.dizin / "kullanicilar"),
            "TAMLIFE_LOG_DIR": str(self.dizin / "log"),
            "TAMLIFE_BACKUP_DIR": str(self.dizin / "yedek"),
            "TAMLIFE_LOCAL_USER": self.kullanici,
            "TAMLIFE_LOCAL_PASSWORD": self.parola,
            "TAMLIFE_LOCAL_ROLE": "admin",
            "TAMLIFE_ALLOWED_HOSTS": "127.0.0.1,localhost",
            "TAMLIFE_COOKIE_SECURE": "false",
            "AD_ENABLED": "false",
            **(ek or {}),
        }

    def baslat(self, ek_ortam: dict[str, str] | None = None, bekle_sn: float = 60) -> Ornek:
        gunluk = open(self.dizin / "uvicorn.log", "ab")  # noqa: SIM115 - surec boyunca acik
        komut = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(self.port), "--no-proxy-headers",
                 "--log-level", "warning"]  # fmt: skip
        self.surec = subprocess.Popen(komut, cwd=BACKEND, env=self.ortam(ek_ortam), stdout=gunluk, stderr=subprocess.STDOUT)
        son = time.monotonic() + bekle_sn
        while time.monotonic() < son:
            if self.surec.poll() is not None:
                raise RuntimeError(f"ornek acilamadi; {self.dizin / 'uvicorn.log'}")
            try:
                c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
                c.request("GET", "/api/v1/health")
                if c.getresponse().status == 200:
                    return self
            except OSError:
                time.sleep(0.2)
        raise RuntimeError("ornek zamaninda acilmadi")

    def durdur(self) -> None:
        if self.surec and self.surec.poll() is None:
            if sys.platform == "win32":
                # venv python.exe Windows'ta asil yorumlayiciyi alt surecte acar.
                # Yalniz launcher'i durdurmak test sunucusunu acik birakirdi.
                subprocess.run(["taskkill.exe", "/PID", str(self.surec.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=False)
                self.surec.wait(20)
            else:
                self.surec.terminate()
                try:
                    self.surec.wait(15)
                except subprocess.TimeoutExpired:
                    self.surec.kill()
                    self.surec.wait(15)

    def rss_mb(self) -> float:
        return rss_agaci_mb(self.surec.pid) if self.surec else 0.0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    kaynak = p.add_mutually_exclusive_group(required=True)
    kaynak.add_argument("--kaynak", type=Path, help="kopyalanacak panel DB'si (orn. var\\dev.db)")
    kaynak.add_argument("--bos", action="store_true", help="bos sema ile ac")
    p.add_argument("--port", type=int, default=8199)
    p.add_argument("--dizin", type=Path, help="kopya klasoru (varsayilan gecici; kapanista silinir)")
    p.add_argument("--arayuz", action="store_true", help="derlenmis arayuzu de sun (ekran-react/dist; gorsel / Playwright denemeleri)")
    a = p.parse_args()
    if a.port in (8117, 443):
        print("8117/443 canli paneldir; baska port verin.")
        return 2
    dizin = a.dizin or Path(tempfile.mkdtemp(prefix="tamlife_yuk_"))
    if a.kaynak:
        db_kopyala(a.kaynak.resolve(), dizin)
    else:
        bos_db_kur(dizin)
    ek = {"TAMLIFE_STATIC_DIR": str(BACKEND.parent / "ekran-react" / "dist")} if a.arayuz else None
    o = Ornek(a.port, dizin).baslat(ek)
    print(f"ornek: http://127.0.0.1:{a.port}  kullanici={o.kullanici}  parola={o.parola}  kopya={dizin}")
    print(f"  ..\\.venv\\Scripts\\python.exe -m araclar.yuk.yuk_testi http://127.0.0.1:{a.port} --kullanici {o.kullanici} --parola {o.parola} kirilma")
    try:
        while o.surec and o.surec.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        o.durdur()
        if not a.dizin:
            shutil.rmtree(dizin, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
