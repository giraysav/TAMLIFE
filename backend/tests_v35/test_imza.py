# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
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
from tests_v35.conftest import login_ok

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
    assert bos["mod"] == "" and bos["html"] == "" and bos["kayitli"] is False
    assert 'alt="Turkcell TAM"' in bos["kurumsal_html"] and "data:image/jpeg;base64," in bos["kurumsal_html"] and bos["sablon"] == bos["kurumsal_html"]
    r = client.put("/api/v1/session/imza", json={"mod": "serbest", "html": '<p>Giray <b>Sav</b><script>x</script></p>'}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["html"] == "<p>Giray <b>Sav</b></p>" and r.json()["data"]["kayitli"] is True
    assert client.put("/api/v1/session/imza", json={"mod": "serbest", "html": ""}, headers=hdr).json()["data"]["kayitli"] is False  # bos = imza yok
    assert client.put("/api/v1/session/imza", json={"mod": "baska"}, headers=hdr).status_code == 400


def test_kurumsal_imza_alanlar_onizleme_ve_kayit(client):
    """2026-10-26 kullanici: imza.html tasarimi panele: ad / cep / sirket / web profilden, unvan / birim / sabit / e-posta imza alanlarindan."""
    hdr = login_ok(client)
    assert client.put("/api/v1/session/profile", json={"first_name": "Giray", "last_name": "Sav", "phone": "0532 210 72 84", "website": "superonline.net"}, headers=hdr).status_code == 200
    alanlar = {"unvan": "Teknik Müşteri Yöneticisi", "birim": "Kurumsal <Çözümler>", "sabit": "+90 212 000 00 00", "eposta": "giray.sav@turkcell.com.tr"}
    on = client.post("/api/v1/session/imza/onizleme", json={"alanlar": alanlar}, headers=hdr).json()["data"]["html"]
    assert ">Giray Sav<" in on and ">Teknik Müşteri Yöneticisi<" in on and "Kurumsal &lt;Çözümler&gt;" in on  # metin kacislanir
    assert 'href="tel:05322107284"' in on and 'href="mailto:giray.sav@turkcell.com.tr"' in on and 'href="https://superonline.net"' in on
    assert ">Turkcell<" in on and 'width="620"' in on  # sirket bos: Turkcell; mail genisligine uygun
    assert client.get("/api/v1/session/imza").json()["data"]["kayitli"] is False  # onizleme kaydetmez
    hatali = client.put("/api/v1/session/imza", json={"mod": "kurumsal", "alanlar": {"eposta": "gecersiz"}}, headers=hdr)
    assert hatali.status_code == 400 and "E-posta" in hatali.text
    assert client.put("/api/v1/session/imza", json={"mod": "kurumsal", "alanlar": {"adres": "x"}}, headers=hdr).status_code == 400
    d = client.put("/api/v1/session/imza", json={"mod": "kurumsal", "alanlar": alanlar}, headers=hdr).json()["data"]
    assert d["mod"] == "kurumsal" and d["kayitli"] and d["alanlar"]["eposta"] == "giray.sav@turkcell.com.tr" and d["kurumsal_html"] == on
    # serbest kipe gecince kurumsal alanlar kalir; kurumsal HTML serbest duzenlemede bicimini korur (font kisaltmasi izinli)
    d = client.put("/api/v1/session/imza", json={"mod": "serbest", "html": on}, headers=hdr).json()["data"]
    assert d["mod"] == "serbest" and "font:700 19px/1.1 Arial" in d["html"] and d["alanlar"]["unvan"] == "Teknik Müşteri Yöneticisi"


def test_aylik_rapor_iletisi_profil_imzasini_tasir(client, monkeypatch, tmp_path):
    monkeypatch.setenv("TAMLIFE_REPORT_DIR", str(tmp_path / "raporlar"))
    hdr = login_ok(client)
    with Session(engine()) as db:
        kisi = db.query(AppUser).filter(AppUser.username == "admin").one()
        db.add(Customer(id=1, external_key="t-a", name="Alfa Test A.S.", segment="MA", owner_id=kisi.id))
        db.commit()
    imza_html = f'<table><tr><td><img src="{PNG_URL}" width="96"></td><td><b>Giray Sav</b><br>TAM</td></tr></table>'
    assert client.put("/api/v1/session/imza", json={"mod": "serbest", "html": imza_html}, headers=hdr).status_code == 200
    assert client.get("/api/v1/musteri/1/rapor/taslak").json()["data"]["profil_imza"] is True
    r = client.post("/api/v1/musteri/1/rapor/gonder", json={"onay": True, "to": "musteri@example.com", "signature": "Eski metin imza"}, headers=hdr)
    assert r.status_code == 200, r.text
    msg = message_from_bytes(base64.b64decode(r.json()["data"]["eml_base64"]), policy=default)
    html = msg.get_body(("html",)).get_content()
    assert "<b>Giray Sav</b><br>TAM" in html and 'src="cid:imza1@tamlife"' in html and "Eski metin imza" not in html
    gomulu = {p["Content-ID"]: p.get_content() for p in msg.walk() if p.get("Content-ID")}
    assert gomulu["<imza1@tamlife>"] == PNG
    assert "Giray Sav" in msg.get_body(("plain",)).get_content()


def test_aylik_rapor_iletisi_kurumsal_imzayi_tasir(client, monkeypatch, tmp_path):
    monkeypatch.setenv("TAMLIFE_REPORT_DIR", str(tmp_path / "raporlar"))
    hdr = login_ok(client)
    with Session(engine()) as db:
        kisi = db.query(AppUser).filter(AppUser.username == "admin").one()
        db.add(Customer(id=1, external_key="t-a", name="Alfa Test A.S.", segment="MA", owner_id=kisi.id))
        db.commit()
    client.put("/api/v1/session/imza", json={"mod": "kurumsal", "alanlar": {"unvan": "TAM", "eposta": "tam@turkcell.com.tr"}}, headers=hdr)
    r = client.post("/api/v1/musteri/1/rapor/gonder", json={"onay": True, "to": "musteri@example.com"}, headers=hdr)
    assert r.status_code == 200, r.text
    msg = message_from_bytes(base64.b64decode(r.json()["data"]["eml_base64"]), policy=default)
    html = msg.get_body(("html",)).get_content()
    assert 'alt="Turkcell TAM"' in html and 'src="cid:imza1@tamlife"' in html and "data:image" not in html
    assert any(p.get_content_type() == "image/jpeg" and p["Content-ID"] == "<imza1@tamlife>" for p in msg.walk())
    assert "tam@turkcell.com.tr" in msg.get_body(("plain",)).get_content()
