"""Ekip ozeti HTTP katmani. Genel Bakis'ta bolum; ayri modul/menu yok. Girisi olan herkes cagirir, kapsam serviste
(admin/TeamMngr tum ekip, TeamMember yalniz kendisi).

  GET /ekip/ozet  -> ekip satirlari + sayilar + ozet cumlesi
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_user
from app.ekip import servis
from app.ortak import ok
from app.session import Principal

router = APIRouter(prefix="/api/v1/ekip", tags=["ekip"])


@router.get("/ozet")
def ozet(user: Principal = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    sonuc = servis.ozet(db, user)
    db.commit()  # kullanici_kaydi dev/yerel oturumda app_user satiri acabilir
    return ok(sonuc)
