# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Ekip ozeti (Genel Bakis): rapor uyumu, risk, utilizasyon, takvim, projeler, siralama, ozet cumleleri ve kapsam."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine, kullanici_oturumu
from app.ekip import servis
from app.models import AppUser, CalendarDay, Customer, ProjectItem, Report, ScoringExclusion
from app.ortak import rapor_donemi, rapor_uyum_aylari, simdi


def _giris(client, monkeypatch, kullanici: str, rol: str) -> dict[str, str]:
    client.post("/api/v1/session/logout")
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", kullanici)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    r = client.post("/api/v1/session/login", json={"username": kullanici, "password": "test-parola-1"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""}


def _kurulum(client, monkeypatch) -> dict[str, int]:
    """ayse: 2 cati (1 skorlu) + ayri raporlu istirak, 1 rapor; mehmet: yuksek risk, puanlama disi; mudur yonetici."""
    hdr = _giris(client, monkeypatch, "ayse", "TeamMember")
    bugun = servis._bugun()
    assert (
        client.put(
            "/api/v1/takvim/gun", json={"tarih": bugun.isoformat(), "durum": "yillik_izin", "online": 2, "yuzyuze": 1}, headers=hdr
        ).status_code
        == 200
    )
    with kullanici_oturumu("ayse") as k:
        k.add(CalendarDay(day=bugun.replace(month=1, day=15), status="calisiyor", online_count=4, face_count=3))
        k.commit()
    _giris(client, monkeypatch, "mehmet", "TeamMember")
    _giris(client, monkeypatch, "mudur", "TeamMngr")
    with Session(engine()) as db:
        k = {u.username: u.id for u in db.scalars(select(AppUser))}
        c1 = Customer(
            external_key="A1",
            name="Alfa",
            owner_id=k["ayse"],
            score=80.0,
            alarm_count=2,
            complaint_count=1,
            request_count=3,
            alarm_closed_count=4,
        )
        c2 = Customer(external_key="A2", name="Beta", owner_id=k["ayse"])
        db.add_all([c1, c2])
        db.flush()
        db.add(Customer(external_key="A3", name="Alfa İştirak", owner_id=k["ayse"], parent_id=c1.id, separate_report=True))
        db.add(Customer(external_key="A4", name="Alfa Şube", owner_id=k["ayse"], parent_id=c1.id))  # rapor birimi degil
        db.add(Customer(external_key="M1", name="Gama", owner_id=k["mehmet"], score=60.0, alarm_count=10, complaint_count=7))
        db.add(Report(user_id=k["ayse"], customer_id=c1.id, report_month=rapor_donemi(bugun)[1], report_year=rapor_donemi(bugun)[0], created_at=simdi()))
        db.add(ScoringExclusion(user_id=k["mehmet"], set_by="test", at=simdi()))
        zaman = simdi()
        for baslik, oncelik, durum in (("Kritik iş", "kritik", "devam"), ("Normal iş", "orta", "acik"), ("Biten", "yuksek", "kapandi")):
            db.add(
                ProjectItem(
                    owner_id=k["ayse"], category="proje", title=baslik, priority=oncelik, status=durum, created_at=zaman, updated_at=zaman
                )
            )
        db.commit()
    return k


