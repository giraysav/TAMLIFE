"""Cerez oturumu. HttpOnly, SameSite=Lax, Secure ayari. Govdede token yok."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from dataclasses import dataclass, field

from fastapi import APIRouter, FastAPI, Request, Response
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings

SESSION_COOKIE = "tamlife_session"
CSRF_COOKIE = "tamlife_csrf"
CSRF_HEADER = "x-csrf-token"
AKTIF_OTURUM_ZAMAN_ASIMI_DK = 30
AD_OTURUM_BOSTA_DK = 10
AKTIF_OTURUM_TAZELEME_SN = 60
_SAFE = {"GET", "HEAD", "OPTIONS"}


@dataclass
class SessionUser:
    id: int
    username: str
    role: str
    is_admin: bool
    is_active: bool = True
    allowed_modules: dict = field(default_factory=dict)
    is_ad_user: bool = False


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


def authenticate(username: str, password: str, settings: Settings) -> SessionUser | None:
    """Yerel kullanici yalniz dev/test ve ortam degiskeni varken. Sonra sahte AD."""
    if settings.env in {"dev", "test"} and settings.local_user and settings.local_password:
        if _same(username, settings.local_user):
            if not _same(password, settings.local_password):
                return None
            role = settings.local_role or "TeamMember"
            return SessionUser(
                id=1,
                username=settings.local_user,
                role=role,
                is_admin=role == "admin",
                allowed_modules={},
            )
    from app.adapters.ad_fake import directory

    hit = directory.authenticate(username, password)
    if hit is None:
        return None
    return SessionUser(
        id=2,
        username=hit.username,
        role=hit.role,
        is_admin=hit.is_admin,
        is_ad_user=True,
        allowed_modules={},
    )


def _same(left: str, right: str) -> bool:
    return hmac.compare_digest(hashlib.sha256(left.encode()).digest(), hashlib.sha256(right.encode()).digest())


def _cookie_value(header: str, name: str) -> str:
    prefix = name + "="
    for part in header.split(";"):
        item = part.strip()
        if item.startswith(prefix):
            return item[len(prefix):]
    return ""


def _reference() -> str:
    return uuid.uuid4().hex[:8]


class CsrfMiddleware:
    def __init__(self, app) -> None:  # noqa: ANN001
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http" or scope["method"].upper() in _SAFE:
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
        cookie = _cookie_value(headers.get("cookie", ""), CSRF_COOKIE)
        header = headers.get(CSRF_HEADER, "")
        if not cookie or not header or not _same(cookie, header):
            body = (
                '{"status":"error","code":"TL-SRV-01","message":"CSRF dogrulanamadi","reference":"'
                + _reference()
                + '"}'
            ).encode()
            await send({
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def _apply_cookie(response: Response, name: str, value: str, settings: Settings, httponly: bool) -> None:
    response.set_cookie(
        key=name,
        value=value,
        httponly=httponly,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def current_user(request: Request) -> SessionUser | None:
    sid = request.cookies.get(SESSION_COOKIE, "")
    record = request.app.state.sessions.get(sid) if sid else None
    if not record:
        return None
    idle = time.time() - record["seen"]
    limit = (AD_OTURUM_BOSTA_DK if record["user"].is_ad_user else AKTIF_OTURUM_ZAMAN_ASIMI_DK) * 60
    if idle > limit:
        request.app.state.sessions.pop(sid, None)
        return None
    if idle >= AKTIF_OTURUM_TAZELEME_SN:
        record["seen"] = time.time()
    user = record["user"]
    if not user.is_active:
        return None
    return user


router = APIRouter()


@router.get("/csrf")
def issue_csrf(response: Response) -> dict:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    _apply_cookie(response, CSRF_COOKIE, token, settings, httponly=False)
    return {"status": "success", "data": {}}


@router.post("/session")
def open_session(payload: LoginIn, request: Request, response: Response) -> Response:
    settings = get_settings()
    user = authenticate(payload.username, payload.password, settings)
    if user is None or not user.is_active:
        body = {"status": "error", "code": "TL-SRV-01", "message": "Giris basarisiz", "reference": _reference()}
        return Response(content=__import__("json").dumps(body), status_code=401, media_type="application/json")
    sid = secrets.token_urlsafe(32)
    request.app.state.sessions[sid] = {"user": user, "seen": time.time()}
    ok = {"status": "success", "data": {"username": user.username, "role": user.role}}
    result = Response(content=__import__("json").dumps(ok), status_code=200, media_type="application/json")
    _apply_cookie(result, SESSION_COOKIE, sid, settings, httponly=True)
    return result


@router.get("/session")
def read_session(request: Request) -> Response:
    user = current_user(request)
    if user is None:
        body = {"status": "error", "code": "TL-SRV-01", "message": "Oturum gerekli", "reference": _reference()}
        return Response(content=__import__("json").dumps(body), status_code=401, media_type="application/json")
    ok = {"status": "success", "data": {"username": user.username, "role": user.role}}
    return Response(content=__import__("json").dumps(ok), status_code=200, media_type="application/json")


@router.delete("/session")
def close_session(request: Request) -> Response:
    sid = request.cookies.get(SESSION_COOKIE, "")
    if sid:
        request.app.state.sessions.pop(sid, None)
    settings = get_settings()
    result = Response(
        content=__import__("json").dumps({"status": "success", "data": {}}),
        status_code=200,
        media_type="application/json",
    )
    result.delete_cookie(SESSION_COOKIE, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")
    return result


def setup(app: FastAPI) -> None:
    app.state.sessions = {}
    app.state.settings = get_settings()
    app.add_middleware(CsrfMiddleware)
    app.include_router(router, prefix="/api/v1")
