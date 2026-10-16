"""Gelir Faydasi onay akisi ve zorunlu alanlar (2026-10-15 kullanici istegi: "yeni giriste tum basliklar dolu olsun; yeni is modul
sahibine onaya gitsin, sahip kontrol edip canliya alsin; Excel ve PDF rapor").

Test verisi uydurmadir (Alfa/Beta, Ali/Veli gibi adlar).
"""

from __future__ import annotations

import io
from datetime import date

from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.gelir_uretim import excel, servis
from app.gelir_uretim.models import RevenueBenefit
from app.models import AppUser
from app.sunum.servis import _gelir_uretim
from tests.conftest import login_ok
from tests.test_gelir_uretim import URL, _denetim, _eski, _giris, _govde, _kisi, _liste

TAM_GOVDE = {
    "kind": "proje", "benefit_type": "gelir", "title": "Alfa yedek devre", "status": "devam", "status_note": "Teklif verildi", "roadmap": "Mayıs: faz 1",
    "description": "Yedek devre satışı", "customers": "Alfa A.Ş.", "revenue_amount": 1000, "revenue_currency": "TRY", "revenue_period": "ay",
    "year_revenue": 12000, "hours_per_month": 0, "hours_per_year": 0, "extra_note": "-", "start_date": "2026-04-01", "end_date": "2026-12-31",
    "other_people": "", "person_ids": [],
}  # fmt: skip


def _ekip():
    return {"ali": _kisi("ali", "Ali Örnek"), "veli": _kisi("veli", "Veli Deneme"), "sahip": _kisi("tcsahip", "Selin Sahip", rol="TeamMngr")}


def _sahip_ata(client, hdr, kimlik) -> None:
    r = client.put(f"{URL}/sahip", json={"user_id": kimlik}, headers=hdr)
    assert r.status_code == 200, r.text


# --- zorunlu alanlar -------------------------------------------------------------------------------------------------
def test_yeni_giriste_tum_basliklar_zorunlu_sifir_kabul(client):
    ekip = _ekip()
    hdr = login_ok(client)
    r = client.post(URL, json={"title": "Alfa"}, headers=hdr)
    assert r.status_code == 400
    mesaj = r.json()["detail"]
    for baslik in ("İlgili TAM", "Güncel durum", "Yol haritası", "Detaylı açıklaması", "Hangi müşteri/müşterileri etkilediği", "Aylık gelir faydası",
                   "Yıllık gelir faydası", "Aylık verimlilik faydası", "Yıllık verimlilik faydası", "Ek açıklamalar", "Başlangıç tarihi", "Bitiş tarihi"):  # fmt: skip
        assert baslik in mesaj, baslik
    # bosluk dolu sayilmaz
    assert client.post(URL, json={**TAM_GOVDE, "roadmap": "   ", "person_ids": [ekip["ali"]]}, headers=hdr).status_code == 400
    # TAM: panel kisisi ya da diger kisiler; sayilar 0 olabilir
    assert client.post(URL, json={**TAM_GOVDE, "person_ids": [ekip["ali"]]}, headers=hdr).status_code == 200
    assert client.post(URL, json={**TAM_GOVDE, "title": "Beta", "other_people": "Dış Kişi", "revenue_amount": 0, "year_revenue": 0}, headers=hdr).status_code == 200
    assert client.post(URL, json={**TAM_GOVDE, "title": "Gama"}, headers=hdr).status_code == 400  # TAM yok


def test_eski_kaydin_bos_alanlari_duzenlemeyi_engellemez_dolu_alan_bosaltilamaz(client):
    hdr = login_ok(client)
    kimlik = _eski(client, hdr, title="Eski iş", customers="Alfa")
    kayit = _liste(client)["items"][0]
    assert "roadmap" in kayit["eksik"] and "customers" not in kayit["eksik"] and kayit["approval"] == "onayli"
    assert client.put(f"{URL}/{kimlik}", json={"title": "Eski iş", "customers": "Alfa", "status": "tamamlandi"}, headers=hdr).status_code == 200
    r = client.put(f"{URL}/{kimlik}", json={"title": "Eski iş", "customers": ""}, headers=hdr)
    assert r.status_code == 400 and "Hangi müşteri" in r.json()["detail"]


