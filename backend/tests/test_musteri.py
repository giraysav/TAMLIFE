"""Musteri karti ve aylik rapor: kapsam, kart semasi, kimlik/iletisim duzenleme, rapor taslak/gonderim/geri alma."""

import base64
import re
from email import message_from_bytes
from email.policy import default

import pytest
from sqlalchemy.orm import Session

from app.db import engine, kullanici_oturumu
from app.models import ApnRevenue, AppUser, Customer, MatrixConfig, Report, ReportDispatch, SmsRevenue
from app.rapor import servis as rapor_servis
from tests.conftest import login_ok

AY = rapor_servis.donem()


@pytest.fixture
def veri(client):
    """admin (id 1) + ayse (id 2); A (cati, admin), A-ist (istirak, admin), B (cati, ayse). Gercek musteri verisi yok."""
    with Session(engine()) as db:
        db.add_all([AppUser(id=1, username="admin", display_name="Admin Kisi", role="admin", is_admin=True), AppUser(id=2, username="ayse", display_name="Ayse Test", role="TeamMember")])
        db.flush()
        db.add_all(
            [
                Customer(id=1, external_key="t-a", name="Alfa Test A.S.", segment="MA", owner_id=1, customer_no="100", inventory_count=5, alarm_count=2, complaint_count=1, request_count=3, score=71.26),
                Customer(id=2, external_key="t-ai", name="Alfa Istirak", segment="MA", owner_id=1, parent_id=1, alarm_count=1),
                Customer(id=3, external_key="t-b", name="Beta Test Ltd", segment="SMB", owner_id=2, score=40),
            ]
        )
        db.add(MatrixConfig(key="destech", headers=["Müşteri Ünvanı", "Rol"], rows=[["ALFA TEST A.S.", "TAC"], ["Beta Test Ltd", "KMT"]]))
        db.commit()
    with kullanici_oturumu("admin") as k:  # gelirler TAM'in kendi dosyasinda
        k.add(SmsRevenue(tam_name="Admin Kisi", customer_name="alfa test a.s.", amount=100, currency="TRY", year=2026, month=9))
        k.add(SmsRevenue(tam_name="Admin Kisi", customer_name="Alfa Istirak", amount=50.5, currency="TRY", year=2026, month=8))
        k.add(ApnRevenue(tam_name="Admin Kisi", customer_name="Alfa Test A.S.", amount=10, currency="USD", installation_pct=40, year=2026, month=9))
        k.commit()
    return client


def _cikis(client, hdr):
    client.post("/api/v1/session/logout", headers=hdr)


def _giris(client, monkeypatch, rol):
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    return login_ok(client)


def test_kapsam_yonetici_hepsini_member_kendininkini_gorur(veri, monkeypatch):
    hdr = login_ok(veri)
    d = veri.get("/api/v1/musteri").json()["data"]
    assert d["total"] == 3 and [i["name"] for i in d["items"]] == ["Alfa Istirak", "Alfa Test A.S.", "Beta Test Ltd"]
    assert next(i for i in d["items"] if i["id"] == 1)["score"] == 71.3 and next(i for i in d["items"] if i["id"] == 2)["score"] is None  # istirakin skoru yok
    _cikis(veri, hdr)
    _giris(veri, monkeypatch, "TeamMember")  # 2026-10-26: personel yalniz kendisine atanan kartlari gorur (app.gorunurluk)
    d = veri.get("/api/v1/musteri").json()["data"]
    assert {i["id"] for i in d["items"]} == {1, 2} and d["total"] == 2  # 2: kendi catisinin istiraki
    assert veri.get("/api/v1/musteri/3").status_code == 404  # baskasinin karti: varligi sizdirilmaz
    assert {i["id"] for i in veri.get("/api/v1/musteri/portfoy").json()["data"]["items"]} == {1}
    assert [k["id"] for k in veri.get("/api/v1/musteri/secenekler").json()["data"]["tam"]] in ([], [1])  # TAM suzgecinde yalniz kendisi
    assert veri.get("/api/v1/musteri/1").json()["data"]["erisim"]["kimlik_duzenle"] is True


def test_arama_joker_karakterleri_literaldir(veri):
    login_ok(veri)
    assert veri.get("/api/v1/musteri", params={"q": "alfa"}).json()["data"]["total"] == 2
    assert veri.get("/api/v1/musteri", params={"q": "%"}).json()["data"]["total"] == 0
    assert veri.get("/api/v1/musteri", params={"q": "_"}).json()["data"]["total"] == 0


