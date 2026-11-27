# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Sunucu metinlerinin dili: X-Dil basligi (tr varsayilan, en), ekip cumleleri ve saglik kontrolleri."""

from __future__ import annotations

from app import dil
from app.ekip import servis as ekip
from tests_v35.conftest import login_ok


def _kontroller(client, baslik: dict[str, str]) -> dict[str, str]:
    r = client.get("/api/v1/yonetim/ozet", headers=baslik)
    assert r.status_code == 200, r.text
    return {k["id"]: k["ayrinti"] for k in r.json()["data"]["saglik"]["kontroller"]}


def test_saglik_metni_istegin_dilinde(client):
    login_ok(client)
    tr = _kontroller(client, {})
    en = _kontroller(client, {"X-Dil": "en"})
    assert tr["veritabani"].startswith("Yanıt ")
    assert en["veritabani"].startswith("Response ")
    assert "aktif oturum" in tr["oturum"] and "active sessions" in en["oturum"]
    assert _kontroller(client, {"X-Dil": "xx"})["veritabani"].startswith("Yanıt ")  # bilinmeyen dil: Turkce


def test_ekip_cumlesi_ingilizce():
    satir = {
        "ad": "Ayşe",
        "bugun": "yillik_izin",
        "bugun_ad": "Yıllık İzin",
        "musteri": 2,
        "rapor_beklenen": 2,
        "rapor_atilan": 1,
        "uyum": 40,
        "alarm": 0,
        "sikayet": 0,
        "talep": 0,
        "kapanan": 0,
        "final_skor": 72.5,
        "online": 0,
        "yuzyuze": 0,
        "proje_acik": 0,
        "proje_kapanan": 0,
        "onemli_isler": [],
        "risk": 0,
    }
    assert ekip.kisi_cumlesi(satir).startswith("Ayşe, bugün yıllık izin.")
    assert "72,5" in ekip.kisi_cumlesi(satir)
    jeton = dil.ayarla("en")
    try:
        cumle = ekip.kisi_cumlesi(satir)
        assert cumle.startswith("Ayşe is on annual leave today.")
        assert "72.5" in cumle and "compliance" in cumle
        assert ekip.ekip_cumlesi([satir], risk_var=True) == "1 TAMs have critical report compliance (below 50%)."
    finally:
        dil.geri_al(jeton)