# --- onay akisi ------------------------------------------------------------------------------------------------------
def test_personel_girisi_sahibe_onaya_duser_onaylaninca_canliya_alinir(client, monkeypatch):
    ekip = _ekip()
    hdr = login_ok(client)
    _sahip_ata(client, hdr, ekip["sahip"])
    assert _liste(client)["onay"]["sahip"] == {"id": ekip["sahip"], "ad": "Selin Sahip"}

    h = _giris(client, monkeypatch, "ali", "TeamMember")
    r = client.post(URL, json={**TAM_GOVDE, "person_ids": [ekip["ali"]]}, headers=h)
    assert r.status_code == 200 and r.json()["data"]["approval"] == "bekliyor"
    kimlik = r.json()["data"]["id"]
    kendi = _liste(client)
    assert [k["approval"] for k in kendi["items"]] == ["bekliyor"] and kendi["ozet"]["is_sayisi"] == 0 and kendi["ozet"]["aylik_gelir"] == {}
    # giren kisi bekleyen kaydini duzeltebilir
    assert client.put(f"{URL}/{kimlik}", json={**TAM_GOVDE, "roadmap": "Haziran: faz 2", "person_ids": [ekip["ali"]]}, headers=h).status_code == 200
    # personel kendi kaydini onaylayamaz
    assert client.post(f"{URL}/{kimlik}/onay", json={"karar": "onayla"}, headers=h).status_code == 403

    # baska personel bekleyen kaydi gormez, degistiremez
    h2 = _giris(client, monkeypatch, "veli", "TeamMember")
    assert _liste(client)["items"] == []
    assert client.put(f"{URL}/{kimlik}", json={**TAM_GOVDE, "person_ids": [ekip["ali"]]}, headers=h2).status_code == 404

    # sahip bekleyeni gorur, sayar; onaylar
    hs = _giris(client, monkeypatch, "tcsahip", "TeamMngr")
    sahip_gorunum = _liste(client)
    assert sahip_gorunum["onay"]["yonetebilir"] is True and sahip_gorunum["onay"]["bekleyen"] == 1
    assert [k["title"] for k in _liste(client, onay="bekliyor")["items"]] == ["Alfa yedek devre"]
    r = client.post(f"{URL}/{kimlik}/onay", json={"karar": "onayla"}, headers=hs)
    assert r.status_code == 200 and r.json()["data"]["approval"] == "onayli"

    # artik herkes gorur, ozete girer; giren kisi onayli kaydi degistiremez
    _giris(client, monkeypatch, "veli", "TeamMember")
    veri = _liste(client)
    k = veri["items"][0]
    assert (k["approval"], k["approved_by"], k["roadmap"]) == ("onayli", "Selin Sahip", "Haziran: faz 2") and veri["ozet"]["aylik_gelir"] == {"TRY": 1000.0}
    h = _giris(client, monkeypatch, "ali", "TeamMember")
    assert client.put(f"{URL}/{kimlik}", json={**TAM_GOVDE, "person_ids": [ekip["ali"]]}, headers=h).status_code == 403
    assert client.delete(f"{URL}/{kimlik}", headers=h).status_code == 403
    assert [a for a, _ in _denetim()] == ["gelir_uretim.sahip", "gelir_uretim.ekle", "gelir_uretim.guncelle", "gelir_uretim.onayla"]


