# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Giris, oturum, CSRF / Origin kapisi, yanit basliklari, giris sinirlayici, yetki ve denetim izi."""

from __future__ import annotations

import pytest
from conftest import ORIGIN, PAROLA, giris, kullanici_ekle
from starlette.requests import Request

from app.audit import SecretAuditError, guard
from app.config import get_settings
from app.db import oturum
from app.models import AuditEvent
from app.security import client_ip
from app.yonetim.gunlukler import _hucre
from app.yonetim.kalici_yazici import yazici


def _denetim() -> list[AuditEvent]:
    yazici.bosalt(zorla=True)
    with oturum() as db:
        return list(db.query(AuditEvent).order_by(AuditEvent.id))


def test_saglik_ve_guvenlik_basliklari(istemci):
    r = istemci.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["data"]["service"] == "tamlife"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"


def test_oturumsuz_istek_reddedilir(istemci):
    assert istemci.get("/api/v1/musteri/portfoy").status_code == 401


def test_hatali_parola_reddedilir_ve_denetime_yazilir(istemci):
    kullanici_ekle("tcdeneme")
    r = giris(istemci, "tcdeneme", "yanlis")
    assert r.status_code == 401 and "yanlis" not in r.text
    olay = _denetim()[-1]
    assert (olay.actor, olay.action, olay.outcome) == ("tcdeneme", "login", "deny")
    assert olay.ip == "testclient"  # giris olaylarinda istemci adresi (TestClient sahte istemcisi)


def test_basarili_giris_oturum_cerezi_ve_denetim(istemci):
    kullanici_ekle("tcdeneme")
    r = giris(istemci, "tcdeneme")
    assert r.status_code == 200 and r.json()["data"]["role"] == "TeamMember"
    cerez = r.headers.get_list("set-cookie")
    assert any("httponly" in c.lower() and "samesite=strict" in c.lower() for c in cerez)
    assert istemci.get("/api/v1/session/me").status_code == 200
    assert PAROLA not in str([(e.detail, e.actor) for e in _denetim()])


def test_kayitsiz_kullanici_ad_kapaliyken_giremez(istemci):
    assert giris(istemci, "tcyok").status_code == 401


def test_csrf_basligi_olmadan_yazma_reddedilir(istemci):
    kullanici_ekle("tcdeneme")
    giris(istemci, "tcdeneme")
    istemci.headers.pop("x-csrf-token")
    r = istemci.post("/api/v1/session/logout")
    assert r.status_code == 403


def test_yabanci_origin_reddedilir(istemci):
    kullanici_ekle("tcdeneme")
    giris(istemci, "tcdeneme")
    r = istemci.post("/api/v1/session/logout", headers={"Origin": "https://kotu.example"})
    assert r.status_code == 403
    assert istemci.post("/api/v1/session/logout", headers={"Origin": ORIGIN}).status_code == 200


def test_giris_sinirlayici_kilitler(istemci):
    kullanici_ekle("tcdeneme")
    for _ in range(get_settings().login_max_attempts):
        assert giris(istemci, "tcdeneme", "yanlis").status_code == 401
    r = giris(istemci, "tcdeneme")  # parola dogru olsa da kilitli
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_personel_yonetim_uclarina_giremez(istemci):
    kullanici_ekle("tcdeneme")
    giris(istemci, "tcdeneme")
    assert istemci.get("/api/v1/yonetim/gunlukler").status_code == 403
    assert istemci.get("/api/v1/yonetim/gunlukler/kullanicilar").status_code == 403


def test_denetim_agaci_kullaniciya_gore_ve_son_giris_ip(istemci):
    kullanici_ekle("yonetici", "admin")
    kullanici_ekle("TCdeneme")
    giris(istemci, "TCdeneme", "yanlis")
    giris(istemci, "TCdeneme")
    istemci.cookies.clear()
    istemci.headers.pop("x-csrf-token", None)
    giris(istemci, "yonetici")
    r = istemci.get("/api/v1/yonetim/gunlukler/kullanicilar").json()["data"]
    satir = next(k for k in r["kullanicilar"] if k["kullanici"].lower() == "tcdeneme")
    assert (satir["olay"], satir["red"]) == (2, 1)
    assert satir["son_giris"] and satir["son_giris_ip"] == "testclient"
    olaylar = istemci.get("/api/v1/yonetim/gunlukler", params={"kullanici": "tcdeneme"}).json()["data"]
    assert olaylar["toplam"] == 2 and {s["sonuc"] for s in olaylar["satirlar"]} == {"allow", "deny"}


@pytest.mark.parametrize("deger", ["=cmd|' /C calc'!A0", "+1+1", "-2", "@SUM(A1)", "\tx"])
def test_csv_formul_enjeksiyonu_etkisiz(deger):
    assert _hucre(deger).startswith("'")
    assert _hucre("normal metin") == "normal metin"


def test_denetim_gizli_alan_kabul_etmez():
    with pytest.raises(SecretAuditError):
        guard("password=gizli")
    assert guard("x" * 900) == "x" * 500


def _istek(kaynak: str, xff: str) -> Request:
    return Request({"type": "http", "client": (kaynak, 1), "headers": [(b"x-forwarded-for", xff.encode())] if xff else []})


def test_istemci_ipsi_yalniz_guvenilen_vekilden_xff(monkeypatch):
    assert client_ip(_istek("10.0.0.9", "1.2.3.4")) == "10.0.0.9"  # guvenilmeyen kaynak: XFF yok sayilir
    monkeypatch.setenv("TAMLIFE_TRUSTED_PROXIES", "127.0.0.1")
    assert client_ip(_istek("127.0.0.1", "1.2.3.4")) == "1.2.3.4"
    assert client_ip(_istek("127.0.0.1", "")) == "127.0.0.1"


def test_telif_bilgisi_kodda_ve_saglik_ucunda(istemci):
    import app

    assert app.__author__ == "Giray Sav"
    assert "Giray Sav" in istemci.get("/api/v1/health").json()["data"]["copyright"]
