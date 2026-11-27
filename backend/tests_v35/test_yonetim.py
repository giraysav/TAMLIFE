# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Yonetim alani: yetki, genel durum, kalici denetim/gunluk, ariza kaydi, veritabani/yedek, oturumlar, uygulama gunlugu."""

import pytest
from fastapi.testclient import TestClient

from app.audit import audit_log
from app.models import TABLE_OWNER, AuditEvent, Base
from app.yonetim import dosya_gunlugu
from app.yonetim.kalici_yazici import yazici
from tests_v35.conftest import login_ok


def _uc(client, yol):
    return client.get(f"/api/v1/yonetim/{yol}")


def test_yonetim_yalniz_admin(client, monkeypatch):
    assert _uc(client, "ozet").status_code == 401  # oturum yok
    login_ok(client)
    assert _uc(client, "ozet").status_code == 200
    client.post("/api/v1/session/logout", headers={"X-CSRF-Token": client.cookies.get("tamlife_csrf")})
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    hdr = login_ok(client)
    for yol in ("ozet", "veritabani", "arizalar", "gunlukler", "gunlukler.csv", "oturumlar", "uygulama-gunlugu", "ariza-kodlari"):
        assert _uc(client, yol).status_code == 403, yol
    assert client.post("/api/v1/yonetim/veritabani/yedek", headers=hdr).status_code == 403
    assert client.get("/api/v1/tampon/kaynaklar").status_code == 403


def test_genel_durum_yapisi_ve_saglik(client):
    login_ok(client)
    d = _uc(client, "ozet").json()["data"]
    kimlikler = [k["id"] for k in d["saglik"]["kontroller"]]
    assert kimlikler == ["veritabani", "sema", "disk", "gunluk", "oturum", "tampon", "entegrasyon", "ariza"]
    assert d["saglik"]["genel"] in {"ok", "uyari", "hata"}
    assert {k["durum"] for k in d["saglik"]["kontroller"]} <= {"ok", "uyari", "hata"}
    assert next(k for k in d["saglik"]["kontroller"] if k["id"] == "veritabani")["durum"] == "ok"
    assert d["gostergeler"]["veritabani"]["motor"] == "sqlite"
    assert d["gostergeler"]["oturum"]["aktif"] >= 1
    assert {"hazir_parti", "kural", "kural_etkin", "son"} <= set(d["gostergeler"]["tampon"])
    assert {b["id"] for b in d["baglantilar"]} >= {"ad", "oracle_reportdb"}


def test_denetim_kalici_ve_filtrelenir(client):
    login_ok(client)
    client.post("/api/v1/session/login", json={"username": "admin", "password": "yanlis"})  # red olayi
    audit_log.remember(actor="x", action="deneme.olay", outcome="allow", module_key="test", detail="=1+1 formul")
    d = _uc(client, "gunlukler").json()["data"]
    olaylar = {s["olay"] for s in d["satirlar"]}
    assert {"login", "deneme.olay"} <= olaylar and d["toplam"] >= 3
    assert all(s["zaman"].endswith("Z") for s in d["satirlar"])
    red = client.get("/api/v1/yonetim/gunlukler?sonuc=deny").json()["data"]["satirlar"]
    assert red and all(s["sonuc"] == "deny" for s in red)
    assert [s["olay"] for s in client.get("/api/v1/yonetim/gunlukler?olay=deneme").json()["data"]["satirlar"]] == ["deneme.olay"]
    assert client.get("/api/v1/yonetim/gunlukler?q=FORMUL").json()["data"]["toplam"] == 1  # buyuk/kucuk harf duyarsiz
    assert client.get("/api/v1/yonetim/gunlukler?q=%25").json()["data"]["toplam"] == 0  # joker literal
    assert client.get("/api/v1/yonetim/gunlukler?bas=2999-01-01").json()["data"]["toplam"] == 0


