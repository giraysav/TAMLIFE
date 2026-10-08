"""Onedesk, ICT SMS / APN gelirleri, TAM Takvim + sunuma gonder, rol ek yetkileri, musteri portfoyu ve dev ornek verisi."""

from __future__ import annotations

import io
import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import ornek_veri
from app.deps import engine
from app.models import ApnRevenue, ApnWork, AppUser, CalendarDay, Customer, OnedeskRecord, Presentation, SmsRevenue
from app.onedesk import yz
from app.tampon import depo
from tests.conftest import login_ok

YIL = datetime.now(UTC).year
SIMDI = datetime.now(UTC)
TUM_MODULLER = ["musteri", "takvim", "takvim_ozet", "onedesk", "tamsms", "tamapn", "sunum", "rapor"]


@pytest.fixture
def veri(client):
    """admin (id 1) + ayse (id 2, giris yapmis). A(cati,admin) A-ist(istirak,admin) B(cati,ayse)."""
    with Session(engine()) as db:
        db.add_all(
            [
                AppUser(id=1, username="admin", display_name="Admin Kisi", role="admin", is_admin=True),
                AppUser(id=2, username="ayse", display_name="Ayse Test", role="TeamMember", last_login_at=SIMDI),
            ]
        )
        db.flush()
        db.add_all(
            [
                Customer(id=1, external_key="t-a", name="Alfa Test A.S.", segment="MA", owner_id=1, score=70),
                Customer(id=2, external_key="t-ai", name="Alfa Istirak", segment="MA", owner_id=1, parent_id=1),
                Customer(id=3, external_key="t-b", name="Beta Test Ltd", segment="SMB", owner_id=2),
            ]
        )
        db.commit()
    return client


def _cikis(client, hdr):
    client.post("/api/v1/session/logout", headers=hdr)


def _giris(client, monkeypatch, rol):
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    return login_ok(client)


