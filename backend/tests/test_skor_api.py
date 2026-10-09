"""Final skor uclari (/api/v1/skor): kriter surumleri, onizleme/uygulama, tek skor, talep, personel/istirak."""

import pytest
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser, Customer, ScoreHistory
from tests.conftest import login_ok

KRITER = [{"title": "Musteri segmenti", "weight": 100, "b50": "SMB", "b70": "MA", "b100": "SA, PA, WHOLESALE"}]


@pytest.fixture
def veri(client):
    with Session(engine()) as db:
        db.add_all([AppUser(id=1, username="admin", display_name="Admin", role="admin", is_admin=True), AppUser(id=2, username="ayse", display_name="Ayse", role="TeamMember")])
        db.flush()
        db.add_all(
            [
                Customer(id=1, external_key="s1", name="Cati MA", segment="MA", owner_id=1),
                Customer(id=2, external_key="s2", name="Cati SMB", segment="SMB", owner_id=2),
                Customer(id=3, external_key="s3", name="Cati Segmentsiz", segment="", owner_id=1),
                Customer(id=4, external_key="s4", name="Istirak", segment="MA", owner_id=1, parent_id=1),
            ]
        )
        db.commit()
    return client


def test_yetki_matrisi(veri, monkeypatch):
    for yol in ("/api/v1/skor/kriterler/parent", "/api/v1/skor/talepler"):
        assert veri.get(yol).status_code == 401
    hdr = login_ok(veri)
    veri.post("/api/v1/session/logout", headers=hdr)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    hdr = login_ok(veri)
    assert veri.get("/api/v1/skor/kriterler/parent").status_code == 403  # admin
    assert veri.post("/api/v1/skor/toplu/onizleme", json={}, headers=hdr).status_code == 403  # admin/TeamMngr
    assert veri.get("/api/v1/skor/talepler").status_code == 403
    assert veri.put("/api/v1/skor/puanlama-disi", json={"disi": []}, headers=hdr).status_code == 403


