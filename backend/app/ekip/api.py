# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Ekip ozeti HTTP katmani. Genel Bakis'ta bolum; ayri modul/menu yok. Girisi olan herkes cagirir, kapsam serviste
(admin/TeamMngr tum ekip, TeamMember yalniz kendisi).

  GET /ekip/ozet  -> ekip satirlari + sayilar + ozet cumlesi
"""

from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import dil
from app.db import get_db
from app.deps import require_user
from app.ekip import servis
from app.ortak import ok
from app.session import Principal

router = APIRouter(prefix="/api/v1/ekip", tags=["ekip"])

# Ozet bir kerede yuzlerce SQLite satiri okur; sqlite3 her adimda GIL'i birakir ve baska is parcacigi CPU'dayken geri almak
# switchinterval (5 ms) kadar bekler. Eszamanli ozetler birbirini bu yuzden 20 kat yavaslatiyor, diger uclari da surukluyordu
# (yerel olcum: 4 eszamanlida tek istek 42 ms -> 908 ms). Hesap tek sirada yapilir; ayni kisi icin, BU ISTEK geldikten SONRA
# baslamis bir hesap varsa onun sonucu paylasilir (veri istekten daha eski olmaz).
_KILIT = threading.Lock()
_SON: dict[tuple[str, str, bool, str], tuple[float, dict]] = {}


@router.get("/ozet")
def ozet(user: Principal = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    geldi, anahtar = time.monotonic(), (user.username, user.role, user.is_admin, dil.secili())
    with _KILIT:
        son = _SON.get(anahtar)
        if son is not None and son[0] >= geldi:
            return ok(son[1])
        bas = time.monotonic()
        sonuc = servis.ozet(db, user)
        db.commit()  # kullanici_kaydi dev/yerel oturumda app_user satiri acabilir
        _SON[anahtar] = (bas, sonuc)
    return ok(sonuc)
