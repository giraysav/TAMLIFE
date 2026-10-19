"""Musteri karti Operasyon dugmeleri: kartin secilen turdeki acik / yil ici kapanan kayitlari (yalniz kartin kendisi, gorunurluk) ve
portfoy kartlarinda Onedesk kayitlari kutusu icin acik / kapanan sayilari. Uydurma test verisi."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db import engine
from app.models import Customer, OnedeskRecord
from tests.conftest import login_ok
from tests.test_musteri import _cikis, _giris, veri  # noqa: F401 - fixture

URL = "/api/v1/musteri/{}/kayitlar"


def _kayit(cid, durum, acilis, kapanis=None, tur="alarm", ticket=""):
    return OnedeskRecord(
        kind=tur, external_key=f"t{cid}{acilis}{durum}{tur}", customer_id=cid, status=durum, customer_label="", location=f"nw_li_cust_{cid}",
        category="AVAILABILITY", opened_at=acilis, closed_at=kapanis, root_cause="", resolution="", source="temip", ticket_no=ticket,
        customer_no="", detail="Outstanding/Handled" if durum == "open" else "Closed/atm",
    )  # fmt: skip


def _kur():
    d = lambda ay, gun=1, yil=2026: datetime(yil, ay, gun, 10, tzinfo=UTC)
    with Session(engine()) as db:
        db.add_all([
            _kayit(1, "open", d(10, 1), ticket="10134000001"),
            _kayit(1, "open", d(10, 3)),
            _kayit(1, "open", d(10, 2), tur="talep"),
            _kayit(1, "closed", d(3, 1), d(3, 2)),
            _kayit(1, "closed", d(5, 1), d(5, 3)),
            _kayit(1, "closed", d(12, 30, 2025), d(12, 31, 2025)),  # gecen yil kapandi
            _kayit(2, "closed", d(6, 1), d(6, 2)),  # istirak: catinin listesine girmez (sayaclar da kartin kendisini sayar)
            _kayit(3, "open", d(9, 1)),  # baska TAM'in musterisi
        ])  # fmt: skip
        db.commit()


def test_kart_kayitlari_tur_durum_siralama_yil_ve_gorunurluk(veri, monkeypatch):  # noqa: F811
    _kur()
    hdr = login_ok(veri)
    r = veri.get(URL.format(1), params={"tur": "alarm", "durum": "acik"}).json()["data"]
    assert r["toplam"] == 2 and [k["acilis"][:10] for k in r["kayitlar"]] == ["2026-10-03", "2026-10-01"]  # en yeni acilan once
    k = r["kayitlar"][1]
    assert (k["ticket"], k["ci"], k["baslik"], k["durum"], k["kapanis"]) == ("10134000001", "nw_li_cust_1", "AVAILABILITY", "Outstanding/Handled", None)
    assert k["sure_dk"] > 0
    r = veri.get(URL.format(1), params={"tur": "alarm", "durum": "kapali"}).json()["data"]
    assert r["toplam"] == 2 and [k["kapanis"][:10] for k in r["kayitlar"]] == ["2026-05-03", "2026-03-02"] and r["kayitlar"][1]["sure_dk"] == 24 * 60
    assert veri.get(URL.format(1), params={"tur": "alarm", "durum": "kapali", "yil": 2025}).json()["data"]["toplam"] == 1
    assert veri.get(URL.format(1), params={"tur": "talep", "durum": "acik"}).json()["data"]["toplam"] == 1
    assert veri.get(URL.format(1), params={"tur": "sikayet", "durum": "kapali"}).json()["data"]["kayitlar"] == []
    p = veri.get(URL.format(1), params={"tur": "alarm", "durum": "acik", "per_page": 1, "page": 2}).json()["data"]
    assert (p["sayfa"], len(p["kayitlar"])) == (2, 1)
    assert veri.get(URL.format(1), params={"tur": "olay", "durum": "acik"}).status_code == 422
    assert veri.get(URL.format(1), params={"tur": "alarm"}).status_code == 422
    _cikis(veri, hdr)
    _giris(veri, monkeypatch, "TeamMember")
    assert veri.get(URL.format(3), params={"tur": "alarm", "durum": "acik"}).status_code == 404  # baskasinin karti sizdirilmaz
    assert veri.get(URL.format(1), params={"tur": "alarm", "durum": "acik"}).status_code == 200


def test_portfoy_kartinda_acik_ve_kapanan_sayilari(veri):  # noqa: F811
    with Session(engine()) as db:
        c = db.get(Customer, 1)
        c.alarm_closed_count, c.complaint_closed_count, c.request_closed_count = 40, 5, 7
        db.commit()
    login_ok(veri)
    m = next(i for i in veri.get("/api/v1/musteri/portfoy").json()["data"]["items"] if i["id"] == 1)
    assert (m["alarm"], m["alarm_kapanan"], m["sikayet"], m["sikayet_kapanan"], m["talep"], m["talep_kapanan"]) == (2, 40, 1, 5, 3, 7)
    assert veri.get("/api/v1/musteri/kayitlar/acik").status_code in (404, 405, 422)  # portfoy acik kayit paneli kaldirildi
