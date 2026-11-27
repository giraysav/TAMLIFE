# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Profil (kisinin kendi bilgileri), kisiye ozel Ceyrek Bazli Sunum yetkisi ve TAM Utilizasyon > Musteri Listesi (toplu ekle/sil)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser, Customer, OnedeskRecord, Report
from app.musteri import servis as ms
from app.rolgorunum import SUNUM_YETKISI, etkin
from app.session import Principal
from tests_v35.conftest import login_ok


def _cikis(client, hdr):
    assert client.post("/api/v1/session/logout", headers=hdr).status_code == 200


def _kisi_ekle(**alanlar) -> int:
    with Session(engine()) as db:
        satir = AppUser(**alanlar)
        db.add(satir)
        db.commit()
        return satir.id


# --- profil ------------------------------------------------------------------------------------------------------------
def test_profil_okuma_ve_guncelleme(client):
    hdr = login_ok(client)
    d = client.get("/api/v1/session/me").json()["data"]
    assert d["profile"]["username"] == "admin" and d["display_name"] and d["profile"]["phone"] == ""
    govde = {"first_name": " Giray ", "last_name": "Sav", "phone": "+90 532 000 00 00", "company": "Turkcell Teknoloji", "website": "turkcell.com.tr"}
    r = client.put("/api/v1/session/profile", json=govde, headers=hdr)
    assert r.status_code == 200, r.text
    p = r.json()["data"]
    assert (p["first_name"], p["last_name"], p["website"]) == ("Giray", "Sav", "https://turkcell.com.tr") and "address" not in p  # adres 2026-10-26 kalkti
    assert p["username"] == "admin" and p["display_name"] == "Giray Sav"
    d = client.get("/api/v1/session/me").json()["data"]
    assert d["display_name"] == "Giray Sav" and d["username"] == "admin" and d["profile"]["phone"] == "+90 532 000 00 00"
    # yalniz gonderilen alan degisir; ad ve soyad kendi basina kaymaz
    assert client.put("/api/v1/session/profile", json={"phone": "0212 000 00 00"}, headers=hdr).json()["data"]["first_name"] == "Giray"
    assert client.put("/api/v1/session/profile", json={"last_name": "Savlı"}, headers=hdr).json()["data"]["display_name"] == "Giray Savlı"
    with Session(engine()) as db:
        assert db.scalar(select(AppUser.display_name).where(AppUser.username == "admin")) == "Giray Savlı"  # Takvim/Ekip listeleri de bunu gosterir


def test_profil_kullanici_adi_ve_rol_degistirilemez_ve_dogrulama(client):
    hdr = login_ok(client)
    for yasak in ({"username": "baska"}, {"role": "admin"}, {"is_admin": True}, {"active": False}):
        assert client.put("/api/v1/session/profile", json=yasak, headers=hdr).status_code == 422, yasak
    assert client.put("/api/v1/session/profile", json={"phone": "abc"}, headers=hdr).status_code == 400
    assert client.put("/api/v1/session/profile", json={"first_name": "x" * 101}, headers=hdr).status_code == 400
    for kotu in ("javascript:alert(1)", "javascript://x", "ftp://sunucu", "https://a b.com", "https://-kotu.com"):
        assert client.put("/api/v1/session/profile", json={"website": kotu}, headers=hdr).status_code == 400, kotu
    assert client.put("/api/v1/session/profile", json={"website": "http://www.turkcell.com.tr:8080/yol"}, headers=hdr).status_code == 200
    assert client.put("/api/v1/session/profile", json={"phone": "1"}).status_code == 403  # CSRF'siz
    assert client.get("/api/v1/session/me").json()["data"]["username"] == "admin"


def test_profil_ad_user_alani_ve_turetilmis_ad(client):
    login_ok(client)
    _kisi_ekle(username="ayse.demir", display_name="Ayşe Nur Demir", role="TeamMember", is_ad_user=True)
    with Session(engine()) as db:
        satir = db.scalar(select(AppUser).where(AppUser.username == "ayse.demir"))
        from app.kullanicilar import ad_soyad, profil_sozlugu

        assert ad_soyad(satir) == ("Ayşe Nur", "Demir")  # bos profil: display_name'den turetilir
        assert profil_sozlugu(satir, Principal("ayse.demir", "TeamMember", False))["ad_user"] is True


def test_profil_oturumsuz_401(client):
    assert client.put("/api/v1/session/profile", json={"phone": "1"}).status_code in {401, 403}


