"""Rol gorunumu uclari: rolun gorecegi sayfalar ve giris sayfasi. Okuma: admin ya da rol ekrani verilenler; yazma: yalniz admin."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit_log
from app.authz import is_admin
from app.deps import get_db, require_admin, require_user
from app.ortak import ok
from app.rolgorunum import etkin, gorunumler, katalog, kaydet
from app.session import Principal

router = APIRouter(prefix="/api/v1/roller", tags=["roller"])


class RolGovde(BaseModel):
    modules: list[str] = Field(max_length=500)
    landing: str = Field(max_length=80)


@router.get("")
def roller(user: Principal = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    izinli = etkin(db, user).izinli
    if not is_admin(user) and (izinli is None or "roller" not in izinli):
        raise HTTPException(status_code=403, detail="Yetki yok")  # salt okunur gorunum: yalniz rol ekrani verilenlere
    return ok({"roles": gorunumler(db), "catalog": katalog()})


@router.put("/{rol}")
def roller_kaydet(rol: str, body: RolGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    sonuc = kaydet(db, rol, body.modules, body.landing, admin.username)
    db.commit()
    audit_log.remember(
        actor=admin.username,
        action="roller.kaydet",
        outcome="allow",
        module_key="roller",
        detail=f"rol={rol} adet={len(sonuc['modules'])} giris={sonuc['landing']}",
    )
    return ok(sonuc)
