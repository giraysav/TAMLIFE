"""Final skor uclari (/api/v1/skor): kriter surumleri, onizleme/uygulama, tek skor, talep, personel/istirak."""

import pytest
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser, Customer, ScoreApprovalRequest, ScoreHistory
from app.skor import gunluk, servis
from app.skor.motor import SERVIS_PUANLARI
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
    """Karma puanlama (2026-11-21, 1100f9a: servis.OTOMATIK_PUANLAMA=True): verisi olan kriter kaynaktan, olmayan dokum secimine duser.
    Varsayilan artik bu; fixture acikca sabitler. Gunluk ozet (06:00 turu) bir kez calistirilir ki kaynaklar 'hazir' olsun."""
    monkeypatch.setattr(servis, "OTOMATIK_PUANLAMA", True)
    gunluk_turu()


def gunluk_turu():
    """Gunluk utilizasyon turu (skor/gunluk.py) yalniz ozet yazar; skor yazimi test edilen uclara birakilir."""
    with Session(engine()) as db:
        gunluk.calistir(db, skor_yaz=False)


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
    # 1100f9a / 02e22aa: REPORTDB / ONENTDB yerine gunluk ozet kaynaklari (Kayit hacmi, ONENT envanteri)
    kaynak_adlari = {"Panel (kart + aylık rapor)", "Ürün-Tutar (Excel)", "Kayıt hacmi (alarm + talep + şikayet)", "ONENT (aktif CI envanteri)"}
    assert {k["ad"] for k in on["kaynaklar"]} >= kaynak_adlari and on["uyarilar"] == []
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


def test_manuel_puanlama_kriter_dokumunden(veri, otomatik):
    """Karma puanlama (2026-11-21, 1100f9a): verisi olan kriter kaynaktan gelir; verisi olmayan kriter Toplu atama > Kriter dokumunde
    secilir, skor sunucuda hesaplanir. Eksik kriterde ara skor yazilir, dolu kriterlerle orantili (08ab686). Raporlama elle (7a9fb1a)."""
    hdr = login_ok(veri)
    kriterler = [KRITER[0] | {"weight": 50}, {"title": "Raporlama", "type": "auto_rapor", "weight": 50}]
    uyg = veri.put("/api/v1/skor/kriterler/parent", json={"criteria": kriterler}, headers=hdr).json()["data"]["uygulama"]
    # segment kartta olan cati: segment kaynaktan, Raporlama secilmedi -> ara skor (kismi); hic dolu kriteri olmayan atlanir
    assert {u["id"]: u["yeni"] for u in uyg["uygulanan"]} == {1: 70.0, 2: 50.0} and uyg["kismi"] == 2
    assert [a["id"] for a in uyg["atlanan"]] == [3] and "eksik kriter" in uyg["atlanan"][0]["neden"]
    on = veri.post("/api/v1/skor/toplu/onizleme", json={}, headers=hdr).json()["data"]
    assert on["manuel"] is True and on["ozet"]["hazir"] == 0
    m1 = next(m for m in on["musteriler"] if m["id"] == 1)
    assert (m1["kriterler"][0]["durum"], m1["kriterler"][0]["deger"], m1["kriterler"][0]["puan"]) == ("otomatik", "MA", 70)
    m3 = next(m for m in on["musteriler"] if m["id"] == 3)
    segment, rapor = m3["kriterler"]
    assert segment["durum"] == "eksik" and segment["deger"] is None and m3["eksik"] == ["Musteri segmenti", "Raporlama"]
    assert [(s["puan"], s["etiket"]) for s in segment["secenekler"]] == [(50, "SMB"), (70, "MA"), (100, "SA, PA, WHOLESALE")]  # 0 yok, bos 30 hucresi yok
    assert rapor["durum"] == "eksik" and [s["puan"] for s in rapor["secenekler"]] == [30, 50, 70, 100]
    yaz = lambda mid, s: veri.put(f"/api/v1/skor/toplu/manuel/{mid}", json={"secimler": s}, headers=hdr)
    assert yaz(3, {}).status_code == 400  # en az bir kriter dolu olmali
    assert yaz(3, {"Musteri segmenti": 55}).status_code == 400
    assert yaz(3, {"Musteri segmenti": 0}).status_code == 400  # 0 puan kriteri yok
    assert yaz(3, {"Musteri segmenti": 30}).status_code == 400  # 30 hucresinde kural yok
    assert yaz(4, {"Musteri segmenti": 100}).status_code == 404  # istirak
    r = yaz(3, {"Musteri segmenti": 100})
    assert r.status_code == 200 and r.json()["data"] == {"id": 3, "ad": "Cati Segmentsiz", "eski": None, "yeni": 100.0}  # ara skor
    r = yaz(3, {"Musteri segmenti": 100, "Raporlama": 50})
    assert r.status_code == 200 and r.json()["data"] == {"id": 3, "ad": "Cati Segmentsiz", "eski": 100.0, "yeni": 75.0}
    # verisi olan kriterde kaynak onceliklidir: kart segmenti MA (70) secilen 100'un onune gecer
    assert yaz(1, {"Musteri segmenti": 100, "Raporlama": 70}).json()["data"]["yeni"] == 70.0
    m3 = next(m for m in veri.post("/api/v1/skor/toplu/onizleme", json={}, headers=hdr).json()["data"]["musteriler"] if m["id"] == 3)
    assert m3["tamam"] and (m3["mevcut"], m3["yeni"]) == (75.0, 75.0) and m3["kriterler"][0]["durum"] == "manuel" and m3["kriterler"][0]["puan"] == 100
    sonuc = veri.post("/api/v1/skor/toplu/uygula", json={"customer_ids": [3, 2]}, headers=hdr).json()["data"]
    assert {u["id"] for u in sonuc["uygulanan"]} == {2, 3} and sonuc["atlanan"] == [] and sonuc["kismi"] == 1  # 2: Raporlama secilmedi
    # agirlik degisince kayitli secimlerle yeniden hesaplanir
    kriterler[0]["weight"] = 150
    uyg = veri.put("/api/v1/skor/kriterler/parent", json={"criteria": kriterler}, headers=hdr).json()["data"]["uygulama"]
    assert uyg["uygulanan"] == [{"id": 3, "ad": "Cati Segmentsiz", "eski": 75.0, "yeni": 87.5}] and uyg["degismeyen"] == 2
    with Session(engine()) as db:
        h = db.query(ScoreHistory).filter_by(customer_id=3, source="toplu").order_by(ScoreHistory.id).first()
        assert h.detail[0]["kaynak"].startswith("Manuel") and h.detail[0]["puan"] == 100