def test_ekip_ozeti_yonetici_tum_ekibi_gorur(client, monkeypatch):
    _kurulum(client, monkeypatch)
    r = client.get("/api/v1/ekip/ozet")
    assert r.status_code == 200, r.text
    veri = r.json()["data"]
    assert veri["kapsam"] == "ekip" and veri["risk_var"] is True
    s = {x["ad"]: x for x in veri["satirlar"]}
    assert set(s) == {"ayse", "mehmet"}  # yonetici (mudur) ekip satiri olmaz: tek personel kumesi yalniz TeamMember
    # siralama agirlik puanina gore; puanlama disi (mehmet) en altta
    assert veri["satirlar"][0]["ad"] == "ayse"
    a = s["ayse"]
    bugun = servis._bugun()
    donem_sayisi = len(rapor_uyum_aylari(bugun))  # 2026-11-03: Ekim 2026 doneminden itibaren
    assert a["musteri"] == 2 and a["rapor_beklenen"] == 3 * donem_sayisi and a["rapor_atilan"] == 1
    assert a["uyum"] == round(100 / (3 * donem_sayisi))
    assert (a["alarm"], a["sikayet"], a["talep"], a["kapanan"], a["risk"]) == (2, 1, 3, 4, 3)
    assert a["final_skor"] == 80.0 and a["agirlik_puani"] == 40.0
    assert a["bugun"] == "yillik_izin" and a["bugun_ad"] == "Yıllık İzin" and (a["online"], a["yuzyuze"]) == (6, 4)
    assert a["proje_acik"] == 2 and a["proje_kapanan"] == 1 and [i["baslik"] for i in a["onemli_isler"]] == ["Kritik iş"]
    assert (
        "skoru 80,0" in a["cumle"] and "bugün yıllık izin" in a["cumle"] and f"1/{3 * donem_sayisi} rapor" in a["cumle"] and "kritik seviyede" in a["cumle"]
    )
    m = s["mehmet"]
    assert m["puanlama_disi"] is True and m["final_skor"] is None and m["risk"] == 17 and m["bugun"] is None
    assert "takvim kaydı yok" in m["cumle"]
    assert veri["sayilar"] == {"kisi": 2, "kritik_uyum": 2, "yuksek_risk": 1, "acik_proje": 2}  # "bugun izinli" kutusu kalkti (2026-10-14)
    # riskli utilizasyon: ayse Alfa (skor 80) 3 acik kayit -> R = 3 x 0,8 = 2,4; p = 2,4 / 18,4; U = 40 -> 40 x (1 + p)
    assert a["risk_puani"] == 2.4 and a["risk_orani"] == round(2.4 / 18.4, 3) and a["riskli_utilizasyon"] == round(40 * (1 + round(2.4 / 18.4, 3)), 1)
    assert "Risk ağırlıklı utilizasyonu" in a["cumle"]
    assert m["risk_puani"] == 10.2 and m["riskli_utilizasyon"] is None  # puanlama disi: utilizasyon yok, risk puani yine hesaplanir
    assert veri["cumle"] == "2 TAM'ın rapor uyumu kritik seviyede (%50 altı) · 1 TAM yüksek risk yükü taşıyor."


def test_ekip_ozeti_uye_yalniz_kendini_gorur(client, monkeypatch):
    _kurulum(client, monkeypatch)
    hdr = _giris(client, monkeypatch, "mehmet", "TeamMember")
    veri = client.get("/api/v1/ekip/ozet").json()["data"]
    assert veri["kapsam"] == "kendi" and [x["ad"] for x in veri["satirlar"]] == ["mehmet"]
    assert client.post("/api/v1/session/logout", headers=hdr).status_code == 200
    assert client.get("/api/v1/ekip/ozet").status_code == 401


def test_ekip_cumlesi_veri_yokken_saglikli_demez():
    satir = {"rapor_beklenen": 2, "uyum": 100, "risk": 0}
    assert "ReportDB verisi henüz alınmadı" in servis.ekip_cumlesi([satir], risk_var=False)
    assert servis.ekip_cumlesi([satir], risk_var=True) == "Ekip genelinde rapor uyumu ve risk göstergeleri şu an sağlıklı seviyede."
    assert servis.ekip_cumlesi([], risk_var=True) is None


def test_riskli_utilizasyon_formulu():
    """risk = olasilik x etki; oran doygun (R=E iken %50); utilizasyonla orantili, risk yoksa utilizasyonun kendisi."""
    musteriler = [
        Customer(external_key="x1", name="x1", score=50.0, alarm_count=10, complaint_count=6),  # 16 x 0,5 = 8
        Customer(external_key="x2", name="x2", score=None, alarm_count=8, complaint_count=0),  # skorsuz: etki 1 -> 8
    ]
    assert servis.risk_puani(musteriler) == 16.0
    assert servis.risk_orani(16.0) == 0.5 and servis.risk_orani(0) == 0.0 and servis.risk_orani(1000) < 1
    assert servis.riskli_utilizasyon(60.0, 0.5) == 90.0 and servis.riskli_utilizasyon(60.0, 0.0) == 60.0
    assert servis.riskli_utilizasyon(None, 0.5) is None


