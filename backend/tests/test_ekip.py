"""Ekip ozeti (Genel Bakis): rapor uyumu, risk, utilizasyon, takvim, projeler, siralama, ozet cumleleri ve kapsam."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.ekip import servis
from app.models import AppUser, Customer, ProjectItem, Report, ScoringExclusion
from app.ortak import rapor_donemi, simdi


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
    bugun = datetime.now().date()
    assert (
        client.put(
            "/api/v1/takvim/gun", json={"tarih": bugun.isoformat(), "durum": "yillik_izin", "online": 2, "yuzyuze": 1}, headers=hdr
        ).status_code
        == 200
    )
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
    assert set(s) == {"ayse", "mehmet", "mudur"}
    # siralama agirlik puanina gore; puanlama disi (mehmet) ve skorsuz (mudur) en altta
    assert veri["satirlar"][0]["ad"] == "ayse"
    a = s["ayse"]
    assert a["musteri"] == 2 and a["rapor_beklenen"] == 3 and a["rapor_atilan"] == 1 and a["uyum"] == 33
    assert (a["alarm"], a["sikayet"], a["talep"], a["kapanan"], a["risk"]) == (2, 1, 3, 4, 3)
    assert a["final_skor"] == 80.0 and a["agirlik_puani"] == 40.0
    assert a["bugun"] == "yillik_izin" and a["bugun_ad"] == "Yıllık İzin" and (a["online"], a["yuzyuze"]) == (2, 1)
    assert a["proje_acik"] == 2 and a["proje_kapanan"] == 1 and [i["baslik"] for i in a["onemli_isler"]] == ["Kritik iş"]
    assert (
        "skoru 80,0" in a["cumle"] and "bugün yıllık izin" in a["cumle"] and "1/3 rapor" in a["cumle"] and "kritik seviyede" in a["cumle"]
    )
    m = s["mehmet"]
    assert m["puanlama_disi"] is True and m["final_skor"] is None and m["risk"] == 17 and m["bugun"] is None
    assert "takvim kaydı yok" in m["cumle"]
    assert veri["sayilar"] == {"kisi": 3, "kritik_uyum": 2, "yuksek_risk": 1, "acik_proje": 2, "bugun_izinli": 1}
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
