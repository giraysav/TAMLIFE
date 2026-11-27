# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Sunum senkronu (2026-10-15 kullanici bildirimi: "ceyrek sunuma akan veriler hatali; once karsilastirsin, guncel degilse elle
tetiklenince tum verileri sync etsin"). Gecmis ceyregin dondurulmus goruntusu sonradan girilen veriyle karsilastirilir ve yenilenir."""

from __future__ import annotations

import dataclasses

import pytest
from sqlalchemy.orm import Session

from app.db import engine
from app.models import Customer
from app.sunum import servis
from tests_v35.conftest import login_ok
from tests_v35.test_sunum import CEYREK, YIL, _cikis, _donem, _geri, _giris, _kaynak_sec, _sunum_sayisi, sunum_verisi

URL = "/api/v1/sunum"


@pytest.fixture
def veri(client):
    return sunum_verisi(client)


def _karsilastir(client, yil, ceyrek) -> dict:
    r = client.get(f"{URL}/karsilastir", params={"yil": yil, "ceyrek": ceyrek})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _durumlar(v: dict) -> dict[str, str]:
    return {s["kaynak"]: s["durum"] for s in v["kaynaklar"]}


def test_gecmis_ceyrek_farki_bulunur_ve_senkronla_yenilenir(veri, monkeypatch):
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, ["portfoy", "takvim"])
    onceki = _geri(YIL, CEYREK, 1)

    # hic goruntulenmemis gecmis ceyrek: eksik; karsilastirma hicbir sey yazmaz
    v = _karsilastir(veri, *onceki)
    assert _durumlar(v) == {"portfoy": "eksik", "takvim": "eksik"} and v["senkron_gerekli"] is True and _sunum_sayisi() == 0
    _donem(veri, *onceki)  # ilk goruntuleme dondurur
    v = _karsilastir(veri, *onceki)
    assert _durumlar(v) == {"portfoy": "guncel", "takvim": "guncel"} and v["senkron_gerekli"] is False

    # dondurulduktan sonra girilen veri: farkli + hangi KPI degisti
    with Session(engine()) as db:
        db.add(Customer(id=4, external_key="t-c", name="Gama", segment="MA", owner_id=1))
        db.commit()
    v = _karsilastir(veri, *onceki)
    portfoy = next(s for s in v["kaynaklar"] if s["kaynak"] == "portfoy")
    assert portfoy["durum"] == "farkli" and {"ad": "Çatı müşteri", "eski": 2, "yeni": 3} in portfoy["farklar"]
    assert _durumlar(v)["takvim"] == "guncel" and v["sayilar"]["farkli"] == 1

    # yetkisiz senkron reddedilir
    _cikis(veri, hdr)
    h = _giris(veri, monkeypatch, "TeamMember")
    assert _karsilastir(veri, *onceki)["yonetebilir"] is False
    assert veri.post(f"{URL}/senkron", json={"yil": onceki[0], "ceyrek": onceki[1]}, headers=h).status_code == 403
    _cikis(veri, h)
    hdr = _giris(veri, monkeypatch, "admin")

    r = veri.post(f"{URL}/senkron", json={"yil": onceki[0], "ceyrek": onceki[1]}, headers=hdr)
    assert r.status_code == 200, r.text
    sonuc = r.json()["data"]
    assert sonuc["yenilenen"] == ["portfoy"] and sonuc["sonra"]["senkron_gerekli"] is False
    portfoy = next(o for o in _donem(veri, *onceki)["ogeler"] if o["kaynak"] == "portfoy")
    assert portfoy["gonderen"] == "Admin Kisi" and next(k["deger"] for k in portfoy["veri"]["kpi"] if k["ad"] == "Çatı müşteri") == 3
    # ikinci senkron yenileyecek bir sey bulmaz
    assert veri.post(f"{URL}/senkron", json={"yil": onceki[0], "ceyrek": onceki[1]}, headers=hdr).json()["data"]["yenilenen"] == []


def test_bu_ceyrek_canli_gelecek_ve_eski_anlik_kapsam_disi(veri):
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, ["portfoy", "takvim"])
    assert _durumlar(_karsilastir(veri, YIL, CEYREK)) == {"portfoy": "canli", "takvim": "canli"}
    assert _durumlar(_karsilastir(veri, YIL + 1, CEYREK)) == {"portfoy": "kapsam_disi", "takvim": "kapsam_disi"}
    assert _durumlar(_karsilastir(veri, *_geri(YIL, CEYREK, 2)))["portfoy"] == "kapsam_disi"
    # bu ceyrekte elle sabitlenmis ve sonra degisen kaynak farkli gorunur
    veri.post(f"{URL}/gonder", json={"kaynak": "portfoy", "yil": YIL, "ceyrek": CEYREK, "gonder": True}, headers=hdr)
    with Session(engine()) as db:
        db.add(Customer(id=4, external_key="t-c", name="Gama", segment="MA", owner_id=1))
        db.commit()
    assert _durumlar(_karsilastir(veri, YIL, CEYREK))["portfoy"] == "farkli"
    assert veri.post(f"{URL}/senkron", json={"yil": YIL, "ceyrek": CEYREK}, headers=hdr).json()["data"]["yenilenen"] == ["portfoy"]


def test_onayli_ceyrek_karsilastirilir_ama_senkronlanmaz(veri):
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, ["portfoy"])
    veri.post(f"{URL}/onay", json={"yil": YIL, "ceyrek": CEYREK, "onay": True}, headers=hdr)
    v = _karsilastir(veri, YIL, CEYREK)
    assert v["onayli"] is True and _durumlar(v) == {"portfoy": "guncel"}
    with Session(engine()) as db:
        db.add(Customer(id=4, external_key="t-c", name="Gama", segment="MA", owner_id=1))
        db.commit()
    assert _durumlar(_karsilastir(veri, YIL, CEYREK)) == {"portfoy": "farkli"}
    r = veri.post(f"{URL}/senkron", json={"yil": YIL, "ceyrek": CEYREK}, headers=hdr)
    assert r.status_code == 409 and "onayı kaldırın" in r.json()["detail"]


def test_hatali_kaynak_ve_oynak_zaman_damgasi(veri, monkeypatch):
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, ["onedesk", "portfoy"])

    def bozuk(*_):
        raise RuntimeError("kaynak bozuk")

    monkeypatch.setitem(servis.KAYNAKLAR, "onedesk", dataclasses.replace(servis.KAYNAKLAR["onedesk"], uret=bozuk))
    v = _karsilastir(veri, YIL, CEYREK)
    hata = next(s for s in v["kaynaklar"] if s["kaynak"] == "onedesk")
    assert hata["durum"] == "hata" and len(hata["kayit_no"]) == 8 and v["sayilar"]["hata"] == 1
    # tanitim olcum zamani her hesapta degisir: karsilastirmada sayilmaz
    assert servis._iz({"olcum": "2026-10-15T09:00:00", "kod": {"satir": 5}}) == servis._iz({"kod": {"satir": 5}, "olcum": "2026-10-16T10:00:00"})
    assert servis._iz({"a": (1, 2)}) == servis._iz({"a": [1, 2]})
