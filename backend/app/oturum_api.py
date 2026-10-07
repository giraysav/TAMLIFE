"""Oturum uclari: giris, cikis ve /session/me (menu, giris sayfasi, izinler)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ad import directory
from app.audit import SecretAuditError, audit_log
from app.config import get_settings
from app.deps import get_db, require_user
from app.navigation import navigation_for
from app.ortak import ok
from app.rolgorunum import etkin
from app.security import client_ip, limiter
from app.session import Principal, current_user, login, logout

router = APIRouter(prefix="/api/v1/session", tags=["oturum"])


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login", response_model=None)
def open_session(body: LoginBody, request: Request, response: Response) -> Response | dict:
    ip = client_ip(request)
    name = body.username.strip()
    wait = limiter.retry_after(ip, name)
    if wait:
        audit_log.remember(actor=name, action="login", outcome="deny", detail="locked")
        return JSONResponse({"detail": "Cok fazla deneme"}, status_code=429, headers={"Retry-After": str(wait)})
    found = directory.authenticate(name, body.password)
    if found is None:
        limiter.failed(ip, name)
        audit_log.remember(actor=name, action="login", outcome="deny", detail="bad credentials")
        raise HTTPException(status_code=401, detail="Giris reddedildi")
    limiter.succeeded(ip, name)
    login(request, response, Principal(found.username, found.role, found.is_admin))
    try:
        audit_log.remember(actor=found.username, action="login", outcome="allow", detail="local")
    except SecretAuditError:
        pass
    return ok({"username": found.username, "role": found.role})


@router.post("/logout")
def close_session(request: Request, response: Response) -> dict:
    user = current_user(request)
    logout(request, response)
    if user is not None:
        audit_log.remember(actor=user.username, action="logout", outcome="allow")
    return ok({})


@router.get("/me")
def whoami(user: Principal = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    gorunum = etkin(db, user)
    nav = navigation_for(user, gorunum.izinli)
    return ok(
        {
            "username": user.username,
            "role": user.role,
            "is_admin": user.is_admin,
            "idle_timeout_minutes": get_settings().session_idle_minutes,
            "navigation": nav,
            "landing": gorunum.landing,
            "permissions": {"modules": [item["id"] for item in nav]},
        }
    )
