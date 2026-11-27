# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""TEMIP Musteri No'sunu karta elle atama (CRM unvan hatasi): numara karta eklenir, kayitlar baglanir, sayaclar yenilenir; baska kartta
yazili numara atanmaz; geri alma numarayi karttan siler ve kayitlar Radar'a doner."""

from sqlalchemy.orm import Session

from app.db import engine
from app.models import Customer
from tests_v35.conftest import login_ok
from tests_v35.test_temip_kayit import SahteTemip, calistir, kart, kayitlar, sayac, tsatir

URL = "/api/v1/tampon/temip"


def _kur(monkeypatch):
    a = kart("ORNEK-A", "10000001")
    b = kart("TURK EKONOMI BANKASI")  # numarasiz kart (CRM unvan farki: TEMIP'te 'TURK EKONOMI BANKASI A.S.')
    t = SahteTemip(monkeypatch)
    t.kapali = [tsatir("1", "22306933", unvan="TURK EKONOMI BANKASI A.S.", kapanis="2026-10-17 11:00:00", durum="Closed/atm")]
    t.acik = [tsatir("2", "22306933", unvan="TURK EKONOMI BANKASI A.S."), tsatir("3", "10000001")]
    calistir()
    return a, b


def test_elle_atama_karta_baglar_sayaci_yeniler_geri_alinir(client, monkeypatch):
    a, b = _kur(monkeypatch)
    assert kayitlar()["2"].customer_id is None  # numara kartta yok: Radar
    hdr = login_ok(client)
    assert [k["ad"] for k in client.get(f"{URL}/kartlar", params={"q": "türk ekonomi"}).json()["data"]] == ["TURK EKONOMI BANKASI"]
    r = client.post(f"{URL}/ata", json={"musteri_no": "22306933", "kart_id": b}, headers=hdr)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert (d["kart_musteri_no"], d["kayit"], d["yeniden_baglanan"]) == ("22306933", 2, 2)
    assert {k: v.customer_id for k, v in kayitlar().items()} == {"1": b, "2": b, "3": a}
    assert sayac(b) == (1, 1)
    e = client.get(f"{URL}/eslesme").json()["data"]  # test kartlarinin sorumlusu yok: 'kart_personelsiz' dalinda
    assert {m["musteri_no"]: m["kart_id"] for m in e["musteriler"]} == {"10000001": a, "22306933": b} and e["bagli_olmayan"] == 0
    [atama] = client.get(f"{URL}/atamalar").json()["data"]
    assert (atama["musteri_no"], atama["kart"], atama["temip_unvan"], atama["kim"]) == (
        "22306933",
        "TURK EKONOMI BANKASI",
        "TURK EKONOMI BANKASI A.S.",
        "admin",
    )
    calistir()  # sonraki iceri alma turu atamayi korur (numara kartta)
    assert kayitlar()["2"].customer_id == b

    r = client.post(f"{URL}/ata/kaldir", json={"musteri_no": "22306933"}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["yeniden_baglanan"] == 2
    with Session(engine()) as db:
        assert db.get(Customer, b).customer_no is None
    assert kayitlar()["2"].customer_id is None and sayac(b) == (0, 0) and client.get(f"{URL}/atamalar").json()["data"] == []


def test_elle_atama_kurallari(client, monkeypatch):
    a, b = _kur(monkeypatch)
    hdr = login_ok(client)
    ata = lambda no, k: client.post(f"{URL}/ata", json={"musteri_no": no, "kart_id": k}, headers=hdr)
    assert ata("2230693", b).status_code == 400  # 8 hane degil
    assert ata("99999999", b).status_code == 404  # TEMIP kaydi yok
    assert ata("22306933", 999999).status_code == 404
    assert ata("10000001", a).status_code == 409  # zaten bu kartta
    r = ata("10000001", b)
    assert r.status_code == 409 and "ORNEK-A" in r.json()["detail"]  # baska kartta: once oradan cikarilmali
    with Session(engine()) as db:
        db.get(Customer, a).customer_no = "1" * 195
        db.commit()
    assert ata("22306933", a).status_code == 409  # alan dolu (200 karakter)
    assert client.post(f"{URL}/ata/kaldir", json={"musteri_no": "10000001"}, headers=hdr).status_code == 404  # elle atama degil
    istirak = kart("TURK EKONOMI BANKASI ISTIRAK")
    with Session(engine()) as db:
        db.get(Customer, istirak).parent_id = b
        db.commit()
    assert ata("22306933", istirak).status_code == 400  # istirak karta atama yapilmaz
    assert [k["id"] for k in client.get(f"{URL}/kartlar", params={"q": "türk ekonomi"}).json()["data"]] == [b]  # aramada yalniz cati
    assert client.post(f"{URL}/ata", json={"musteri_no": "22306933", "kart_id": b}).status_code == 403  # CSRF'siz


def test_elle_atama_yalniz_admin(client):
    assert client.get(f"{URL}/atamalar").status_code == 401
    assert client.post(f"{URL}/ata", json={"musteri_no": "22306933", "kart_id": 1}).status_code in (401, 403)


def test_personele_yeni_kart_olarak_ata_ve_personel_suzgecli_arama(client, monkeypatch):
    from app.models import AppUser

    _kur(monkeypatch)
    with Session(engine()) as db:
        tam = AppUser(username="ornek_tam", display_name="Ornek Tam", role="TeamMember")
        mudur = AppUser(username="ornek_mudur", display_name="Ornek Mudur", role="TeamMngr")
        db.add_all([tam, mudur])
        db.commit()
        tam_id, mudur_id = tam.id, mudur.id
        db.get(Customer, 1).owner_id = tam_id  # ORNEK-A bu TAM'in karti
        db.commit()
    hdr = login_ok(client)
    assert [p["ad"] for p in client.get(f"{URL}/personel").json()["data"]] == ["Ornek Tam"]  # yonetici personel degil
    assert [k["ad"] for k in client.get(f"{URL}/kartlar", params={"tam": tam_id}).json()["data"]] == [
        "ORNEK-A"
    ]  # bos arama: TAM'in tum kartlari
    assert client.post(f"{URL}/ata", json={"musteri_no": "22306933"}, headers=hdr).status_code == 400  # kart ya da personel secilmeli
    assert client.post(f"{URL}/ata", json={"musteri_no": "22306933", "tam_id": mudur_id}, headers=hdr).status_code == 404  # personel degil
    r = client.post(f"{URL}/ata", json={"musteri_no": "22306933", "tam_id": tam_id, "unvan": "TEB YENI KART"}, headers=hdr)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["yeni_kart"] is True and d["kart"] == "TEB YENI KART" and d["kart_musteri_no"] == "22306933" and d["yeniden_baglanan"] == 2
    with Session(engine()) as db:
        kart = db.get(Customer, d["kart_id"])
        assert (kart.owner_id, kart.parent_id) == (tam_id, None)
    assert kayitlar()["2"].customer_id == d["kart_id"]
    [atama] = client.get(f"{URL}/atamalar").json()["data"]
    assert (atama["yeni_kart"], atama["personel"]) == (True, "Ornek Tam")
    assert (
        client.post(f"{URL}/ata", json={"musteri_no": "22306933", "tam_id": tam_id}, headers=hdr).status_code == 409
    )  # numara artik kartta
    assert client.post(f"{URL}/ata/kaldir", json={"musteri_no": "22306933"}, headers=hdr).status_code == 200
    with Session(engine()) as db:
        assert db.get(Customer, d["kart_id"]) is not None  # acilan kart silinmez, yalniz numara cikar
    assert kayitlar()["2"].customer_id is None