def test_ret_gerekce_ister_duzeltilince_yeniden_onaya_duser(client, monkeypatch):
    ekip = _ekip()
    hdr = login_ok(client)
    _sahip_ata(client, hdr, ekip["sahip"])
    h = _giris(client, monkeypatch, "ali", "TeamMember")
    kimlik = client.post(URL, json={**TAM_GOVDE, "person_ids": [ekip["ali"]]}, headers=h).json()["data"]["id"]
    hs = _giris(client, monkeypatch, "tcsahip", "TeamMngr")
    assert client.post(f"{URL}/{kimlik}/onay", json={"karar": "reddet"}, headers=hs).status_code == 400  # gerekce yok
    assert client.post(f"{URL}/{kimlik}/onay", json={"karar": "reddet", "gerekce": "Tutarı kontrol edin"}, headers=hs).json()["data"]["approval"] == "reddedildi"
    h = _giris(client, monkeypatch, "ali", "TeamMember")
    k = _liste(client)["items"][0]
    assert (k["approval"], k["approval_note"]) == ("reddedildi", "Tutarı kontrol edin")
    r = client.put(f"{URL}/{kimlik}", json={**TAM_GOVDE, "revenue_amount": 900, "person_ids": [ekip["ali"]]}, headers=h)
    assert r.status_code == 200 and "approval" in r.json()["data"]["degisen"]
    k = _liste(client)["items"][0]
    assert (k["approval"], k["approval_note"]) == ("bekliyor", "Tutarı kontrol edin")
    # giren kisi kendi bekleyen kaydini silebilir
    assert client.delete(f"{URL}/{kimlik}", headers=h).status_code == 200


def test_sahip_ve_admin_girisi_dogrudan_onayli_geri_alinabilir(client, monkeypatch):
    ekip = _ekip()
    hdr = login_ok(client)
    assert client.post(URL, json={**TAM_GOVDE, "person_ids": [ekip["ali"]]}, headers=hdr).json()["data"]["approval"] == "onayli"  # admin
    _sahip_ata(client, hdr, ekip["sahip"])
    hs = _giris(client, monkeypatch, "tcsahip", "TeamMngr")
    r = client.post(URL, json={**TAM_GOVDE, "title": "Beta", "person_ids": [ekip["veli"]]}, headers=hs)
    assert r.json()["data"]["approval"] == "onayli"
    assert client.post(f"{URL}/{r.json()['data']['id']}/onay", json={"karar": "geri_al"}, headers=hs).json()["data"]["approval"] == "bekliyor"
    # sahiplik kalkinca TeamMngr onay yetkisini kaybeder
    _giris(client, monkeypatch, "admin", "admin")
    hdr = login_ok(client)
    _sahip_ata(client, hdr, None)
    hs = _giris(client, monkeypatch, "tcsahip", "TeamMngr")
    assert _liste(client)["onay"] == {"sahip": None, "yonetebilir": False, "bekleyen": 0, "benim": ekip["sahip"]}
    assert client.post(f"{URL}/{r.json()['data']['id']}/onay", json={"karar": "onayla"}, headers=hs).status_code == 403


def test_sahip_adaylari_etkin_admin_olmayan_hesaplar(client):
    ekip = _ekip()
    pasif = _kisi("tcpasif", "Pasif", aktif=False)
    hdr = login_ok(client)
    adaylar = {a["id"] for a in client.get(f"{URL}/sahip").json()["data"]["adaylar"]}
    assert {ekip["ali"], ekip["sahip"]} <= adaylar and pasif not in adaylar
    with Session(engine()) as db:
        admin_id = db.scalar(select(AppUser.id).where(AppUser.username == "admin"))
    assert admin_id not in adaylar
    for kotu in (pasif, admin_id, 999999):
        assert client.put(f"{URL}/sahip", json={"user_id": kotu}, headers=hdr).status_code == 400


