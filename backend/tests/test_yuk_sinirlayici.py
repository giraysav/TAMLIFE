"""CPU benchmark'lari: giris sinirlayici budamasi, ayar okuma ve oturum deposu. Hizli; her CI kosusunda calisir.

Olculen (2026-10-14, yama 54 oncesi): 20 bin sahte IP ile LoginLimiter.failed toplam 184 sn (karesel: esik ustunde her deneme tum
sozlugu yeniden kuruyordu ve her cagri get_settings ile ~1 ms harciyordu). Sonrasi: 20 bin 0,8 sn, 1 milyon ~40 sn (dogrusal).
TAMLIFE_YUK_IP=1000000 ile milyon IP kosusu acilir (varsayilan 200 bin).
"""

from __future__ import annotations

import os
import time

from app.config import get_settings
from app.security import LoginLimiter
from app.session import _LOCK, _STORE, MAX_SESSIONS, Principal, _Entry, _now

SAHTE_IP = int(os.environ.get("TAMLIFE_YUK_IP", "200000"))


def _sel(s: LoginLimiter, bas: int, adet: int) -> tuple[float, float]:
    """adet farkli sahte IP'den birer hatali giris. Donus: (toplam sn, en kotu tek cagri sn)."""
    en_kotu, t0 = 0.0, time.perf_counter()
    for i in range(bas, bas + adet):
        a = time.perf_counter()
        s.failed(f"10.{i >> 16 & 255}.{i >> 8 & 255}.{i & 255}", f"k{i}")
        en_kotu = max(en_kotu, time.perf_counter() - a)
    return time.perf_counter() - t0, en_kotu


def test_budama_dogrusal_buyur_milyon_ip_cpu_kilitlemez():
    kucuk, _ = _sel(LoginLimiter(), 0, SAHTE_IP // 10)
    s = LoginLimiter()
    buyuk, en_kotu = _sel(s, 0, SAHTE_IP)
    oran = buyuk / kucuk
    print(f"\n{SAHTE_IP} sahte IP: {buyuk:.2f} sn ({buyuk / SAHTE_IP * 1e6:.1f} us/deneme), en kotu cagri {en_kotu * 1000:.0f} ms, "
          f"10x veri {oran:.1f}x sure, anahtar {len(s._fails) + len(s._locked)}")  # fmt: skip
    assert oran < 20, f"budama karesel buyuyor: 10 kat veri {oran:.1f} kat sure"  # dogrusal ~10, karesel ~100
    assert en_kotu < 1.0, f"tek deneme {en_kotu:.2f} sn kilidi tuttu"
    assert len(s._fails) <= LoginLimiter.SERT_SINIR  # bellek tavani (anahtar basina ~1 KB)


def test_sel_sonrasi_mevcut_kilit_korunur(monkeypatch):
    monkeypatch.setenv("TAMLIFE_LOGIN_MAX_ATTEMPTS", "3")
    s = LoginLimiter()
    for _ in range(3):
        s.failed("10.250.0.1", "kurban")
    assert s.retry_after("10.250.0.1", "kurban") > 0
    _sel(s, 0, LoginLimiter.SERT_SINIR + 20_000)  # sert sinir asilir, en eski sayaclar atilir
    assert s.retry_after("10.250.0.1", "kurban") > 0, "sahte IP seli kilidi acti"


def test_get_settings_her_cagrida_yeniden_kurulmaz(monkeypatch):
    get_settings()
    t0 = time.perf_counter()
    for _ in range(10_000):
        get_settings()
    us = (time.perf_counter() - t0) / 10_000 * 1e6
    print(f"\nget_settings {us:.1f} us/cagri")
    assert us < 300, f"get_settings {us:.0f} us: pydantic her cagrida kuruluyor (yama 54 oncesi ~1000 us)"
    monkeypatch.setenv("TAMLIFE_LOGIN_MAX_ATTEMPTS", "7")
    assert get_settings().login_max_attempts == 7  # ortam degisikligi yine yansir


def test_dolu_oturum_deposunda_giris_hizli(client):
    simdi = _now()
    with _LOCK:
        for i in range(MAX_SESSIONS - 1):
            _STORE[f"t{i}"] = _Entry(Principal(f"u{i}", "TeamMember", False), "c", simdi, simdi)
    t0 = time.perf_counter()
    r = client.post("/api/v1/session/login", json={"username": "admin", "password": "test-parola-1"})
    gecen = time.perf_counter() - t0
    print(f"\n{MAX_SESSIONS} oturumda giris {gecen * 1000:.0f} ms (yama 54 oncesi 2,1 sn: her oturum icin get_settings)")
    assert r.status_code == 200 and gecen < 1.0
    assert len(_STORE) <= MAX_SESSIONS
