"""FastAPI shell for directory slots, the panel schema, and ingest slots."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from app.ad_fake import directory
from app.audit import SecretAuditError, audit_log
from app.authz import can_open
from app.catalog import HOME_CARDS, MODULES, get
from app.config import get_settings
from app.ingest import status as ingest_status
from app.models import TABLE_OWNER
from app.session import Principal, current_user, login, logout


class LoginBody(BaseModel):
    username: str
    password: str


def create_app() -> FastAPI:
    app = FastAPI(title="TAMLIFE", version="3.5.0")

    @app.get("/api/v1/health")
    def health() -> dict:
        settings = get_settings()
        return {
            "status": "success",
            "data": {
                "service": "tamlife",
                "database": "postgresql",
                "database_configured": settings.database_url.startswith("postgresql"),
            },
        }

    @app.get("/api/v1/directory")
    def directory_slot() -> dict:
        return {"status": "success", "data": directory.slot()}

    @app.post("/api/v1/session/login")
    def open_session(body: LoginBody, response: Response) -> dict:
        found = directory.authenticate(body.username, body.password)
        if found is None:
            raise HTTPException(status_code=401, detail="Giris reddedildi")
        login(response, Principal(found.username, found.role, found.is_admin))
        try:
            audit_log.remember(actor=found.username, action="login", outcome="allow", detail="local")
        except SecretAuditError:
            pass
        return {"status": "success", "data": {"username": found.username, "role": found.role}}

    @app.post("/api/v1/session/logout")
    def close_session(request: Request, response: Response) -> dict:
        user = current_user(request)
        logout(request, response)
        if user is not None:
            audit_log.remember(actor=user.username, action="logout", outcome="allow")
        return {"status": "success", "data": {}}

    @app.get("/api/v1/modules")
    def list_modules(request: Request) -> dict:
        _require_user(request)
        data = [
            {
                "key": item.key,
                "title": item.title,
                "kind": item.kind,
                "admin_only": item.admin_only,
                "public": item.public,
                "in_nav": item.in_nav,
            }
            for item in MODULES
        ]
        return {"status": "success", "data": data}

    @app.get("/api/v1/home")
    def home(request: Request) -> dict:
        _require_user(request)
        data = [
            {"key": card.key, "title": card.title, "i18n": card.i18n, "card_id": card.card_id}
            for card in HOME_CARDS
        ]
        return {"status": "success", "data": data}

    @app.get("/api/v1/modules/{key}")
    def open_module(key: str, request: Request) -> dict:
        user = _require_user(request)
        try:
            module = get(key)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Modul yok") from exc
        if not can_open(user, module, get):
            audit_log.remember(
                actor=user.username,
                action="open",
                outcome="deny",
                module_key=key,
                detail="forbidden",
            )
            raise HTTPException(status_code=403, detail="Yetki yok")
        return {"status": "success", "data": {"module": key}}

    @app.get("/api/v1/sources")
    def sources(request: Request) -> dict:
        _require_user(request)
        return {"status": "success", "data": ingest_status()}

    @app.get("/api/v1/schema")
    def schema(request: Request) -> dict:
        _require_user(request)
        rows = [{"table": name, "owner": owner} for name, owner in sorted(TABLE_OWNER.items())]
        return {"status": "success", "data": rows}

    return app


def _require_user(request: Request) -> Principal:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Oturum gerekli")
    return user


app = create_app()
