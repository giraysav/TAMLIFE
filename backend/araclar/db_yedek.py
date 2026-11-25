"""Canli veritabaninin anlik yedegi (SQLite backup API; panel calisirken tutarli kopya). kurulum\\panel_testi.ps1 yeniden baslatmadan
once, kurulum\\citrix_paket.ps1 Citrix paketine koymak icin cagirir. Butunluk denetlenir (quick_check); yol stdout'a yazilir.

  cd backend; ..\\.venv\\Scripts\\python.exe araclar\\db_yedek.py [etiket]          -> var\\yedek\\tamlife_<zaman>_<etiket>.db
  cd backend; ..\\.venv\\Scripts\\python.exe araclar\\db_yedek.py --hedef <dosya>   -> verilen dosya (varsa uzerine yazilir)
"""

from __future__ import annotations

import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def main() -> int:
    argumanlar = sys.argv[1:]
    if argumanlar[:1] == ["--hedef"] and len(argumanlar) == 2:
        hedef = Path(argumanlar[1]).resolve()
    else:
        etiket = re.sub(r"[^A-Za-z0-9_-]", "", argumanlar[0] if argumanlar else "elle")[:40] or "elle"
        hedef = KOK / "var" / "yedek" / f"tamlife_{datetime.now():%Y%m%d_%H%M%S}_{etiket}.db"
    kaynak = KOK / "var" / "dev.db"
    if not kaynak.is_file():
        print(f"veritabani yok: {kaynak}", file=sys.stderr)
        return 1
    if hedef == kaynak.resolve():
        print("hedef canli veritabaninin kendisi olamaz", file=sys.stderr)
        return 1
    hedef.parent.mkdir(parents=True, exist_ok=True)
    for ek in ("", "-wal", "-shm"):  # eski kopya ve ona ait WAL/SHM kalmasin (yeni kopyayla karisirsa bozar)
        Path(f"{hedef}{ek}").unlink(missing_ok=True)
    k = sqlite3.connect(f"{kaynak.as_uri()}?mode=ro", uri=True, timeout=60)
    y = sqlite3.connect(hedef)
    try:
        k.backup(y)
        y.execute("PRAGMA journal_mode=DELETE")  # tek dosya: yanina WAL/SHM birakmaz (tasinabilir kopya)
        sonuc = y.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        y.close()
        k.close()
    if sonuc != "ok":
        print(f"yedek bozuk ({sonuc}): {hedef}", file=sys.stderr)
        return 1
    print(hedef)
    return 0


if __name__ == "__main__":
    sys.exit(main())
