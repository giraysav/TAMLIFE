"""Server-side session. HttpOnly cookie, idle and absolute expiry, CSRF token.

The cookie value is never returned in JSON. A new token is issued on every login,
so a token seen before login cannot be reused afterwards (no fixation).
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

from fastapi import Request, Response

from app.config import get_settings

CSRF_COOKIE = "tamlife_csrf"
CSRF_HEADER = "x-csrf-token"
MAX_SESSIONS = 2000


@dataclass(frozen=True)
class Principal:
    username: str
    role: str
    is_admin: bool


@dataclass
class _Entry:
    principal: Principal
    csrf: str
    created: float
    last_seen: float = field(default=0.0)


_STORE: dict[str, _Entry] = {}
_LOCK = threading.Lock()


def _now() -> float:
    return time.monotonic()


def _expired(entry: _Entry, now: float) -> bool:
    settings = get_settings()
    return (
        now - entry.last_seen > settings.session_idle_minutes * 60
        or now - entry.created > settings.session_max_hours * 3600
    )


def _purge(now: float) -> None:
    for token in [t for t, e in _STORE.items() if _expired(e, now)]:
        _STORE.pop(token, None)
    while len(_STORE) >= MAX_SESSIONS:
        oldest = min(_STORE, key=lambda t: _STORE[t].last_seen)
        _STORE.pop(oldest, None)


def login(request: Request, response: Response, principal: Principal) -> None:
    settings = get_settings()
    now = _now()
    old = request.cookies.get(settings.cookie_name)
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    with _LOCK:
        if old:
            _STORE.pop(old, None)
        _purge(now)
        _STORE[token] = _Entry(principal=principal, csrf=csrf, created=now, last_seen=now)
    secure = settings.cookie_secure_effective
    response.set_cookie(settings.cookie_name, token, httponly=True, samesite="strict", secure=secure, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, samesite="strict", secure=secure, path="/")


def _entry(request: Request, touch: bool) -> _Entry | None:
    token = request.cookies.get(get_settings().cookie_name)
    if not token:
        return None
    now = _now()
    with _LOCK:
        entry = _STORE.get(token)
        if entry is None:
            return None
        if _expired(entry, now):
            _STORE.pop(token, None)
            return None
        if touch:
            entry.last_seen = now
        return entry


def current_user(request: Request) -> Principal | None:
    entry = _entry(request, touch=True)
    return entry.principal if entry else None


def csrf_valid(request: Request) -> bool:
    """Header must equal the server-side token of this session (not only the cookie)."""
    entry = _entry(request, touch=False)
    sent = request.headers.get(CSRF_HEADER, "")
    return bool(entry and sent and secrets.compare_digest(sent, entry.csrf))


def logout(request: Request, response: Response) -> None:
    settings = get_settings()
    token = request.cookies.get(settings.cookie_name)
    if token:
        with _LOCK:
            _STORE.pop(token, None)
    response.delete_cookie(settings.cookie_name, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def reset_for_tests() -> None:
    with _LOCK:
        _STORE.clear()
