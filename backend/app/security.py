"""Login throttling, response headers, Origin and CSRF gate."""

from __future__ import annotations

import threading
import time
from collections import deque
from itertools import islice

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.session import csrf_valid

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
LOGIN_PATH = "/api/v1/session/login"
DEMO_YAZMA_IZNI = {"/api/v1/session/misafir", "/api/v1/session/logout"}
CSRF_MUAF = {LOGIN_PATH, "/api/v1/session/misafir"}  # oturum henuz yok; Origin denetimi yine uygulanir
# Derlenmis arayuz (HTML/JS/CSS): ayni kaynaktan yukleme, satir ici betik yok. API cevaplari 'none' kalir.
UI_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


class LoginLimiter:
    """Counts failures per (ip, username) and per ip. Locks for lockout_seconds.

    Budama amortize: esik her budamadan sonra kalan anahtar sayisinin iki katina cikar (ya da pencere dolunca bir kez),
    boylece her deneme O(1) kalir. Eskiden esik ustunde her deneme tum sozlugu yeniden kuruyordu: 20 bin sahte IP 184 sn CPU,
    karesel (tests/test_yuk_sinirlayici.py). SERT_SINIR bellek tavanidir; asilirsa en eski sayaclar atilir, kilitler atilmaz.
    """

    AZAMI_ANAHTAR = 5000
    SERT_SINIR = 200_000

    def __init__(self) -> None:
        self._fails: dict[str, deque[float]] = {}
        self._locked: dict[str, float] = {}
        self._lock = threading.Lock()
        self._esik = self.AZAMI_ANAHTAR
        self._son_buda = time.monotonic()

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
                limit = settings.login_max_attempts * (settings.login_ip_carpani if key.startswith("i:") else 1)
                window = self._fails.setdefault(key, deque())
                window.append(now)
                while window and now - window[0] > settings.login_window_seconds:
                    window.popleft()
                if len(window) >= limit:
                    self._locked[key] = now + settings.login_lockout_seconds
                    window.clear()
            boy = len(self._fails) + len(self._locked)
            if boy > self._esik or (boy > self.AZAMI_ANAHTAR and now - self._son_buda > settings.login_window_seconds):
                self._buda(now, settings.login_window_seconds)

    def _buda(self, now: float, pencere: float) -> None:
        """Yalniz suresi gecmis kayitlar atilir: toplu temizlik kilidi acmasin, sozluk sinirsiz buyumesin."""
        self._fails = {k: w for k, w in self._fails.items() if w and now - w[-1] <= pencere}
        self._locked = {k: t for k, t in self._locked.items() if t > now}
        if len(self._fails) > self.SERT_SINIR:  # sozluk ekleme sirasi ~ ilk deneme zamani: en eskiler atilir
            self._fails = dict(islice(self._fails.items(), len(self._fails) - self.SERT_SINIR // 2, None))
        self._esik = max(self.AZAMI_ANAHTAR, 2 * (len(self._fails) + len(self._locked)))
        self._son_buda = now

    def succeeded(self, ip: str, username: str) -> None:
        with self._lock:
            key = self._keys(ip, username)[0]
            self._fails.pop(key, None)
            self._locked.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._fails.clear()
            self._locked.clear()
            self._esik = self.AZAMI_ANAHTAR


limiter = LoginLimiter()


def client_ip(request: Request) -> str:
    """Gercek istemci IP'si. X-Forwarded-For yalniz guvenilir proxy'den gelirse sagdan ilk guvenilmeyen adres alinir (istemcinin
    basa yazdigi sahte adres secilmez)."""
    peer = request.client.host if request.client else "-"
    guvenilir = get_settings().trusted_proxies_list
    if peer not in guvenilir:
        return peer
    for adres in reversed(request.headers.get("x-forwarded-for", "").split(",")):
        adres = adres.strip()
        if adres and adres not in guvenilir:
            return adres
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
            if get_settings().demo and request.url.path not in DEMO_YAZMA_IZNI:  # demo ornegi SALT OKUNUR: hicbir yazma gecmez
                return JSONResponse({"detail": "Demo ortami salt okunurdur (örnek veriler değiştirilemez)."}, status_code=403)
            if not _same_origin(request):
                return JSONResponse({"detail": "Kaynak reddedildi"}, status_code=403)
            if request.url.path not in CSRF_MUAF and not csrf_valid(request):
                return JSONResponse({"detail": "CSRF dogrulanamadi"}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        arayuz = not request.url.path.startswith("/api/") and response.headers.get("content-type", "").startswith(
            ("text/html", "text/css", "text/javascript", "application/javascript", "image/")
        )
        response.headers.setdefault("Content-Security-Policy", UI_CSP if arayuz else "default-src 'none'; frame-ancestors 'none'")
        return response