def test_kart_semasi(veri):
    login_ok(veri)
    k = veri.get("/api/v1/musteri/1").json()["data"]
    assert set(k) >= {"kimlik", "operasyon", "ekip", "iletisim", "kritik_ci", "raporlar", "gelirler", "erisim", "tam_secenekleri"}
    assert k["kimlik"]["unvan"] == "Alfa Test A.S." and k["kimlik"]["tam"] == "Admin Kisi" and k["kimlik"]["cati"] is None
    assert [i["unvan"] for i in k["kimlik"]["istirakler"]] == ["Alfa Istirak"]
    assert k["operasyon"]["final_skor"] == 71.3 and k["operasyon"]["kendi"]["alarm"] == 2
    assert k["operasyon"]["istirak_dahil"]["alarm"] == 3  # cati + istirak
    assert k["operasyon"]["ft_hacim"] == "0,00 ₺"
    assert k["ekip"]["satirlar"] == [["ALFA TEST A.S.", "TAC"]]  # unvan eslesmesi: buyuk/kucuk harf gozetilmez
    assert k["gelirler"]["ict"]["toplam"] == {"TRY": 150.5} and k["gelirler"]["apn"]["toplam"] == {"USD": 10.0}
    assert k["gelirler"]["apn"]["son"][0]["installation_pct"] == 40
    assert set(k["iletisim"]) >= {"tac_name", "sol_kmt_email", "mobil_kmt_detail", "sales_manager"}
    ist = veri.get("/api/v1/musteri/2").json()["data"]
    assert ist["kimlik"]["cati"] == {"id": 1, "unvan": "Alfa Test A.S."} and ist["operasyon"]["final_skor"] is None and ist["kimlik"]["ayri_rapor"] is False


def test_rapor_ve_gelir_bolumleri_modul_iznine_baglidir(veri, monkeypatch):
    hdr = login_ok(veri)
    assert veri.put("/api/v1/roller/TeamMember", json={"modules": ["musteri"], "landing": "ozet"}, headers=hdr).status_code == 200
    _cikis(veri, hdr)
    _giris(veri, monkeypatch, "TeamMember")
    k = veri.get("/api/v1/musteri/1").json()["data"]
    assert "raporlar" not in k and "gelirler" not in k and k["erisim"]["rapor"] is False
    assert "tam_secenekleri" not in k and k["erisim"]["tam_degistir"] is False  # sorumlu devri yalniz yonetici
    assert k["erisim"]["sil"] is True and k["erisim"]["kimlik_duzenle"] is True  # kendi karti (2026-10-19: herkes kendi verisinde)
    assert veri.get("/api/v1/rapor/gonderilenler").status_code == 403  # rapor modulu verilmedi


def test_kimlik_guncelle_ve_unvan_baglantilari_tasinir(veri):
    hdr = login_ok(veri)
    put = lambda mid, **g: veri.put(f"/api/v1/musteri/{mid}/kimlik", json=g, headers=hdr)
    assert put(1, name="beta  TEST ltd").status_code == 409  # baska musterinin unvani (bosluk/harf farki yok sayilir)
    assert put(1, segment="Kurumsal").status_code == 400  # eski deger yalniz mevcut degerse korunur
    assert put(1, inventory=-1).status_code == 400
    assert put(1, name="x" * 151).status_code == 400
    r = put(1, name="Alfa Yeni A.S.", segment="sa", sector="Enerji", ncst="N-9", customer_no="200", ft_volume="1.000,00 ₺", inventory=7)
    assert r.status_code == 200 and r.json()["data"]["unvan"] == "Alfa Yeni A.S."
    k = veri.get("/api/v1/musteri/1").json()["data"]
    assert k["kimlik"]["segment"] == "SA" and k["kimlik"]["ncst"] == "N-9" and k["kimlik"]["envanter"] == 7 and k["operasyon"]["ft_hacim"] == "1.000,00 ₺"
    # gelirler ve matris satiri yeni unvana tasindi: kart bos gelmez
    assert k["gelirler"]["ict"]["toplam"] == {"TRY": 150.5} and k["gelirler"]["apn"]["toplam"] == {"USD": 10.0}  # cati + istirak
    assert k["ekip"]["satirlar"] == [["Alfa Yeni A.S.", "TAC"]]
    # mevcut eski segment degeri baska alan duzenlenirken engellenmez
    with Session(engine()) as db:
        db.get(Customer, 3).segment = "Kurumsal"
        db.commit()
    assert put(3, sector="Gida", segment="Kurumsal").status_code == 200
    assert put(3, name="").status_code == 400


