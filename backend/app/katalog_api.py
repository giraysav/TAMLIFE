"""Modul katalogu uclari: erisilebilir moduller, ana sayfa kartlari ve tek modul erisim denetimi (rol gorunumu sunucuda zorlanir)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit import audit_log
from app.authz import can_open
from app.catalog import HOME_CARDS, MODULES, get
from app.deps import get_db, require_user
from app.ortak import ok
from app.rolgorunum import etkin
from app.session import Principal

router = APIRouter(prefix="/api/v1", tags=["katalog"])


@router.get("/modules")
def list_modules(user: Principal = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    izinli = etkin(db, user).izinli
    return ok(
        [
            {
                "key": item.key,
                "title": item.title,
                "kind": item.kind,
                "admin_only": item.admin_only,
                "public": item.public,
                "in_nav": item.in_nav,
                "permission": item.permission,
                "i18n": item.i18n,
                "card_id": item.card_id,
                "box_id": item.box_id,
                "permission_group": item.permission_group,
                "ready": item.ready,
                "registry_id": item.registry_id,
                "registry_status": item.registry_status,
                "modal_id": item.modal_id,
                "table": item.table,
            }
            for item in MODULES
            if can_open(user, item, get, izinli)
        ]
    )


@router.get("/home")
def home(user: Principal = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    izinli = etkin(db, user).izinli
    return ok(
        [
            {"key": card.key, "title": card.title, "i18n": card.i18n, "card_id": card.card_id}
            for card in HOME_CARDS
            if can_open(user, card, get, izinli)
        ]
    )


@router.get("/modules/{key:path}")
def open_module(key: str, user: Principal = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    izinli = etkin(db, user).izinli
    ana, _, alt = key.partition("/")
    try:
        module = get(ana)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Modul yok") from exc
    if alt and alt not in {c.key for c in module.children}:
        raise HTTPException(status_code=404, detail="Modul yok")
    if not can_open(user, module, get, izinli) or (alt and izinli is not None and key not in izinli):
        audit_log.remember(actor=user.username, action="open", outcome="deny", module_key=key, detail="forbidden")
        raise HTTPException(status_code=403, detail="Yetki yok")
    return ok({"module": key})