# --- kisiye ozel Ceyrek Bazli Sunum yetkisi ----------------------------------------------------------------------------
def test_roller_kisi_listesi_ve_kisi_yetkisi(client, monkeypatch):
    hdr = login_ok(client)
    uid = _kisi_ekle(username="ayse.demir", display_name="Ayşe Demir", role="TeamMember", is_ad_user=True, ad_domain="turkcell")
    _kisi_ekle(username="pasif.kisi", display_name="Pasif Kisi", role="TeamMember", active=False)
    d = client.get("/api/v1/roller").json()["data"]
    kisiler = {u["username"]: u for u in d["users"]}
    assert "pasif.kisi" not in kisiler and kisiler["admin"]["role"] == "admin"
    assert kisiler["ayse.demir"]["auth"] == "AD" and kisiler["ayse.demir"]["permissions"] == [] and kisiler["ayse.demir"]["display_name"] == "Ayşe Demir"
    ayse = Principal("ayse.demir", "TeamMember", False)
    with Session(engine()) as db:
        assert not etkin(db, ayse).yetkili_mi(SUNUM_YETKISI)

    r = client.put(f"/api/v1/roller/kisiler/{uid}", json={"permissions": [SUNUM_YETKISI]}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["permissions"] == [SUNUM_YETKISI]
    with Session(engine()) as db:
        assert etkin(db, ayse).yetkili_mi(SUNUM_YETKISI)
        assert not etkin(db, Principal("baska", "TeamMember", False)).yetkili_mi(SUNUM_YETKISI)  # yalniz secilen kisi
    assert next(u for u in client.get("/api/v1/roller").json()["data"]["users"] if u["username"] == "ayse.demir")["permissions"] == [SUNUM_YETKISI]
    rol = next(x for x in client.get("/api/v1/roller").json()["data"]["roles"] if x["role"] == "TeamMember")
    assert SUNUM_YETKISI not in rol["permissions"]  # rolun kendi yetkisi degismedi

    assert client.put(f"/api/v1/roller/kisiler/{uid}", json={"permissions": ["yok.yetki"]}, headers=hdr).status_code == 400
    assert client.put(f"/api/v1/roller/kisiler/{uid + 99}", json={"permissions": []}, headers=hdr).status_code == 404
    admin_id = kisiler["admin"]["id"]
    assert client.put(f"/api/v1/roller/kisiler/{admin_id}", json={"permissions": [SUNUM_YETKISI]}, headers=hdr).status_code == 400  # admin zaten hepsine sahip
    assert client.put(f"/api/v1/roller/kisiler/{uid}", json={"permissions": []}, headers=hdr).status_code == 200
    with Session(engine()) as db:
        assert not etkin(db, ayse).yetkili_mi(SUNUM_YETKISI)

    _cikis(client, hdr)  # member kendine yetki veremez, listeyi goremez
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    hdr = login_ok(client)
    assert client.get("/api/v1/roller").status_code == 403
    assert client.put(f"/api/v1/roller/kisiler/{uid}", json={"permissions": [SUNUM_YETKISI]}, headers=hdr).status_code == 403


def test_kisi_yetkisi_oturumda_gorunur(client, monkeypatch):
    """Rolunde yetki olmayan TeamMember'a kisiye ozel verilen Ceyrek Sunum yetkisi /session/me eylem listesinde ve Sunum yonetiminde gecerlidir."""
    hdr = login_ok(client)
    _cikis(client, hdr)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    login_ok(client)  # 'admin' kullanici satiri TeamMember olarak yeniden yazilir (giris_isle)
    assert SUNUM_YETKISI not in client.get("/api/v1/session/me").json()["data"]["permissions"]["actions"]
    with Session(engine()) as db:
        db.scalar(select(AppUser).where(AppUser.username == "admin")).permissions = [SUNUM_YETKISI]
        db.commit()
    assert SUNUM_YETKISI in client.get("/api/v1/session/me").json()["data"]["permissions"]["actions"]


# --- TAM Utilizasyon > Musteri Listesi ---------------------------------------------------------------------------------
def _liste(client):
    return client.get("/api/v1/yonetim/musteriler").json()["data"]


def test_musteri_listesi_toplu_ekle_ve_agac_sirasi(client):
    hdr = login_ok(client)
    r = client.post(
        "/api/v1/yonetim/musteriler/toplu-ekle",
        json={"satirlar": [{"name": "Beta Ltd"}, {"name": "Alfa A.S.", "segment": "MA"}, {"name": "alfa  a.s."}, {"name": "Gama", "segment": "XYZ"}, {"name": "  "}]},
        headers=hdr,
    )
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["eklenen"] == 2 and len(d["atlanan"]) == 3
    sebepler = {a["ad"]: a["sebep"] for a in d["atlanan"]}
    assert "ünvanla" in sebepler["alfa  a.s."] and "Segment" in sebepler["Gama"] and "zorunlu" in sebepler["  "]
    alfa = next(m for m in _liste(client)["items"] if m["name"] == "Alfa A.S.")
    r = client.post("/api/v1/yonetim/musteriler/toplu-ekle", json={"satirlar": [{"name": "Alfa Istirak 2"}, {"name": "Alfa Istirak 1"}], "parent_id": alfa["id"]}, headers=hdr)
    assert r.json()["data"]["eklenen"] == 2
    liste = _liste(client)
    assert liste["total"] == 4 and [m["name"] for m in liste["items"]] == ["Alfa A.S.", "Alfa Istirak 1", "Alfa Istirak 2", "Beta Ltd"]  # cati, altinda istirakleri
    ist = liste["items"][1]
    assert ist["parent_id"] == alfa["id"] and ist["parent_name"] == "Alfa A.S." and ist["segment"] == "MA"  # segment catidan
    assert liste["items"][0]["affiliates"] == 2 and liste["items"][3]["parent_id"] is None
    assert client.post("/api/v1/yonetim/musteriler/toplu-ekle", json={"satirlar": [{"name": "X"}], "parent_id": 9999}, headers=hdr).status_code == 404
    assert client.post("/api/v1/yonetim/musteriler/toplu-ekle", json={"satirlar": []}, headers=hdr).status_code == 400
    assert client.post("/api/v1/yonetim/musteriler/toplu-ekle", json={"satirlar": [{"name": "Z"}] * 501}, headers=hdr).status_code == 422


def test_musteri_listesi_secilenleri_ve_hepsini_sil(client):
    hdr = login_ok(client)
    with Session(engine()) as db:
        uid = db.scalar(select(AppUser.id).where(AppUser.username == "admin"))
        a = Customer(external_key="t-a", name="Alfa A.S.", owner_id=uid)
        b = Customer(external_key="t-b", name="Beta Ltd", owner_id=uid)
        db.add_all([a, b])
        db.flush()
        i1 = Customer(external_key="t-a1", name="Alfa Istirak", owner_id=uid, parent_id=a.id)
        db.add(i1)
        db.flush()
        db.add(Report(customer_id=a.id, user_id=uid, report_month=1, report_year=2026))
        db.add(OnedeskRecord(kind="alarm", external_key="od-1", customer_id=i1.id, customer_label="Alfa Istirak"))
        db.commit()
        a_id, i1_id = a.id, i1.id
    assert client.post("/api/v1/yonetim/musteriler/sil", json={"ids": []}, headers=hdr).status_code == 400
    # cati secilince istiraki de gider; bagli rapor silinir, Onedesk kaydi kalir ama musteriden kopar
    r = client.post("/api/v1/yonetim/musteriler/sil", json={"ids": [a_id, i1_id, 987654]}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["silinen"] == 2
    assert [m["name"] for m in _liste(client)["items"]] == ["Beta Ltd"]
    with Session(engine()) as db:
        assert db.scalar(select(Report.id)) is None
        od = db.scalar(select(OnedeskRecord))
        assert od is not None and od.customer_id is None and od.customer_label == "Alfa Istirak"
    # hepsini sil: onay metni olmadan reddedilir
    assert client.post("/api/v1/yonetim/musteriler/sil", json={"hepsi": True}, headers=hdr).status_code == 400
    assert client.post("/api/v1/yonetim/musteriler/sil", json={"hepsi": True, "onay": "evet"}, headers=hdr).status_code == 400
    assert _liste(client)["total"] == 1
    r = client.post("/api/v1/yonetim/musteriler/sil", json={"hepsi": True, "onay": "sil"}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["silinen"] == 1 and _liste(client)["total"] == 0


def test_musteri_listesi_admin_disina_kapali(client, monkeypatch):
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMngr")
    hdr = login_ok(client)
    assert client.get("/api/v1/yonetim/musteriler").status_code == 403
    assert client.post("/api/v1/yonetim/musteriler/sil", json={"ids": [1]}, headers=hdr).status_code == 403
    assert client.post("/api/v1/yonetim/musteriler/toplu-ekle", json={"satirlar": [{"name": "X"}]}, headers=hdr).status_code == 403


def test_musteriye_bagli_tablolar_kapsami_ve_sirasi():
    ad = [t.name for t, _ in ms.musteriye_bagli_tablolar()]
    assert {"report", "report_dispatch", "report_draft", "report_recipient", "score_history", "score_detail", "customer_team", "distribution_log", "onedesk_record", "presentation"} <= set(ad)
    assert ad.index("report_dispatch") < ad.index("report")  # gonderim rapordan once silinir
    assert "customer" not in ad


def test_cok_sayida_musteri_tek_istekte_silinir(client):
    """IN listesi parcalanir: SQLite/PostgreSQL parametre sinirini asan sayida musteri tek istekte (hepsi) silinebilir."""
    n = 1200
    hdr = login_ok(client)
    with Session(engine()) as db:
        db.add_all([Customer(external_key=f"t-{i}", name=f"Musteri {i:05d}") for i in range(n)])
        db.commit()
    assert _liste(client)["total"] == n
    r = client.post("/api/v1/yonetim/musteriler/sil", json={"hepsi": True, "onay": "SIL"}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["silinen"] == n and _liste(client)["total"] == 0
