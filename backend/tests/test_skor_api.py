"""Final skor uclari (/api/v1/skor): kriter surumleri, onizleme/uygulama, tek skor, talep, personel/istirak."""

import pytest
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser, Customer, ScoreApprovalRequest, ScoreHistory
from app.skor import servis
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


@pytest.mark.parametrize("rol", ["TeamMember", "TeamMngr"])
def test_yetki_matrisi(veri, monkeypatch, rol):
    """Uretim: utilizasyon yalniz_admin - yonetim uclarinin hepsi yalniz admin (TeamMngr dahil 403)."""
    for yol in ("/api/v1/skor/kriterler/parent", "/api/v1/skor/talepler", "/api/v1/skor/agac"):
        assert veri.get(yol).status_code == 401
    hdr = login_ok(veri)
    veri.post("/api/v1/session/logout", headers=hdr)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    hdr = login_ok(veri)
    for yol in ("/api/v1/skor/kriterler/parent", "/api/v1/skor/talepler", "/api/v1/skor/agac", "/api/v1/skor/meta", "/api/v1/skor/siralama", "/api/v1/skor/urun-tutar"):
        assert veri.get(yol).status_code == 403, yol
    assert veri.put("/api/v1/skor/kriterler/parent", json={"criteria": KRITER}, headers=hdr).status_code == 403
    assert veri.post("/api/v1/skor/toplu/onizleme", json={}, headers=hdr).status_code == 403
    assert veri.post("/api/v1/skor/toplu/uygula", json={"customer_ids": [1]}, headers=hdr).status_code == 403
    assert veri.put("/api/v1/skor/musteri/1", json={"tam_id": 1, "score": 50}, headers=hdr).status_code == 403
    assert veri.post("/api/v1/skor/talepler/1/karar", json={"action": "approve"}, headers=hdr).status_code == 403
    assert veri.put("/api/v1/skor/puanlama-disi", json={"disi": []}, headers=hdr).status_code == 403
    assert veri.put("/api/v1/skor/istirak/4/final-dahil", json={"dahil": True}, headers=hdr).status_code == 403
    assert veri.put("/api/v1/skor/urun-tutar/1", content=b"x", headers=hdr).status_code == 403
    assert veri.post("/api/v1/skor/kaynak-onizle", json={"satir": {}}, headers=hdr).status_code == 403
    assert veri.post("/api/v1/skor/talepler", json={"customer_id": 1}, headers=hdr).status_code == 200  # TAM tarafi acik


@pytest.fixture
def otomatik(monkeypatch):
    """Otomatik (veri kaynakli) puanlama: 2026-10-20'den beri kapali (servis.OTOMATIK_PUANLAMA); kod ve testleri korunur."""
    monkeypatch.setattr(servis, "OTOMATIK_PUANLAMA", True)