def test_manuel_servis_cesitliligi_alt_kriter(veri, otomatik):
    """Servis Cesitliligi dokumde alt kriter: alinan servisler isaretlenir. fe9b96c (2026-11-24): veriyle AYNI kural - alinan servislerin
    puanlari toplanir, satirin baremi uygulanir (eski oran kurali kalkti); servis puanlari YALNIZ kriter tablosunda degisir."""
    hdr = login_ok(veri)
    servis_satiri = {"title": "2. Servis Çeşitliliği", "type": "servis_cesitliligi", "weight": 20, "servis_puanlari": {"Cloud": 10, "Data": 30}}
    veri.put("/api/v1/skor/kriterler/parent", json={"criteria": [KRITER[0] | {"weight": 80}, servis_satiri]}, headers=hdr)
    m3 = next(m for m in veri.post("/api/v1/skor/toplu/onizleme", json={}, headers=hdr).json()["data"]["musteriler"] if m["id"] == 3)
    satir = m3["kriterler"][1]
    servisler = {s["ad"]: s["puan"] for s in satir["servisler"]}
    assert satir["durum"] == "eksik" and "secenekler" not in satir
    assert (servisler["Cloud"], servisler["Data"]) == (10.0, 30.0) and set(servisler) == set(SERVIS_PUANLARI)  # eksik servis varsayilanla
    assert [(k["puan"], k["alt"]) for k in satir["kurallar"]] == [(30, 1), (50, 20), (70, 30), (100, 40)]  # satirin varsayilan baremi
    yaz = lambda govde: veri.put("/api/v1/skor/toplu/manuel/3", json=govde, headers=hdr)
    assert yaz({"secimler": {"Musteri segmenti": 100, "2. Servis Çeşitliliği": 50}}).status_code == 400  # puan degil servis listesi
    assert yaz({"secimler": {"Musteri segmenti": 100, "2. Servis Çeşitliliği": ["Uydurma"]}}).status_code == 400  # listede olmayan servis
    r = yaz({"secimler": {"Musteri segmenti": 100, "2. Servis Çeşitliliği": ["Data"]}}).json()["data"]
    assert r["yeni"] == 94.0  # segment 80 + servis toplami 30 -> barem 30-39 = 70 puan -> 20 x 0,7 = 14
    assert yaz({"secimler": {"Musteri segmenti": 100, "2. Servis Çeşitliliği": []}}).json()["data"]["yeni"] == 80.0  # hic servis yok: 0
    # dokum govdesindeki servis puanlari yok sayilir: kriter tablosu degismez
    assert yaz({"secimler": {"Musteri segmenti": 100, "2. Servis Çeşitliliği": ["Data"]}, "servis_puanlari": {"Data": 40}}).json()["data"]["yeni"] == 94.0
    assert veri.get("/api/v1/skor/kriterler/parent").json()["data"]["version"] == 1
    # servis puani kriter tablosunda duzenlenir: yeni surum, kayitli secimle yeniden hesap (Data 40 -> barem 40+ = 100)
    put = lambda puanlar: veri.put(
        "/api/v1/skor/kriterler/parent", json={"criteria": [KRITER[0] | {"weight": 80}, servis_satiri | {"servis_puanlari": puanlar}]}, headers=hdr
    )
    assert put({"Cloud": -1}).status_code == 400 and put({"Cloud": 101}).status_code == 400 and put({"Uydurma": 5}).status_code == 400
    r = put({"Cloud": 10, "Data": 40}).json()["data"]
    assert r["version"] == 2 and r["uygulama"]["uygulanan"] == [{"id": 3, "ad": "Cati Segmentsiz", "eski": 94.0, "yeni": 100.0}]
    kayit = veri.get("/api/v1/skor/kriterler/parent").json()["data"]["criteria"][1]["servis_puanlari"]
    assert kayit["Data"] == 40 and kayit["Cloud"] == 10 and set(kayit) == set(SERVIS_PUANLARI)
    m3 = next(m for m in veri.post("/api/v1/skor/toplu/onizleme", json={}, headers=hdr).json()["data"]["musteriler"] if m["id"] == 3)
    assert m3["tamam"] and m3["kriterler"][1]["deger"] == ["Data"] and m3["kriterler"][1]["puan"] == 100  # kayitli secim geri gelir