def _rol_ver(client, hdr, rol="TeamMember", moduller=None, yetkiler=None):
    govde = {"modules": moduller or TUM_MODULLER, "landing": "ozet"}
    if yetkiler is not None:
        govde["permissions"] = yetkiler
    r = client.put(f"/api/v1/roller/{rol}", json=govde, headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _kayit(db, **alan):
    ortak = {"kind": "alarm", "status": "closed", "customer_id": 1, "customer_label": "Alfa Test A.S.", "location": "Gebze", "category": "Hat", "opened_at": SIMDI - timedelta(days=5), "closed_at": SIMDI - timedelta(days=4)}
    db.add(OnedeskRecord(**{**ortak, **alan}))


# --- rol ek yetkileri ---------------------------------------------------------------------------------
def test_rol_yetkileri_kaydedilir_ve_korunur(veri):
    hdr = login_ok(veri)
    ilk = veri.get("/api/v1/roller").json()["data"]
    assert ilk["permission_catalog"] == [{"id": "takvim.sunuma_gonder", "label": "TAM Takvim: çeyrek bazlı sunuma gönder"}]
    assert next(r for r in ilk["roles"] if r["role"] == "TeamMember")["permissions"] == []  # varsayilan kapali
    assert next(r for r in ilk["roles"] if r["role"] == "admin")["permissions"] == ["takvim.sunuma_gonder"]
    assert _rol_ver(veri, hdr, yetkiler=["takvim.sunuma_gonder"])["permissions"] == ["takvim.sunuma_gonder"]
    assert _rol_ver(veri, hdr)["permissions"] == ["takvim.sunuma_gonder"]  # permissions verilmezse mevcut yetki korunur
    assert _rol_ver(veri, hdr, yetkiler=[])["permissions"] == []
    r = veri.put("/api/v1/roller/TeamMember", json={"modules": TUM_MODULLER, "landing": "ozet", "permissions": ["yok.boyle.yetki"]}, headers=hdr)
    assert r.status_code == 400


def test_me_eylem_yetkilerini_dondurur(veri, monkeypatch):
    hdr = login_ok(veri)
    assert veri.get("/api/v1/session/me").json()["data"]["permissions"]["actions"] == ["takvim.sunuma_gonder"]  # admin hepsine sahip
    _rol_ver(veri, hdr, yetkiler=["takvim.sunuma_gonder"])
    _cikis(veri, hdr)
    _giris(veri, monkeypatch, "TeamMember")
    assert veri.get("/api/v1/session/me").json()["data"]["permissions"]["actions"] == ["takvim.sunuma_gonder"]


# --- Onedesk -------------------------------------------------------------------------------------------
def test_onedesk_acik_ve_yil_boyu_kapanan(veri):
    login_ok(veri)
    with Session(engine()) as db:
        _kayit(db, kind="alarm", status="open", closed_at=None, external_key="1")
        _kayit(db, kind="alarm", status="open", closed_at=None, opened_at=SIMDI - timedelta(days=40), external_key="2")
        _kayit(db, kind="talep", status="open", closed_at=None, external_key="3")
        _kayit(db, kind="sikayet", status="open", closed_at=None, customer_id=3, customer_label="Beta Test Ltd", external_key="4")
        _kayit(db, kind="alarm", external_key="5")  # bu yil kapandi
        _kayit(db, kind="talep", external_key="6")
        _kayit(db, kind="alarm", closed_at=datetime(YIL - 1, 12, 30, tzinfo=UTC), opened_at=datetime(YIL - 1, 12, 29, tzinfo=UTC), external_key="7")  # gecen yil
        db.commit()
    acik = veri.get("/api/v1/onedesk/durum", params={"kapsam": "acik"}).json()["data"]
    assert acik["toplam"] == {"alarm": 2, "talep": 1, "sikayet": 1, "hepsi": 4}
    assert acik["musteriler"][0]["ad"] == "Alfa Test A.S." and acik["musteriler"][0]["toplam"] == 3
    assert [k["etiket"] for k in acik["grafik"]] == ["0-24 saat", "1-7 gün", "7-30 gün", "30 gün+"]
    assert sum(k["alarm"] for k in acik["grafik"]) == 2 and acik["grafik"][3]["alarm"] == 1  # 40 gunluk
    kapali = veri.get("/api/v1/onedesk/durum", params={"kapsam": "kapali"}).json()["data"]
    assert kapali["toplam"] == {"alarm": 1, "talep": 1, "sikayet": 0, "hepsi": 2}  # gecen yil sayilmaz
    assert len(kapali["grafik"]) == 12 and sum(a["alarm"] + a["talep"] for a in kapali["grafik"]) == 2
    gecen = veri.get("/api/v1/onedesk/durum", params={"kapsam": "kapali", "yil": YIL - 1}).json()["data"]
    assert gecen["toplam"]["alarm"] == 1
    assert veri.get("/api/v1/onedesk/durum", params={"kapsam": "yanlis"}).status_code == 400


def test_onedesk_top10_musteri_ve_lokasyon(veri):
    login_ok(veri)
    with Session(engine()) as db:
        for i in range(12):  # 12 musteri; i. musterinin (12-i) kaydi var
            for n in range(12 - i):
                _kayit(db, customer_id=None, customer_label=f"Firma {i:02d}", location="Ana Ofis" if n % 3 else "Depo", external_key=f"{i}-{n}", kind=("alarm", "talep", "sikayet")[n % 3])
        db.commit()
    d = veri.get("/api/v1/onedesk/top10").json()["data"]
    assert len(d["musteriler"]) == 10 and [m["ad"] for m in d["musteriler"]][:3] == ["Firma 00", "Firma 01", "Firma 02"]
    ilk = d["musteriler"][0]
    assert ilk["sira"] == 1 and ilk["toplam"] == 12 and ilk["alarm"] + ilk["talep"] + ilk["sikayet"] == 12
    assert ilk["lokasyon"] == "Ana Ofis" and ilk["lokasyonlar"][0]["adet"] == 8 and ilk["lokasyonlar"][1] == {"ad": "Depo", "adet": 4}
    assert "Firma 11" not in {m["ad"] for m in d["musteriler"]}


def test_onedesk_rca_ortak_noktalar_ve_oneriler(veri):
    login_ok(veri)
    with Session(engine()) as db:
        for i, kok in enumerate(["Fiber kablo kesildi (devre 12)", "Fiber kablo kesildi (devre 340)", "Fiber kablo kesildi (devre 7)", "Klima arızası sıcaklık yükseldi"]):
            _kayit(db, root_cause=kok, external_key=f"r{i}", location="Gebze" if i < 3 else "Izmir")
        _kayit(db, root_cause="", external_key="bos")
        db.commit()
    rca = veri.get("/api/v1/onedesk/rca").json()["data"]
    assert rca["kapsanan"] == 4
    ilk = rca["ortak_noktalar"][0]
    assert ilk["adet"] == 3 and ilk["oran"] == 75.0 and ilk["lokasyon_sayisi"] == 1 and "Fiber" in ilk["kok_sebep"]
    assert any("fiziksel" in o for o in ilk["oneriler"])
    assert {"kelime": "kablo", "adet": 3} in rca["anahtar_kelimeler"]
    assert rca["tekrar_lokasyonlar"][0]["lokasyon"] == "Gebze"
    o = veri.get("/api/v1/onedesk/oneriler").json()["data"]
    assert o["gruplar"][0]["adet"] == 3 and o["yz"]["hazir"] is False and o["yz"]["saglayici"] == "yerlesik"
    assert veri.post("/api/v1/onedesk/yz-yorum", headers=login_hdr(veri)).status_code == 503  # YZ varsayilan kapali


def login_hdr(client):
    return {"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""}


def test_onedesk_yz_yorumu_yalniz_kok_sebep_gonderir(veri, monkeypatch):
    hdr = login_ok(veri)
    with Session(engine()) as db:
        _kayit(db, root_cause="Fiber kablo kesildi (devre 12)", external_key="y1", customer_label="Gizli Musteri A.S.", location="Gizli Lokasyon")
        db.commit()
    monkeypatch.setenv("TAMLIFE_YZ_SAGLAYICI", "anthropic")
    assert veri.post("/api/v1/onedesk/yz-yorum", headers=hdr).status_code == 503  # veri paylasimi izni ve anahtar yok
    monkeypatch.setenv("TAMLIFE_YZ_VERI_PAYLASIMI", "izinli")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anahtar-degil-gercek")
    gonderilen = {}

    class Yanit(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def sahte(istek, timeout):
        gonderilen["govde"] = istek.data.decode("utf-8")
        gonderilen["adres"] = istek.full_url
        return Yanit(json.dumps({"content": [{"type": "text", "text": "1. Fiber yedekliliği sağlayın."}]}).encode())

    monkeypatch.setattr(yz.urllib.request, "urlopen", sahte)
    r = veri.post("/api/v1/onedesk/yz-yorum", headers=hdr)
    assert r.status_code == 200 and "Fiber yedekliliği" in r.json()["data"]["yorum"]
    assert gonderilen["adres"] == yz.ADRES
    assert "Fiber kablo kesildi" in gonderilen["govde"] and "Gizli Musteri" not in gonderilen["govde"] and "Gizli Lokasyon" not in gonderilen["govde"]
    assert "test-anahtar" not in r.text
    assert veri.get("/api/v1/onedesk/oneriler").json()["data"]["yz"] == {"saglayici": "anthropic", "hazir": True, "model": yz.VARSAYILAN_MODEL, "eksik": []}


def test_onedesk_member_yalniz_kendi_portfoyunu_gorur(veri, monkeypatch):
    hdr = login_ok(veri)
    with Session(engine()) as db:
        _kayit(db, status="open", closed_at=None, external_key="a1")  # Alfa (admin kullanicisinin musterisi)
        _kayit(db, status="open", closed_at=None, customer_id=2, customer_label="Alfa Istirak", external_key="a2")  # istirak, cati kendisinde
        _kayit(db, status="open", closed_at=None, customer_id=3, customer_label="Beta Test Ltd", external_key="b1")
        _kayit(db, status="open", closed_at=None, customer_id=None, customer_label="Eslesmeyen", external_key="e1")
        db.commit()
    assert veri.get("/api/v1/onedesk/durum", params={"kapsam": "acik"}).json()["data"]["toplam"]["hepsi"] == 4  # yonetici hepsi
    _cikis(veri, hdr)
    _giris(veri, monkeypatch, "TeamMember")  # 'admin' kullanicisi member olarak: yalniz kendi musterileri
    assert veri.get("/api/v1/onedesk/durum", params={"kapsam": "acik"}).json()["data"]["toplam"]["hepsi"] == 2


def test_onedesk_modul_yetkisi_ve_kaynak_yalniz_admin(veri, monkeypatch):
    hdr = login_ok(veri)
    _rol_ver(veri, hdr, moduller=["musteri"])
    _cikis(veri, hdr)
    _giris(veri, monkeypatch, "TeamMember")
    assert veri.get("/api/v1/onedesk/durum").status_code == 403
    assert veri.get("/api/v1/onedesk/kaynak").status_code == 403
    assert veri.post("/api/v1/onedesk/ice-al/1", json={}, headers=login_hdr(veri)).status_code == 403


def _parti(db, basliklar, satirlar, durum="ready"):
    p = depo.parti_olustur(db, "csv", "test", "admin")
    depo.ice_al(db, p, basliklar, satirlar)
    db.refresh(p)
    p.status = durum
    db.commit()
    return p.id


def test_onedesk_veri_girisi_partisi_aktarilir_ve_sayaclar_yenilenir(veri):
    hdr = login_ok(veri)
    basliklar = ["Çağrı No", "Tür", "Durum", "Müşteri Adı", "Lokasyon", "Kategori", "Açılış Tarihi", "Kapanış Tarihi", "Kök Sebep", "Çözüm Açıklaması"]
    bugun = SIMDI.strftime("%d.%m.%Y %H:%M")
    satirlar = [
        ["INC1", "Alarm", "Açık", "ALFA TEST A.S.", "Gebze", "Hat", bugun, "", "", ""],
        ["INC2", "Alarm", "Kapalı", "Alfa Test A.S.", "Gebze", "Hat", bugun, bugun, "Fiber kablo kesildi", "Ek yapıldı"],
        ["INC3", "Talep", "Kapalı", "Bilinmeyen Firma", "Ankara", "Yeni hat", bugun, bugun, "", ""],
        ["INC4", "Şikayet", "Açık", "Beta Test Ltd", "Izmir", "Yavaşlık", bugun, "", "", ""],
        ["", "Alarm", "Açık", "", "", "", "", "", "", ""],  # musterisiz: atlanir
    ]
    with Session(engine()) as db:
        pid = _parti(db, basliklar, satirlar)
        taslak = _parti(db, basliklar, satirlar, durum="receiving")
    assert veri.post(f"/api/v1/onedesk/ice-al/{taslak}", json={}, headers=hdr).status_code == 409  # hazir degil
    r = veri.post(f"/api/v1/onedesk/ice-al/{pid}", json={}, headers=hdr)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert (d["eklenen"], d["guncellenen"], d["atlanan"], d["musteri_eslesmeyen"], d["etkilenen_musteri"]) == (4, 0, 1, 1, 2)
    assert d["sutunlar"]["kok"] == "Kök Sebep" and d["sutunlar"]["tur"] == "Tür"
    with Session(engine()) as db:
        a, b = db.get(Customer, 1), db.get(Customer, 3)
        assert (a.alarm_count, a.alarm_closed_count) == (1, 1) and (b.complaint_count, b.request_count) == (1, 0)
        inc3 = db.scalar(select(OnedeskRecord).where(OnedeskRecord.external_key == "INC3"))
        assert inc3.customer_id is None and inc3.customer_label == "Bilinmeyen Firma" and inc3.status == "closed"
    r2 = veri.post(f"/api/v1/onedesk/ice-al/{pid}", json={}, headers=hdr).json()["data"]  # ayni numara guncellenir, cogalmaz
    assert (r2["eklenen"], r2["guncellenen"]) == (0, 4)
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(OnedeskRecord)) == 4
    kaynak = veri.get("/api/v1/onedesk/kaynak").json()["data"]
    assert kaynak["kayit"] == 4 and kaynak["canli_baglanti"]["acik"] is False and {p["id"] for p in kaynak["partiler"]} == {pid}


def test_onedesk_aktarim_tur_sutunu_yoksa_tur_secilmeli(veri):
    hdr = login_ok(veri)
    with Session(engine()) as db:
        pid = _parti(db, ["Çağrı No", "Müşteri", "Kapanış Tarihi"], [["1", "Alfa Test A.S.", "01.02.2026 10:00"]])
    assert veri.post(f"/api/v1/onedesk/ice-al/{pid}", json={}, headers=hdr).status_code == 400
    assert veri.post(f"/api/v1/onedesk/ice-al/{pid}", json={"tur": "x"}, headers=hdr).status_code == 400
    r = veri.post(f"/api/v1/onedesk/ice-al/{pid}", json={"tur": "alarm"}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["eklenen"] == 1
    with Session(engine()) as db:
        k = db.scalar(select(OnedeskRecord))
        assert k.status == "closed" and k.closed_at.year == 2026 and k.kind == "alarm"


# --- ICT SMS & APN -------------------------------------------------------------------------------------
def test_sms_gelirleri_ekle_duzenle_sil_ve_dogrulama(veri):
    hdr = login_ok(veri)
    assert veri.post("/api/v1/gelir/sms", json={"musteri": "Alfa", "tutar": 10}, headers=hdr).status_code == 400  # proje zorunlu
    assert veri.post("/api/v1/gelir/sms", json={"musteri": "Alfa", "proje": "P", "tutar": "abc"}, headers=hdr).status_code == 400
    assert veri.post("/api/v1/gelir/sms", json={"musteri": "Alfa", "proje": "P", "tutar": -1}, headers=hdr).status_code == 400
    assert veri.post("/api/v1/gelir/sms", json={"musteri": "Alfa", "proje": "P", "tutar": 5, "para_birimi": "GBP"}, headers=hdr).status_code == 400
    r = veri.post("/api/v1/gelir/sms", json={"musteri": "Alfa Test A.S.", "proje": "OTP", "tutar": "1.250,50"}, headers=hdr)
    assert r.status_code == 200, r.text
    kayit = r.json()["data"]
    assert kayit["tutar"] == 1250.5 and kayit["para_birimi"] == "TRY" and kayit["tam"] == "Admin Kisi"
    veri.post("/api/v1/gelir/sms", json={"musteri": "Beta", "proje": "Kampanya", "tutar": 100, "para_birimi": "USD"}, headers=hdr)
    liste = veri.get("/api/v1/gelir/sms").json()["data"]
    assert len(liste["items"]) == 2 and liste["toplam"] == {"TRY": 1250.5, "USD": 100.0} and liste["yillar"] == [YIL]
    g = veri.put(f"/api/v1/gelir/sms/{kayit['id']}", json={"musteri": "Alfa Test A.S.", "proje": "OTP 2", "tutar": 2000}, headers=hdr)
    assert g.json()["data"]["proje"] == "OTP 2" and g.json()["data"]["tutar"] == 2000
    assert veri.delete(f"/api/v1/gelir/sms/{kayit['id']}", headers=hdr).status_code == 200
    assert veri.delete(f"/api/v1/gelir/sms/{kayit['id']}", headers=hdr).status_code == 404
    assert veri.get("/api/v1/gelir/musteri-adlari").json()["data"] == ["Alfa Istirak", "Alfa Test A.S.", "Beta Test Ltd"]


def test_gelir_member_baskasinin_kaydini_goremez(veri, monkeypatch):
    hdr = login_ok(veri)
    with Session(engine()) as db:
        db.add(SmsRevenue(tam_name="Ayse Test", customer_name="Beta", project="X", amount=5, currency="TRY", year=YIL, month=1, created_by="ayse"))
        db.add(SmsRevenue(tam_name="Admin Kisi", customer_name="Alfa", project="Y", amount=7, currency="TRY", year=YIL, month=1, created_by="admin"))
        db.commit()
        diger = db.scalar(select(SmsRevenue.id).where(SmsRevenue.created_by == "ayse"))
    assert len(veri.get("/api/v1/gelir/sms").json()["data"]["items"]) == 2  # yonetici hepsi
    _cikis(veri, hdr)
    hdr = _giris(veri, monkeypatch, "TeamMember")
    assert [i["proje"] for i in veri.get("/api/v1/gelir/sms").json()["data"]["items"]] == ["Y"]
    assert veri.put(f"/api/v1/gelir/sms/{diger}", json={"musteri": "B", "proje": "Z", "tutar": 1}, headers=hdr).status_code == 404
    assert veri.delete(f"/api/v1/gelir/sms/{diger}", headers=hdr).status_code == 404


def test_apn_kurulum_alanlari_ve_tarih_kurallari(veri):
    hdr = login_ok(veri)
    govde = {"musteri": "Alfa Test A.S.", "apn_adi": "lojistik.m2m", "talep_tarihi": "2026-03-10", "teslim_tarihi": "2026-03-25", "tutar": 12500}
    r = veri.post("/api/v1/gelir/apn/kurulum", json=govde, headers=hdr)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["apn_adi"] == "lojistik.m2m" and d["talep_tarihi"] == "2026-03-10" and d["teslim_tarihi"] == "2026-03-25" and d["tutar"] == 12500
    assert veri.post("/api/v1/gelir/apn/kurulum", json={**govde, "teslim_tarihi": "2026-03-01"}, headers=hdr).status_code == 400  # teslim < talep
    assert veri.post("/api/v1/gelir/apn/kurulum", json={**govde, "apn_adi": ""}, headers=hdr).status_code == 400
    assert veri.post("/api/v1/gelir/apn/kurulum", json={**govde, "talep_tarihi": "31.02.2026"}, headers=hdr).status_code == 400
    veri.post("/api/v1/gelir/apn/kurulum", json={**govde, "talep_tarihi": "10.04.2026", "teslim_tarihi": None, "tutar": 500}, headers=hdr)  # GG.AA.YYYY, teslim edilmedi
    liste = veri.get("/api/v1/gelir/apn/kurulum").json()["data"]
    assert liste["toplam"] == 13000.0 and liste["teslim_edilen"] == 1 and liste["bekleyen"] == 1
    assert [i["talep_tarihi"] for i in liste["items"]] == ["2026-04-10", "2026-03-10"]  # en yeni ustte
    assert len(veri.get("/api/v1/gelir/apn/kurulum", params={"yil": 2025}).json()["data"]["items"]) == 0
    with Session(engine()) as db:
        a = db.scalar(select(ApnRevenue).where(ApnRevenue.id == d["id"]))
        assert (a.year, a.month, a.currency) == (2026, 3, "TRY")  # donem teslim tarihinden


def test_apn_musteri_calismalari(veri):
    hdr = login_ok(veri)
    bugun = datetime.now(UTC).date()
    govde = {"musteri": "Alfa Test A.S.", "toplanti_konusu": "Yedekleme topolojisi", "toplanti_tarihi": bugun.isoformat(), "planli_tarih": (bugun + timedelta(days=10)).isoformat(), "apn_adi": "filo.apn"}
    r = veri.post("/api/v1/gelir/apn/calisma", json=govde, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["apn_adi"] == "filo.apn"
    assert veri.post("/api/v1/gelir/apn/calisma", json={**govde, "planli_tarih": (bugun - timedelta(days=1)).isoformat()}, headers=hdr).status_code == 400
    assert veri.post("/api/v1/gelir/apn/calisma", json={**govde, "toplanti_konusu": ""}, headers=hdr).status_code == 400
    assert veri.post("/api/v1/gelir/apn/calisma", json={**govde, "toplanti_tarihi": None}, headers=hdr).status_code == 400
    veri.post("/api/v1/gelir/apn/calisma", json={**govde, "planli_tarih": None, "apn_adi": ""}, headers=hdr)
    liste = veri.get("/api/v1/gelir/apn/calisma").json()["data"]
    assert len(liste["items"]) == 2 and liste["yaklasan"] == 1 and liste["items"][0]["planli_tarih"] is not None  # planli olan once
    kid = r.json()["data"]["id"]
    assert veri.put(f"/api/v1/gelir/apn/calisma/{kid}", json={**govde, "toplanti_konusu": "Yeni"}, headers=hdr).json()["data"]["toplanti_konusu"] == "Yeni"
    assert veri.delete(f"/api/v1/gelir/apn/calisma/{kid}", headers=hdr).status_code == 200
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(ApnWork)) == 1


# --- Takvim ---------------------------------------------------------------------------------------------
def test_giris_yapan_kisi_takvim_listesine_dusar(client):
    hdr = login_ok(client)
    uyeler = client.get("/api/v1/takvim/ekip").json()["data"]["uyeler"]
    assert [u["kullanici"] for u in uyeler] == ["admin"] and uyeler[0]["son_giris"] and uyeler[0]["rol"] == "admin"
    assert client.get("/api/v1/takvim/ekip", params={"ceyrek": 9}).status_code == 422
    assert hdr  # oturum acik


def test_gun_ve_toplu_kayit_ile_ekip_ozeti(veri):
    hdr = login_ok(veri)  # 'admin' kisisi (id 1) kendi takvimini yazar
    with Session(engine()) as db:
        db.add(CalendarDay(user_id=2, day=date(YIL, 2, 3), status="yillik_izin"))
        db.add(CalendarDay(user_id=2, day=date(YIL, 2, 4), status="arife_tatili"))
        db.add(CalendarDay(user_id=2, day=date(YIL, 5, 5), status="raporlu"))  # farkli ceyrek
        db.commit()
    assert veri.put("/api/v1/takvim/gun", json={"tarih": f"{YIL}-02-02", "durum": "calisiyor", "online": 2, "yuzyuze": 1}, headers=hdr).status_code == 200
    assert veri.put("/api/v1/takvim/gun", json={"tarih": f"{YIL}-02-02", "durum": "yok"}, headers=hdr).status_code == 400
    assert veri.put("/api/v1/takvim/gun", json={"tarih": "bozuk", "durum": "calisiyor"}, headers=hdr).status_code == 400
    assert veri.put("/api/v1/takvim/gun", json={"tarih": f"{YIL}-02-02", "durum": "calisiyor", "online": 999}, headers=hdr).status_code == 400
    # toplu: Pzt-Cmt (hafta sonu atlanir) yillik izin; hafta sonu da isteyince
    pzt = date(YIL, 2, 9) - timedelta(days=date(YIL, 2, 9).weekday())
    r = veri.put("/api/v1/takvim/toplu", json={"baslangic": pzt.isoformat(), "bitis": (pzt + timedelta(days=6)).isoformat(), "durum": "sirket_izni"}, headers=hdr)
    assert r.json()["data"]["atanan"] == 5
    assert veri.put("/api/v1/takvim/toplu", json={"baslangic": "2026-01-10", "bitis": "2026-01-01", "durum": "sirket_izni"}, headers=hdr).status_code == 400
    assert veri.put("/api/v1/takvim/toplu", json={"baslangic": "2026-01-01", "bitis": "2026-06-01", "durum": "sirket_izni"}, headers=hdr).status_code == 400  # 62 gun siniri
    ay = veri.get("/api/v1/takvim/ben", params={"yil": YIL, "ay": pzt.month}).json()["data"]
    assert ay["ozet"]["durumlar"]["sirket_izni"] >= 1 and any(g["durum"] == "sirket_izni" for g in ay["gunler"])
    # donem: 1. ceyrek; ayse (id 2) 1 yillik + yarim gun arife
    ekip = veri.get("/api/v1/takvim/ekip", params={"yil": YIL, "ceyrek": 1}).json()["data"]
    ayse = next(u for u in ekip["uyeler"] if u["kullanici"] == "ayse")
    assert ayse["durumlar"]["yillik_izin"] == 1 and ayse["durumlar"]["arife_tatili"] == 1 and ayse["izin_gun"] == 1.5 and ayse["kayitli_gun"] == 2
    tum = veri.get("/api/v1/takvim/ekip", params={"yil": YIL, "ceyrek": 0}).json()["data"]
    assert next(u for u in tum["uyeler"] if u["kullanici"] == "ayse")["durumlar"]["raporlu"] == 1
    admin_ozet = next(u for u in ekip["uyeler"] if u["kullanici"] == "admin")
    assert admin_ozet["online"] == 2 and admin_ozet["yuzyuze"] == 1 and admin_ozet["toplanti"] == 3
    gunler = veri.get(f"/api/v1/takvim/ekip/{ayse['id']}", params={"yil": YIL, "ceyrek": 1}).json()["data"]
    assert gunler["uye"] == "Ayse Test" and len(gunler["gunler"]) == 2
    assert veri.get("/api/v1/takvim/ekip/999", params={"yil": YIL, "ceyrek": 1}).status_code == 404
    # varsayilan gune geri donus kaydi siler
    veri.put("/api/v1/takvim/gun", json={"tarih": f"{YIL}-02-02", "durum": "calisiyor"}, headers=hdr)
    with Session(engine()) as db:
        assert db.scalar(select(CalendarDay).where(CalendarDay.user_id == 1, CalendarDay.day == date(YIL, 2, 2))) is None


def test_sunuma_gonder_yalniz_yetkili_rol_ve_admin(veri, monkeypatch):
    hdr = login_ok(veri)
    with Session(engine()) as db:
        db.add(CalendarDay(user_id=2, day=date(YIL, 2, 3), status="yillik_izin"))
        db.commit()
    govde = {"yil": YIL, "ceyrek": 1, "gonder": True}
    _rol_ver(veri, hdr, yetkiler=[])
    # admin her zaman gonderebilir
    ekip = veri.get("/api/v1/takvim/ekip", params={"yil": YIL, "ceyrek": 1}).json()["data"]
    assert ekip["sunuma_gonderebilir"] is True and ekip["sunumda"] is None and ekip["donem"] == f"{YIL}-Q1"
    assert veri.post("/api/v1/takvim/sunuma-gonder", json=govde, headers=hdr).status_code == 200
    _cikis(veri, hdr)

    hdr = _giris(veri, monkeypatch, "TeamMember")  # yetkisiz rol
    e = veri.get("/api/v1/takvim/ekip", params={"yil": YIL, "ceyrek": 1}).json()["data"]
    assert e["sunuma_gonderebilir"] is False and e["sunumda"]["gonderen"] == "Admin Kisi"
    assert veri.post("/api/v1/takvim/sunuma-gonder", json={**govde, "gonder": False}, headers=hdr).status_code == 403
    _cikis(veri, hdr)

    hdr = login_ok_admin(veri, monkeypatch)
    _rol_ver(veri, hdr, yetkiler=["takvim.sunuma_gonder"])  # admin Rol Yonetimi'nden verir
    _cikis(veri, hdr)
    hdr = _giris(veri, monkeypatch, "TeamMember")
    assert veri.get("/api/v1/takvim/ekip", params={"yil": YIL, "ceyrek": 1}).json()["data"]["sunuma_gonderebilir"] is True
    assert veri.post("/api/v1/takvim/sunuma-gonder", json={**govde, "gonder": False}, headers=hdr).json()["data"]["sunumda"] is None
    assert veri.get("/api/v1/takvim/ekip", params={"yil": YIL, "ceyrek": 1}).json()["data"]["sunumda"] is None


def login_ok_admin(client, monkeypatch):
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "admin")
    return login_ok(client)


def test_sunuma_gonderilen_ogeler_ceyrek_basina_tek_kayit(veri):
    hdr = login_ok(veri)
    with Session(engine()) as db:
        db.add(CalendarDay(user_id=2, day=date(YIL, 8, 3), status="raporlu"))
        db.commit()
    for _ in range(2):  # tekrar gonderim gunceller
        assert veri.post("/api/v1/takvim/sunuma-gonder", json={"yil": YIL, "ceyrek": 3, "gonder": True}, headers=hdr).status_code == 200
    ogeler = veri.get("/api/v1/sunum/ogeler").json()["data"]
    assert len(ogeler) == 1 and ogeler[0]["donem"] == f"{YIL}-Q3" and ogeler[0]["kaynak"] == "takvim"
    ayse = next(u for u in ogeler[0]["veri"]["uyeler"] if u["ad"] == "Ayse Test")
    assert ayse["durumlar"]["raporlu"] == 1 and ogeler[0]["veri"]["genel"]["durumlar"]["raporlu"] == 1
    assert veri.get("/api/v1/sunum/ogeler", params={"yil": YIL - 5}).json()["data"] == []
    veri.post("/api/v1/takvim/sunuma-gonder", json={"yil": YIL, "ceyrek": 3, "gonder": False}, headers=hdr)
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Presentation)) == 0