def test_denetim_csv_bom_ve_formul_etkisizlestirilir(client):
    login_ok(client)
    audit_log.remember(actor="x", action="deneme.csv", outcome="allow", module_key="test", detail="=HYPERLINK(1)")
    r = _uc(client, "gunlukler.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf")
    metin = r.content.decode("utf-8-sig")
    assert metin.splitlines()[0].startswith("Zaman (UTC);Kullanıcı;Olay")
    assert "'=HYPERLINK(1)" in metin and ";=HYPERLINK" not in metin


def test_denetim_db_kapaliyken_istek_dusmez(client, monkeypatch):
    """Yazici hata verirse olay kuyrukta kalir, istek 200 doner; DB gelince yazilir."""
    login_ok(client)
    yazici.sifirla()

    def _yok():
        raise RuntimeError("db yok")

    with monkeypatch.context() as m:  # yalniz bu blokta; client fixture'inin ortam degiskenleri geri alinmasin
        m.setattr("app.db.engine", _yok)
        audit_log.remember(actor="x", action="kuyrukta", outcome="allow")
        assert yazici.bekleyen() == 1
    assert yazici.bosalt(zorla=True) == 1 and yazici.bekleyen() == 0
    assert any(s["olay"] == "kuyrukta" for s in client.get("/api/v1/yonetim/gunlukler").json()["data"]["satirlar"])


def _hatali_istemci(client):
    """Yakalanmayan istisna 500 doner (test istemcisi istisnayi yukari firlatmasin)."""
    client.app.add_api_route("/api/v1/_patla", lambda: 1 / 0, methods=["GET"])
    istemci = TestClient(client.app, base_url="http://testserver", raise_server_exceptions=False)
    login_ok(istemci)
    return istemci


def test_yakalanmayan_hata_kod_ve_kayit_no_doner(client):
    istemci = _hatali_istemci(client)
    r = istemci.get("/api/v1/_patla")
    assert r.status_code == 500
    g = r.json()
    assert g["hata_kodu"] == "TL-SRV-01" and len(g["kayit_no"]) == 32
    assert g["kayit_no"][:8] in g["detail"] and "division" not in r.text  # ham istisna metni donmez
    liste = istemci.get("/api/v1/yonetim/arizalar").json()["data"]
    assert liste["toplam"] == 1
    a = liste["satirlar"][0]
    assert a["kayit_no"] == g["kayit_no"] and a["durum"] == "open" and a["istisna"] == "ZeroDivisionError"
    assert a["kaynak"] == "GET /api/v1/_patla" and a["kullanici"] == "admin" and a["cozum_adimi"]


