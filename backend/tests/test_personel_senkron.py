"""Tek personel kumesi (2026-10-13): takvim, ekip ozeti, utilizasyon, proje ve musteri listeleri ayni kisileri gosterir;
yalniz etkin TeamMember. TeamMngr ve admin hicbir kisi listesinde satir olmaz, kisisel takvim modulunu de acamaz."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app import kullanicilar
from app.db import engine
from app.hesap import _personel
from app.models import AppUser, Customer, ProjectItem
from app.sunum import servis as sunum
from app.takvim.servis import bu_ceyrek
from tests.conftest import login_ok

SIMDI = datetime.now(UTC)


def _kisiler() -> None:
    with Session(engine()) as db:
        db.add_all(
            [
                AppUser(username="ayse", display_name="Ayse Test", role="TeamMember"),  # hic giris yapmamis: yine listelenir
                AppUser(username="mehmet", display_name="Mehmet Test", role="TeamMember", last_login_at=SIMDI),
                AppUser(username="mudur", display_name="Mudur Kisi", role="TeamMngr", last_login_at=SIMDI),
                AppUser(username="yonetici", display_name="Admin Iki", role="admin", is_admin=True, last_login_at=SIMDI),
                AppUser(username="eski", display_name="Eski Kisi", role="TeamMember", active=False, last_login_at=SIMDI),
            ]
        )
        db.commit()


def _giris(client, monkeypatch, rol: str) -> dict[str, str]:
    client.post("/api/v1/session/logout")
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    return login_ok(client)


def test_tum_listeler_ayni_personeli_gosterir(client):
    login_ok(client)  # admin
    _kisiler()
    beklenen = {"Ayse Test", "Mehmet Test"}
    takvim = {u["ad"] for u in client.get("/api/v1/takvim/ekip").json()["data"]["uyeler"]}
    ekip = {s["ad"] for s in client.get("/api/v1/ekip/ozet").json()["data"]["satirlar"]}
    proje = client.get("/api/v1/proje").json()["data"]
    musteri = {t["ad"] for t in client.get("/api/v1/musteri/secenekler").json()["data"]["tam"]}
    agac = {p["ad"] for p in client.get("/api/v1/skor/agac").json()["data"]["tum_personel"]}
    assert takvim == ekip == musteri == agac == beklenen
    assert {t["ad"] for t in proje["tamlar"]} == {d["tam"] for d in proje["ozet"]} == beklenen  # projesi olmayan da satir


def test_yonetici_ve_admin_takvim_tutmaz_ama_ekip_takvimini_gorur(client, monkeypatch):
    login_ok(client)
    hdr = {"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""}
    _kisiler()
    r = client.get("/api/v1/roller").json()["data"]
    takvim = next(m for m in r["catalog"] if m["id"] == "takvim")
    assert takvim["personel_only"] is True
    # TeamMngr kaydina 'takvim' verilse bile dusurulur; TeamMember'da kalir
    moduller = ["takvim", "takvim_ozet", "musteri"]
    assert client.put("/api/v1/roller/TeamMngr", json={"modules": moduller, "landing": "ozet"}, headers=hdr).json()["data"]["modules"] == ["musteri", "takvim_ozet"]
    assert "takvim" in client.put("/api/v1/roller/TeamMember", json={"modules": moduller, "landing": "ozet"}, headers=hdr).json()["data"]["modules"]
    # admin: kendi takvimini acamaz
    assert client.get("/api/v1/takvim/ben", params={"yil": 2026, "ay": 2}).status_code == 403
    assert client.put("/api/v1/takvim/gun", json={"tarih": "2026-02-02", "durum": "calisiyor"}, headers=hdr).status_code == 403
    # TeamMngr: TAM Takvim'i gorur (listede kendisi yok), kendi takvimini acamaz
    _giris(client, monkeypatch, "TeamMngr")
    assert client.get("/api/v1/takvim/ben", params={"yil": 2026, "ay": 2}).status_code == 403
    assert {u["ad"] for u in client.get("/api/v1/takvim/ekip").json()["data"]["uyeler"]} == {"Ayse Test", "Mehmet Test"}
    # TeamMember: kendi takvimini yazar
    hdr = _giris(client, monkeypatch, "TeamMember")
    assert client.put("/api/v1/takvim/gun", json={"tarih": "2026-02-02", "durum": "calisiyor", "online": 1}, headers=hdr).status_code == 200


def test_personel_kumesi_tek_tanim(client):
    login_ok(client)
    _kisiler()
    with Session(engine()) as db:
        assert [u.username for u in kullanicilar.personel(db)] == ["ayse", "mehmet"]
        k = {u.username: u for u in db.query(AppUser)}
        assert [kullanicilar.personel_mi(k[a]) for a in ("ayse", "mudur", "yonetici", "eski")] == [True, False, False, False]
        assert kullanicilar.personel_mi(None) is False
        # komut satiri denetimi: ayni kume ve disarida kalanlar nedeniyle
        import contextlib
        import io

        cikti = io.StringIO()
        with contextlib.redirect_stdout(cikti):
            _personel(db)
    metin = cikti.getvalue()
    assert "PERSONEL (2 kisi" in metin and "mudur" in metin and "rol TeamMngr" in metin and "PASIF hesap" in metin and "-> admin" in metin


def test_yonetici_sahipli_kayitlar_tek_atanmamis_satirinda_toplanir(client):
    """Rapor durumu, proje ozeti ve sunum tablolari: TeamMngr/admin sahipli ya da sahipsiz kayit kisi satiri acmaz; sayilar kaybolmaz."""
    login_ok(client)
    _kisiler()
    with Session(engine()) as db:
        k = {u.username: u.id for u in db.query(AppUser)}
        db.add_all(
            [
                Customer(id=11, external_key="s-1", name="Ayse Musterisi", owner_id=k["ayse"]),
                Customer(id=12, external_key="s-2", name="Mudur Musterisi", owner_id=k["mudur"]),
                Customer(id=13, external_key="s-3", name="Sahipsiz Musteri", owner_id=None),
            ]
        )
        an = datetime.now(UTC)
        for sahip, baslik in ((k["ayse"], "Ayse isi"), (k["mudur"], "Mudur isi")):
            db.add(ProjectItem(owner_id=sahip, category="proje", title=baslik, status="devam", created_at=an, updated_at=an))
        db.commit()

    durum = client.get("/api/v1/rapor/durum").json()["data"]
    satirlar = {s["ad"]: s for s in durum["satirlar"]}
    assert set(satirlar) == {"Ayse Test", "Mehmet Test", "-"} and "Mudur Kisi" not in satirlar
    assert (satirlar["Ayse Test"]["musteri"], satirlar["Mehmet Test"]["musteri"], satirlar["-"]["musteri"]) == (1, 0, 2)  # personel 0 satiri; mudur + sahipsiz tek satir
    assert durum["toplam"]["musteri"] == 3

    proje = client.get("/api/v1/proje").json()["data"]
    ozet = {d["tam"]: d["toplam"] for d in proje["ozet"]}
    assert ozet == {"Ayse Test": 1, "Mehmet Test": 0, "Atanmamış": 1} and proje["genel_toplam"] == 2
    assert [d["tam"] for d in proje["ozet"]][-1] == "Atanmamış"  # atanmamis satiri hep sonda
    assert {t["ad"] for t in proje["tamlar"]} == {"Ayse Test", "Mehmet Test"}  # sorumlu secenegi yalniz personel

    yil, ceyrek = bu_ceyrek()
    with Session(engine()) as db:
        satirlar = sunum._proje(db, yil, ceyrek)["tablo"]["satirlar"]
        assert {s[0] for s in satirlar} == {"Ayse Test", "—"} and sum(s[3] for s in satirlar) == 2
        import contextlib
        import io

        cikti = io.StringIO()
        with contextlib.redirect_stdout(cikti):
            _personel(db)
    metin = cikti.getvalue()
    assert "SAHIBI PERSONEL OLMAYAN KAYITLAR" in metin and "musteri: 1, proje: 1" in metin and "(sahibi bos)" in metin