def test_kriter_surumleri_onizleme_ve_toplu_uygulama(veri, otomatik):
    hdr = login_ok(veri)
    bos = veri.get("/api/v1/skor/kriterler/parent").json()["data"]
    assert bos["version"] == 0 and bos["varsayilan"] is True and len(bos["criteria"]) == 7  # uretim varsayilan 7 kriter
    assert veri.get("/api/v1/skor/kriterler/affiliate").json()["data"]["criteria"] == bos["criteria"]
    assert veri.get("/api/v1/skor/kriterler/yok").status_code == 404
    assert veri.put("/api/v1/skor/kriterler/parent", json={"criteria": [{"title": "", "weight": 1}]}, headers=hdr).status_code == 400
    assert veri.put("/api/v1/skor/kriterler/parent", json={"criteria": [{"title": "x", "weight": -1}]}, headers=hdr).status_code == 400
    r = veri.put("/api/v1/skor/kriterler/parent", json={"criteria": KRITER}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["version"] == 1
    # kriter degisince cati musteriler otomatik hesaplanir: segmenti olmayan atlanir (eksik kriter)
    uyg = r.json()["data"]["uygulama"]
    assert {u["id"]: u["yeni"] for u in uyg["uygulanan"]} == {1: 70.0, 2: 50.0} and uyg["degismeyen"] == 0
    assert [a["id"] for a in uyg["atlanan"]] == [3] and "eksik kriter" in uyg["atlanan"][0]["neden"]
    ikinci = veri.put("/api/v1/skor/kriterler/parent", json={"criteria": KRITER}, headers=hdr).json()["data"]
    assert ikinci["version"] == 2 and ikinci["uygulama"]["uygulanan"] == [] and ikinci["uygulama"]["degismeyen"] == 2  # degismeyen yazilmaz
    assert veri.get("/api/v1/skor/kriterler/parent").json()["data"]["version"] == 2
    on = veri.post("/api/v1/skor/toplu/onizleme", json={}, headers=hdr).json()["data"]
    assert on["ozet"] == {"toplam": 3, "hazir": 2} and [m["id"] for m in on["musteriler"]] == [1, 3, 2]  # istirak yok; ada gore
    m1 = next(m for m in on["musteriler"] if m["id"] == 1)
    assert (m1["mevcut"], m1["yeni"], m1["fark"], m1["tam"]) == (70.0, 70.0, 0.0, "Admin")
    assert m1["son_atama"]["kaynak"] == "kriter_degisikligi" and m1["kriterler"][0]["kaynak"].startswith("Panel")
    assert {k["ad"] for k in on["kaynaklar"]} >= {"Panel (kart + aylık rapor)", "Ürün-Tutar (Excel)", "REPORTDB"} and on["uyarilar"] == []
    only2 = veri.post("/api/v1/skor/toplu/onizleme", json={"tam_id": 2}, headers=hdr).json()["data"]
    assert [m["id"] for m in only2["musteriler"]] == [2]
    # toplu uygula: istirak ve olmayan kimlik atlanir
    r = veri.post("/api/v1/skor/toplu/uygula", json={"customer_ids": [1, 4, 99]}, headers=hdr).json()["data"]
    assert r["uygulanan"] == [{"id": 1, "ad": "Cati MA", "eski": 70.0, "yeni": 70.0}] and {a["id"] for a in r["atlanan"]} == {4, 99}
    assert veri.post("/api/v1/skor/toplu/uygula", json={"customer_ids": []}, headers=hdr).status_code == 422
    with Session(engine()) as db:
        assert db.query(ScoreHistory).filter_by(customer_id=1, source="kriter_degisikligi").count() == 1
        h = db.query(ScoreHistory).filter_by(customer_id=1, source="toplu").one()
        assert h.old_score == 70.0 and h.detail[0]["kaynak"].startswith("Panel") and h.detail[0]["deger"] == "MA"  # dokum kaynak/deger tutar


def test_manuel_puanlama_kriter_dokumunden(veri):
    """2026-10-20: otomatik puanlama kapali; her kriter Toplu atama > Kriter dokumunde secilir, skor sunucuda hesaplanir."""
    hdr = login_ok(veri)
    kriterler = [KRITER[0] | {"weight": 50}, {"title": "Raporlama", "type": "auto_rapor", "weight": 50, "b50": "X"}]
    uyg = veri.put("/api/v1/skor/kriterler/parent", json={"criteria": kriterler}, headers=hdr).json()["data"]["uygulama"]
    assert uyg["uygulanan"] == [] and {a["id"] for a in uyg["atlanan"]} == {1, 2, 3}  # kaynak okunmaz: segment kartta olsa da secilmedi
    on = veri.post("/api/v1/skor/toplu/onizleme", json={}, headers=hdr).json()["data"]
    assert on["manuel"] is True and on["kaynaklar"] == [] and on["ozet"]["hazir"] == 0
    m1 = next(m for m in on["musteriler"] if m["id"] == 1)
    segment, rapor = m1["kriterler"]
    assert segment["durum"] == "eksik" and segment["deger"] is None and m1["eksik"] == ["Musteri segmenti"]
    assert [(s["puan"], s["etiket"]) for s in segment["secenekler"]] == [(0, ""), (30, ""), (50, "SMB"), (70, "MA"), (100, "SA, PA, WHOLESALE")]
    assert rapor["durum"] == "otomatik" and rapor["puan"] == 50  # X sabit puani tablo kuralidir, secim gerekmez
    yaz = lambda mid, s: veri.put(f"/api/v1/skor/toplu/manuel/{mid}", json={"secimler": s}, headers=hdr)
    assert yaz(1, {}).status_code == 400  # her kriter secilmeli
    assert yaz(1, {"Musteri segmenti": 55}).status_code == 400
    assert yaz(4, {"Musteri segmenti": 100}).status_code == 404  # istirak
    r = yaz(1, {"Musteri segmenti": 100})
    assert r.status_code == 200 and r.json()["data"] == {"id": 1, "ad": "Cati MA", "eski": None, "yeni": 75.0}
    m1 = next(m for m in veri.post("/api/v1/skor/toplu/onizleme", json={}, headers=hdr).json()["data"]["musteriler"] if m["id"] == 1)
    assert m1["tamam"] and (m1["mevcut"], m1["yeni"]) == (75.0, 75.0) and m1["kriterler"][0]["durum"] == "manuel" and m1["kriterler"][0]["puan"] == 100
    sonuc = veri.post("/api/v1/skor/toplu/uygula", json={"customer_ids": [1, 2]}, headers=hdr).json()["data"]
    assert [u["id"] for u in sonuc["uygulanan"]] == [1] and [a["id"] for a in sonuc["atlanan"]] == [2]
    # agirlik degisince kayitli secimlerle yeniden hesaplanir
    kriterler[0]["weight"] = 150
    uyg = veri.put("/api/v1/skor/kriterler/parent", json={"criteria": kriterler}, headers=hdr).json()["data"]["uygulama"]
    assert uyg["uygulanan"] == [{"id": 1, "ad": "Cati MA", "eski": 75.0, "yeni": 87.5}]
    with Session(engine()) as db:
        h = db.query(ScoreHistory).filter_by(customer_id=1, source="toplu").order_by(ScoreHistory.id).first()
        assert h.detail[0]["kaynak"].startswith("Manuel") and h.detail[0]["puan"] == 100


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
        assert h.score == 88.5 and h.old_score is None and len(h.detail) == 1  # gecersiz puanli satir atildi


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
    assert liste["count"] == 1 and liste["requests"][0]["customer_id"] == 1 and liste["requests"][0]["tam_name"] == "Admin"
    tid = liste["requests"][0]["id"]
    assert veri.post(f"/api/v1/skor/talepler/{tid}/karar", json={"action": "bekle"}, headers=hdr).status_code == 400
    assert veri.post(f"/api/v1/skor/talepler/{tid}/karar", json={"action": "approve"}, headers=hdr).status_code == 200
    assert veri.post(f"/api/v1/skor/talepler/{tid}/karar", json={"action": "approve"}, headers=hdr).status_code == 404  # zaten sonuclandi
    assert veri.get("/api/v1/skor/talepler").json()["data"]["count"] == 0
    assert veri.post("/api/v1/skor/talepler", json={"customer_id": 1}, headers=hdr).status_code == 200  # onaydan sonra yenisi acilabilir
    # skor fiilen atanirsa bekleyen talep kendiliginden onaylanir (uretim toplu_atama.skoru_yaz)
    assert veri.put("/api/v1/skor/musteri/1", json={"tam_id": 1, "score": 61}, headers=hdr).status_code == 200
    assert veri.get("/api/v1/skor/talepler").json()["data"]["count"] == 0
    with Session(engine()) as db:
        t = db.query(ScoreApprovalRequest).filter_by(customer_id=1).order_by(ScoreApprovalRequest.id.desc()).first()
        assert t.status == "approved" and t.resolved_by is not None and t.resolved_at is not None


def test_puanlama_disi_ve_istirak_secimi(veri):
    hdr = login_ok(veri)
    assert veri.put("/api/v1/skor/puanlama-disi", json={"disi": [2, 99]}, headers=hdr).json()["data"] == {"disi": [2]}  # olmayan kimlik atilir
    assert veri.put("/api/v1/skor/puanlama-disi", json={"disi": []}, headers=hdr).json()["data"] == {"disi": []}  # liste tamamen degisir
    assert veri.put("/api/v1/skor/istirak/1/final-dahil", json={"dahil": True}, headers=hdr).status_code == 400  # cati
    assert veri.put("/api/v1/skor/istirak/4/final-dahil", json={"dahil": True}, headers=hdr).json()["data"] == {"dahil": True}
    assert veri.put("/api/v1/skor/istirak/4/final-dahil", json={"dahil": False}, headers=hdr).json()["data"] == {"dahil": False}
