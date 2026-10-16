"""Turkcell'li Takvimi 2026: kurum gunleri herkesin takviminde kaydi olmayan gunde gorunur, kisinin kendi kaydi onceliklidir."""

from __future__ import annotations

from collections import Counter
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser
from app.takvim import servis
from app.takvim.kurum_takvimi import KURUM_GUNLERI


def test_gorseldeki_gunler():
    sayim = Counter(d for d, _, _ in KURUM_GUNLERI.values())
    assert sayim == {"resmi_tatil": 14, "sirket_izni": 13, "arife_tatili": 3}
    assert KURUM_GUNLERI[date(2026, 3, 19)] == ("arife_tatili", "Ramazan Bayramı Arifesi", "sirket_izni")
    assert KURUM_GUNLERI[date(2026, 10, 30)][0] == "sirket_izni" and KURUM_GUNLERI[date(2026, 10, 29)][0] == "resmi_tatil"
    assert {g.month for g, (d, _, d2) in KURUM_GUNLERI.items() if "sirket_izni" in (d, d2)} == {1, 3, 4, 5, 7, 8, 10}


def test_kaydi_olmayan_kisi_kurum_gunlerini_gorur(client):
    ay = servis.ay_oku("hic.girmemis", 2026, 1)
    assert [(g["tarih"], g["durum"], g["kurum"]["aciklama"]) for g in ay["gunler"]] == [
        ("2026-01-01", "resmi_tatil", "Yılbaşı"),
        ("2026-01-02", "sirket_izni", "Şirket tatili"),
    ]
    assert ay["ozet"]["izin_gun"] == 1 and ay["ozet"]["kayitli_gun"] == 0
    assert servis.ay_oku("hic.girmemis", 2026, 3)["ozet"]["izin_gun"] == 0.5  # 19 Mart yarim gun


def test_kendi_kaydi_once_varsayilana_donunce_kurum_gunu(client):
    gun = {"tarih": "2026-01-01", "online": 0, "yuzyuze": 0}
    servis.gun_kaydet("ayse", {**gun, "durum": "calisiyor"})  # tatilde calisti: kayit tutulur
    assert servis.ay_oku("ayse", 2026, 1)["gunler"][0]["durum"] == "calisiyor"
    yanit = servis.gun_kaydet("ayse", {**gun, "durum": "resmi_tatil", "toplanti_ozeti": "", "yapilan_isler": ""})  # Varsayilana don
    assert yanit["durum"] == "resmi_tatil" and yanit["kurum"]["durum"] == "resmi_tatil"
    ay = servis.ay_oku("ayse", 2026, 1)
    assert ay["gunler"][0]["durum"] == "resmi_tatil" and ay["ozet"]["kayitli_gun"] == 0


def test_toplu_izin_tatil_gunlerini_yemez(client):
    assert servis.toplu_kaydet("ayse", {"baslangic": "2026-05-20", "bitis": "2026-05-29", "durum": "yillik_izin"})["atanan"] == 3
    durumlar = {g["tarih"]: g["durum"] for g in servis.ay_oku("ayse", 2026, 5)["gunler"]}
    assert [durumlar[f"2026-05-{g}"] for g in (20, 21, 22, 25, 26, 27)] == ["yillik_izin"] * 3 + [
        "sirket_izni",
        "arife_tatili",
        "resmi_tatil",
    ]


def test_tam_takvim_herkeste_ayni(client):
    with Session(engine()) as db:
        db.add_all([AppUser(username=f"tam{i}", display_name=f"Tam {i}", role="TeamMember", is_admin=False, active=True) for i in (1, 2)])
        db.commit()
        uyeler = servis.ekip(db, 2026, 0)["uyeler"]
    assert [(u["izin_gun"], u["durumlar"]["resmi_tatil"], u["kayitli_gun"]) for u in uyeler] == [(14.5, 14, 0)] * 2


def test_yarim_gun_ikiye_bolunur(client):
    ay = servis.ay_oku("hic.girmemis", 2026, 3)
    (arife,) = [g for g in ay["gunler"] if g["tarih"] == "2026-03-19"]
    assert (arife["durum"], arife["durum2"]) == ("arife_tatili", "sirket_izni")
    assert ay["ozet"]["durumlar"]["arife_tatili"] == 0.5 and ay["ozet"]["durumlar"]["sirket_izni"] == 0.5 and ay["ozet"]["izin_gun"] == 0.5
    # kisi kendi bolunmus gununu girer: yarim yillik izin + yarim calisma = 0,5 izin
    servis.gun_kaydet("ayse", {"tarih": "2026-02-10", "durum": "yillik_izin", "durum2": "calisiyor", "online": 0, "yuzyuze": 0})
    subat = servis.ay_oku("ayse", 2026, 2)
    assert subat["gunler"][0]["durum2"] == "calisiyor" and subat["ozet"]["izin_gun"] == 0.5
    servis.gun_kaydet("ayse", {"tarih": "2026-02-10", "durum": "yillik_izin", "online": 0, "yuzyuze": 0})  # ikinci yari kaldirilir
    assert "durum2" not in servis.ay_oku("ayse", 2026, 2)["gunler"][0]
    with pytest.raises(servis.TakvimHata):
        servis.gun_kaydet("ayse", {"tarih": "2026-02-10", "durum": "raporlu", "durum2": "raporlu"})
    # Varsayilana don: bolunmus kurum gunu kayit tutmaz
    servis.gun_kaydet("ayse", {"tarih": "2026-03-19", "durum": "arife_tatili", "durum2": "sirket_izni", "online": 0, "yuzyuze": 0})
    assert servis.ay_oku("ayse", 2026, 3)["ozet"]["kayitli_gun"] == 0


def test_yil_ozeti_gorunen_durumlar(client):
    servis.gun_kaydet("ayse", {"tarih": "2026-02-10", "durum": "raporlu", "online": 3, "yuzyuze": 1})
    y = servis.ay_oku("ayse", 2026, 6)["yil_ozet"]  # hangi ay acik olursa olsun yil toplami
    g = y["gorunen"]
    assert (y["izin_gun"], y["online"], y["yuzyuze"]) == (15.5, 3, 1)
    assert g["raporlu"] == 1 and g["resmi_tatil"] == 14 and g["arife_tatili"] == 1.5 and g["sirket_izni"] == 14.5
    assert sum(g.values()) == 365 and g["hafta_sonu"] == 104 - 4  # 4 resmi tatil hafta sonuna denk gelir