# --- Musteri portfoyu -----------------------------------------------------------------------------------
def test_portfoy_cati_kartlari_istirak_ve_filtreler(veri, monkeypatch):
    hdr = login_ok(veri)
    with Session(engine()) as db:
        a = db.get(Customer, 1)
        a.alarm_count, a.complaint_count, a.request_count = 2, 1, 3
        db.commit()
    d = veri.get("/api/v1/musteri/portfoy").json()["data"]
    assert [c["name"] for c in d["items"]] == ["Alfa Test A.S.", "Beta Test Ltd"]  # istirak ayri kart degil
    alfa = d["items"][0]
    assert alfa["istirakler"] == [{"id": 2, "name": "Alfa Istirak"}] and (alfa["alarm"], alfa["sikayet"], alfa["talep"]) == (2, 1, 3) and alfa["owner"] == "Admin Kisi"
    assert d["ozet"] == {"cati": 2, "istirak": 1, "alarm": 2, "sikayet": 1, "talep": 3, "ortalama_skor": 70.0, "skorlu": 1}
    assert [c["name"] for c in veri.get("/api/v1/musteri/portfoy", params={"q": "istirak"}).json()["data"]["items"]] == ["Alfa Test A.S."]  # istirak adi catiyi bulur
    assert veri.get("/api/v1/musteri/portfoy", params={"tam": 2}).json()["data"]["total"] == 1
    assert veri.get("/api/v1/musteri/portfoy", params={"segment": "SMB"}).json()["data"]["items"][0]["name"] == "Beta Test Ltd"
    assert veri.get("/api/v1/musteri/portfoy", params={"q": "%"}).json()["data"]["total"] == 0
    sec = veri.get("/api/v1/musteri/secenekler").json()["data"]
    assert sec["yonetici"] is True and sec["segmentler"] == ["SMB", "SA", "MA", "PA", "WHOLESALE"]
    assert {t["ad"] for t in sec["tam"]} == {"Admin Kisi", "Ayse Test"} and {c["ad"] for c in sec["catilar"]} == {"Alfa Test A.S.", "Beta Test Ltd"}
    _cikis(veri, hdr)
    _giris(veri, monkeypatch, "TeamMember")  # 'admin' kullanicisi member olarak
    m = veri.get("/api/v1/musteri/portfoy").json()["data"]
    assert [c["name"] for c in m["items"]] == ["Alfa Test A.S."] and m["ozet"]["cati"] == 1
    s = veri.get("/api/v1/musteri/secenekler").json()["data"]
    assert s["yonetici"] is False and [t["ad"] for t in s["tam"]] == ["Admin Kisi"] and [c["ad"] for c in s["catilar"]] == ["Alfa Test A.S."]


