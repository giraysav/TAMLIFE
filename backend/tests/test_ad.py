"""AD/LDAPS: ayar dogrulama, sebep kodlari ve giris akisi. Canli bind YOK: ldap3 sahte baglantiyla taklit edilir."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from ldap3.utils.conv import escape_filter_chars
from sqlalchemy.orm import Session

from app import ad, hesap, kullanicilar
from app.db import engine
from app.models import AppUser
from tests.conftest import login_ok

AD_ORTAM = {"AD_ENABLED": "true", "AD_SERVER": "ldaps://dc.ornek.local:636", "AD_DOMAIN": "ornek.local"}


@pytest.fixture
def sahte_ad(monkeypatch):
    """Dogru parola 'Dogru-Parola-1'; Who-Am-I yazilan adi doner (degistirilebilir); grup uyeligi acik."""
    durum = {"parola": "Dogru-Parola-1", "whoami": None, "grup": True, "baglanti_hatasi": False, "bind": 0, "filtre": ""}

    class Baglanti:
        def __init__(self, sunucu, user, password, authentication, receive_timeout):
            if durum["baglanti_hatasi"]:
                raise OSError("ag yok")
            self.user, self.password, self.entries = user, password, []
            kisa = user.split("@")[0].split("\\")[-1]
            self.extend = SimpleNamespace(standard=SimpleNamespace(who_am_i=lambda: f"u:ORNEK\\{durum['whoami'] or kisa}"))

        def bind(self):
            durum["bind"] += 1
            return self.password == durum["parola"]

        def unbind(self):
            return True

        def search(self, kok, filtre, attributes, size_limit):
            durum["filtre"] = filtre
            self.entries = [1] if durum["grup"] else []
            return bool(self.entries)

    lib = SimpleNamespace(Server=lambda *a, **k: object(), Connection=Baglanti, Tls=lambda **k: object(), SIMPLE="SIMPLE", NONE="NONE", LDAPSocketOpenError=OSError, kacis=escape_filter_chars)
    monkeypatch.setattr(ad, "_ldap", lambda: lib)
    for k, v in AD_ORTAM.items():
        monkeypatch.setenv(k, v)
    return durum


def test_domain_ayristir(monkeypatch):
    monkeypatch.setenv("AD_DOMAIN", "ornek.local")
    assert ad.domain_ayristir("ayse.kaya") == ("ayse.kaya", "ornek.local")
    assert ad.domain_ayristir("ayse.kaya@diger.local") == ("ayse.kaya", "diger.local")
    assert ad.domain_ayristir("ORNEK\\ayse.kaya") == ("ayse.kaya", "ORNEK")
    assert ad._oturum_adi("ayse.kaya") == "ayse.kaya@ornek.local" and ad._oturum_adi("ORNEK\\a") == "ORNEK\\a"


def test_ayar_dogrula_guvensiz_ayarda_panel_acilmaz(monkeypatch):
    ad.ayar_dogrula()  # kapaliyken hicbir sey istenmez
    monkeypatch.setenv("AD_ENABLED", "true")
    monkeypatch.setenv("AD_SERVER", "ldap://dc.ornek.local")
    with pytest.raises(RuntimeError, match="ldaps"):
        ad.ayar_dogrula()
    from app.main import create_app

    with pytest.raises(RuntimeError, match="ldaps"):
        create_app()
    monkeypatch.setenv("AD_SERVER", "ldaps://dc.ornek.local")
    monkeypatch.setenv("AD_IZINLI_GRUPLAR", "CN=TAM,OU=G,DC=ornek,DC=local")
    with pytest.raises(RuntimeError, match="ARAMA_KOKU"):
        ad.ayar_dogrula()
    monkeypatch.setenv("AD_ARAMA_KOKU", "DC=ornek,DC=local")
    monkeypatch.setenv("AD_KIMLIK_KONTROLU", "belki")
    with pytest.raises(RuntimeError, match="KIMLIK"):
        ad.ayar_dogrula()


def test_dogrula_sebep_kodlari(sahte_ad, monkeypatch):
    assert ad.dogrula("ayse.kaya", "Dogru-Parola-1") == (True, "ad_onayladi")
    assert ad.dogrula("ayse.kaya", "yanlis") == (False, "ad_reddetti")
    assert ad.dogrula("ayse.kaya", "") == (False, "eksik_bilgi")
    once = sahte_ad["bind"]
    assert ad.dogrula("ayse.kaya@yabanci.com", "Dogru-Parola-1") == (False, "alan_izinsiz: yabanci.com")
    assert sahte_ad["bind"] == once  # zorunlu modda alan disina bind denenmez
    monkeypatch.setenv("AD_ALAN_KONTROLU", "izle")
    assert ad.dogrula("ayse.kaya@yabanci.com", "Dogru-Parola-1") == (False, "ad_onayladi_alan_disi:yabanci.com")
    sahte_ad["whoami"] = "baska.kisi"
    assert ad.dogrula("ayse.kaya", "Dogru-Parola-1") == (True, "ad_onayladi_kimlik_farkli:baska.kisi")  # izle: gecer, kaydedilir
    monkeypatch.setenv("AD_KIMLIK_KONTROLU", "zorunlu")
    assert ad.dogrula("ayse.kaya", "Dogru-Parola-1") == (False, "ad_kimlik_uyusmuyor: baska.kisi")
    sahte_ad["whoami"] = None
    monkeypatch.setenv("AD_IZINLI_GRUPLAR", "CN=TAM*,DC=ornek")
    monkeypatch.setenv("AD_ARAMA_KOKU", "DC=ornek")
    sahte_ad["grup"] = False
    assert ad.dogrula("ay*se", "Dogru-Parola-1") == (False, "ad_grup_izinsiz")
    assert "sAMAccountName=ay\\2ase" in sahte_ad["filtre"] and "memberOf=CN=TAM\\2a" in sahte_ad["filtre"]  # LDAP enjeksiyonu kacisli
    sahte_ad["baglanti_hatasi"] = True
    assert ad.dogrula("ayse.kaya", "Dogru-Parola-1") == (False, "ad_ulasilamadi: OSError")
    monkeypatch.setenv("AD_ENABLED", "false")
    assert ad.dogrula("ayse.kaya", "Dogru-Parola-1") == (False, "ad_kapali")


def _giris(client, kullanici, parola):
    return client.post("/api/v1/session/login", json={"username": kullanici, "password": parola})


def test_ilk_giriste_ad_kullanicisi_teammember_acilir_rol_db_den(client, sahte_ad):
    r = _giris(client, "tcakaya", "Dogru-Parola-1")
    assert r.status_code == 200 and r.json()["data"]["role"] == "TeamMember"
    with Session(engine()) as db:
        u = kullanicilar.bul(db, "tcakaya")
        assert u.is_ad_user and u.ad_domain == "ornek.local" and u.display_name == "Tcakaya" and not u.is_admin and u.last_login_at is not None
        u.role = "TeamMngr"  # rol yalniz panel DB'sinden
        db.commit()
    client.post("/api/v1/session/logout", headers={"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""})
    assert _giris(client, "TCAKAYA", "yanlis").status_code == 401
    r = _giris(client, "TcAkaya", "Dogru-Parola-1")
    assert r.status_code == 200 and client.get("/api/v1/session/me").json()["data"]["role"] == "TeamMngr"


def test_pasif_ve_otomatik_acma_kapali(client, sahte_ad, monkeypatch):
    with Session(engine()) as db:
        db.add(AppUser(username="pasif.kisi", display_name="P", role="TeamMember", active=False, is_ad_user=True))
        db.commit()
    once = sahte_ad["bind"]
    assert _giris(client, "pasif.kisi", "Dogru-Parola-1").status_code == 401
    assert sahte_ad["bind"] == once  # pasif kisi icin AD'ye gidilmez
    # 2026-10-15: yalniz tc/ng/te ile baslayan kullanici adlarina hesap acilir (AD dogrulasa da)
    assert _giris(client, "yeni.kisi", "Dogru-Parola-1").status_code == 401
    with Session(engine()) as db:
        assert kullanicilar.bul(db, "yeni.kisi") is None
    monkeypatch.setenv("AD_OTOMATIK_AC", "false")
    assert _giris(client, "tcyeni", "Dogru-Parola-1").status_code == 401
    assert _giris(client, "yeni.kisi", "Dogru-Parola-1").status_code == 401
    with Session(engine()) as db:
        assert kullanicilar.bul(db, "yeni.kisi") is None


def test_yerel_acil_hesap_ve_dev_yerel_giris_ad_acikken(client, sahte_ad):
    with Session(engine()) as db:
        db.add(AppUser(username="ladinadmin", display_name="Acil", role="admin", is_admin=True, password_hash=kullanicilar.parola_ozeti("Acil-Durum-Parolasi")))
        db.commit()
    assert _giris(client, "ladinadmin", "yanlis-parola-xx").status_code == 401
    r = _giris(client, "ladinadmin", "Acil-Durum-Parolasi")
    assert r.status_code == 200 and r.json()["data"]["role"] == "admin"
    assert sahte_ad["bind"] == 0  # yerel hesap AD'ye gitmez
    client.post("/api/v1/session/logout", headers={"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""})
    login_ok(client)  # dev/test yerel kullanici (TAMLIFE_LOCAL_*) AD acikken de calisir


def test_parola_ozeti():
    ozet = kullanicilar.parola_ozeti("En-Az-On-Iki-Karakter")
    assert ozet.startswith("scrypt$") and "En-Az" not in ozet
    assert kullanicilar.parola_dogru("En-Az-On-Iki-Karakter", ozet) and not kullanicilar.parola_dogru("baska", ozet)
    assert not kullanicilar.parola_dogru("x", None) and not kullanicilar.parola_dogru("x", "bozuk$kayit")
    with pytest.raises(ValueError):
        kullanicilar.parola_ozeti("kisa")


def test_env_dosyasi_yukle_mevcut_ortami_ezmez(tmp_path, monkeypatch):
    from app.config import env_dosyasi_yukle

    dosya = tmp_path / ".env"
    dosya.write_text('# yorum\nAD_DOMAIN="ornek.local"\nAD_SERVER=ldaps://dc:636\nBOZUK SATIR\n', encoding="utf-8")
    monkeypatch.delenv("AD_DOMAIN", raising=False)
    monkeypatch.setenv("AD_SERVER", "ldaps://ortamdaki:636")
    env_dosyasi_yukle(dosya)
    import os

    assert os.environ["AD_DOMAIN"] == "ornek.local" and os.environ["AD_SERVER"] == "ldaps://ortamdaki:636"
    monkeypatch.delenv("AD_DOMAIN")


def test_hesap_komut_satiri(client, monkeypatch, capsys):
    assert hesap.main(["rol", "yeni.mudur", "TeamMngr"]) == 0
    assert hesap.main(["pasif", "yeni.mudur"]) == 0
    with Session(engine()) as db:
        u = kullanicilar.bul(db, "yeni.mudur")
        assert u.is_ad_user and u.role == "TeamMngr" and not u.active and u.display_name == "Yeni Mudur"
    assert hesap.main(["parola", "yeni.mudur"]) == 1  # AD kullanicisina yerel parola verilmez
    assert hesap.main(["rol", "x", "Patron"]) == 2
    with Session(engine()) as db:
        db.add(AppUser(username="acil", display_name="Acil", role="admin", is_admin=True))
        db.commit()
    girdiler = iter(["Yeni-Acil-Parola-1", "Yeni-Acil-Parola-1"])
    monkeypatch.setattr(hesap.getpass, "getpass", lambda _istem="": next(girdiler))
    assert hesap.main(["parola", "acil"]) == 0
    with Session(engine()) as db:
        assert kullanicilar.parola_dogru("Yeni-Acil-Parola-1", kullanicilar.bul(db, "acil").password_hash)
    assert hesap.main(["liste"]) == 0 and "yeni.mudur" in capsys.readouterr().out


# --- Kurum Baglantilari: AD erisim testi (bind YOK). Gercek ag yok: DNS / TCP / TLS taklit edilir. ------------------------
@pytest.fixture
def sahte_ag(monkeypatch):
    """socket.getaddrinfo / create_connection ve ssl.create_default_context taklidi; durum[...] ile halka kirilir."""
    import socket
    import ssl

    durum: dict[str, BaseException | None] = {"dns": None, "tcp": None, "tls": None, "ca": None}

    class Soket:
        def close(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Tls(Soket):
        def getpeercert(self):
            return {"subject": ((("commonName", "dc.ornek.local"),),), "issuer": ((("commonName", "Ornek Kurum CA"),),), "notAfter": "Jan  1 00:00:00 2030 GMT"}

        def version(self):
            return "TLSv1.3"

    class Baglam:
        def load_verify_locations(self, yol):
            if durum["ca"]:
                raise durum["ca"]

        def wrap_socket(self, ham, server_hostname):
            if durum["tls"]:
                raise durum["tls"]
            return Tls()

    def adres_coz(host, port):
        if durum["dns"]:
            raise durum["dns"]
        return [(2, 1, 6, "", ("10.0.0.5", 0))]

    def baglan(adres, timeout):
        if durum["tcp"]:
            raise durum["tcp"]
        return Soket()

    monkeypatch.setattr(socket, "getaddrinfo", adres_coz)
    monkeypatch.setattr(socket, "create_connection", baglan)
    monkeypatch.setattr(ssl, "create_default_context", Baglam)
    for k, v in AD_ORTAM.items():
        monkeypatch.setenv(k, v)
    return durum


def test_ad_erisim_adimlari_ilk_kirilan_halkada_durur(sahte_ag, monkeypatch):
    import ssl

    adimlar = ad.erisim_adimlari()
    assert [(x["adim"], x["durum"]) for x in adimlar] == [("dns", "ok"), ("tcp", "ok"), ("tls", "ok")]
    assert "10.0.0.5" in adimlar[0]["ayrinti"] and "TLSv1.3" in adimlar[2]["ayrinti"] and "Ornek Kurum CA" in adimlar[2]["ayrinti"]
    sahte_ag["tcp"] = ConnectionRefusedError("reddedildi")
    assert [(x["adim"], x["durum"]) for x in ad.erisim_adimlari()] == [("dns", "ok"), ("tcp", "hata")]
    sahte_ag["tcp"], sahte_ag["tls"] = None, ssl.SSLCertVerificationError("unable to get local issuer certificate")
    son = ad.erisim_adimlari()[-1]
    assert son["adim"] == "tls" and son["durum"] == "hata" and son["baslik"] == "SERTIFIKA DOGRULANAMADI"
    sahte_ag["dns"] = OSError("isim cozulemedi")
    assert [(x["adim"], x["durum"]) for x in ad.erisim_adimlari()] == [("dns", "hata")]
    monkeypatch.setenv("AD_ENABLED", "false")
    assert [(x["adim"], x["durum"]) for x in ad.erisim_adimlari()] == [("ayar", "hata")]


def test_ad_tani_ayni_adimlari_yazar(sahte_ag, capsys, monkeypatch):
    assert ad.tani() == 0
    cikti = capsys.readouterr().out
    assert "[OK]" in cikti and "DNS: dc.ornek.local" in cikti and "TLS ve sertifika dogrulandi" in cikti
    sahte_ag["ca"] = OSError("dosya yok")
    monkeypatch.setenv("AD_CA_CERT_FILE", "olmayan.pem")
    assert ad.tani() == 2 and "CA dosyasi okunamadi" in capsys.readouterr().out


def test_kurum_baglantilari_ucu_sir_vermez_ad_testi_admin_ve_csrf(client, monkeypatch):
    from app.external import source_key_names

    assert client.get("/api/v1/yonetim/kurum").status_code == 401
    hdr = login_ok(client)
    r = client.get("/api/v1/yonetim/kurum")
    assert r.status_code == 200 and r.json()["data"]["baglantilar"][0]["state"] == "disabled"  # AD kapali: yarim sayilmaz
    for k, v in {**AD_ORTAM, "AD_CA_CERT_FILE": "C:/kurulum/kurum-zinciri.pem", "AD_IZINLI_GRUPLAR": "CN=TAM-Grubu,OU=G,DC=ornek,DC=local",
                 "AD_ARAMA_KOKU": "DC=ornek,DC=local", "ORACLE_REPORTDB_ENABLED": "true", "ORACLE_REPORTDB_PASSWORD": "cok-gizli-parola"}.items():
        monkeypatch.setenv(k, v)
    r = client.get("/api/v1/yonetim/kurum")
    b = r.json()["data"]["baglantilar"]
    assert [x["id"] for x in b] == ["ad", "oracle_reportdb", "oracle_onent", "oracle_galapagos"]
    assert b[0]["state"] == "ready" and b[0]["missing"] == [] and b[0]["tur"] == "dizin"
    assert b[0]["bilgiler"] == {"sunucu": "dc.ornek.local", "port": 636, "ldaps": True, "ssl": True, "alan": "ornek.local",
                                "ca_dosyasi": True, "grup_kisiti": True, "otomatik_ac": True}  # fmt: skip
    assert "kurum-zinciri" not in r.text and "TAM-Grubu" not in r.text and "cok-gizli-parola" not in r.text
    assert "GALAPAGOSDB_DB_IMPORT_QUERY" in source_key_names() and not any(k.startswith("URUNTUTAR") for k in source_key_names())

    from app.yonetim import router as yonetim_router

    monkeypatch.setattr(yonetim_router.ad, "erisim_adimlari", lambda: [{"adim": "dns", "durum": "hata", "baslik": "DNS: dc", "ayrinti": ""}])
    assert client.post("/api/v1/yonetim/kurum/ad-testi").status_code == 403  # CSRF'siz
    r = client.post("/api/v1/yonetim/kurum/ad-testi", headers=hdr)
    assert r.status_code == 200 and r.json()["data"] == {"tamam": False, "adimlar": [{"adim": "dns", "durum": "hata", "baslik": "DNS: dc", "ayrinti": ""}]}
    client.post("/api/v1/session/logout", headers=hdr)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    hdr = login_ok(client)
    assert client.get("/api/v1/yonetim/kurum").status_code == 403
    assert client.post("/api/v1/yonetim/kurum/ad-testi", headers=hdr).status_code == 403


def test_kurum_ad_testi_ucu_taklit_soketle(client, sahte_ag):
    hdr = login_ok(client)
    r = client.post("/api/v1/yonetim/kurum/ad-testi", headers=hdr)
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["tamam"] is True and [x["adim"] for x in d["adimlar"]] == ["dns", "tcp", "tls"]


ORACLE_ORTAM = {
    "ORACLE_REPORTDB_ENABLED": "true",
    "ORACLE_REPORTDB_HOST": "rapor-db.ornek.invalid",
    "ORACLE_REPORTDB_PORT": "1522",
    "ORACLE_REPORTDB_SERVICE_NAME": "GIZLISERVIS",
    "ORACLE_REPORTDB_USER": "gizli_kullanici",
    "ORACLE_REPORTDB_PASSWORD": "cok-gizli-parola",
    "ORACLE_REPORTDB_IMPORT_QUERY": "DELETE FROM x",
}


def test_kurum_oracle_kartlari_sir_vermez(client, monkeypatch):
    for k, v in ORACLE_ORTAM.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("ONENTDB_DB_ENABLED", "true")
    login_ok(client)
    r = client.get("/api/v1/yonetim/kurum")
    b = {x["id"]: x for x in r.json()["data"]["baglantilar"]}
    rdb = b["oracle_reportdb"]
    assert rdb["tur"] == "oracle" and rdb["state"] == "ready" and rdb["label"] == "REPORTDB" and rdb["acma_anahtari"] == "ORACLE_REPORTDB_ENABLED"
    assert rdb["bilgiler"] == {"sunucu": "rapor-db.ornek.invalid", "port": 1522, "servis": "GIZLISERVIS", "kullanici": "gizli_kullanici", "parola": True, "zaman_asimi": 10,
                               "oracle_istemci": False, "sorgu_tamam": False, "sorgu_hata": rdb["bilgiler"]["sorgu_hata"]}  # fmt: skip
    assert "SELECT" in rdb["bilgiler"]["sorgu_hata"] and rdb["son_parti"] is None and rdb["reportdb"]["kartlara_yaz"] is False
    assert b["oracle_onent"]["state"] == "incomplete" and "ONENTDB_DB_HOST" in b["oracle_onent"]["missing"]
    assert b["oracle_galapagos"]["state"] == "disabled" and b["oracle_galapagos"]["bilgiler"]["sunucu"] == ""
    for gizli in ("cok-gizli-parola", "DELETE"):  # parola ve sorgu metni hic verilmez
        assert gizli not in r.text


def test_kurum_oracle_testi_adimlari_ilk_kirilan_halkada_durur(client, sahte_ag, monkeypatch):
    from app.tampon import oracle

    hdr = login_ok(client)
    r = client.post("/api/v1/yonetim/kurum/oracle_reportdb/test", headers=hdr)  # kapali
    assert r.json()["data"] == {"tamam": False, "adimlar": [{"adim": "ayar", "durum": "hata", "baslik": "ORACLE_REPORTDB_ENABLED=true değil", "ayrinti": r.json()["data"]["adimlar"][0]["ayrinti"]}]}
    for k, v in ORACLE_ORTAM.items():
        monkeypatch.setenv(k, v)
    cagri: list[str] = []
    monkeypatch.setattr(oracle, "baglanti_testi", lambda k: cagri.append(k) or {"ok": False, "mesaj": "ORA-01017: ***", "ipucu": "Kullanıcı adı ya da parola hatalı."})
    sahte_ag["tcp"] = TimeoutError("timed out")
    d = client.post("/api/v1/yonetim/kurum/oracle_reportdb/test", headers=hdr).json()["data"]
    assert d["tamam"] is False and [(x["adim"], x["durum"]) for x in d["adimlar"]] == [("ayar", "ok"), ("dns", "ok"), ("tcp", "hata")]
    assert d["adimlar"][2]["baslik"] == "Porta ulaşılamadı (1522)" and cagri == []  # TCP kirilinca oturum denenmez
    sahte_ag["tcp"] = None
    r = client.post("/api/v1/yonetim/kurum/oracle_reportdb/test", headers=hdr)
    d = r.json()["data"]
    assert [x["adim"] for x in d["adimlar"]] == ["ayar", "dns", "tcp", "oturum"] and d["adimlar"][3]["durum"] == "hata"
    assert "parola hatalı" in d["adimlar"][3]["ayrinti"] and cagri == ["oracle_reportdb"]
    assert "10.0.0.5" not in r.text and "rapor-db" not in r.text  # IP ve adres yazilmaz
    monkeypatch.setattr(oracle, "baglanti_testi", lambda k: {"ok": True, "mesaj": "SELECT 1 FROM DUAL → 1", "ipucu": ""})
    assert client.post("/api/v1/yonetim/kurum/oracle_reportdb/test", headers=hdr).json()["data"]["tamam"] is True
    assert client.post("/api/v1/yonetim/kurum/ad/test", headers=hdr).status_code == 404
    assert client.post("/api/v1/yonetim/kurum/oracle_reportdb/test").status_code == 403  # CSRF'siz


def test_admin_yalniz_admin_rolunden_gelir(client, sahte_ad):
    """Yonetim konsolu: elle olusturulup admin rolu verilen kullanici admin; rolu degismis eski is_admin isareti admin yapmaz."""
    with Session(engine()) as db:
        db.add(AppUser(username="elle.admin", display_name="Elle", role="admin", is_admin=False, password_hash=kullanicilar.parola_ozeti("Elle-Admin-Parola-1")))
        db.add(AppUser(username="eski.admin", display_name="Eski", role="TeamMember", is_admin=True, password_hash=kullanicilar.parola_ozeti("Eski-Admin-Parola-1")))
        db.commit()
    r = _giris(client, "elle.admin", "Elle-Admin-Parola-1")
    assert r.status_code == 200 and client.get("/api/v1/session/me").json()["data"]["is_admin"] is True
    client.post("/api/v1/session/logout", headers={"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""})
    r = _giris(client, "eski.admin", "Eski-Admin-Parola-1")
    assert r.status_code == 200 and client.get("/api/v1/session/me").json()["data"]["is_admin"] is False
    assert client.get("/api/v1/yonetim/ozet").status_code == 403
    with Session(engine()) as db:
        assert kullanicilar.bul(db, "eski.admin").is_admin is False  # giriste rolle uyumlu hale gelir
