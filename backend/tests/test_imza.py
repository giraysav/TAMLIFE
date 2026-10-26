"""E-posta imzasi (2026-10-26): izin listeli HTML temizligi, profil uclari, adresin kalkmasi ve aylik rapor iletisinde imza + gomulu
gorsel (cid). Uydurma veri; ag yok."""

import base64
from email import message_from_bytes
from email.policy import default

import pytest
from sqlalchemy.orm import Session

from app import imza
from app.db import engine
from app.models import AppUser, Customer
from tests.conftest import login_ok

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
PNG_URL = "data:image/png;base64," + base64.b64encode(PNG).decode()


def test_temizleyici_tehlikeli_icerigi_atar_bicimi_korur():
    ham = (
        '<p style="color:#002855;font-weight:700;background:url(http://x/y.png);behavior:url(x)">Ad <b>Soyad</b></p>'
        '<script>alert(1)</script><img src="http://disari.example/iz.png"><img src="x" onerror="alert(1)">'
        f'<table cellpadding="0"><tr><td valign="middle"><img src="{PNG_URL}" width="96" onload="x()"></td><td>TAM</td></tr></table>'
        '<a href="javascript:alert(1)">kotu</a> <a href="https://superonline.net" onclick="x()">web</a><iframe src="x"></iframe>'
        '<div style="width:expression(alert(1));font-size:13px">son</div>'
    )
    t = imza.temizle(ham)
    assert "<script" not in t and "alert" not in t and "onerror" not in t and "onload" not in t and "onclick" not in t
    assert "http://disari" not in t and "<iframe" not in t and "url(" not in t and "expression" not in t
    assert '<p style="color:#002855;font-weight:700">Ad <b>Soyad</b></p>' in t
    assert f'<img src="{PNG_URL}" width="96">' in t and '<td valign="middle">' in t
    assert '<a target="_blank">kotu</a>' in t and '<a href="https://superonline.net" target="_blank">web</a>' in t
    assert '<div style="font-size:13px">son</div>' in t
    assert imza.temizle("   <p> </p> ") == ""  # bos imza
    assert imza.duz_metin(t).splitlines()[0] == "Ad Soyad"


def test_temizleyici_gorsel_sinirlari():
    buyuk = "data:image/png;base64," + base64.b64encode(PNG + b"\x00" * imza.AZAMI_GORSEL).decode()
    with pytest.raises(imza.ImzaHata):
        imza.temizle(f'<img src="{buyuk}">')
    with pytest.raises(imza.ImzaHata):
        imza.temizle("".join(f'<img src="{PNG_URL}">' for _ in range(imza.EN_FAZLA_GORSEL + 1)))
    assert "svg" not in imza.temizle('<img src="data:image/svg+xml;base64,PHN2Zz4=">')  # svg (betik tasiyabilir) kabul edilmez


def test_gomulu_gorseller_cid_olur_bilinen_tek_parca():
    h, parcalar = imza.gomulu_gorselleri_ayir(f'<img src="{PNG_URL}"><img src="{PNG_URL}">')
    assert h == '<img src="cid:imza1@tamlife"><img src="cid:imza1@tamlife">' and parcalar == [("imza1@tamlife", PNG, "png")]
    h, parcalar = imza.gomulu_gorselleri_ayir(f'<img src="{PNG_URL}">', {PNG: "teknocan@tamlife"})
    assert h == '<img src="cid:teknocan@tamlife">' and parcalar == []


def test_profil_imza_uclari_ve_adres_kalkti(client):
    hdr = login_ok(client)
    assert "address" not in client.get("/api/v1/session/me").json()["data"]["profile"]
    assert client.put("/api/v1/session/profile", json={"address": "X"}, headers=hdr).status_code == 422  # alan kalkti
    bos = client.get("/api/v1/session/imza").json()["data"]
    assert bos["html"] == "" and bos["kayitli"] is False and "Teknocan" in bos["sablon"] and "data:image/png;base64," in bos["sablon"]
    r = client.put("/api/v1/session/imza", json={"html": '<p>Giray <b>Sav</b><script>x</script></p>'}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["html"] == "<p>Giray <b>Sav</b></p>" and r.json()["data"]["kayitli"] is True
    assert client.put("/api/v1/session/imza", json={"html": ""}, headers=hdr).json()["data"]["kayitli"] is False


def test_aylik_rapor_iletisi_profil_imzasini_tasir(client, monkeypatch, tmp_path):
    monkeypatch.setenv("TAMLIFE_REPORT_DIR", str(tmp_path / "raporlar"))
    hdr = login_ok(client)
    with Session(engine()) as db:
        kisi = db.query(AppUser).filter(AppUser.username == "admin").one()
        db.add(Customer(id=1, external_key="t-a", name="Alfa Test A.S.", segment="MA", owner_id=kisi.id))
        db.commit()
    imza_html = f'<table><tr><td><img src="{PNG_URL}" width="96"></td><td><b>Giray Sav</b><br>TAM</td></tr></table>'
    assert client.put("/api/v1/session/imza", json={"html": imza_html}, headers=hdr).status_code == 200
    assert client.get("/api/v1/musteri/1/rapor/taslak").json()["data"]["profil_imza"] is True
    r = client.post("/api/v1/musteri/1/rapor/gonder", json={"onay": True, "to": "musteri@example.com", "signature": "Eski metin imza"}, headers=hdr)
    assert r.status_code == 200, r.text
    msg = message_from_bytes(base64.b64decode(r.json()["data"]["eml_base64"]), policy=default)
    html = msg.get_body(("html",)).get_content()
    assert "<b>Giray Sav</b><br>TAM" in html and 'src="cid:imza1@tamlife"' in html and "Eski metin imza" not in html
    gomulu = {p["Content-ID"]: p.get_content() for p in msg.walk() if p.get("Content-ID")}
    assert gomulu["<imza1@tamlife>"] == PNG
    assert "Giray Sav" in msg.get_body(("plain",)).get_content()
