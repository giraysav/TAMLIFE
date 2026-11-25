"""Prod guncellemesinden SONRA canli dogrulama (yalniz OKUR). kurulum\\prod_dogrula.ps1 cagirir; elle de calisir.

  cd backend; ..\\.venv\\Scripts\\python.exe araclar\\guncelleme_dogrula.py --commit <sha> --baslangic "YYYY-MM-DD HH:MM:SS" [--bekle 480]

--baslangic: guncellemenin basladigi YEREL saat (bu andan sonraki arizalar ve isci calismasi denetlenir).
Satir bicimi panel_saglik.py ile ayni: DURUM|baslik|ayrinti (TAMAM | UYARI | HATA). Cikis kodu = HATA sayisi.
2026-10-27 kullanici: "prod'a gonder calisinca prod'a gelen tum gelistirmenin sorunsuz calistiginin teyit edilmesi".
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]  # backend
PROJE = KOK.parent
PANEL = "http://127.0.0.1:8117"
# Oturumsuz istekte 401 / 403 donmesi beklenen uclar: modul yonlendiricisi yuklenmis, veritabanina inmeden kimlik istiyor.
# 5xx = modul cokuyor; 404 = uc / modul yuklenmemis. Her ana modulden bir uc.
UCLAR = (
    "/api/v1/session/me", "/api/v1/musteri", "/api/v1/musteri/portfoy", "/api/v1/rapor/durum", "/api/v1/onedesk/durum",
    "/api/v1/gelir/sms", "/api/v1/proje", "/api/v1/radar", "/api/v1/sunum/kaynaklar", "/api/v1/talep", "/api/v1/takvim/ben",
    "/api/v1/ekip/ozet", "/api/v1/skor/meta", "/api/v1/yonetim/ozet", "/api/v1/tampon/kaynaklar", "/api/v1/session/imza",
)  # fmt: skip

sonuclar: list[tuple[str, str, str]] = []


def yaz(durum: str, baslik: str, ayrinti: str = "") -> None:
    ayrinti = " ".join(str(ayrinti).split())[:300]
    sonuclar.append((durum, baslik, ayrinti))
    print(f"{durum}|{baslik}|{ayrinti}", flush=True)


def git(*arg: str) -> str:
    return subprocess.run(["git", "-C", str(PROJE), *arg], capture_output=True, text=True, encoding="utf-8", check=False).stdout.strip()


def http(yol: str, zaman: int = 15) -> tuple[int, bytes]:
    istek = urllib.request.Request(PANEL + yol, headers={"User-Agent": "tamlife-dogrulama"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # kurum vekiline gitmesin
    try:
        with opener.open(istek, timeout=zaman) as y:
            return y.status, y.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except OSError:
        return 0, b""


def kod_surumu(commit: str) -> None:
    bas = git("rev-parse", "HEAD")
    kirli = [s for s in git("status", "--porcelain", "--untracked-files=no").splitlines() if s.strip()]
    if commit and bas != commit:
        yaz("HATA", "Kod surumu", f"prod {bas[:7]}, beklenen {commit[:7]}")
    elif kirli:
        yaz("HATA", "Kod surumu", f"{bas[:7]} ama {len(kirli)} commit edilmemis degisiklik var: {', '.join(kirli[:3])}")
    else:
        yaz("TAMAM", "Kod surumu", f"{bas[:7]} {git('log', '-1', '--format=%s')[:90]} (calisma agaci temiz)")


def sema() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    bas = ScriptDirectory.from_config(Config(str(KOK / "alembic.ini"))).get_current_head()
    c = sqlite3.connect(f"{(KOK / 'var' / 'dev.db').as_uri()}?mode=ro", uri=True, timeout=30)
    surum = c.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    c.close()
    yaz("TAMAM" if surum == bas else "HATA", "Veritabani semasi", f"veritabani {surum}, kod {bas}")


def arayuz(baslangic: datetime) -> None:
    dist = PROJE / "ekran-react" / "dist" / "index.html"
    if not dist.is_file():
        yaz("HATA", "Arayuz derlemesi", "dist/index.html yok")
        return
    zaman = datetime.fromtimestamp(dist.stat().st_mtime)
    if zaman < baslangic:
        yaz("HATA", "Arayuz derlemesi", f"dist bu guncellemede derlenmemis ({zaman:%H:%M}, guncelleme {baslangic:%H:%M})")
    else:
        yaz("TAMAM", "Arayuz derlemesi", f"{zaman:%H:%M:%S}'de derlendi")
    durum, govde = http("/")
    if durum != 200 or b"<div id=\"root\"" not in govde and b"id=root" not in govde:
        yaz("HATA", "Canli arayuz sayfasi", f"GET / -> {durum}")
        return
    varliklar = re.findall(rb'(?:src|href)="(/assets/[^"]+\.(?:js|css))"', govde)
    bozuk = [v.decode() for v in varliklar if http(v.decode())[0] != 200]
    if not varliklar:
        yaz("HATA", "Canli arayuz dosyalari", "sayfada /assets/ basvurusu yok")
    elif bozuk:
        yaz("HATA", "Canli arayuz dosyalari", f"yuklenmeyen: {', '.join(bozuk[:3])}")
    else:
        yaz("TAMAM", "Canli arayuz", f"sayfa + {len(varliklar)} dosya yukleniyor")


def api() -> None:
    durum, _ = http("/api/v1/health")
    if durum != 200:
        yaz("HATA", "API saglik ucu", f"/api/v1/health -> {durum}")
        return
    sonuc = {u: http(u)[0] for u in UCLAR}
    bozuk = {u: d for u, d in sonuc.items() if d not in (401, 403)}
    if bozuk:
        yaz("HATA", "API modulleri", "; ".join(f"{u} -> {d or 'yanit yok'}" for u, d in list(bozuk.items())[:5]))
    else:
        yaz("TAMAM", "API modulleri", f"{len(UCLAR)} uc ayakta (oturumsuz istege kimlik istiyor, cokmuyor)")


def arizalar(baslangic: datetime) -> None:
    utc = baslangic.astimezone().astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")  # fault_event.at UTC
    c = sqlite3.connect(f"{(KOK / 'var' / 'dev.db').as_uri()}?mode=ro", uri=True, timeout=30)
    satirlar = c.execute("SELECT code, source, message FROM fault_event WHERE at >= ? AND severity = 'error' ORDER BY id", (utc,)).fetchall()
    c.close()
    if satirlar:
        yaz("HATA", "Guncelleme sonrasi arizalar", f"{len(satirlar)} yeni hata: " + "; ".join(f"{k} {s} {m[:60]}" for k, s, m in satirlar[:3]))
    else:
        yaz("TAMAM", "Guncelleme sonrasi arizalar", "yeni hata kaydi yok")


def isci(baslangic: datetime, bekle: int) -> None:
    from app.config import get_settings

    klasor = Path(get_settings().log_dir.strip()) if get_settings().log_dir.strip() else KOK / "var" / "logs"
    gunluk = klasor / "isci.log"
    son = time.monotonic() + bekle
    print(f"BILGI|ReportDB iscisi|guncelleme sonrasi ilk calismasi bekleniyor (en cok {bekle // 60} dk)", flush=True)
    while True:
        ok = hata = None
        if gunluk.is_file():
            with open(gunluk, encoding="utf-8", errors="replace") as f:
                for satir in f.readlines()[-200:]:
                    m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) reportdb (OK|HATA)", satir)
                    if m and datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") >= baslangic:
                        ok, hata = (satir.strip()[20:160], hata) if m.group(2) == "OK" else (ok, satir.strip()[20:160])
        if ok:
            yaz("TAMAM", "ReportDB iscisi (guncelleme sonrasi)", ok)
            return
        if hata:
            yaz("HATA", "ReportDB iscisi (guncelleme sonrasi)", hata)
            return
        if time.monotonic() > son:
            yaz("HATA", "ReportDB iscisi (guncelleme sonrasi)", f"{bekle // 60} dk icinde calismadi")
            return
        time.sleep(15)


def main() -> int:
    for akim in (sys.stdout, sys.stderr):
        if hasattr(akim, "reconfigure"):
            akim.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--commit", default="")
    p.add_argument("--baslangic", required=True, help="guncellemenin basladigi yerel saat: YYYY-MM-DD HH:MM:SS")
    p.add_argument("--bekle", type=int, default=480, help="ReportDB iscisinin ilk calismasi icin en cok bekleme (sn)")
    a = p.parse_args()
    sys.path.insert(0, str(KOK))
    from app.config import env_dosyasi_yukle

    env_dosyasi_yukle()
    baslangic = datetime.strptime(a.baslangic, "%Y-%m-%d %H:%M:%S")  # yerel saat (dosya zamanlari ve isci.log da yerel)
    for adim in (lambda: kod_surumu(a.commit), sema, lambda: arayuz(baslangic), api, lambda: isci(baslangic, a.bekle), lambda: arizalar(baslangic)):
        try:
            adim()
        except Exception as e:  # noqa: BLE001 - tek denetim digerlerini durdurmasin
            yaz("HATA", "Denetim", f"calismadi: {type(e).__name__}: {e}")
    return sum(1 for d, _, _ in sonuclar if d == "HATA")


if __name__ == "__main__":
    sys.exit(main())
