"""Panel disindaki betiklerin (kurulum\\gece_sync.ps1) ariza kaydi: fault_event + uygulama gunlugu (app.ariza.kaydet). Admin ust
cubuk zilinde ve Yonetim > Arizalar'da gorunur. Panel kapaliyken de calisir (veritabanina dogrudan yazar). Kayit numarasini yazar.

  cd backend; ..\\.venv\\Scripts\\python.exe araclar\\ariza_bildir.py TL-SNC-01 "ayrinti" [--seviye warning] [--kaynak gece_sync]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    from app import ariza

    a = argparse.ArgumentParser()
    a.add_argument("kod", choices=sorted(ariza.KODLAR))
    a.add_argument("ayrinti")
    a.add_argument("--seviye", choices=ariza.SEVIYELER, default="error")
    a.add_argument("--kaynak", default="betik")
    g = a.parse_args()
    print(ariza.kaydet(g.kod, g.ayrinti, kaynak=g.kaynak, kullanici="sistem", seviye=g.seviye))
    return 0


if __name__ == "__main__":
    sys.exit(main())
