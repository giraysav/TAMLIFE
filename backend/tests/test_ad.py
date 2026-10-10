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
    r = _giris(client, "ayse.kaya", "Dogru-Parola-1")
    assert r.status_code == 200 and r.json()["data"]["role"] == "TeamMember"
    with Session(engine()) as db:
        u = kullanicilar.bul(db, "ayse.kaya")
        assert u.is_ad_user and u.ad_domain == "ornek.local" and u.display_name == "Ayse Kaya" and not u.is_admin and u.last_login_at is not None
        u.role = "TeamMngr"  # rol yalniz panel DB'sinden
        db.commit()
    client.post("/api/v1/session/logout", headers={"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""})
    assert _giris(client, "AYSE.KAYA", "yanlis").status_code == 401
    r = _giris(client, "Ayse.Kaya", "Dogru-Parola-1")
    assert r.status_code == 200 and client.get("/api/v1/session/me").json()["data"]["role"] == "TeamMngr"


def test_pasif_ve_otomatik_acma_kapali(client, sahte_ad, monkeypatch):
    with Session(engine()) as db:
        db.add(AppUser(username="pasif.kisi", display_name="P", role="TeamMember", active=False, is_ad_user=True))
        db.commit()
    once = sahte_ad["bind"]
    assert _giris(client, "pasif.kisi", "Dogru-Parola-1").status_code == 401
    assert sahte_ad["bind"] == once  # pasif kisi icin AD'ye gidilmez
    monkeypatch.setenv("AD_OTOMATIK_AC", "false")
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