def test_ariza_durum_akisi_ve_filtre(client):
    istemci = _hatali_istemci(client)
    istemci.get("/api/v1/_patla")
    istemci.get("/api/v1/_patla")
    hdr = {"X-CSRF-Token": istemci.cookies.get("tamlife_csrf")}
    ilk = istemci.get("/api/v1/yonetim/arizalar").json()["data"]["satirlar"][0]
    r = istemci.post(f"/api/v1/yonetim/arizalar/{ilk['id']}/durum", json={"durum": "closed", "notu": "disk dolu degildi"}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["durum"] == "closed" and r.json()["data"]["kapatan"] == "admin"
    assert istemci.get("/api/v1/yonetim/arizalar?durum=open").json()["data"]["toplam"] == 1
    assert istemci.get("/api/v1/yonetim/arizalar?durum=closed").json()["data"]["toplam"] == 1
    assert istemci.get(f"/api/v1/yonetim/arizalar?q={ilk['kayit_no'][:8]}").json()["data"]["toplam"] == 1
    assert istemci.post(f"/api/v1/yonetim/arizalar/{ilk['id']}/durum", json={"durum": "x"}, headers=hdr).status_code == 400
    assert istemci.post("/api/v1/yonetim/arizalar/99999/durum", json={"durum": "ack"}, headers=hdr).status_code == 404
    assert istemci.post(f"/api/v1/yonetim/arizalar/{ilk['id']}/durum", json={"durum": "ack"}).status_code == 403  # CSRF'siz
    g = istemci.get("/api/v1/yonetim/ozet").json()["data"]
    assert g["gostergeler"]["ariza"]["acik"] == 1


def test_ariza_mesajinda_sir_maskelenir():
    from app import ariza

    assert "hunter2" not in ariza.temizle("baglanti password=hunter2 host=x")
    assert ariza.temizle("a\n b\t c") == "a b c"


def test_veritabani_bilgisi_ve_tablo_sahipligi(client):
    login_ok(client)
    d = _uc(client, "veritabani").json()["data"]
    assert d["motor"] == "sqlite" and d["butunluk"] == "ok" and d["dosya"] == "test.db"
    adlar = {t["ad"]: t for t in d["tablolar"]}
    assert set(adlar) == set(Base.metadata.tables) and set(adlar) <= set(TABLE_OWNER)
    assert adlar["fault_event"]["modul"] == "yonetim" and adlar["ingest_block"]["modul"] == "ingest"
    assert all(t["var"] for t in d["tablolar"]) and d["eksik_tablolar"] == []
    assert d["yedek"]["desteklenir"] is True and d["boyut_bayt"] > 0
    assert d["toplam_satir"] == sum(t["satir"] for t in d["tablolar"])


def test_tablo_sahipligi_metadata_ile_ayni():
    from app.models import KullaniciBase

    assert set(Base.metadata.tables) | set(KullaniciBase.metadata.tables) == set(TABLE_OWNER)


def test_yedek_al_dogrula_ve_koruma(client, tmp_path, monkeypatch):
    from datetime import UTC, date, datetime, timedelta

    from app.db import kullanici_oturumu
    from app.models import CalendarDay

    hdr = login_ok(client)
    with kullanici_oturumu("admin") as k:  # admin takvim tutmaz (API 403); kullanici dosyasi dogrudan olusturulur
        k.add(CalendarDay(day=date(2026, 2, 2), status="raporlu"))
        k.commit()
    monkeypatch.setenv("TAMLIFE_BACKUP_KEEP", "2")
    sayac = iter(range(1, 100))
    # ad saniye cozunurlugunde: ard arda alinan yedeklerin adi cakismasin diye saat ilerletilir
    monkeypatch.setattr(
        "app.yonetim.veritabani.simdi", lambda: datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC) + timedelta(seconds=next(sayac))
    )
    adlar = []
    for _ in range(4):
        r = client.post("/api/v1/yonetim/veritabani/yedek", headers=hdr)
        assert r.status_code == 200 and r.json()["data"]["butunluk"] == "ok" and r.json()["data"]["boyut_bayt"] > 0
        adlar.append(r.json()["data"]["ad"])
    assert len(set(adlar)) == 4
    kisiler = sorted((tmp_path / "yedek").glob("*_kullanicilar"))
    assert [p.name for p in kisiler] == [a.removesuffix(".db") + "_kullanicilar" for a in sorted(adlar)[-2:]]  # budanan yedegin klasoru da gider
    assert (kisiler[-1] / "admin.db").is_file()
    dosyalar = client.get("/api/v1/yonetim/veritabani").json()["data"]["kullanici_dosyalari"]
    assert dosyalar == [{"kullanici": "admin", "boyut_bayt": dosyalar[0]["boyut_bayt"], "butunluk": "ok", "satirlar": {"calendar_day": 1, "sms_revenue": 0, "apn_revenue": 0, "apn_work": 0}}]
    yedek = client.get("/api/v1/yonetim/veritabani").json()["data"]["yedek"]
    assert yedek["saklanan"] == 2 and [y["ad"] for y in yedek["liste"]] == sorted(adlar, reverse=True)[:2]  # en yeni 2 kalir
    d = client.post(f"/api/v1/yonetim/veritabani/yedek/{adlar[-1]}/dogrula", headers=hdr).json()["data"]
    assert d["tamam"] is True and d["butunluk"] == "ok"
    assert client.post("/api/v1/yonetim/veritabani/yedek/..%2Fx.db/dogrula", headers=hdr).status_code in (400, 404)
    assert client.post("/api/v1/yonetim/veritabani/yedek/tamlife_x.db/dogrula", headers=hdr).status_code == 400
    assert client.post("/api/v1/yonetim/veritabani/yedek/tamlife_20990101_000000.db/dogrula", headers=hdr).status_code == 404
    assert client.post("/api/v1/yonetim/veritabani/yedek").status_code == 403  # CSRF'siz
    olaylar = {s["olay"] for s in client.get("/api/v1/yonetim/gunlukler?olay=yonetim.").json()["data"]["satirlar"]}
    assert olaylar == {"yonetim.yedek_al"}


