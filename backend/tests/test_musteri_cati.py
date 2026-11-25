"""Musteri kartindan cati/istirak duzenleme; yalniz sentetik musteri verisi."""

import pytest
from sqlalchemy.orm import Session

from app.db import engine
from app.models import Customer
from tests.conftest import login_ok
from tests.test_musteri import veri as veri  # noqa: PLC0414 -- reused pytest fixture, explicit re-export


def test_istirak_cati_degistir_ve_ayir(veri):
    hdr = login_ok(veri)
    yol = "/api/v1/musteri/2"
    assert veri.put(yol + "/kimlik", json={"parent_id": 3}, headers=hdr).status_code == 200
    kart = veri.get(yol).json()["data"]
    assert kart["kimlik"]["cati"]["id"] == 3
    assert kart["kimlik"]["tam_id"] == 1  # iliski degisikligi TAM devri yapmaz
    assert any(c["id"] == 2 for c in veri.get("/api/v1/musteri/3").json()["data"]["kimlik"]["istirakler"])
    assert not veri.get("/api/v1/musteri/1").json()["data"]["kimlik"]["istirakler"]
    assert veri.put(yol + "/kimlik", json={"parent_id": None}, headers=hdr).status_code == 200
    assert veri.get(yol).json()["data"]["kimlik"]["cati"] is None
    assert veri.put(yol + "/kimlik", json={"parent_id": 1}, headers=hdr).status_code == 200
    assert veri.get(yol).json()["data"]["kimlik"]["cati"]["id"] == 1


@pytest.mark.parametrize(
    "parent_id,status", [(2, 400), (999, 404), (True, 400), (0, 400), (-1, 400), ("1", 400), (1.0, 400), (2147483648, 400)]
)
def test_gecersiz_cati_kaydi_degistirmez(veri, parent_id, status):
    hdr = login_ok(veri)
    r = veri.put("/api/v1/musteri/2/kimlik", json={"name": "DEGISMEMELI", "parent_id": parent_id}, headers=hdr)
    assert r.status_code == status
    with Session(engine()) as db:
        c = db.get(Customer, 2)
        assert c.parent_id == 1 and c.name == "Alfa Istirak"


def test_dongu_ve_ic_ice_istirak_yok(veri):
    hdr = login_ok(veri)
    assert veri.put("/api/v1/musteri/1/kimlik", json={"parent_id": 2}, headers=hdr).status_code == 400
    assert veri.put("/api/v1/musteri/3/kimlik", json={"parent_id": 2}, headers=hdr).status_code == 400
    assert veri.put("/api/v1/musteri/1/kimlik", json={"parent_id": 3}, headers=hdr).status_code == 409
    assert veri.get("/api/v1/musteri/1").json()["data"]["kimlik"]["cati"] is None


def test_kartta_yalniz_diger_catilar(veri):
    login_ok(veri)
    kart = veri.get("/api/v1/musteri/1").json()["data"]
    assert [c["id"] for c in kart["cati_secenekleri"]] == [3]
    kart = veri.get("/api/v1/musteri/2").json()["data"]
    assert {c["id"] for c in kart["cati_secenekleri"]} == {1, 3}


def test_admin_ve_csrf_gerekli(veri, monkeypatch):
    hdr = login_ok(veri)
    assert veri.put("/api/v1/musteri/2/kimlik", json={"parent_id": None}).status_code == 403
    veri.post("/api/v1/session/logout", headers=hdr)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    hdr = login_ok(veri)
    # 2026-10-19: personel kendi kartinda cati secer, yalniz kendi catilari arasindan (Beta, id 3, ayse'nin)
    assert veri.put("/api/v1/musteri/2/kimlik", json={"parent_id": 3}, headers=hdr).status_code == 404
    assert 3 not in {c["id"] for c in veri.get("/api/v1/musteri/2").json()["data"]["cati_secenekleri"]}
    assert veri.put("/api/v1/musteri/2/kimlik", json={"parent_id": None}, headers=hdr).status_code == 200