def test_ekip_ozeti_her_modulun_kutusu(client, monkeypatch):
    """2026-10-14: menudeki modullerin (Yonetim ve OZETTE_YOK haric) Genel Bakis'ta ozet kutusu var; kapsam modulun kendi kurali."""
    from app.ekip.moduller import OZETTE_YOK

    _kurulum(client, monkeypatch)
    veri = client.get("/api/v1/ekip/ozet").json()["data"]  # mudur (TeamMngr): tum ekip
    k = {x["id"]: x for x in veri["moduller"]}
    menu = [i["id"] for i in client.get("/api/v1/session/me").json()["data"]["navigation"] if i["id"] != "yonetim" and i["id"] not in OZETTE_YOK]
    assert [x["id"] for x in veri["moduller"]] == [i for i in menu if i in k] and set(menu) <= set(k)  # menu sirasi, eksiksiz
    assert (k["musteri"]["deger"], k["musteri"]["alt"]) == (3, "çatı · 2 iştirak")  # ayse 2 + mehmet 1 cati; ayse 2 istirak
    assert k["onedesk"]["deger"] == 2 + 1 + 3 + 10 + 7 and k["onedesk"]["ton"] == "kirmizi"
    bugun = servis._bugun()
    donem_sayisi = len(rapor_uyum_aylari(bugun))
    assert k["rapor"]["deger"] == f"1/{4 * donem_sayisi}" and str(bugun.year) in k["rapor"]["alt"]
    assert k["proje"]["deger"] == 2 and "1 yüksek/kritik" in k["proje"]["alt"]
    assert k["takvim_ozet"]["deger"] == 10  # ayse: yil icinde 6 online + 4 yuz yuze
    # kullanici 2026-10-14 13:36Z cikardi
    assert not {"takvim", "tamsms", "tamapn", "sunum", "baglantili", "toptan"} & set(k)
    assert k["talep"]["deger"] == 0 and k["radar"]["deger"] is None  # ReportDB verisi yok: uydurma sayi yok
    assert k["gelir_uretim"]["deger"] == 0
    assert all(x["ad"] and x["ikon"] for x in veri["moduller"])

    _giris(client, monkeypatch, "ayse", "TeamMember")
    k = {x["id"]: x for x in client.get("/api/v1/ekip/ozet").json()["data"]["moduller"]}
    assert k["musteri"]["deger"] == 2 and k["onedesk"]["deger"] == 6  # TeamMember: kisiye bagli kutular yalniz kendisi
    assert "utilizasyon" not in k and "roller" not in k  # yalniz admin moduller kutu acmaz


def test_ozet_eszamanli_istekte_tek_hesap_paylasilir_sirali_istekte_taze(monkeypatch):
    """Genel Bakis ozeti tek sirada hesaplanir (sqlite3 GIL konvoyu); bekleyen ayni kisi istegi kendisinden SONRA baslamis
    hesabin sonucunu alir, sirali istek her zaman yeniden hesaplar."""
    import threading
    import time

    from app.ekip import api as ekip_api
    from app.session import Principal

    hesaplar: list[int] = []
    ilk_basladi, birak = threading.Event(), threading.Event()

    def sahte_ozet(db, user):
        hesaplar.append(1)
        if len(hesaplar) == 1:
            ilk_basladi.set()
            birak.wait(5)
        time.sleep(0.05)
        return {"n": len(hesaplar)}

    class Db:
        def commit(self) -> None:
            pass

    monkeypatch.setattr(ekip_api.servis, "ozet", sahte_ozet)
    monkeypatch.setattr(ekip_api, "_SON", {})
    kisi = Principal(username="kuyruk", role="TeamMngr", is_admin=False)
    sonuclar: list[int] = []
    cagir = lambda: sonuclar.append(ekip_api.ozet(kisi, Db())["data"]["n"])

    ilk = threading.Thread(target=cagir)
    ilk.start()
    assert ilk_basladi.wait(5)
    bekleyenler = [threading.Thread(target=cagir) for _ in range(8)]
    for t in bekleyenler:
        t.start()
    time.sleep(0.1)
    birak.set()
    for t in [ilk, *bekleyenler]:
        t.join(10)
    assert len(hesaplar) == 2, "ilk hesap suruyorken gelen 8 istek tek ikinci hesabi paylasmali"
    assert sorted(sonuclar) == [1] + [2] * 8

    cagir()
    assert len(hesaplar) == 3 and sonuclar[-1] == 3, "sirali istek eski sonucu almamali"


def test_rapor_uyumu_ekim_2026_doneminden_baslar():
    """2026-11-03 kullanici: "Ekim ayi atilan raporlar itibariyla hesaplanacak, yil basindan bugune olan kisimlari hesaplatma"."""
    assert rapor_uyum_aylari(date(2026, 10, 15)) == []  # son donem Eylul: baslangictan once
    assert rapor_uyum_aylari(date(2026, 11, 3)) == [10]
    assert rapor_uyum_aylari(date(2026, 12, 20)) == [10, 11]
    assert rapor_uyum_aylari(date(2027, 1, 5)) == []  # son donem onceki yilin Araligi
    assert rapor_uyum_aylari(date(2027, 4, 2)) == [1, 2, 3]  # sonraki yillar Ocak'tan
