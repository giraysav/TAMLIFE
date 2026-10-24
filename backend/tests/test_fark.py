"""Veri Girisi > Fark: canli DB (TEMIP) kayitlarinin kartla / TAM ile eslesmeyen numaralari listelenir; secilenler toplu olarak personel
adina yeni kartla atanir (uymayan atlanir, kayitlar tek seferde baglanir); personelsiz karta TAM secilir."""

from sqlalchemy.orm import Session

from app.db import engine
from app.models import Customer
from tests.conftest import login_ok
from tests.test_temip_kayit import SahteTemip, calistir, kart, kayitlar, kisi, sahip, tsatir

URL = "/api/v1/tampon/fark"


def _kur(monkeypatch):
    a = kart("ORNEK-A", "10000001")  # sorumlusuz kart: 'kart_personelsiz'
    kart("ORNEK-B", "10000002")
    kart("ORNEK-C", "10000002")  # ayni numara iki kartta: 'belirsiz'
    t = SahteTemip(monkeypatch)
    t.kapali = [tsatir("1", "22306933", unvan="TURK EKONOMI BANKASI A.S.", kapanis="2026-10-17 11:00:00", durum="Closed/atm")]
    t.acik = [
        tsatir("2", "22306933", unvan="TURK EKONOMI BANKASI A.S."),
        tsatir("3", "10000001"),
        tsatir("4", "10000002"),
        tsatir("5", "33333333", unvan="ORNEK LOJISTIK"),
        tsatir("6", "44444444", unvan="ORNEK LOJISTIK"),  # ayni unvan: toplu atamada ikincisi atlanir
    ]
    calistir()
    return a


def test_fark_listesi_tur_ve_arama(client, monkeypatch):
    a = _kur(monkeypatch)
    login_ok(client)
    d = client.get(URL).json()["data"]
    assert d["hazir"] is True
    assert {m["musteri_no"]: m["durum"] for m in d["satirlar"]} == {
        "22306933": "radar", "33333333": "radar", "44444444": "radar", "10000002": "belirsiz", "10000001": "kart_personelsiz",
    }  # fmt: skip
    assert d["ozet"]["radar"] == {"musteri": 3, "kayit": 4, "acik": 3} and d["ozet"]["belirsiz"]["musteri"] == 1
    assert d["toplam_kayit"] == 6 and all(m["kaynak"] == "TEMIP" for m in d["satirlar"])
    assert [m["musteri_no"] for m in client.get(URL, params={"tur": "radar", "q": "türk"}).json()["data"]["satirlar"]] == ["22306933"]
    assert client.get(URL, params={"tur": "belirsiz"}).json()["data"]["satirlar"][0]["aday_kartlar"] == "ORNEK-B, ORNEK-C"
    [p] = client.get(URL, params={"tur": "kart_personelsiz"}).json()["data"]["satirlar"]
    assert p["kart_id"] == a


def test_toplu_ata_yeni_kartlar_acar_uymayani_atlar(client, monkeypatch):
    _kur(monkeypatch)
    tam = kisi("tam")
    hdr = login_ok(client)
    r = client.post(
        f"{URL}/toplu-ata", json={"musteri_nolar": ["22306933", "33333333", "44444444", "10000001", "22306933"], "tam_id": tam}, headers=hdr
    )
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["atanan"] == 2 and d["kartlar"] == ["TURK EKONOMI BANKASI A.S.", "ORNEK LOJISTIK"] and d["yeniden_baglanan"] == 3
    assert {x["musteri_no"] for x in d["atlanan"]} == {"44444444", "10000001"}  # ayni unvanli kart var / numara zaten kartta
    with Session(engine()) as db:
        yeni = {c.customer_no: c.owner_id for c in db.query(Customer).filter(Customer.customer_no.in_(["22306933", "33333333"]))}
    assert yeni == {"22306933": tam, "33333333": tam}
    k = kayitlar()
    assert k["1"].customer_id == k["2"].customer_id is not None and k["6"].customer_id is None
    atamalar = client.get("/api/v1/tampon/temip/atamalar").json()["data"]
    assert [x["musteri_no"] for x in atamalar] == ["22306933", "33333333"] and all(
        x["yeni_kart"] and x["personel"] == "Ornek tam" for x in atamalar
    )
    assert [m["musteri_no"] for m in client.get(URL, params={"tur": "radar"}).json()["data"]["satirlar"]] == ["44444444"]


def test_toplu_ata_sinirlari_ve_personel(client, monkeypatch):
    _kur(monkeypatch)
    mudur = kisi("mudur", "TeamMngr")
    hdr = login_ok(client)
    git = lambda govde: client.post(f"{URL}/toplu-ata", json=govde, headers=hdr)
    assert git({"musteri_nolar": [], "tam_id": 1}).status_code == 422
    assert git({"musteri_nolar": ["1"] * 201, "tam_id": 1}).status_code == 422
    d = git({"musteri_nolar": ["22306933"], "tam_id": mudur}).json()["data"]  # personel degil: atlanir, kart acilmaz
    assert d["atanan"] == 0 and len(d["atlanan"]) == 1
    with Session(engine()) as db:
        assert db.query(Customer).filter(Customer.customer_no == "22306933").count() == 0
    assert client.post(f"{URL}/toplu-ata", json={"musteri_nolar": ["22306933"], "tam_id": 1}).status_code == 403  # CSRF'siz


def test_personelsiz_karta_tam_secilir(client, monkeypatch):
    a = _kur(monkeypatch)
    tam = kisi("tam")
    hdr = login_ok(client)
    assert client.post(f"{URL}/kart-sahibi", json={"kart_id": 999999, "tam_id": tam}, headers=hdr).status_code == 404
    r = client.post(f"{URL}/kart-sahibi", json={"kart_id": a, "tam_id": tam}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["personel"] == "Ornek tam"
    assert client.get(URL, params={"tur": "kart_personelsiz"}).json()["data"]["satirlar"] == []
    sahip(a, None)


def test_fark_yalniz_admin(client):
    assert client.get(URL).status_code == 401
    assert client.post(f"{URL}/toplu-ata", json={"musteri_nolar": ["22306933"], "tam_id": 1}).status_code in (401, 403)