def test_iletisim_dogrulama_ve_kayit(veri):
    hdr = login_ok(veri)
    put = lambda **g: veri.put("/api/v1/musteri/1/iletisim", json=g, headers=hdr)
    assert put(tac_email="gecersiz").status_code == 400
    assert put(tac_gsm="abc").status_code == 400
    assert put(sales_manager="s" * 101).status_code == 400
    r = put(tac_name="Test TAC", tac_email="tac@example.com", tac_gsm="+90 555 000 00 00", mobil_kmt_detail="not")
    assert r.status_code == 200 and r.json()["data"]["tac_email"] == "tac@example.com"
    assert veri.get("/api/v1/musteri/1").json()["data"]["iletisim"]["tac_name"] == "Test TAC"
    assert put(tac_name="").json()["data"]["tac_name"] == ""  # alan temizlenebilir


def test_ekle_tam_degistir_sil_kurallari(veri, monkeypatch):
    hdr = login_ok(veri)
    r = veri.post("/api/v1/musteri", json={"name": "Gama Test", "segment": "pa", "owner_id": 2}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["owner_id"] == 2
    assert veri.post("/api/v1/musteri", json={"name": "gama   test"}, headers=hdr).status_code == 409
    ist = veri.post("/api/v1/musteri", json={"name": "Gama Alt", "parent_id": 1}, headers=hdr).json()["data"]["id"]
    assert veri.get(f"/api/v1/musteri/{ist}").json()["data"]["kimlik"]["segment"] == "MA"  # catinin segmenti
    assert veri.put("/api/v1/musteri/1/sorumlu", json={"owner_id": 99}, headers=hdr).status_code == 404
    assert veri.put("/api/v1/musteri/1/sorumlu", json={"owner_id": 2}, headers=hdr).status_code == 200
    _cikis(veri, hdr)

    # 'admin' satirina (id 1) bagli Member (2026-10-19 kullanici karari): yalniz KENDI verisinde ekler, duzenler, siler.
    # Kart 1 artik ayse'nin (id 2); kart 2 (istirak) ve 'Gama Alt' id 1'in.
    hdr2 = _giris(veri, monkeypatch, "TeamMember")
    assert veri.post("/api/v1/musteri", json={"name": "Baskasi", "owner_id": 2}, headers=hdr2).status_code == 403  # baskasi adina ekleyemez
    kendi = veri.post("/api/v1/musteri", json={"name": "Kendi Musterim"}, headers=hdr2)
    assert kendi.status_code == 200 and kendi.json()["data"]["owner_id"] == 1  # kendi adina acilir
    assert veri.put("/api/v1/musteri/2/sorumlu", json={"owner_id": 2}, headers=hdr2).status_code == 403  # devir yalniz yonetici
    assert veri.put("/api/v1/musteri/2/kimlik", json={"sector": "X"}, headers=hdr2).status_code == 200
    assert veri.put("/api/v1/musteri/2/kimlik", json={"parent_id": 3}, headers=hdr2).status_code == 404  # baskasinin catisina baglayamaz
    assert veri.put("/api/v1/musteri/2/iletisim", json={"tac_name": "X"}, headers=hdr2).status_code == 200
    # baskasinin karti 2026-10-26'dan beri gorunmez: yazma da 404 (varligi sizdirilmaz)
    assert veri.put("/api/v1/musteri/3/kimlik", json={"sector": "X"}, headers=hdr2).status_code == 404
    assert veri.put("/api/v1/musteri/3/iletisim", json={"tac_name": "X"}, headers=hdr2).status_code == 404
    assert veri.put("/api/v1/musteri/3/rapor/taslak", json={"alanlar": {}}, headers=hdr2).status_code == 404  # aylik rapor da
    assert veri.delete("/api/v1/musteri/3", headers=hdr2).status_code == 404
    kart = veri.get("/api/v1/musteri/2").json()["data"]
    assert all(kart["erisim"][k] for k in ("kimlik_duzenle", "iletisim_duzenle", "istirak_ekle", "sil", "ayri_rapor_sec"))
    assert kart["erisim"]["tam_degistir"] is False and "tam_secenekleri" not in kart
    assert {c["id"] for c in kart["cati_secenekleri"]} == {kendi.json()["data"]["id"]}  # yalniz kendi catilari (kart 1 ayse'nin)
    assert veri.delete(f"/api/v1/musteri/{ist}", headers=hdr2).status_code == 200  # kendi kartini siler
    _cikis(veri, hdr2)

    hdr3 = _giris(veri, monkeypatch, "admin")
    with Session(engine()) as db:
        db.add(Report(customer_id=2, user_id=1, report_month=1, report_year=2026, is_submitted=True))
        db.commit()
    erisim = veri.get("/api/v1/musteri/2").json()["data"]["erisim"]
    assert all(erisim[k] for k in ("kimlik_duzenle", "iletisim_duzenle", "istirak_ekle", "sil", "tam_degistir", "ayri_rapor_sec"))
    r = veri.delete("/api/v1/musteri/1", headers=hdr3)
    assert r.status_code == 200 and r.json()["data"]["silinen"] == 2  # cati + kalan istirak (Gama Alt"i Member sildi)
    assert veri.get("/api/v1/musteri/1").status_code == 404 and veri.get("/api/v1/musteri/2").status_code == 404


def test_taslak_varsayilanlari_kayit_ve_dil(veri):
    hdr = login_ok(veri)
    t = veri.get("/api/v1/musteri/1/rapor/taslak").json()["data"]
    assert (t["yil"], t["ay"]) == AY and t["kayitli"] is False and t["birim"] is True and t["gonderim"] is None
    a = t["alanlar"]
    assert a["dil"] == "tr" and a["konu"].startswith("TAM Aylık Rapor - ") and a["konu"].endswith("| Alfa Test A.S.")
    assert "Sayın Müşterimiz" in a["govde"] and a["imza"].startswith("Admin Kisi\nTeknik Müşteri Yöneticisi")  # gorunen ad (2026-10-26)
    assert a["olumlu"].startswith("Bu dönem") and "Erişim & Arıza Takibi" in a["bilgi"]
    assert veri.put("/api/v1/musteri/1/rapor/taslak", json={"alanlar": {"dil": "de"}}, headers=hdr).status_code == 400
    assert veri.put("/api/v1/musteri/1/rapor/taslak", json={"alanlar": {"dil": "en", "olumlu": "Iyi gecti", "bilinmeyen": "at", "konu": "k" * 500}}, headers=hdr).status_code == 200
    t = veri.get("/api/v1/musteri/1/rapor/taslak").json()["data"]
    assert t["kayitli"] is True and t["alanlar"]["dil"] == "en" and t["alanlar"]["olumlu"] == "Iyi gecti"
    assert len(t["alanlar"]["konu"]) == 200 and "bilinmeyen" not in t["alanlar"]
    assert t["alanlar"]["devam"].startswith("No open work items")  # diger alanlar secili dilin baslangic metni


def test_alicilar_dogrulama(veri, monkeypatch):
    hdr = login_ok(veri)
    put = lambda **g: veri.put("/api/v1/musteri/1/rapor/alicilar", json=g, headers=hdr)
    assert put(kime="gecersiz").status_code == 400
    assert put(kime=[f"u{i}@example.com" for i in range(21)]).status_code == 400
    r = put(kime="a@example.com; b@example.com", bilgi=["c@example.com"])
    assert r.json()["data"] == {"kime": "a@example.com; b@example.com", "bilgi": "c@example.com"}
    monkeypatch.setenv("RAPOR_MAIL_IZINLI_ALANLAR", "example.com")
    assert put(kime="a@baska.org").status_code == 400
    assert put(kime="a@example.com").status_code == 200
    assert veri.get("/api/v1/musteri/1/rapor/taslak").json()["data"]["alicilar"]["kime"] == "a@example.com"


def test_icinde_bulunulan_ayin_raporu_ayri_donem(veri, monkeypatch, tmp_path):
    """2026-10-31 kullanici: ay sonunda icinde bulunulan ayin raporu da hazirlanabilir; her donemde ayda tek kural ayri, eski aylar kapali."""
    monkeypatch.setenv("TAMLIFE_REPORT_DIR", str(tmp_path / "raporlar"))
    hdr = login_ok(veri)
    url = "/api/v1/musteri/1/rapor"
    onceki, bu = (f"{y}-{a:02d}" for y, a in rapor_servis.secilebilir_donemler())
    t = veri.get(f"{url}/taslak").json()["data"]
    assert (t["yil"], t["ay"]) == AY and t["donemler"] == [onceki, bu] and t["ay_bitmedi"] is False
    t = veri.get(f"{url}/taslak", params={"donem": bu}).json()["data"]
    assert f"{t['yil']}-{t['ay']:02d}" == bu and t["ay_bitmedi"] is True
    eski_yil, eski_ay = rapor_servis._onceki_donem(*AY)
    assert veri.get(f"{url}/taslak", params={"donem": f"{eski_yil}-{eski_ay:02d}"}).status_code == 400  # eski ay kapali
    assert veri.get(f"{url}/taslak", params={"donem": "2026-13"}).status_code == 422
    assert veri.post(f"{url}/gonder", params={"donem": bu}, json={"onay": True}, headers=hdr).status_code == 200
    assert veri.post(f"{url}/gonder", params={"donem": bu}, json={"onay": True}, headers=hdr).status_code == 409  # o donemde tek
    assert veri.get(f"{url}/taslak").json()["data"]["gonderim"] is None  # onceki ay hala acik
    assert veri.post(f"{url}/gonder", json={"onay": True}, headers=hdr).status_code == 200


def test_gonderim_onay_ayda_tek_kilit_geri_alma(veri, monkeypatch, tmp_path):
    monkeypatch.setenv("TAMLIFE_REPORT_DIR", str(tmp_path / "raporlar"))
    hdr = login_ok(veri)
    url = "/api/v1/musteri/1/rapor"
    assert veri.post(f"{url}/gonder", json={}, headers=hdr).status_code == 400  # onay yok
    assert veri.post(f"{url}/gonder", json={"onay": True, "pdf_base64": "bozuk!"}, headers=hdr).status_code == 400
    assert veri.post(f"{url}/gonder", json={"onay": True, "pdf_base64": base64.b64encode(b"degil").decode()}, headers=hdr).status_code == 400
    pdf = base64.b64encode(b"%PDF-1.4 test").decode()
    r = veri.post(f"{url}/gonder", json={"onay": True, "to": "a@example.com", "subject": "  Konu   test ", "pdf_base64": pdf}, headers=hdr)
    assert r.status_code == 200, r.text
    g = r.json()["data"]["gonderim"]
    assert g["konu"] == "Konu test" and g["durum"] == "sent" and g["pdf"] is True and g["gonderen"] == "admin"
    assert list((tmp_path / "raporlar").rglob("*.pdf")) and r.json()["data"]["kime"] == ["a@example.com"]
    with Session(engine()) as db:
        assert db.get(Customer, 1).report_count == 1
        assert db.query(Report).filter_by(customer_id=1, report_month=AY[1], report_year=AY[0], is_submitted=True).count() == 1
    # ayda tek: ikinci gonderim 409, taslak kilitli
    r2 = veri.post(f"{url}/gonder", json={"onay": True}, headers=hdr)
    assert r2.status_code == 409 and r2.json()["kilitli"] is True and r2.json()["gonderim"]["id"] == g["id"]
    k = veri.put(f"{url}/taslak", json={"alanlar": {"olumlu": "x"}}, headers=hdr)
    assert k.status_code == 409 and k.json()["kilitli"] is True
    assert veri.get(f"{url}/taslak").json()["data"]["gonderim"]["id"] == g["id"]
    assert [x["id"] for x in veri.get(f"{url}/gecmis").json()["data"]] == [g["id"]]
    _cikis(veri, hdr)

    hdr2 = _giris(veri, monkeypatch, "TeamMngr")  # yonetici geri alamaz, yalniz admin
    assert veri.post(f"/api/v1/rapor/gonderim/{g['id']}/geri-al", headers=hdr2).status_code == 403
    _cikis(veri, hdr2)
    hdr3 = _giris(veri, monkeypatch, "admin")
    r3 = veri.post(f"/api/v1/rapor/gonderim/{g['id']}/geri-al", headers=hdr3)
    assert r3.status_code == 200 and r3.json()["data"]["durum"] == "reverted" and r3.json()["data"]["geri_alan"] == "admin"
    assert veri.post(f"/api/v1/rapor/gonderim/{g['id']}/geri-al", headers=hdr3).status_code == 404
    with Session(engine()) as db:
        assert db.get(Customer, 1).report_count == 0 and db.query(Report).filter_by(customer_id=1).count() == 0
        assert db.get(ReportDispatch, g["id"]).status == "reverted"  # arsivde kalir
    assert veri.post(f"{url}/gonder", json={"onay": True}, headers=hdr3).status_code == 200  # ay yeniden acildi


def test_gonderim_outlook_taslagi_eml(veri, monkeypatch, tmp_path):
    """Gonderim .eml taslagi dondurur: X-Unsent, alicilar, konu, kacislanmis HTML govde, gomulu logolar, PDF eki."""
    monkeypatch.setenv("TAMLIFE_REPORT_DIR", str(tmp_path / "raporlar"))
    monkeypatch.setenv("AD_DOMAIN", "turkcell.com.tr")
    hdr = login_ok(veri)
    url = "/api/v1/musteri/1/rapor"
    # kayitli taslak: govde ve imza buradan gelir, istek yalniz dili degistirir
    alanlar = {"govde": "Sayın <b>Müşterimiz</b>,\n\nRapor ekte.\nİkinci satır", "imza": "Ad Soyad\nTAM"}
    assert veri.put(f"{url}/taslak", json={"alanlar": alanlar}, headers=hdr).status_code == 200
    pdf = base64.b64encode(b"%PDF-1.4 test").decode()
    govde = {"onay": True, "to": "giray.sav@turkcell.com.tr", "cc": "b@example.com", "subject": "Konu", "lang": "en", "pdf_base64": pdf}
    r = veri.post(f"{url}/gonder", json=govde, headers=hdr)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["eml_adi"].startswith("TAM_Aylik_Rapor_") and d["eml_adi"].endswith(".eml")
    msg = message_from_bytes(base64.b64decode(d["eml_base64"]), policy=default)
    assert msg["X-Unsent"] == "1" and msg["Subject"] == "Konu" and msg["From"] is None  # taslak: Outlook kisinin hesabindan (2026-10-26)
    assert msg["To"] == "GIRAY SAV <giray.sav@turkcell.com.tr>" and msg["Cc"] == "b@example.com"  # musteri adresine ad uydurulmaz
    html = msg.get_body(("html",)).get_content()
    assert "Sayın &lt;b&gt;Müşterimiz&lt;/b&gt;," in html and "<b>Müşterimiz" not in html  # personel metni kacislanir
    assert "Rapor ekte.<br>İkinci satır" in html and ">Ad Soyad</span><br>TAM" in html
    assert "TAM Monthly Report" in html and "${" not in html and "<!--" not in html
    assert "CORPORATE CUSTOMER" not in html and "Monthly Technical Account Report" not in html  # sade baslik
    assert re.search(r"TAM Monthly Report <span[^>]*>&nbsp;\|&nbsp;</span> \w+ \d{4}</div>\s*<div[^>]*>Alfa Test A.S.</div>", html)  # altinda musteri
    assert html.count("cid:teknocan@tamlife") == 2 and "imzalogo" not in html  # baslik + imza bandi
    assert html.count('width="144" height="144"') == 2 and 'width="72"' not in html  # logo iki bantta da 144 px
    assert re.search(r'align="left"[^>]*text-align:left;">\s*<div[^>]*>TAM Monthly Report', html) and "text-align:center" not in html  # baslik sola yasli
    cidler = {p["Content-ID"] for p in msg.walk() if p.get_content_maintype() == "image"}
    assert cidler == {"<teknocan@tamlife>"}
    ekler = list(msg.iter_attachments())
    assert [e.get_filename() for e in ekler] == [d["eml_adi"][:-4] + ".pdf"] and ekler[0].get_content() == b"%PDF-1.4 test"
    assert msg.get_body(("plain",)).get_content().rstrip().endswith("Ad Soyad\nTAM")


def _rapor_arizalari(bekle: int = 0) -> list:
    """TL-RAP-01 kayitlari (ariza kaydi arka planda yazilir: en cok ~2 sn beklenir)."""
    import time

    from app.yonetim.models import FaultEvent

    for _ in range(40):
        with Session(engine()) as db:
            kayitlar = [(f.code, f.source, f.message, f.actor) for f in db.query(FaultEvent).filter(FaultEvent.code == "TL-RAP-01")]
        if len(kayitlar) >= bekle:
            return kayitlar
        time.sleep(0.05)
    return kayitlar


def test_gonderim_hatasi_admin_bildirimi(veri, monkeypatch, tmp_path):
    """2026-10-26: gonderimde beklenmeyen hata TL-RAP-01 ariza kaydi + admin ust cubuk bildirimi; kullanici hatasi bildirim uretmez."""
    monkeypatch.setenv("TAMLIFE_REPORT_DIR", str(tmp_path / "raporlar"))
    hdr = login_ok(veri)
    url = "/api/v1/musteri/1/rapor"
    assert veri.post(f"{url}/gonder", json={"onay": False, "to": "musteri@example.com"}, headers=hdr).status_code == 400  # onay yok
    assert veri.post(f"{url}/gonder", json={"onay": True, "to": "bozuk"}, headers=hdr).status_code == 400  # gecersiz alici

    def disk_dolu(*_a: object) -> None:
        raise OSError("disk dolu")

    monkeypatch.setattr(rapor_servis, "_pdf_yaz", disk_dolu)
    pdf = base64.b64encode(b"%PDF-1.4 test").decode()
    assert veri.post(f"{url}/gonder", json={"onay": True, "to": "musteri@example.com", "pdf_base64": pdf}, headers=hdr).status_code == 500
    (kod, kaynak, mesaj, kisi), = _rapor_arizalari(bekle=1)
    assert (kod, kaynak, kisi) == ("TL-RAP-01", "rapor.gonder", "admin") and mesaj.startswith("müşteri #1 Alfa Test") and "OSError" in mesaj
    b = veri.get("/api/v1/yonetim/bildirimler").json()["data"]
    assert b["toplam"] == 1 and b["son"][0]["kod"] == "TL-RAP-01"
    a = veri.get("/api/v1/yonetim/arizalar?kod=TL-RAP-01").json()["data"]
    assert a["toplam"] == 1
    veri.post(f"/api/v1/yonetim/arizalar/{a['satirlar'][0]['id']}/durum", json={"durum": "closed", "notu": "disk bosaltildi"}, headers=hdr)
    assert veri.get("/api/v1/yonetim/bildirimler").json()["data"]["toplam"] == 0  # kapatilan kayit bildirimden duser


def test_gece_senkronu_admin_bildirimi(veri):
    """2026-10-27: gece senkronu sorunu (kurulum/gece_sync.ps1 -> araclar/ariza_bildir.py) TL-SNC-01 ile admin zilinde gorunur."""
    from app import ariza

    login_ok(veri)
    ariza.kaydet("TL-SNC-01", "gece senkronu HATA: PANEL ACILAMADI", kaynak="gece_sync", kullanici="sistem")
    b = veri.get("/api/v1/yonetim/bildirimler").json()["data"]
    assert b["toplam"] == 1 and b["son"][0]["kod"] == "TL-SNC-01"


def test_ayri_rapor_ve_durum_ozeti(veri):
    hdr = login_ok(veri)
    assert veri.put("/api/v1/musteri/1/ayri-rapor", json={"ayri_rapor": True}, headers=hdr).status_code == 400  # cati
    assert veri.put("/api/v1/musteri/2/ayri-rapor", json={"ayri_rapor": True}, headers=hdr).json()["data"] == {"ayri_rapor": True}
    yil, ay = AY
    d = veri.get("/api/v1/rapor/durum").json()["data"]
    assert d["toplam"] == {"musteri": 3, "atilan": 0, "bekleyen": 3, "muaf": 0}  # A, B ve ayri rapor secilmis istirak
    assert veri.post("/api/v1/musteri/1/rapor/gonder", json={"onay": True}, headers=hdr).status_code == 200
    d = veri.get("/api/v1/rapor/durum", params={"yil": yil, "ay": ay}).json()["data"]
    assert d["toplam"] == {"musteri": 3, "atilan": 1, "bekleyen": 2, "muaf": 0}
    satirlar = {s["ad"]: s for s in d["satirlar"]}
    assert satirlar["-"] == {"id": None, "ad": "-", "musteri": 2, "atilan": 1, "bekleyen": 1, "muaf": 0}  # admin sahipli birimler tek '-' satirinda: yonetici TAM satiri olmaz
    assert satirlar["Ayse Test"] == {"id": 2, "ad": "Ayse Test", "musteri": 1, "atilan": 0, "bekleyen": 1, "muaf": 0} and "Admin Kisi" not in satirlar
    assert veri.put("/api/v1/musteri/2/ayri-rapor", json={"ayri_rapor": False}, headers=hdr).status_code == 200
    assert veri.get("/api/v1/rapor/durum").json()["data"]["toplam"]["musteri"] == 2


def test_rapor_muaf_bekleyene_sayilmaz(veri):
    """2026-10-31 kullanici: kartta 'raporu atilmamaktadir' isaretli musteri durum ozetinde bekleyen degil, muaf sayilir."""
    hdr = login_ok(veri)
    once = veri.get("/api/v1/rapor/durum").json()["data"]["toplam"]
    assert veri.get("/api/v1/musteri/1").json()["data"]["kimlik"]["rapor_muaf"] is False
    assert veri.put("/api/v1/musteri/1/rapor-muaf", json={"rapor_muaf": True}, headers=hdr).json()["data"] == {"rapor_muaf": True}
    kart = veri.get("/api/v1/musteri/1").json()["data"]
    assert kart["kimlik"]["rapor_muaf"] is True and kart["erisim"]["rapor_muaf_sec"] is True
    sonra = veri.get("/api/v1/rapor/durum").json()["data"]["toplam"]
    assert sonra == {**once, "musteri": once["musteri"] - 1, "bekleyen": once["bekleyen"] - 1, "muaf": 1}
    assert veri.put("/api/v1/musteri/1/rapor-muaf", json={"rapor_muaf": "evet"}, headers=hdr).status_code == 422
    assert veri.put("/api/v1/musteri/1/rapor-muaf", json={"rapor_muaf": False}, headers=hdr).status_code == 200
    assert veri.get("/api/v1/rapor/durum").json()["data"]["toplam"] == once


def test_yetkisiz_ve_csrf(veri, monkeypatch):
    assert veri.get("/api/v1/musteri").status_code == 401
    hdr = login_ok(veri)
    assert veri.put("/api/v1/musteri/1/kimlik", json={"sector": "x"}).status_code == 403  # CSRF'siz
    # moduller bos liste verilirse musteri modulu kapali
    assert veri.put("/api/v1/roller/TeamMember", json={"modules": [], "landing": "ozet"}, headers=hdr).status_code == 200
    _cikis(veri, hdr)
    hdr = _giris(veri, monkeypatch, "TeamMember")
    assert veri.get("/api/v1/musteri").status_code == 403  # modul verilmedi
    # modullere musteri eklenirse erisilebilir
    _cikis(veri, hdr)
    admin_hdr = _giris(veri, monkeypatch, "admin")  # rol ortam degiskeni TeamMember'da kalmasin
    assert veri.put("/api/v1/roller/TeamMember", json={"modules": ["musteri"], "landing": "ozet"}, headers=admin_hdr).status_code == 200
    _cikis(veri, admin_hdr)
    hdr = _giris(veri, monkeypatch, "TeamMember")
    assert veri.get("/api/v1/musteri").status_code == 200  # okuma acik
    assert veri.put("/api/v1/musteri/3/kimlik", json={"sector": "x"}, headers=hdr).status_code == 404  # 2026-10-26: kendisine atanmamis kart gorunmez


def test_yazan_kisinin_kullanici_satiri_yoksa_olusturulur(client):
    """Yerel/dev oturumunda app_user satiri bos olabilir; musteri ekleme ve rapor gonderimi gecerli kisi kimligiyle yazilir."""
    hdr = login_ok(client)
    with Session(engine()) as db:
        assert db.query(AppUser).filter_by(username="admin").count() == 1  # giris satiri olusturur
        db.query(AppUser).delete()  # satir sonradan kaybolmus gibi: yazma yine olusturmali
        db.commit()
    mid = client.post("/api/v1/musteri", json={"name": "Satirsiz Test"}, headers=hdr).json()["data"]["id"]
    with Session(engine()) as db:
        kisi = db.query(AppUser).filter_by(username="admin").one()
        assert db.get(Customer, mid).owner_id is None  # yonetici/admin kendi adina musteri sahibi olmaz (tek personel kumesi, 2026-10-13)
    assert client.post(f"/api/v1/musteri/{mid}/rapor/gonder", json={"onay": True}, headers=hdr).status_code == 200
    with Session(engine()) as db:
        r = db.query(Report).filter_by(customer_id=mid).one()
        g = db.query(ReportDispatch).filter_by(customer_id=mid).one()
        assert r.user_id == kisi.id and g.sender_id == kisi.id


def test_modul_sahibi_musteri_personel_listesinde_yer_alir(veri):
    """2026-10-20 kullanici: modul sahipleri (ICT SMS, APN, Toptan, Baglantili Araclar) listelere geri eklendi, sorumlu yapilabilir."""
    with Session(engine()) as db:
        db.add(AppUser(id=3, username="modulcu", display_name="Modul Sahibi", role="TeamMember", module_owner="tamapn"))
        db.commit()
    hdr = login_ok(veri)
    tam = {k["id"] for k in veri.get("/api/v1/musteri/secenekler").json()["data"]["tam"]}
    assert {2, 3} <= tam
    assert 3 in {k["id"] for k in veri.get("/api/v1/musteri/1").json()["data"]["tam_secenekleri"]}
    assert veri.put("/api/v1/musteri/1/sorumlu", json={"owner_id": 3}, headers=hdr).status_code == 200


def test_raporlar_herkese_acik_benim_yerim_kisiye_ozel(veri, monkeypatch):
    """2026-10-26 kullanici karari: Benim Yerim (Musteri Yonetimi) kisiye ozel, Raporlar (Aylik Raporlar durum ozeti) herkese acik."""
    hdr = login_ok(veri)
    yonetici = veri.get("/api/v1/rapor/durum").json()["data"]
    _cikis(veri, hdr)
    _giris(veri, monkeypatch, "TeamMember")
    assert veri.get("/api/v1/musteri").json()["data"]["total"] == 2  # yalniz kendi kartlari
    durum = veri.get("/api/v1/rapor/durum").json()["data"]
    assert durum["toplam"] == yonetici["toplam"] and durum["toplam"]["musteri"] >= 2  # rapor birimlerinin hepsi (baskasininki dahil)
    assert any(s["ad"] == "Ayse Test" for s in durum["satirlar"])  # baska TAM'in satiri da gorunur