def test_tek_musteri_skoru_kurallari(veri):
    hdr = login_ok(veri)
    put = lambda mid, **g: veri.put(f"/api/v1/skor/musteri/{mid}", json=g, headers=hdr)
    assert put(1, tam_id=1, score=101).status_code == 400  # 0-100
    assert put(1, tam_id=1, score=-1).status_code == 400
    assert put(1, tam_id=1, score="abc").status_code == 400
    assert put(1, tam_id=2, score=50).status_code == 400  # musteri-personel eslesmiyor
    assert put(4, tam_id=1, score=50).status_code == 400  # istirak
    assert put(99, tam_id=1, score=50).status_code == 404
    detay = [{"baslik": "k", "puan": 70, "agirlik": 10}, {"baslik": "alt kriter", "puan": 85}, {"baslik": "gecersiz", "puan": 155}, {"baslik": "eksi", "puan": -5}]
    assert put(1, tam_id=1, score=88.5, detay=detay).status_code == 200
    with Session(engine()) as db:
        c = db.get(Customer, 1)
        assert c.score == 88.5
        h = db.query(ScoreHistory).filter_by(customer_id=1, source="sayfa").one()
        # 0-100 disi puanli satir atilir; 5885c1c'den beri ara puanlar (Sozlesme alt kriterleri 15 / 85) gecerli
        assert h.score == 88.5 and h.old_score is None and [d["baslik"] for d in h.detail] == ["k", "alt kriter"]


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
