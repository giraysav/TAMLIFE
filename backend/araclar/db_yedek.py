"""Canli veritabaninin anlik yedegi (SQLite backup API; panel calisirken tutarli kopya). kurulum\\panel_testi.ps1 yeniden baslatmadan
once cagirir. Yedek: backend\\var\\yedek\\tamlife_<zaman>_<etiket>.db; yol stdout'a yazilir. Butunluk denetlenir (quick_check).

  cd backend; ..\\.venv\\Scripts\\python.exe araclar\\db_yedek.py [etiket]
"""

from __future__ import annotations

import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def main() -> int:
    etiket = re.sub(r"[^A-Za-z0-9_-]", "", sys.argv[1] if len(sys.argv) > 1 else "elle")[:40] or "elle"
    kaynak = KOK / "var" / "dev.db"
    if not kaynak.is_file():
        print(f"veritabani yok: {kaynak}", file=sys.stderr)
        return 1
    hedef = KOK / "var" / "yedek" / f"tamlife_{datetime.now():%Y%m%d_%H%M%S}_{etiket}.db"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    k = sqlite3.connect(f"{kaynak.as_uri()}?mode=ro", uri=True, timeout=60)
    y = sqlite3.connect(hedef)
    try:
        k.backup(y)
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
