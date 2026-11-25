"""Ceyrek Bazli Sunum: sunuma akan kaynaklar, canli / dondurulmus goruntu, genel gonderim, yetki ve 0004 gocu."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from alembic import command
from app import catalog
from app.db import engine, kullanici_oturumu
from app.gelir_uretim.models import RevenueBenefit, RevenueBenefitPerson
from app.models import ApnRevenue, AppUser, CalendarDay, Customer, OnedeskRecord, Presentation, ProjectItem, Report, RoleView, SmsRevenue
from app.ortak import rapor_donemi, simdi
from app.sunum import servis, tanitim
from app.takvim import kurum_takvimi
from app.takvim.servis import bu_ceyrek, donem_araligi
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
    return sunum_verisi(client)


def sunum_verisi(client):
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
    assert liste["duzenleyebilir"] is True and all(k["acik"] for k in liste["kaynaklar"])  # varsayilan: her modulun alani gorunur (2026-10-14)
    assert {k["id"] for k in liste["kaynaklar"]} == set(servis.KAYNAKLAR)
    assert all(k["ad_en"] and k["aciklama"] and k["aciklama_en"] and k["modul"] for k in liste["kaynaklar"])
    acik = _kaynak_sec(veri, hdr, ["rapor", "takvim", "rapor"])
    assert [k["id"] for k in acik if k["acik"]] == ["rapor", "takvim"]  # kaynak (sunum akis) sirasi, tekrar yok
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
    veri.put("/api/v1/roller/TeamMember", json={"modules": ["takvim"], "landing": "ozet"}, headers=hdr)  # sunum modulu verilmedi
    _cikis(veri, hdr)
    _giris(veri, monkeypatch, "TeamMember")
    assert veri.get("/api/v1/sunum/donem").status_code == 403
    # sunum modulu verilirse 200:
    _cikis(veri, {"X-CSRF-Token": veri.cookies.get("tamlife_csrf")})
    admin_hdr = _giris(veri, monkeypatch, "admin")
    veri.put("/api/v1/roller/TeamMember", json={"modules": ["takvim", "sunum"], "landing": "ozet"}, headers=admin_hdr)
    _cikis(veri, admin_hdr)
    _giris(veri, monkeypatch, "TeamMember")
    assert veri.get("/api/v1/sunum/donem").status_code == 200


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
        assert rapor["kpi"][0]["deger"] == 1 and rapor["kpi"][0]["alt"] == "/ 2 · %50"  # ilk ay: 2 rapor biriminden 1'i atildi
    else:  # ceyregin ilk ayindayiz: rapor donemi (onceki ay) onceki ceyrekte, bu ceyrekte beklenen rapor henuz yok
        assert rapor["kpi"] == [] and all(len(s) == 2 for s in rapor["tablo"]["satirlar"])
    assert ogeler["takvim"]["veri"]["ceyrek"] == CEYREK and any(u["ad"] == "Ayse Test" for u in ogeler["takvim"]["veri"]["uyeler"])


def test_gecmis_ceyrek_onaysizken_modullerle_senkron(veri, monkeypatch):
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, ["takvim", "portfoy"])
    onceki, eski, gelecek = _geri(YIL, CEYREK, 1), _geri(YIL, CEYREK, 2), (YIL + 1, CEYREK)

    ilk = _donem(veri, *onceki)
    assert ilk["zaman"] == "gecmis" and [(o["kaynak"], o["durum"], o["gonderen"]) for o in ilk["ogeler"]] == [("portfoy", "kayitli", ""), ("takvim", "kayitli", "")]
    assert _sunum_sayisi() == 2
    # 2026-10-20: onaysiz ceyrekte sonradan degisen veri sunuma da akar (kayit yenilenir, yeni kayit acilmaz)
    with Session(engine()) as db:
        db.add(Customer(id=4, external_key="t-c", name="Gama", segment="MA", owner_id=1))
        db.commit()
    tekrar = _donem(veri, *onceki)
    cati = lambda d: next(k["deger"] for o in d["ogeler"] if o["kaynak"] == "portfoy" for k in o["veri"]["kpi"] if k["ad"] == "Çatı müşteri")
    assert cati(tekrar) == cati(ilk) + 1 and _sunum_sayisi() == 2

    # anlik kaynak yalniz bir onceki ceyrek icin dondurulur; daha eski ceyrege bugunku durum yazilmaz
    d = _donem(veri, *eski)
    assert [(o["kaynak"], o["durum"]) for o in d["ogeler"]] == [("portfoy", "yok"), ("takvim", "kayitli")]
    assert _sunum_sayisi() == 3
    g = _donem(veri, *gelecek)
    assert g["zaman"] == "gelecek" and [(o["kaynak"], o["durum"]) for o in g["ogeler"]] == [("portfoy", "yok"), ("takvim", "yok")] and _sunum_sayisi() == 3

    # yetkili 'Guncelle': yeniden dondurur (gonderen artik kisi); 'Kaldir' sonrasi isaretli kaynak bir sonraki goruntulemede yeniden donar
    r = veri.post("/api/v1/sunum/gonder", json={"kaynak": "portfoy", "yil": onceki[0], "ceyrek": onceki[1], "gonder": True}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["sunumda"]["gonderen"] == "Admin Kisi"
    portfoy = next(o for o in _donem(veri, *onceki)["ogeler"] if o["kaynak"] == "portfoy")
    assert next(k["deger"] for k in portfoy["veri"]["kpi"] if k["ad"] == "Çatı müşteri") == 3
    assert veri.post("/api/v1/sunum/gonder", json={"kaynak": "takvim", "yil": eski[0], "ceyrek": eski[1], "gonder": False}, headers=hdr).json()["data"]["sunumda"] is None
    assert [o["durum"] for o in _donem(veri, *eski)["ogeler"]] == ["yok", "kayitli"]


def test_kaynak_elle_sabitlenir_kaldirilir_gizli_alan_gosterilmez(veri):
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, ["rapor"])
    govde = {"kaynak": "rapor", "yil": YIL, "ceyrek": CEYREK, "gonder": True}
    assert veri.post("/api/v1/sunum/gonder", json={**govde, "kaynak": "yok"}, headers=hdr).status_code == 404
    assert veri.post("/api/v1/sunum/gonder", json={**govde, "ceyrek": 0}, headers=hdr).status_code == 422
    assert veri.post("/api/v1/sunum/gonder", json=govde, headers=hdr).status_code == 200
    (oge,) = _donem(veri, YIL, CEYREK)["ogeler"]
    assert oge["kaynak"] == "rapor" and oge["durum"] == "kayitli" and oge["gonderen"] == "Admin Kisi"
    _kaynak_sec(veri, hdr, [])  # sunumdan cikarilan alan sabitlenmis kaydi olsa da gosterilmez
    assert _donem(veri, YIL, CEYREK)["ogeler"] == []
    _kaynak_sec(veri, hdr, ["rapor"])
    veri.post("/api/v1/sunum/gonder", json={**govde, "gonder": False}, headers=hdr)
    assert [o["durum"] for o in _donem(veri, YIL, CEYREK)["ogeler"]] == ["canli"] and _sunum_sayisi() == 0


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


def _kalem(kimlik, sahip, kategori, olusma: date, durum="devam", kapanis: date | None = None, guncelleme: date | None = None) -> ProjectItem:
    an = datetime(olusma.year, olusma.month, olusma.day, 12, tzinfo=UTC)
    son = datetime(guncelleme.year, guncelleme.month, guncelleme.day, 12, tzinfo=UTC) if guncelleme else an
    return ProjectItem(id=kimlik, owner_id=sahip, category=kategori, title=f"Is {kimlik}", status=durum, closed_date=kapanis, created_at=an, updated_at=son)


def test_sayilarla_tam_ekibi_yonetici_ozeti_proje_kartini_tekrarlamaz(veri):
    """Sayılarla TAM; gelir, müşteri, utilizasyon ve ekip büyüklüğünü özetler, proje tablosunu tekrar etmez."""
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, ["sayilar"])
    (oge,) = _donem(veri, YIL, CEYREK)["ogeler"]
    v = oge["veri"]
    kpi = {k["kod"]: k for k in v["kpi"]}
    assert v["stil"] == "sayilar" and list(kpi) == ["gelir", "yillik_gelir", "fayda", "musteri", "utilizasyon", "tam"]
    assert kpi["gelir"]["deger"] == 0 and kpi["yillik_gelir"]["deger"] == 0 and kpi["fayda"]["deger"] == 0
    assert (kpi["musteri"]["deger"], kpi["musteri"]["alt"]) == (3, "2 çatı · 1 iştirak")
    assert kpi["utilizasyon"]["deger"] == 50 and kpi["tam"]["deger"] == 1
    assert "tablo" not in v


def test_tanitim_olculmus_sayilar_verir(veri):
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, ["tanitim"])
    (oge,) = _donem(veri, YIL, CEYREK)["ogeler"]
    v = oge["veri"]
    assert oge["durum"] == "canli" and oge["anlik"] is True and v["stil"] == "tanitim"
    kod = v["kod"]
    assert kod["satir"] > 1000 and kod["dosya"] > 10 and 0 < kod["test_satir"] < kod["satir"]
    assert sum(d["satir"] for d in kod["diller"]) == kod["satir"] and abs(sum(d["pay"] for d in kod["diller"]) - 100) <= 0.3
    assert [d["dil"] for d in kod["diller"]][:2] == ["Python", "TypeScript"] and all(d["rol"] and d["rol_en"] for d in kod["diller"])
    sayi = {s["kod"]: s["deger"] for s in v["sayilar"]}
    assert sayi["modul"] == len(v["kapsam"]) == sum(1 for m in catalog.MODULES if m.ready)
    assert sayi["uc"] > 50 and sayi["tablo"] > 20 and sayi["goc"] >= 8 and sayi["test"] > 100 and sayi["dosya"] == kod["dosya"]
    canli = {x["ad_en"]: x["deger"] for x in v["canli"]}
    assert canli["Parent customers"] == 2 and canli["Affiliates"] == 1 and canli["TAMs"] == 1 and canli["Monthly reports"] == 1 and canli["Alarms and tickets"] == 2
    assert v["amac"]["tr"] and v["amac"]["en"] and len(v["fayda"]) == 4 and all(f["aciklama"] and f["aciklama_en"] for f in v["fayda"])
    # ust yonetim duzeni (2026-10-20): ozet, 3 maddelik amac, is alanlarina gore kapsam (her hazir modul tam bir alanda)
    assert v["slogan"]["tr"] and v["ozet"]["tr"] and v["ozet"]["en"] and len(v["amac_maddeleri"]) == 3
    alan_modulleri = [m["ad"] for a in v["alanlar"] for m in a["moduller"]]
    assert len(v["alanlar"]) == 4 and sorted(alan_modulleri) == sorted(m["ad"] for m in v["kapsam"])
    assert [k["kod"] for k in v["kpi"]] == ["satir", "modul", "uc", "test"]  # eski arayuzun de cizebilecegi genel KPI listesi


def test_kod_olcumu_yalniz_yazilan_dolu_satirlari_dile_gore_sayar(tmp_path):
    def yaz(yol: str, metin: str) -> None:
        p = tmp_path / yol
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(metin, encoding="utf-8")

    assert tanitim.kod_olc(tmp_path) is None  # hic kod dosyasi yok
    yaz("backend/app/a.py", "x = 1\n\n\ny = 2\n")  # 2 dolu satir
    yaz("backend/tests/test_a.py", "def test_a():\n    pass\n\n")  # 2 dolu satir, test
    yaz("backend/var/gecici.py", "x = 1\n")  # calisma verisi: sayilmaz
    yaz("ekran-react/src/x.ts", "const a = 1\n")
    yaz("ekran-react/src/y.tsx", "export const Y = () => null\n\nexport const Z = 1\nexport const W = 2\n")  # 3 dolu satir
    yaz("ekran-react/src/x.test.ts", "it('a', () => {})\n")  # test
    yaz("ekran-react/src/index.css", "a { color: red }\nb { color: blue }\n")
    yaz("ekran-react/src/components/ui/button.tsx", "\n".join(["x"] * 50))  # hazir bilesen: sayilmaz
    yaz("ekran-react/node_modules/z/i.ts", "x\n" * 100)
    yaz("ekran-react/public/lib.ts", "x\n" * 100)  # ucuncu taraf: sayilmaz
    yaz("kurulum/k.ps1", "Write-Host 1\nWrite-Host 2\nWrite-Host 3\n")
    yaz("README.md", "# oku\n")  # kod degil
    o = tanitim.kod_olc(tmp_path)
    assert o is not None
    assert [(d["dil"], d["satir"], d["dosya"]) for d in o["diller"]] == [("TypeScript", 5, 3), ("Python", 4, 2), ("PowerShell", 3, 1), ("CSS", 2, 1)]  # satira gore azalan
    assert (o["satir"], o["dosya"], o["test_satir"]) == (14, 7, 3)  # test: test_a.py (2) + x.test.ts (1)
    assert abs(sum(d["pay"] for d in o["diller"]) - 100) <= 0.3


def test_uc_ve_revizyon_sayimi(tmp_path, client):
    api = tmp_path / "backend" / "app" / "x"
    api.mkdir(parents=True)
    (api / "api.py").write_text(
        '@router.get("/a")\n@router.post("/b")\n    @router.delete("/c")\n# @router.get("/yorum")\n@app.get("/", include_in_schema=False)\nx = "@router.get(" \n',
        encoding="utf-8",
    )
    (tmp_path / "backend" / "alembic" / "versions").mkdir(parents=True)
    for ad in ("0001_a.py", "0002_b.py", "env.py", "__init__.py"):
        (tmp_path / "backend" / "alembic" / "versions" / ad).write_text("", encoding="utf-8")
    assert tanitim.uc_say(tmp_path) == 3 and tanitim.revizyon_say(tmp_path) == 2
    # gercek uygulamada sayim OpenAPI'deki yol+yontem sayisiyla ayni (kodla ayrisirsa bu test uyarir)
    openapi = sum(len(yontemler) for yontemler in client.app.openapi()["paths"].values())
    assert tanitim.uc_say() == openapi


def test_kisa_kart_onizleme_ipuclari_sutunlara_uyar(veri):
    """Her kaynagin yuku genel bicimde: kpi alanlari tam, tablo.onizleme sutun numaralari tablo icinde; eski arayuz icin 'kpi' her zaman var."""
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, list(servis.KAYNAKLAR))
    for oge in _donem(veri, YIL, CEYREK)["ogeler"]:
        v = oge["veri"]
        if oge["kaynak"] == "takvim":
            continue  # kendi grafigi
        assert isinstance(v["kpi"], list), oge["kaynak"]
        assert all({"ad", "ad_en", "deger", "birim", "alt", "alt_en", "onceki", "kod"} <= set(k) for k in v["kpi"]), oge["kaynak"]
        tablo = v.get("tablo")
        if tablo and "onizleme" in tablo:
            onizleme, kolonlar = tablo["onizleme"], len(tablo["sutunlar"])
            assert onizleme["adet"] >= 1 and all(onizleme[a] < kolonlar for a in ("sira", "etiket", "deger") if a in onizleme), oge["kaynak"]
    liste = {o["kaynak"]: o["veri"]["tablo"].get("onizleme") for o in _donem(veri, YIL, CEYREK)["ogeler"] if o["kaynak"] in {"utilizasyon", "onedesk", "radar", "portfoy"}}
    assert liste == {"utilizasyon": {"adet": 3, "sira": 0, "etiket": 1, "deger": 3, "tavan": 100}, "onedesk": {"adet": 3, "sira": 0, "etiket": 1, "deger": 5}, "radar": {"adet": 3, "sira": 0, "etiket": 1, "deger": 2}, "portfoy": {"adet": 6, "etiket": 0, "deger": 1}}


def test_test_sayilari_dosyasi_gercek_sayidan_az_olamaz():
    """test_sayilari.json her teslimde guncellenir; kaynak koddaki test islevi sayisindan kucukse unutulmus demektir."""
    kok = Path(__file__).resolve().parents[1]
    islev = sum(len([s for s in p.read_text(encoding="utf-8").splitlines() if s.lstrip().startswith(("def test_", "async def test_"))]) for p in (kok / "tests").glob("test_*.py"))
    v = __import__("json").loads(tanitim.TEST_SAYILARI.read_text(encoding="utf-8"))
    assert v["backend"] >= islev and v["arayuz"] > 100 and tanitim.otomatik_test_say() == v["backend"] + v["arayuz"]


def test_gelir_faydasi_kaynagi_kisa_kart_ozeti_verir(veri):
    """Gelir Faydasi Saglanan Isler: ceyrekte suren isler, iptal haric; aylik tutar para birimi basina, kisi adlari ortak personel kumesinden."""
    bas, _ = donem_araligi(YIL, CEYREK)
    simdi_ = simdi()
    with Session(engine()) as db:
        db.add_all(
            [
                RevenueBenefit(id=1, title="Kampanya otomasyonu", status="devam", revenue_amount=50000, revenue_currency="TRY", revenue_period="ay", hours_per_month=20, start_date=bas, created_at=simdi_, updated_at=simdi_),
                RevenueBenefit(id=2, title="Rapor otomasyonu", status="tamamlandi", year_revenue=120000, start_date=bas, end_date=bas + timedelta(days=5), created_at=simdi_, updated_at=simdi_),
                RevenueBenefit(id=3, title="Vazgecilen is", status="iptal", revenue_amount=999, revenue_period="ay", start_date=bas, created_at=simdi_, updated_at=simdi_),
            ]
        )
        db.flush()
        db.add(RevenueBenefitPerson(item_id=1, user_id=2))
        db.commit()
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, ["gelir_uretim"])
    (oge,) = _donem(veri, YIL, CEYREK)["ogeler"]
    v = oge["veri"]
    kpi = {k["ad_en"]: k["deger"] for k in v["kpi"]}
    assert kpi["Work delivering benefit"] == 2 and kpi["Completed"] == 1 and kpi["Monthly revenue TRY"] == 50000 and kpi["In-year revenue"] == 120000
    assert [s[0] for s in v["tablo"]["satirlar"]] == ["Kampanya otomasyonu", "Rapor otomasyonu"] and v["tablo"]["satirlar"][0][1] == "Ayse Test"
    assert v["tablo"]["onizleme"] == {"adet": 3, "etiket": 0, "deger": 4} and v["tablo"]["sutunlar"][4]["ad_en"] == "Monthly revenue TRY"


def test_her_modulun_sunumda_alani_var():
    """Menude gorunen her panel modulu (hazir olmayan Baglantili Araclar dahil; Yonetim'in Rol Yonetimi'si veri modulu degil) en az bir sunum kaynagiyla temsil edilir."""
    menude = {m.key for m in catalog.MODULES if m.in_nav and m.key != "roller"}
    assert menude <= {k.modul for k in servis.KAYNAKLAR.values()}


def test_duzen_sira_ve_gorunurluk(veri, monkeypatch):
    hdr = login_ok(veri)
    sira = ["portfoy", "takvim", *(k for k in servis.KAYNAKLAR if k not in {"portfoy", "takvim"})]
    r = veri.put("/api/v1/sunum/kaynaklar", json={"kaynaklar": ["takvim", "portfoy", "izin"], "sira": ["izin", "portfoy"]}, headers=hdr)
    assert r.status_code == 200, r.text
    liste = r.json()["data"]["kaynaklar"]
    assert [k["id"] for k in liste][:2] == ["izin", "portfoy"] and len(liste) == len(servis.KAYNAKLAR)  # eksik verilen sira: kalanlar eski sirasiyla
    assert [o["kaynak"] for o in _donem(veri, YIL, CEYREK)["ogeler"]] == ["izin", "portfoy", "takvim"]
    assert veri.put("/api/v1/sunum/kaynaklar", json={"kaynaklar": [], "sira": ["yok"]}, headers=hdr).status_code == 400
    _kaynak_sec(veri, hdr, list(servis.KAYNAKLAR))
    veri.put("/api/v1/sunum/kaynaklar", json={"kaynaklar": list(servis.KAYNAKLAR), "sira": sira}, headers=hdr)
    assert [o["kaynak"] for o in _donem(veri, YIL, CEYREK)["ogeler"]] == sira
    _cikis(veri, hdr)
    hdr = _giris(veri, monkeypatch, "TeamMember")  # gorur, duzenleyemez
    assert [k["id"] for k in veri.get("/api/v1/sunum/kaynaklar").json()["data"]["kaynaklar"]] == sira
    assert veri.put("/api/v1/sunum/kaynaklar", json={"kaynaklar": [], "sira": sira}, headers=hdr).status_code == 403


def test_onay_sunumu_sabitler_ve_kaldirilabilir(veri, monkeypatch):
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, ["portfoy", "baglantili"])
    govde = {"yil": YIL, "ceyrek": CEYREK, "onay": True}
    r = veri.post("/api/v1/sunum/onay", json=govde, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["onay"]["onaylayan"] == "Admin Kisi"
    d = _donem(veri, YIL, CEYREK)
    assert d["onay"]["onaylayan"] == "Admin Kisi" and [(o["kaynak"], o["durum"], o["gonderen"]) for o in d["ogeler"]] == [("portfoy", "kayitli", "Admin Kisi"), ("baglantili", "kayitli", "Admin Kisi")]
    assert [k["deger"] for k in d["ogeler"][1]["veri"]["kpi"]] == [0, 0, 0, 0]  # karti olmayan Baglantili Araclar alani da durur
    # onayli sunum degismez: yeni veri, duzen degisikligi ve sabitleme onu etkilemez
    with Session(engine()) as db:
        db.add(Customer(id=4, external_key="t-c", name="Gama", segment="MA", owner_id=1))
        db.commit()
    _kaynak_sec(veri, hdr, ["onedesk"])
    assert _donem(veri, YIL, CEYREK)["ogeler"] == d["ogeler"]
    assert veri.post("/api/v1/sunum/gonder", json={"kaynak": "onedesk", "yil": YIL, "ceyrek": CEYREK, "gonder": True}, headers=hdr).status_code == 409
    assert veri.post("/api/v1/takvim/sunuma-gonder", json={"yil": YIL, "ceyrek": CEYREK, "gonder": True}, headers=hdr).status_code == 409
    assert veri.post("/api/v1/sunum/onay", json=govde, headers=hdr).status_code == 409
    assert veri.post("/api/v1/sunum/onay", json={**govde, "yil": YIL + 1}, headers=hdr).status_code == 400  # baslamamis ceyrek
    _cikis(veri, hdr)
    hdr = _giris(veri, monkeypatch, "TeamMember")
    assert veri.post("/api/v1/sunum/onay", json={**govde, "onay": False}, headers=hdr).status_code == 403
    _cikis(veri, hdr)
    hdr = _giris(veri, monkeypatch, "admin")
    assert veri.post("/api/v1/sunum/onay", json={**govde, "onay": False}, headers=hdr).json()["data"]["onay"] is None
    d = _donem(veri, YIL, CEYREK)
    assert d["onay"] is None and [(o["kaynak"], o["durum"]) for o in d["ogeler"]] == [("onedesk", "canli")] and _sunum_sayisi() == 0


def test_izin_kaynagi_metin_gondermez(veri, monkeypatch):
    monkeypatch.setattr(kurum_takvimi, "KURUM_GUNLERI", {})  # yalniz kisinin kayitlari (kurum gunleri: test_kurum_takvimi.py)
    bas, _ = donem_araligi(YIL, CEYREK)
    with kullanici_oturumu("ayse") as k:
        k.add(CalendarDay(day=bas, status="yillik_izin"))
        k.add(CalendarDay(day=bas + timedelta(days=1), status="calisiyor", work_notes="Gizli is metni", meeting_notes="Gizli toplanti"))
        k.commit()
    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, ["izin"])
    (oge,) = _donem(veri, YIL, CEYREK)["ogeler"]
    kpi = {k["ad_en"]: k["deger"] for k in oge["veri"]["kpi"]}
    # 2026-10-20: izin kirilimlari kisi basina toplanmaz (ekip satiri donemin takvimi; burada kurum gunu yok -> 0); kisi satirinda 1
    assert kpi["Leave days"] == 0 and kpi["Annual leave"] == 0 and kpi["Days with work notes"] == 1 and kpi["Days with meeting notes"] == 1
    ayse = next(s for s in oge["veri"]["tablo"]["satirlar"] if s[0] == "Ayse Test")
    assert ayse[1] == 1 and ayse[2] == 1
    assert oge["veri"]["tablo"]["satirlar"] == [["Ayse Test", 1, 1, 0, 0, 1, 1]]
    assert "Gizli" not in str(oge)


def test_disa_aktar_excel_ekranla_ayni(veri, monkeypatch):
    """2026-10-20 kullanici: ceyregin her verisi Excel / PDF olarak disa aktarilir (ekrandaki ogelerle ayni)."""
    import io as _io

    from openpyxl import load_workbook

    hdr = login_ok(veri)
    _kaynak_sec(veri, hdr, ["portfoy", "takvim"])
    from app.sunum import disa_aktar

    with Session(engine()) as db:
        d = disa_aktar.bolumler(db, YIL, CEYREK, "admin")
    assert [b["kaynak"] for b in d["bolumler"]] == ["portfoy", "takvim"]
    portfoy = d["bolumler"][0]["tablolar"]
    assert portfoy[0]["baslik"] == "Göstergeler" and portfoy[0]["satirlar"][0][0] == "Çatı müşteri"
    takvim = {t["baslik"].split(" (")[0]: t for t in d["bolumler"][1]["tablolar"]}
    assert {"Ekip", "Yıl toplamı", "Kişi bazında"} <= set(takvim)  # TAM Takvim tum yil / ceyrek karismasin
    r = veri.get("/api/v1/sunum/excel", params={"yil": YIL, "ceyrek": CEYREK})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    wb = load_workbook(_io.BytesIO(r.content))
    assert wb.sheetnames[0] == "Özet" and len(wb.sheetnames) == 3
    assert veri.get("/api/v1/sunum/excel", params={"yil": YIL, "ceyrek": 5}).status_code == 422
