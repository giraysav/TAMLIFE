"""Login throttling, response headers, Origin and CSRF gate."""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.session import csrf_valid

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
LOGIN_PATH = "/api/v1/session/login"


class LoginLimiter:
    """Counts failures per (ip, username) and per ip. Locks for lockout_seconds."""

    def __init__(self) -> None:
        self._fails: dict[str, deque[float]] = {}
        self._locked: dict[str, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _keys(ip: str, username: str) -> tuple[str, str]:
        return f"u:{ip}:{username.lower()}", f"i:{ip}"

    def retry_after(self, ip: str, username: str) -> int:
        now = time.monotonic()
        with self._lock:
            waits = [self._locked[k] - now for k in self._keys(ip, username) if self._locked.get(k, 0) > now]
        return int(max(waits)) + 1 if waits else 0

    def failed(self, ip: str, username: str) -> None:
        settings = get_settings()
        now = time.monotonic()
        with self._lock:
            for key in self._keys(ip, username):
                limit = settings.login_max_attempts * (4 if key.startswith("i:") else 1)
                window = self._fails.setdefault(key, deque())
                window.append(now)
                while window and now - window[0] > settings.login_window_seconds:
                    window.popleft()
                if len(window) >= limit:
                    self._locked[key] = now + settings.login_lockout_seconds
                    window.clear()
            if len(self._fails) > 5000:
                self._fails.clear()

    def succeeded(self, ip: str, username: str) -> None:
        with self._lock:
            key = self._keys(ip, username)[0]
            self._fails.pop(key, None)
            self._locked.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._fails.clear()
            self._locked.clear()


limiter = LoginLimiter()


def client_ip(request: Request) -> str:
    """Gercek istemci IP'si. X-Forwarded-For yalniz guvenilir proxy'den gelirse okunur."""
    peer = request.client.host if request.client else "-"
    if peer in get_settings().trusted_proxies_list:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return peer


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    host = request.headers.get("host", "")
    allowed = {f"http://{host}", f"https://{host}"} | set(get_settings().allowed_origins_list)
    return origin in allowed


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def gate(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method in UNSAFE:
            if not _same_origin(request):
                return JSONResponse({"detail": "Kaynak reddedildi"}, status_code=403)
            if request.url.path != LOGIN_PATH and not csrf_valid(request):
                return JSONResponse({"detail": "CSRF dogrulanamadi"}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        return response