def test_tam_yedek_manifest_dosyalar_ve_geri_donus_betigi(client, tmp_path):
    """Tam yedek: DB + kisi dosyalari + rapor arsivi + foto + SHA-256 manifest; ROLLBACK betikleri tazelenir; bozulan dosya dogrulamada yakalanir."""
    import json
    from datetime import date

    from app.db import kullanici_oturumu
    from app.models import CalendarDay
    from app.rapor.servis import rapor_klasoru

    hdr = login_ok(client)
    with kullanici_oturumu("admin") as k:
        k.add(CalendarDay(day=date(2026, 2, 2), status="raporlu"))
        k.commit()

    rapor = rapor_klasoru()
    rapor.mkdir(parents=True, exist_ok=True)
    (rapor / "ornek.pdf").write_bytes(b"%PDF-ornek")
    foto = tmp_path / "profil_foto"
    foto.mkdir(exist_ok=True)
    (foto / "admin.jpg").write_bytes(b"jpg")
    r = client.post("/api/v1/yonetim/veritabani/yedek", headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["geri_don_betigi"] is True
    ad = r.json()["data"]["ad"]
    yer, kok = tmp_path / "yedek", ad.removesuffix(".db")
    manifest = json.loads((yer / f"{kok}.manifest.json").read_text())
    yollar = {d["yol"] for d in manifest["dosyalar"]}
    assert {ad, f"{kok}_dosyalar/raporlar/ornek.pdf", f"{kok}_dosyalar/profil_foto/admin.jpg"} <= yollar
    assert any(y.startswith(f"{kok}_kullanicilar/") for y in yollar)
    assert manifest["hedefler"]["db"].endswith("test.db") and manifest["hedefler"]["rapor_dizini"] == str(rapor.resolve())
    assert (yer / "ROLLBACK" / "geri_don.ps1").is_file() and (yer / "ROLLBACK" / "GERI_DON.bat").is_file()
    assert not (yer / "ROLLBACK" / "sifre.hash").exists()  # sifre ozetini panel YAZMAZ (kurulumda konur)
    d = client.get("/api/v1/yonetim/veritabani").json()["data"]["yedek"]
    assert d["ayni_disk"] is True and d["geri_donus"] == {"klasor": str(yer / "ROLLBACK"), "betik": True, "sifre": False}
    assert [y["ad"] for y in d["liste"]] == [ad]  # ROLLBACK klasoru yedek listesine girmez
    assert client.post(f"/api/v1/yonetim/veritabani/yedek/{ad}/dogrula", headers=hdr).json()["data"]["tamam"] is True
    (yer / f"{kok}_dosyalar" / "raporlar" / "ornek.pdf").write_bytes(b"degisti")
    bozuk = client.post(f"/api/v1/yonetim/veritabani/yedek/{ad}/dogrula", headers=hdr).json()["data"]
    assert bozuk["tamam"] is False and "ornek.pdf" in bozuk["butunluk"]


def test_yedek_butunlugu_sifre_ozeti_betikle_uyumlu():
    """kurulum\\yedek_geri_don.ps1 ile ayni bicim: pbkdf2-sha256$tur$tuz$ozet (UTF-8 parola)."""
    import base64
    import hashlib

    tuz, tur = bytes(range(16)), 1000
    ozet = hashlib.pbkdf2_hmac("sha256", "Örnek!*_1".encode(), tuz, tur, 32)
    satir = f"pbkdf2-sha256${tur}${base64.b64encode(tuz).decode()}${base64.b64encode(ozet).decode()}"
    parca = satir.split("$")
    assert len(parca) == 4 and base64.b64decode(parca[2]) == tuz and len(base64.b64decode(parca[3])) == 32


def test_oturumlar_listelenir_ve_kapatilir(client):
    hdr = login_ok(client)
    d = client.get("/api/v1/yonetim/oturumlar").json()["data"]
    assert d["siz"] == "admin" and d["oturumlar"][0]["username"] == "admin"
    assert "token" not in str(d).lower() and set(d["oturumlar"][0]) == {"username", "role", "is_admin", "age_s", "idle_s"}
    r = client.post("/api/v1/yonetim/oturumlar/admin/kapat", headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["kapatilan"] == 1
    assert client.get("/api/v1/session/me").status_code == 401  # oturum sunucuda dustu


def test_uygulama_gunlugu_kayit_numarasiyla_yigin_izi(client, tmp_path, monkeypatch):
    login_ok(client)
    monkeypatch.setenv("TAMLIFE_LOG_DIR", str(tmp_path))
    assert client.get("/api/v1/yonetim/uygulama-gunlugu").json()["data"] == {"dosya": "uygulama.log", "var": False, "satirlar": []}
    (tmp_path / "uygulama.log").write_text(
        "2026-10-07 10:00:00 INFO    tamlife: acilis\n"
        "2026-10-07 10:00:01 ERROR   tamlife.ariza: [TL-SRV-01] [kayit abcd1234] GET /x kullanici=admin boom\n"
        "Traceback (most recent call last):\n"
        '  File "x.py", line 1, in f\n'
        "ZeroDivisionError: division by zero\n"
        "2026-10-07 10:00:02 INFO    tamlife: baska\n",
        encoding="utf-8",
    )
    tum = client.get("/api/v1/yonetim/uygulama-gunlugu").json()["data"]["satirlar"]
    assert len(tum) == 6
    secili = client.get("/api/v1/yonetim/uygulama-gunlugu?kayit=abcd1234").json()["data"]["satirlar"]
    assert len(secili) == 4 and secili[0].startswith("2026-10-07 10:00:01") and "ZeroDivisionError" in secili[-1]
    assert client.get("/api/v1/yonetim/uygulama-gunlugu?kayit=../../etc").status_code == 422  # max_length
    assert client.get("/api/v1/yonetim/uygulama-gunlugu?kayit=ZZZZZZZZ").status_code == 400


def test_dosya_gunlugu_kur_kuyruklu_yazar(tmp_path, monkeypatch):
    import logging

    monkeypatch.setenv("TAMLIFE_LOG_DIR", str(tmp_path / "log"))
    kok = logging.getLogger("tamlife")
    monkeypatch.setattr(kok, "_tamlife_dosya", False, raising=False)
    onceki = list(kok.handlers)
    assert dosya_gunlugu.kur() is True
    try:
        logging.getLogger("tamlife.ariza").error("[TL-SRV-01] [kayit 11112222] deneme")
        dinleyici = dosya_gunlugu._dinleyici
        dinleyici.stop()  # kuyrugu bosaltir
        for h in dinleyici.handlers:
            h.close()
        assert "[kayit 11112222]" in (tmp_path / "log" / "uygulama.log").read_text(encoding="utf-8")
    finally:
        for h in list(kok.handlers):
            if h not in onceki:
                kok.removeHandler(h)


@pytest.mark.parametrize("sayfa,adet,beklenen", [(1, 50, 1), (99, 50, 1)])
def test_sayfalama_sinirlanir(sayfa, adet, beklenen):
    from app.ortak import sayfa_bilgisi

    assert sayfa_bilgisi(sayfa, adet, 10)[0] == beklenen


def test_audit_event_tablosunda_gercekten_satir_var(client):
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from app.db import engine

    login_ok(client)
    yazici.bosalt(zorla=True)
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent)) >= 1


def test_kullanici_dizini_goreli_adreste_mutlaktir(monkeypatch, tmp_path):
    from app.db import kullanici_dizini

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TAMLIFE_DATABASE_URL", "sqlite:///./var/x.db")  # dev.ps1 goreli adres kullanir
    assert kullanici_dizini() == (tmp_path / "var" / "kullanicilar").resolve() and kullanici_dizini().is_absolute()
