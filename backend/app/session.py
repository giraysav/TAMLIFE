# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
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

CSRF_HEADER = "x-csrf-token"
MAX_SESSIONS = 2000
HAREKET_BASLIGI = "x-son-hareket-sn"
HAREKET_ESIGI_SN = 120  # arayuz 2 dakikada bir canli tutma yapar; bundan eski hareketle gelen istek oturumu uzatmaz


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
    """Tek kapanma nedeni: bosta sure. session_max_hours > 0 verilirse mutlak omur siniri da uygulanir (varsayilan 0 = yok)."""
    settings = get_settings()
    if now - entry.last_seen > settings.session_idle_minutes * 60:
        return True
    return settings.session_max_hours > 0 and now - entry.created > settings.session_max_hours * 3600


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
    yol = settings.cookie_path
    response.set_cookie(settings.cookie_name, token, httponly=True, samesite="strict", secure=secure, path=yol)
    response.set_cookie(settings.csrf_cookie_name, csrf, httponly=False, samesite="strict", secure=secure, path=yol)


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


def _kullanici_etkin(request: Request) -> bool:
    """Istek kullanicinin gercek hareketinden mi geliyor? Arayuz her istege `X-Son-Hareket-Sn` (son tus/tik/kaydirmadan beri sn) yazar;
    arka plan yoklamasi (otomatik yenilenen sorgular) bosta bir sekmeyi sunucuda sonsuza dek canli tutmasin diye bosta olan istek
    oturumu uzatmaz. Baslik yoksa (betik, test, eski istemci) istek etkin sayilir."""
    ham = request.headers.get(HAREKET_BASLIGI)
    if ham is None:
        return True
    try:
        return 0 <= int(ham) < HAREKET_ESIGI_SN
    except ValueError:
        return True


def current_user(request: Request) -> Principal | None:
    entry = _entry(request, touch=_kullanici_etkin(request))
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
    response.delete_cookie(settings.cookie_name, path=settings.cookie_path)
    response.delete_cookie(settings.csrf_cookie_name, path=settings.cookie_path)


def aktif_oturumlar() -> list[dict[str, object]]:
    """Suresi dolmamis oturumlar (kimlik bilgisi/belirteç DONMEZ): kullanici, rol, yas ve bosta sure (sn)."""
    simdi = _now()
    with _LOCK:
        return [
            {
                "username": e.principal.username,
                "role": e.principal.role,
                "is_admin": e.principal.is_admin,
                "age_s": int(simdi - e.created),
                "idle_s": int(simdi - e.last_seen),
            }
            for e in _STORE.values()
            if not _expired(e, simdi)
        ]


def kullanici_oturumlarini_kapat(username: str) -> int:
    """Kullanicinin tum oturumlarini sunucuda dusurur (rol degisikligi / supheli etkinlik). Donus: kapatilan adet."""
    with _LOCK:
        kapanacak = [t for t, e in _STORE.items() if e.principal.username == username]
        for t in kapanacak:
            _STORE.pop(t, None)
    return len(kapanacak)