def test_portfoy_member_yalniz_istiraki_varsa_catiyi_gorur(veri, monkeypatch):
    hdr = login_ok(veri)
    with Session(engine()) as db:
        db.get(Customer, 2).owner_id = 1  # istirak admin'de
        db.get(Customer, 1).owner_id = 2  # cati ayse'de
        db.commit()
    _cikis(veri, hdr)
    _giris(veri, monkeypatch, "TeamMember")  # 'admin' kullanicisi (id 1) yalniz istirakin sahibi
    m = veri.get("/api/v1/musteri/portfoy").json()["data"]
    assert [c["name"] for c in m["items"]] == ["Alfa Test A.S."] and [i["name"] for i in m["items"][0]["istirakler"]] == ["Alfa Istirak"]


# --- Dev ornek verisi ----------------------------------------------------------------------------------
def test_ornek_veri_tohumla_ve_yalniz_isaretlileri_temizle(client, monkeypatch):
    with Session(engine()) as db:
        db.add(Customer(external_key="gercek-1", name="Gercek Musteri"))
        db.add(OnedeskRecord(kind="alarm", status="open", source="import", customer_label="Gercek"))
        db.commit()
        sayilar = ornek_veri.tohumla(db)
        assert sayilar["musteri"] == 15 and sayilar["onedesk"] == 480 and sayilar["kisi"] == 6 and sayilar["takvim_gunu"] > 100
        assert ornek_veri.var_mi(db)
        # sayaclar kayitlardan hesaplanir; top10'a yetecek cesitlilik
        assert db.scalar(select(func.count()).select_from(OnedeskRecord).where(OnedeskRecord.source == "ornek", OnedeskRecord.status == "closed")) > 250
        assert db.scalar(select(func.count(Customer.id)).where(Customer.alarm_count > 0)) >= 5
        assert db.scalar(select(func.count()).select_from(SmsRevenue)) == 12 and db.scalar(select(func.count()).select_from(ApnWork)) == 10
        silinen = ornek_veri.temizle(db)
        assert silinen["musteri"] == 15 and silinen["kisi"] == 6
        assert db.scalar(select(func.count()).select_from(Customer)) == 1  # gercek kayit dokunulmaz
        assert db.scalar(select(func.count()).select_from(OnedeskRecord)) == 1
        assert db.scalar(select(func.count()).select_from(CalendarDay)) == 0 and not ornek_veri.var_mi(db)
    monkeypatch.setenv("TAMLIFE_ENV", "uretim")
    assert ornek_veri.main([]) == 2  # dev disinda reddedilir
    monkeypatch.setenv("TAMLIFE_ENV", "test")
    assert ornek_veri.main([]) == 2


def test_tutar_bicimleri(veri):
    hdr = login_ok(veri)
    for ham, beklenen in (("1.250", 1250.0), ("1.250.000", 1250000.0), ("1250.5", 1250.5), ("1.250,75", 1250.75), ("12,5", 12.5), (7, 7.0), ("  ", 0.0)):
        r = veri.post("/api/v1/gelir/sms", json={"musteri": "Alfa", "proje": "P", "tutar": ham}, headers=hdr)
        assert r.status_code == 200, (ham, r.text)
        assert r.json()["data"]["tutar"] == beklenen, ham
    assert veri.post("/api/v1/gelir/sms", json={"musteri": "Alfa", "proje": "P", "tutar": "nan"}, headers=hdr).status_code == 400
    assert veri.post("/api/v1/gelir/sms", json={"musteri": "Alfa", "proje": "P", "tutar": True}, headers=hdr).status_code == 400