def test_kriter_surumleri_onizleme_ve_toplu_uygulama(veri):
    hdr = login_ok(veri)
    assert veri.get("/api/v1/skor/kriterler/parent").json()["data"] == {"scope": "parent", "version": 0, "criteria": []}
    assert veri.get("/api/v1/skor/kriterler/yok").status_code == 404
    assert veri.put("/api/v1/skor/kriterler/parent", json={"criteria": [{"title": "", "weight": 1}]}, headers=hdr).status_code == 400
    assert veri.put("/api/v1/skor/kriterler/parent", json={"criteria": [{"title": "x", "weight": -1}]}, headers=hdr).status_code == 400
    r = veri.put("/api/v1/skor/kriterler/parent", json={"criteria": KRITER}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["version"] == 1
    # kriter degisince cati musteriler otomatik hesaplanir: segmenti olmayan atlanir (eksik kriter)
    uyg = r.json()["data"]["uygulama"]
    assert {u["id"]: u["skor"] for u in uyg["uygulanan"]} == {1: 70.0, 2: 50.0}
    assert [a["id"] for a in uyg["atlanan"]] == [3] and "eksik kriter" in uyg["atlanan"][0]["neden"]
    assert veri.put("/api/v1/skor/kriterler/parent", json={"criteria": KRITER}, headers=hdr).json()["data"]["version"] == 2
    assert veri.get("/api/v1/skor/kriterler/parent").json()["data"]["version"] == 2
    on = veri.post("/api/v1/skor/toplu/onizleme", json={}, headers=hdr).json()["data"]
    assert on["ozet"] == {"toplam": 3, "hazir": 2} and [m["id"] for m in on["musteriler"]] == [1, 2, 3]  # istirak yok
    assert {m["id"]: m["mevcut"] for m in on["musteriler"]}[1] == 70.0
    only2 = veri.post("/api/v1/skor/toplu/onizleme", json={"tam_id": 2}, headers=hdr).json()["data"]
    assert [m["id"] for m in only2["musteriler"]] == [2]
    # toplu uygula: istirak ve olmayan kimlik atlanir
    r = veri.post("/api/v1/skor/toplu/uygula", json={"customer_ids": [1, 4, 99]}, headers=hdr).json()["data"]
    assert [u["id"] for u in r["uygulanan"]] == [1] and {a["id"] for a in r["atlanan"]} == {4, 99}
    assert veri.post("/api/v1/skor/toplu/uygula", json={"customer_ids": []}, headers=hdr).status_code == 422
    with Session(engine()) as db:
        assert db.query(ScoreHistory).filter_by(customer_id=1, source="kriter_degisikligi").count() == 1


def test_tek_musteri_skoru_kurallari(veri):
    hdr = login_ok(veri)
    put = lambda mid, **g: veri.put(f"/api/v1/skor/musteri/{mid}", json=g, headers=hdr)
    assert put(1, tam_id=1, score=101).status_code == 400  # 0-100
    assert put(1, tam_id=1, score=-1).status_code == 400
    assert put(1, tam_id=1, score="abc").status_code == 400
    assert put(1, tam_id=2, score=50).status_code == 400  # musteri-personel eslesmiyor
    assert put(4, tam_id=1, score=50).status_code == 400  # istirak
    assert put(99, tam_id=1, score=50).status_code == 404
    assert put(1, tam_id=1, score=88.5, detay=[{"baslik": "k", "puan": 70, "agirlik": 10}, {"baslik": "gecersiz", "puan": 55}]).status_code == 200
    with Session(engine()) as db:
        c = db.get(Customer, 1)
        assert c.score == 88.5
        h = db.query(ScoreHistory).filter_by(customer_id=1, source="sayfa").one()
        assert h.score == 88.5 and len(h.detail) == 1  # gecersiz puanli satir atildi


def test_onay_talebi_akisi(veri, monkeypatch):
    hdr = login_ok(veri)
    veri.post("/api/v1/session/logout", headers=hdr)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    hdr_m = login_ok(veri)  # 'admin' kullanici satirina bagli Member: 1 numarali musteri kendisinin
    assert veri.post("/api/v1/skor/talepler", json={"customer_id": 4}, headers=hdr_m).status_code == 400  # istirak
    assert veri.post("/api/v1/skor/talepler", json={"customer_id": 2}, headers=hdr_m).status_code == 403  # baskasinin
    r = veri.post("/api/v1/skor/talepler", json={"customer_id": 1}, headers=hdr_m)
    assert r.status_code == 200
    assert veri.post("/api/v1/skor/talepler", json={"customer_id": 1}, headers=hdr_m).status_code == 400  # tek bekleyen
    assert veri.get("/api/v1/skor/talepler").status_code == 403
    veri.post("/api/v1/session/logout", headers=hdr_m)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "admin")
    hdr = login_ok(veri)
    liste = veri.get("/api/v1/skor/talepler").json()["data"]
    assert liste["count"] == 1 and liste["requests"][0]["customer_id"] == 1
    tid = liste["requests"][0]["id"]
    assert veri.post(f"/api/v1/skor/talepler/{tid}/karar", json={"action": "bekle"}, headers=hdr).status_code == 400
    assert veri.post(f"/api/v1/skor/talepler/{tid}/karar", json={"action": "approve"}, headers=hdr).status_code == 200
    assert veri.post(f"/api/v1/skor/talepler/{tid}/karar", json={"action": "approve"}, headers=hdr).status_code == 404  # zaten sonuclandi
    assert veri.get("/api/v1/skor/talepler").json()["data"]["count"] == 0
    assert veri.post("/api/v1/skor/talepler", json={"customer_id": 1}, headers=hdr).status_code == 200  # onaydan sonra yenisi acilabilir


def test_puanlama_disi_ve_istirak_secimi(veri):
    hdr = login_ok(veri)
    assert veri.put("/api/v1/skor/puanlama-disi", json={"disi": [2, 99]}, headers=hdr).json()["data"] == {"disi": [2]}  # olmayan kimlik atilir
    assert veri.put("/api/v1/skor/puanlama-disi", json={"disi": []}, headers=hdr).json()["data"] == {"disi": []}  # liste tamamen degisir
    assert veri.put("/api/v1/skor/istirak/1/final-dahil", json={"dahil": True}, headers=hdr).status_code == 400  # cati
    assert veri.put("/api/v1/skor/istirak/4/final-dahil", json={"dahil": True}, headers=hdr).json()["data"] == {"dahil": True}
    assert veri.put("/api/v1/skor/istirak/4/final-dahil", json={"dahil": False}, headers=hdr).json()["data"] == {"dahil": False}
