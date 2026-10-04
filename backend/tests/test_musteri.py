"""Musteri karti ve aylik rapor: kapsam, kart semasi, kimlik/iletisim duzenleme, rapor taslak/gonderim/geri alma."""

import base64
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app import rapor_servis
from app.deps import engine
from app.models import ApnRevenue, AppUser, Customer, MatrixConfig, Report, ReportDispatch, SmsRevenue
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
        db.add(SmsRevenue(tam_name="Admin Kisi", customer_name="alfa test a.s.", amount=100, currency="TRY", year=2026, month=9))
        db.add(SmsRevenue(tam_name="Admin Kisi", customer_name="Alfa Istirak", amount=50.5, currency="TRY", year=2026, month=8))
        db.add(ApnRevenue(tam_name="Admin Kisi", customer_name="Alfa Test A.S.", amount=10, currency="USD", installation_pct=40, year=2026, month=9))
        db.commit()
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
    _giris(veri, monkeypatch, "TeamMember")  # kullanici 'admin' satirina bagli: yalniz kendi musterileri
    d = veri.get("/api/v1/musteri").json()["data"]
    assert {i["id"] for i in d["items"]} == {1, 2}
    assert veri.get("/api/v1/musteri/3").status_code == 404  # baskasinin musterisinin varligi sizdirilmaz
    assert veri.get("/api/v1/musteri/1").status_code == 200


def test_arama_joker_karakterleri_literaldir(veri):
    login_ok(veri)
    assert veri.get("/api/v1/musteri", params={"q": "alfa"}).json()["data"]["total"] == 2
    assert veri.get("/api/v1/musteri", params={"q": "%"}).json()["data"]["total"] == 0
    assert veri.get("/api/v1/musteri", params={"q": "_"}).json()["data"]["total"] == 0


def test_kart_semasi(veri):
    login_ok(veri)
    k = veri.get("/api/v1/musteri/1").json()["data"]
    assert set(k) >= {"kimlik", "operasyon", "ekip", "iletisim", "kritik_ci", "izleme", "raporlar", "gelirler", "erisim", "tam_secenekleri"}
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
    assert "tam_secenekleri" not in k and k["erisim"]["tam_degistir"] is False and k["erisim"]["sil"] is False
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

    hdr2 = _giris(veri, monkeypatch, "TeamMember")  # 'admin' satirina bagli Member
    assert veri.post("/api/v1/musteri", json={"name": "Baskasi", "owner_id": 2}, headers=hdr2).status_code == 403
    assert veri.post("/api/v1/musteri", json={"name": "Kendi Musterim"}, headers=hdr2).status_code == 200
    assert veri.put("/api/v1/musteri/2/sorumlu", json={"owner_id": 2}, headers=hdr2).status_code == 403
    assert veri.delete("/api/v1/musteri/2", headers=hdr2).status_code == 403
    _cikis(veri, hdr2)

    hdr3 = _giris(veri, monkeypatch, "admin")
    with Session(engine()) as db:
        db.add(Report(customer_id=2, user_id=1, report_month=1, report_year=2026, is_submitted=True))
        db.commit()
    r = veri.delete("/api/v1/musteri/1", headers=hdr3)
    assert r.status_code == 200 and r.json()["data"]["silinen"] == 3  # cati + 2 istirak
    assert veri.get("/api/v1/musteri/1").status_code == 404 and veri.get("/api/v1/musteri/2").status_code == 404


def test_taslak_varsayilanlari_kayit_ve_dil(veri):
    hdr = login_ok(veri)
    t = veri.get("/api/v1/musteri/1/rapor/taslak").json()["data"]
    assert (t["yil"], t["ay"]) == AY and t["kayitli"] is False and t["birim"] is True and t["gonderim"] is None
    a = t["alanlar"]
    assert a["dil"] == "tr" and a["konu"].startswith("TAM Aylık Rapor - ") and a["konu"].endswith("| Alfa Test A.S.")
    assert "Sayın Müşterimiz" in a["govde"] and a["imza"].startswith("admin\nTeknik Müşteri Yöneticisi")
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


def test_ayri_rapor_ve_durum_ozeti(veri):
    hdr = login_ok(veri)
    assert veri.put("/api/v1/musteri/1/ayri-rapor", json={"ayri_rapor": True}, headers=hdr).status_code == 400  # cati
    assert veri.put("/api/v1/musteri/2/ayri-rapor", json={"ayri_rapor": True}, headers=hdr).json()["data"] == {"ayri_rapor": True}
    yil, ay = AY
    d = veri.get("/api/v1/rapor/durum").json()["data"]
    assert d["toplam"] == {"musteri": 3, "atilan": 0, "bekleyen": 3}  # A, B ve ayri rapor secilmis istirak
    assert veri.post("/api/v1/musteri/1/rapor/gonder", json={"onay": True}, headers=hdr).status_code == 200
    d = veri.get("/api/v1/rapor/durum", params={"yil": yil, "ay": ay}).json()["data"]
    assert d["toplam"] == {"musteri": 3, "atilan": 1, "bekleyen": 2}
    satirlar = {s["ad"]: s for s in d["satirlar"]}
    assert satirlar["Admin Kisi"] == {"id": 1, "ad": "Admin Kisi", "musteri": 2, "atilan": 1, "bekleyen": 1}
    assert veri.put("/api/v1/musteri/2/ayri-rapor", json={"ayri_rapor": False}, headers=hdr).status_code == 200
    assert veri.get("/api/v1/rapor/durum").json()["data"]["toplam"]["musteri"] == 2


def test_yetkisiz_ve_csrf(veri, monkeypatch):
    assert veri.get("/api/v1/musteri").status_code == 401
    hdr = login_ok(veri)
    assert veri.put("/api/v1/musteri/1/kimlik", json={"sector": "x"}).status_code == 403  # CSRF'siz
    assert veri.put("/api/v1/roller/TeamMember", json={"modules": [], "landing": "ozet"}, headers=hdr).status_code == 200  # modul yok
    _cikis(veri, hdr)
    _giris(veri, monkeypatch, "TeamMember")
    assert veri.get("/api/v1/musteri").status_code == 403
    assert veri.get("/api/v1/musteri/1").status_code == 403
    _ = datetime.now(UTC)
