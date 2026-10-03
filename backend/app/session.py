"""HttpOnly session cookie. The cookie value is not returned in JSON."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import Request, Response

from app.config import get_settings


@dataclass(frozen=True)
class Principal:
    username: str
    role: str
    is_admin: bool


_STORE: dict[str, Principal] = {}


def login(response: Response, principal: Principal) -> None:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    _STORE[token] = principal
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def current_user(request: Request) -> Principal | None:
    settings = get_settings()
    token = request.cookies.get(settings.cookie_name)
    if not token:
        return None
    return _STORE.get(token)


def logout(request: Request, response: Response) -> None:
    settings = get_settings()
    token = request.cookies.get(settings.cookie_name)
    if token:
        _STORE.pop(token, None)
    response.delete_cookie(settings.cookie_name, path="/")
