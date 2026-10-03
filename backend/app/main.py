"""FastAPI shell for directory slots, the panel schema, and ingest slots."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.ad import directory
from app.admin import overview as admin_overview
from app.audit import SecretAuditError, audit_log
from app.authz import can_open, is_admin
from app.catalog import HOME_CARDS, MODULES, get
from app.config import get_settings
from app.ingest import status as ingest_status
from app.models import TABLE_OWNER
from app.security import client_ip, limiter
from app.security import install as install_security
from app.session import Principal, current_user, login, logout


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def create_app() -> FastAPI:
    settings = get_settings()
    dev = settings.env in {"dev", "test"}
    app = FastAPI(
        title="TAMLIFE",
        version="3.5.0",
        docs_url="/docs" if dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if dev else None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)
    install_security(app)

    @app.get("/api/v1/health")
    def health() -> dict:
        settings = get_settings()
        return {
            "status": "success",
            "data": {
                "service": "tamlife",
                "database": settings.database_url.split(":", 1)[0].split("+", 1)[0],
                "database_configured": bool(settings.database_url),
            },
        }

    @app.get("/api/v1/directory")
    def directory_slot(request: Request) -> dict:
        _require_admin(request)
        return {"status": "success", "data": directory.slot()}

    @app.post("/api/v1/session/login", response_model=None)
    def open_session(body: LoginBody, request: Request, response: Response) -> Response | dict:
        ip = client_ip(request)
        name = body.username.strip()
        wait = limiter.retry_after(ip, name)
        if wait:
            audit_log.remember(actor=name, action="login", outcome="deny", detail="locked")
            return JSONResponse(
                {"detail": "Cok fazla deneme"}, status_code=429, headers={"Retry-After": str(wait)}
            )
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
        return {"status": "success", "data": {"username": found.username, "role": found.role}}

    @app.post("/api/v1/session/logout")
    def close_session(request: Request, response: Response) -> dict:
        user = current_user(request)
        logout(request, response)
        if user is not None:
            audit_log.remember(actor=user.username, action="logout", outcome="allow")
        return {"status": "success", "data": {}}

    @app.get("/api/v1/session/me")
    def whoami(request: Request) -> dict:
        user = _require_user(request)
        return {"status": "success", "data": {"username": user.username, "role": user.role, "is_admin": user.is_admin}}

    @app.get("/api/v1/modules")
    def list_modules(request: Request) -> dict:
        user = _require_user(request)
        data = [
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
            if can_open(user, item, get)
        ]
        return {"status": "success", "data": data}

    @app.get("/api/v1/home")
    def home(request: Request) -> dict:
        user = _require_user(request)
        data = [
            {"key": card.key, "title": card.title, "i18n": card.i18n, "card_id": card.card_id}
            for card in HOME_CARDS
            if can_open(user, card, get)
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

    @app.get("/api/v1/summary")
    def summary(request: Request) -> dict:
        user = _require_user(request)
        data = {
            "modules": sum(1 for item in MODULES if can_open(user, item, get)),
            "home_cards": sum(1 for card in HOME_CARDS if can_open(user, card, get)),
            "tables": len(TABLE_OWNER),
            "external_sources": len(ingest_status()["sources"]),
        }
        return {"status": "success", "data": data}

    @app.get("/api/v1/sources")
    def sources(request: Request) -> dict:
        _require_admin(request)
        return {"status": "success", "data": ingest_status()}

    @app.get("/api/v1/schema")
    def schema(request: Request) -> dict:
        _require_user(request)
        rows = [{"table": name, "owner": owner} for name, owner in sorted(TABLE_OWNER.items())]
        return {"status": "success", "data": rows}

    @app.get("/api/v1/admin")
    def admin_area(request: Request) -> dict:
        _require_admin(request)
        return {"status": "success", "data": admin_overview()}

    return app


def _require_admin(request: Request) -> Principal:
    user = _require_user(request)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Yetki yok")
    return user


def _require_user(request: Request) -> Principal:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Oturum gerekli")
    return user


app = create_app()