# --- rapor ve sunum yalniz onaylilari kapsar ---------------------------------------------------------------------------
def test_rapor_ve_sunum_yalniz_onayli_isleri_kapsar_suzgec_uygulanir(client, monkeypatch):
    ekip = _ekip()
    hdr = login_ok(client)
    client.post(URL, json={**TAM_GOVDE, "person_ids": [ekip["ali"]]}, headers=hdr)
    client.post(URL, json={**TAM_GOVDE, "title": "Beta verimlilik", "benefit_type": "verimlilik", "hours_per_month": 10, "hours_per_year": 120, "person_ids": [ekip["veli"]]}, headers=hdr)
    h = _giris(client, monkeypatch, "ali", "TeamMember")
    client.post(URL, json={**TAM_GOVDE, "title": "Bekleyen iş", "revenue_amount": 777, "person_ids": [ekip["ali"]]}, headers=h)

    kitap = load_workbook(io.BytesIO(client.get(f"{URL}/excel").content))
    basliklar = [s[1] for s in kitap.active.iter_rows(min_row=2, values_only=True)]
    assert basliklar == ["Beta verimlilik", "Alfa yedek devre"]  # ayni baslangic: yeni kayit ustte (liste sirasi)
    ozet = {s[0]: s[1] for s in kitap[excel.OZET_SAYFASI].iter_rows(min_row=3, values_only=True)}
    assert ozet["İş sayısı"] == 2 and ozet["Yıllık verimlilik faydası (saat)"] == 120 and ozet["Kapsam"] == "Onaylı işler (tümü)"
    suzulu = load_workbook(io.BytesIO(client.get(f"{URL}/excel", params={"fayda": "verimlilik", "tam": ekip["veli"]}).content))
    assert [s[1] for s in suzulu.active.iter_rows(min_row=2, values_only=True)] == ["Beta verimlilik"]
    kapsam = {s[0]: s[1] for s in suzulu[excel.OZET_SAYFASI].iter_rows(min_row=3, values_only=True)}["Kapsam"]
    assert "Fayda türü: verimlilik" in kapsam and "TAM: Veli Deneme" in kapsam

    with Session(engine()) as db:
        sunum = _gelir_uretim(db, 2026, 4)
    assert [s[0] for s in sunum["tablo"]["satirlar"]] == ["Alfa yedek devre", "Beta verimlilik"]
    kpi = {k["ad"]: k["deger"] for k in sunum["kpi"]}
    assert kpi["Fayda sağlanan iş"] == 2 and kpi["Aylık gelir TRY"] == 2000 and kpi["Yıllık efor kazancı (saat)"] == 120


# --- Excel ice aktarma: yeni sutunlar ----------------------------------------------------------------------------------
def test_ice_aktarma_yol_haritasi_ve_yillik_verimlilik_okunur_onayli_eklenir(client):
    _ekip()
    hdr = login_ok(client)
    kitap = Workbook()
    ws = kitap.active
    ws.append(list(excel.BASLIKLAR[:13]))
    ws.append(["Ali Örnek", "Alfa otomasyon", "Devam ediyor", "Mayıs: faz 1", "Rapor otomasyonu", "Alfa", "yok", 0, "36 Saat / Ay", "432 saat / 12 ay",
               "-", date(2026, 4, 1), date(2026, 12, 31)])  # fmt: skip
    ws.append(["Veli Deneme", "Beta iş", "Devam ediyor", "", "Açıklama", "Beta", "5K TL / ay", 60000, "yok", "Çalışılmaktadır", "", date(2026, 5, 1), None])
    veri = io.BytesIO()
    kitap.save(veri)
    onizleme = client.post(f"{URL}/ice-al/onizleme", content=veri.getvalue(), headers=hdr).json()["data"]
    assert onizleme["uyarilar"] == []  # 13 baslik da bulundu
    assert [s["hours_per_year"] for s in onizleme["satirlar"]] == [432.0, None]
    sonuc = client.post(f"{URL}/ice-al/uygula", content=veri.getvalue(), headers=hdr).json()["data"]
    assert sonuc["eklendi"] == 2
    with Session(engine()) as db:
        satirlar = {r.title: r for r in db.scalars(select(RevenueBenefit))}
    alfa, beta = satirlar["Alfa otomasyon"], satirlar["Beta iş"]
    assert (alfa.roadmap, alfa.hours_per_year, alfa.hours_per_month, alfa.approval) == ("Mayıs: faz 1", 432.0, 36.0, "onayli")
    assert beta.hours_per_year is None and "Yıllık verimlilik (Excel): Çalışılmaktadır" in beta.extra_note and beta.year_revenue == 60000
    assert servis.eksik_alanlar({a: getattr(beta, a) for a in servis.ALANLAR}, True) == ["roadmap", "hours_per_month", "hours_per_year", "end_date"]


def test_govde_yardimcisi_tum_zorunlu_alanlari_doldurur():
    """test_gelir_uretim._govde yeni giris kuralini gecer (diger testler yalniz konu ettikleri alani degistirir)."""
    temiz = servis.temizle({**_govde(), "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31)})
    assert servis.eksik_alanlar(temiz, False) == []
