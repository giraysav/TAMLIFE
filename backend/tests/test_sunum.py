"""Ceyrek Bazli Sunum: sunuma akan kaynaklar, canli / dondurulmus goruntu, genel gonderim, yetki ve 0004 gocu."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from alembic import command
from app.db import engine, kullanici_oturumu
from app.models import ApnRevenue, AppUser, Customer, OnedeskRecord, Presentation, Report, RoleView, SmsRevenue
from app.ortak import rapor_donemi, simdi
from app.sunum import servis
from app.takvim.servis import bu_ceyrek
from tests.conftest import login_ok

YIL, CEYREK = bu_ceyrek()
ILK_AY = 3 * CEYREK - 2
TUM_MODULLER = ["musteri", "takvim", "takvim_ozet", "onedesk", "tamsms", "tamapn", "sunum", "rapor"]


def _geri(yil: int, ceyrek: int, adim: int) -> tuple[int, int]:
    for _ in range(adim):
        yil, ceyrek = (yil, ceyrek - 1) if ceyrek > 1 else (yil - 1, 4)
    return yil, ceyrek


@pytest.fixture
def veri(client):
    """admin (id 1) + ayse (id 2, TeamMember). Cati A (admin, skor 70), istirak A-ist, cati B (ayse, skor 50); bu ceyrekte birer kayit."""
    with Session(engine()) as db:
        db.add_all(
            [
                AppUser(id=1, username="admin", display_name="Admin Kisi", role="admin", is_admin=True),
                AppUser(id=2, username="ayse", display_name="Ayse Test", role="TeamMember", last_login_at=datetime.now(UTC)),
            ]
        )
        db.flush()
        db.add_all(
            [
                Customer(id=1, external_key="t-a", name="Alfa Test A.S.", segment="MA", owner_id=1, score=70),
                Customer(id=2, external_key="t-ai", name="Alfa Istirak", segment="MA", owner_id=1, parent_id=1),
                Customer(id=3, external_key="t-b", name="Beta Test Ltd", segment="SMB", owner_id=2, score=50),
            ]
        )
        db.flush()
        db.add_all(
            [
                Report(report_month=ILK_AY, report_year=YIL, user_id=1, customer_id=1),
                OnedeskRecord(kind="alarm", status="open", customer_id=1, customer_label="Alfa Test A.S.", location="Gebze", opened_at=datetime(YIL, ILK_AY, 1, 12, tzinfo=UTC), external_key="o1"),
                OnedeskRecord(kind="talep", status="open", customer_id=3, customer_label="Beta Test Ltd", location="Ankara", opened_at=datetime(YIL, ILK_AY, 2, 12, tzinfo=UTC), external_key="o2"),
            ]
        )
        db.commit()
    with kullanici_oturumu("ayse") as k:
        k.add(SmsRevenue(tam_name="Ayse Test", customer_name="Beta Test Ltd", amount=1500, currency="TRY", year=YIL, month=ILK_AY))
        k.add(ApnRevenue(tam_name="Ayse Test", customer_name="Beta Test Ltd", amount=800, request_date=date(YIL, ILK_AY, 2), year=YIL, month=ILK_AY))
        k.commit()
    return client


def _giris(client, monkeypatch, rol):
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    return login_ok(client)


def _cikis(client, hdr):
    client.post("/api/v1/session/logout", headers=hdr)


def _kaynak_sec(client, hdr, kaynaklar):
    r = client.put("/api/v1/sunum/kaynaklar", json={"kaynaklar": kaynaklar}, headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()["data"]["kaynaklar"]


def _donem(client, yil, ceyrek):
    r = client.get("/api/v1/sunum/donem", params={"yil": yil, "ceyrek": ceyrek})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _sunum_sayisi() -> int:
    with Session(engine()) as db:
        return db.scalar(select(func.count()).select_from(Presentation)) or 0


def test_kaynak_listesi_ve_yalniz_yetkili_degistirir(veri, monkeypatch):
    hdr = login_ok(veri)
    liste = veri.get("/api/v1/sunum/kaynaklar").json()["data"]
    assert liste["duzenleyebilir"] is True and not any(k["acik"] for k in liste["kaynaklar"])  # varsayilan: hicbiri akmaz
    assert {k["id"] for k in liste["kaynaklar"]} == set(servis.KAYNAKLAR)
    assert all(k["ad_en"] and k["aciklama"] and k["aciklama_en"] and k["modul"] for k in liste["kaynaklar"])
    acik = _kaynak_sec(veri, hdr, ["rapor", "takvim", "rapor"])
    assert [k["id"] for k in acik if k["acik"]] == ["takvim", "rapor"]  # kayit sirasi, tekrar yok
    assert veri.put("/api/v1/sunum/kaynaklar", json={"kaynaklar": ["yok"]}, headers=hdr).status_code == 400
    veri.put("/api/v1/roller/TeamMember", json={"modules": TUM_MODULLER, "landing": "ozet", "permissions": []}, headers=hdr)
    _cikis(veri, hdr)

    hdr = _giris(veri, monkeypatch, "TeamMember")  # sunumu gorur, yetkisi yok
    assert veri.get("/api/v1/sunum/kaynaklar").json()["data"]["duzenleyebilir"] is False
    assert veri.put("/api/v1/sunum/kaynaklar", json={"kaynaklar": []}, headers=hdr).status_code == 403
    assert veri.post("/api/v1/sunum/gonder", json={"kaynak": "takvim", "yil": YIL, "ceyrek": CEYREK, "gonder": True}, headers=hdr).status_code == 403
    assert _donem(veri, YIL, CEYREK)["yonetebilir"] is False
    _cikis(veri, hdr)

    hdr = _giris(veri, monkeypatch, "admin")
    veri.put("/api/v1/roller/TeamMember", json={"modules": TUM_MODULLER, "landing": "ozet", "permissions": ["sunum.gonder"]}, headers=hdr)
    _cikis(veri, hdr)
    hdr = _giris(veri, monkeypatch, "TeamMember")
    assert [k["id"] for k in _kaynak_sec(veri, hdr, ["onedesk"]) if k["acik"]] == ["onedesk"]
    assert _donem(veri, YIL, CEYREK)["yonetebilir"] is True
    _cikis(veri, hdr)

    hdr = _giris(veri, monkeypatch, "admin")
    veri.put("/api/v1/roller/TeamMember", json={"modules": ["takvim"], "landing": "ozet"}, headers=hdr)  # sunum modulu kapali
    _cikis(veri, hdr)
    _giris(veri, monkeypatch, "TeamMember")
    assert veri.get("/api/v1/sunum/donem").status_code == 403


def test_bu_ceyrek_canli_hesaplanir_ve_saklanmaz(veri):
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, list(servis.KAYNAKLAR))
    d = _donem(veri, YIL, CEYREK)
    assert d["zaman"] == "guncel" and d["donem"] == f"{YIL}-Q{CEYREK}" and d["yonetebilir"] is True
    ogeler = {o["kaynak"]: o for o in d["ogeler"]}
    assert list(ogeler) == list(servis.KAYNAKLAR) and {o["durum"] for o in ogeler.values()} == {"canli"}
    assert _sunum_sayisi() == 0

    def kpi(kaynak, ad):
        return next(k["deger"] for k in ogeler[kaynak]["veri"]["kpi"] if k["ad"] == ad)

    assert kpi("onedesk", "Alarm") == 1 and kpi("onedesk", "Talep") == 1 and kpi("onedesk", "Kayıt oluşan müşteri") == 2
    assert ogeler["onedesk"]["veri"]["tablo"]["satirlar"][0][1] in {"Alfa Test A.S.", "Beta Test Ltd"}
    assert kpi("sms", "Toplam TRY") == 1500 and ogeler["sms"]["veri"]["tablo"]["satirlar"] == [["Ayse Test", 1500]]
    assert kpi("apn", "Kurulum talebi") == 1 and kpi("apn", "Bekleyen") == 1 and kpi("apn", "Toplam tutar") == 800
    assert kpi("portfoy", "Çatı müşteri") == 2 and kpi("portfoy", "İştirak") == 1 and kpi("portfoy", "Ortalama skor") == 60
    assert kpi("utilizasyon", "Sıralamadaki TAM") == 1 and ogeler["utilizasyon"]["veri"]["tablo"]["satirlar"][0][1] == "Ayse Test"  # admin (skor 70) siralamada yok
    rapor = ogeler["rapor"]["veri"]
    if rapor_donemi(simdi()) >= (YIL, ILK_AY):
        assert rapor["kpi"][0]["deger"] == 1 and rapor["kpi"][0]["alt"] == "/ 2"  # ilk ay: 2 rapor biriminden 1'i atildi
    else:  # ceyregin ilk ayindayiz: rapor donemi (onceki ay) onceki ceyrekte, bu ceyrekte beklenen rapor henuz yok
        assert rapor["kpi"] == [] and all(len(s) == 2 for s in rapor["tablo"]["satirlar"])
    assert ogeler["takvim"]["veri"]["ceyrek"] == CEYREK and any(u["ad"] == "Ayse Test" for u in ogeler["takvim"]["veri"]["uyeler"])


def test_gecmis_ceyrek_ilk_goruntulemede_dondurulur(veri, monkeypatch):
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, ["takvim", "portfoy"])
    onceki, eski, gelecek = _geri(YIL, CEYREK, 1), _geri(YIL, CEYREK, 2), (YIL + 1, CEYREK)

    ilk = _donem(veri, *onceki)
    assert ilk["zaman"] == "gecmis" and [(o["kaynak"], o["durum"], o["gonderen"]) for o in ilk["ogeler"]] == [("takvim", "kayitli", ""), ("portfoy", "kayitli", "")]
    assert _sunum_sayisi() == 2
    # sonradan degisen veri dondurulmus goruntuyu degistirmez
    with Session(engine()) as db:
        db.add(Customer(id=4, external_key="t-c", name="Gama", segment="MA", owner_id=1))
        db.commit()
    tekrar = _donem(veri, *onceki)
    assert tekrar["ogeler"] == ilk["ogeler"] and _sunum_sayisi() == 2

    # anlik kaynak yalniz bir onceki ceyrek icin dondurulur; daha eski ceyrege bugunku durum yazilmaz
    d = _donem(veri, *eski)
    assert [(o["kaynak"], o["durum"]) for o in d["ogeler"]] == [("takvim", "kayitli"), ("portfoy", "yok")]
    assert _sunum_sayisi() == 3
    g = _donem(veri, *gelecek)
    assert g["zaman"] == "gelecek" and g["ogeler"] == [] and _sunum_sayisi() == 3

    # yetkili 'Guncelle': yeniden dondurur (gonderen artik kisi); 'Kaldir' sonrasi isaretli kaynak bir sonraki goruntulemede yeniden donar
    r = veri.post("/api/v1/sunum/gonder", json={"kaynak": "portfoy", "yil": onceki[0], "ceyrek": onceki[1], "gonder": True}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["sunumda"]["gonderen"] == "Admin Kisi"
    portfoy = next(o for o in _donem(veri, *onceki)["ogeler"] if o["kaynak"] == "portfoy")
    assert next(k["deger"] for k in portfoy["veri"]["kpi"] if k["ad"] == "Çatı müşteri") == 3
    assert veri.post("/api/v1/sunum/gonder", json={"kaynak": "takvim", "yil": eski[0], "ceyrek": eski[1], "gonder": False}, headers=hdr).json()["data"]["sunumda"] is None
    assert [o["durum"] for o in _donem(veri, *eski)["ogeler"]] == ["kayitli", "yok"]


def test_isaretsiz_kaynak_elle_gonderilir_ve_kaldirilir(veri):
    hdr = login_ok(veri)
    govde = {"kaynak": "rapor", "yil": YIL, "ceyrek": CEYREK, "gonder": True}
    assert veri.post("/api/v1/sunum/gonder", json={**govde, "kaynak": "yok"}, headers=hdr).status_code == 404
    assert veri.post("/api/v1/sunum/gonder", json={**govde, "ceyrek": 0}, headers=hdr).status_code == 422
    assert veri.post("/api/v1/sunum/gonder", json=govde, headers=hdr).status_code == 200
    (oge,) = _donem(veri, YIL, CEYREK)["ogeler"]
    assert oge["kaynak"] == "rapor" and oge["durum"] == "kayitli" and oge["gonderen"] == "Admin Kisi"
    veri.post("/api/v1/sunum/gonder", json={**govde, "gonder": False}, headers=hdr)
    assert _donem(veri, YIL, CEYREK)["ogeler"] == [] and _sunum_sayisi() == 0


def test_bir_kaynagin_hatasi_digerlerini_dusurmez(veri, monkeypatch):
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, ["onedesk", "portfoy"])

    def bozuk(*_):
        raise RuntimeError("kaynak bozuk")

    monkeypatch.setitem(servis.KAYNAKLAR, "onedesk", dataclasses.replace(servis.KAYNAKLAR["onedesk"], uret=bozuk))
    ogeler = {o["kaynak"]: o for o in _donem(veri, YIL, CEYREK)["ogeler"]}
    assert ogeler["onedesk"]["durum"] == "hata" and len(ogeler["onedesk"]["kayit_no"]) == 8 and ogeler["onedesk"]["veri"] is None
    assert ogeler["portfoy"]["durum"] == "canli"


def test_eski_yetki_kimligi_kaybolmaz(veri, monkeypatch):
    """0004 calismamis bir kayit da yeni kimlikle okunur (takvim.sunuma_gonder -> sunum.gonder)."""
    with Session(engine()) as db:
        db.add(RoleView(role="TeamMember", modules=TUM_MODULLER, landing="ozet", permissions=["takvim.sunuma_gonder"]))
        db.commit()
    login_ok(veri)
    roller = veri.get("/api/v1/roller").json()["data"]["roles"]
    assert next(r for r in roller if r["role"] == "TeamMember")["permissions"] == ["sunum.gonder"]
    _giris(veri, monkeypatch, "TeamMember")
    assert veri.get("/api/v1/session/me").json()["data"]["permissions"]["actions"] == ["sunum.gonder"]


def test_alembic_0004_tablo_ve_yetki_gocu(tmp_path):
    kok = Path(__file__).resolve().parents[1]
    url = f"sqlite:///{(tmp_path / 'goc.db').as_posix()}"
    ayar = Config(str(kok / "alembic.ini"))
    ayar.set_main_option("script_location", str(kok / "alembic"))
    ayar.set_main_option("sqlalchemy.url", url)
    command.upgrade(ayar, "0003_utilizasyon")
    motor = create_engine(url)
    with motor.begin() as b:
        b.execute(text("""INSERT INTO role_view (role, modules, landing, permissions, updated_by) VALUES ('TeamMngr', '[]', 'ozet', '["takvim.sunuma_gonder"]', 'x')"""))
    command.upgrade(ayar, "head")
    with motor.connect() as b:
        assert b.execute(text("SELECT permissions FROM role_view")).scalar() == '["sunum.gonder"]'
        assert b.execute(text("SELECT count(*) FROM app_setting")).scalar() == 0
    command.downgrade(ayar, "0003_utilizasyon")
    with motor.connect() as b:
        assert b.execute(text("SELECT permissions FROM role_view")).scalar() == '["takvim.sunuma_gonder"]'
    motor.dispose()


def test_benim_yerim_ve_raporlar_kaynaklari_gruplu(veri):
    """Rol Yonetimi > Ceyrek Bazli Sunum: Benim Yerim (work) ve Raporlar (insights) modullerinin ozeti sunuma akabilir."""
    hdr = login_ok(veri)
    liste = {k["id"]: k for k in veri.get("/api/v1/sunum/kaynaklar").json()["data"]["kaynaklar"]}
    assert {"proje", "talep", "radar"} <= set(liste)
    assert liste["talep"]["grup"] == "work" and liste["onedesk"]["grup"] == "work" and liste["portfoy"]["grup"] == "work"
    assert liste["proje"]["grup"] == "insights" and liste["rapor"]["grup"] == "insights" and liste["radar"]["grup"] == "insights"
    _kaynak_sec(veri, hdr, ["proje", "talep", "radar"])
    ogeler = {o["kaynak"]: o for o in _donem(veri, YIL, CEYREK)["ogeler"]}
    assert ogeler["talep"]["veri"]["kpi"][0]["ad"] == "Açılan talep" and ogeler["proje"]["veri"]["kpi"][0]["ad_en"] == "Opened in quarter"
    assert ogeler["radar"]["veri"]["tablo"]["satirlar"] == []  # ReportDB verisi yok: uydurma aday yok
