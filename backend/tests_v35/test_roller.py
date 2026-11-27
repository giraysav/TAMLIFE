# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Rol gorunumleri: admin hangi rolun hangi modulu gorecegini ve giris sayfasini belirler."""

import dataclasses

from sqlalchemy import text

from app import catalog, navigation, rolgorunum
from app.db import engine
from tests_v35.conftest import login_ok


def _cikis(client, hdr):
    assert client.post("/api/v1/session/logout", headers=hdr).status_code == 200


def _rol_ile_giris(client, monkeypatch, rol):
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    return login_ok(client)


def _nav_idleri(client):
    return {i["id"] for i in client.get("/api/v1/session/me").json()["data"]["navigation"]}


def test_toptan_kaldirildi_ve_yeni_adlar():
    # eski "TAM Toptan" kalkti; 2026-10-14 ayni anahtarla yeni "Toptan" modulu geldi (Musteri Yonetimi icerigi)
    basliklar = {m.key: m.title for m in catalog.MODULES}
    assert basliklar["tamsms"] == "ICT Sms & Gelir"
    assert basliklar["tamapn"] == "APN Gelir ve Kurulum"
    assert basliklar["gelir_uretim"] == "Gelir Faydası Sağlanan İşler"
    assert basliklar["sunum"] == "Çeyrek Sunum"  # 2026-10-20 kullanici: "Çeyrek Bazlı Sunum" -> "Çeyrek Sunum"
    assert basliklar["onedesk"] == "Onedesk"
    assert not any("TAM Toptan" in t or "OneDesk" in t for t in basliklar.values())


def test_varsayilan_gorunum_ve_giris(client, monkeypatch):
    hdr = login_ok(client)
    _cikis(client, hdr)
    _rol_ile_giris(client, monkeypatch, "TeamMember")
    data = client.get("/api/v1/session/me").json()["data"]
    assert data["landing"] == "ozet"
    ids = {i["id"] for i in data["navigation"]}
    assert {"musteri", "talep"} <= ids
    assert not ids & {"utilizasyon", "roller", "admin", "integrations", "veri", "yonetim"}  # TAM Utilizasyon ve Rol Yonetimi Yonetim alanidir: yalniz admin


def test_admin_modulleri_belirler_kaldirilanlar_gizlenir(client, monkeypatch):
    """Admin rol modullerini belirler; kaldirilan moduller kullanici ekranindan ve yetkisinden cikar, admin tam gorur."""
    hdr = login_ok(client)
    r = client.put("/api/v1/roller/TeamMngr", json={"modules": ["musteri", "talep"], "landing": "musteri"}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["landing"] == "ozet"
    listede = client.get("/api/v1/roller").json()["data"]
    mngr = next(x for x in listede["roles"] if x["role"] == "TeamMngr")
    assert mngr["modules"] == ["musteri", "talep"] and mngr["saved"] is True
    assert next(x for x in listede["roles"] if x["role"] == "TeamMember")["saved"] is False
    _cikis(client, hdr)

    # TeamMngr yalniz secilen modulleri gorur, kaldirilanlar gizlenir
    _rol_ile_giris(client, monkeypatch, "TeamMngr")
    data = client.get("/api/v1/session/me").json()["data"]
    assert data["landing"] == "ozet"
    assert {i["id"] for i in data["navigation"]} == {"musteri", "talep"}
    assert client.get("/api/v1/modules/musteri").status_code == 200
    assert client.get("/api/v1/modules/rapor").status_code == 403
    assert client.get("/api/v1/modules/utilizasyon").status_code == 403
    _cikis(client, {"X-CSRF-Token": client.cookies.get("tamlife_csrf")})

    # TeamMember kaydedilmedigi icin varsayilan tum modulleri gorur
    _rol_ile_giris(client, monkeypatch, "TeamMember")
    data_member = client.get("/api/v1/session/me").json()["data"]
    assert {"musteri", "talep", "rapor", "takvim", "takvim_ozet", "onedesk", "sunum", "radar", "proje"} <= {i["id"] for i in data_member["navigation"]}
    _cikis(client, {"X-CSRF-Token": client.cookies.get("tamlife_csrf")})

    # Admin her zaman tum modulleri tam gorur
    _rol_ile_giris(client, monkeypatch, "admin")
    admin_nav = client.get("/api/v1/session/me").json()["data"]["navigation"]
    admin_ids = {i["id"] for i in admin_nav}
    assert {"musteri", "talep", "rapor", "takvim", "takvim_ozet", "onedesk", "sunum", "radar", "proje", "yonetim"} <= admin_ids


def test_rol_kaydi_dogrulamalari(client, monkeypatch):
    hdr = login_ok(client)
    put = lambda rol, **g: client.put(f"/api/v1/roller/{rol}", json=g, headers=hdr)
    assert put("TeamMngr", landing="ozet").status_code == 200  # modul listesi artik gerekmez
    assert put("TeamMngr", permissions=[]).status_code == 200  # giris sayfasi artik gonderilmez
    assert put("TeamMngr", modules=["musteri"], landing="utilizasyon").json()["data"]["landing"] == "ozet"  # eski istemcinin secimi yok sayilir
    assert put("admin", modules=["musteri"], landing="ozet").status_code == 404  # admin duzenlenemez
    assert put("Baska", modules=["musteri"], landing="ozet").status_code == 404
    assert put("TeamMngr", modules=[], landing="ozet").status_code == 200
    assert client.put("/api/v1/roller/TeamMngr", json={"modules": [], "landing": "ozet"}).status_code == 403  # CSRF'siz
    _cikis(client, hdr)
    anon = client.put("/api/v1/roller/TeamMngr", json={"modules": [], "landing": "ozet"})
    assert anon.status_code == 403  # oturumsuz: CSRF kapisi
    hdr2 = _rol_ile_giris(client, monkeypatch, "TeamMngr")
    assert client.get("/api/v1/roller").status_code == 403
    assert client.put("/api/v1/roller/TeamMember", json={"modules": ["musteri"], "landing": "ozet"}, headers=hdr2).status_code == 403


def test_veritabani_okunamazsa_yonetici_olmayan_kapali(client, monkeypatch):
    hdr = login_ok(client)
    _cikis(client, hdr)
    with engine().begin() as con:
        con.execute(text("DROP TABLE role_view"))
    _rol_ile_giris(client, monkeypatch, "TeamMember")
    ids = _nav_idleri(client)
    assert ids == set()
    assert client.get("/api/v1/modules/musteri").status_code == 403


def test_alt_modul_hazirligi(client, monkeypatch):
    alt = (catalog.SubModule("liste", "Müşteri Listesi", "açıklama", True, "Customer List", "description"), catalog.SubModule("kart", "Müşteri Kartı"))
    yeni = tuple(dataclasses.replace(m, children=alt) if m.key == "musteri" else m for m in catalog.MODULES)
    for yer in (catalog, navigation, rolgorunum):
        monkeypatch.setattr(yer, "MODULES", yeni)
    import app.katalog_api as ana

    monkeypatch.setattr(ana, "MODULES", yeni)
    monkeypatch.setattr(catalog, "BY_KEY", {m.key: m for m in yeni})

    hdr = login_ok(client)
    nav = client.get("/api/v1/session/me").json()["data"]["navigation"]
    kok = next(i for i in nav if i["id"] == "musteri")
    assert [c["id"] for c in kok["children"]] == ["musteri/liste", "musteri/kart"]
    assert (kok["children"][0]["label_en"], kok["children"][0]["description_en"]) == ("Customer List", "description")
    assert client.get("/api/v1/modules/musteri/liste").status_code == 200
    assert client.get("/api/v1/modules/musteri/yok").status_code == 404

    # Manager yalniz secilen alt modulu gorur (kaldirilan gizlenir)
    assert client.put("/api/v1/roller/TeamMngr", json={"modules": ["musteri", "musteri/liste"], "landing": "musteri/liste"}, headers=hdr).status_code == 200
    _cikis(client, hdr)
    _rol_ile_giris(client, monkeypatch, "TeamMngr")
    nav = client.get("/api/v1/session/me").json()["data"]["navigation"]
    assert [c["id"] for c in next(i for i in nav if i["id"] == "musteri")["children"]] == ["musteri/liste"]
    assert client.get("/api/v1/modules/musteri/kart").status_code == 403


def test_yonetim_alani_role_verilemez(client, monkeypatch):
    """Yonetim alani (utilizasyon, roller, yonetim ucu) yalniz admin: ne varsayilan gorunumle ne kayitli eski gorunumle ne API ile acilir."""
    hdr = login_ok(client)
    listede = client.get("/api/v1/roller").json()["data"]
    assert {m["id"] for m in listede["catalog"]}.isdisjoint({"utilizasyon", "roller"})  # rol ekraninda secenek olarak da cikmaz
    r = client.put("/api/v1/roller/TeamMngr", json={"modules": ["musteri", "utilizasyon"], "landing": "ozet"}, headers=hdr)
    assert r.status_code == 200 and "utilizasyon" not in r.json()["data"]["modules"]  # modul listesi yok sayilir
    # Eskiden kaydedilmis gorunum (bu kural gelmeden once) Yonetim kimligi tasisa bile role acilmaz
    with engine().begin() as con:
        con.execute(text("DELETE FROM role_view"))
        con.execute(
            text("INSERT INTO role_view (role, modules, landing, permissions, updated_by) VALUES ('TeamMngr', :m, 'ozet', '[]', 'eski')"),
            {"m": '["musteri", "utilizasyon", "roller"]'},
        )
    _cikis(client, hdr)
    hdr2 = _rol_ile_giris(client, monkeypatch, "TeamMngr")
    assert _nav_idleri(client).isdisjoint({"utilizasyon", "roller", "yonetim"})
    for k in ("utilizasyon", "roller"):
        assert client.get(f"/api/v1/modules/{k}").status_code == 403, k
    assert client.get("/api/v1/roller").status_code == 403
    assert client.put("/api/v1/roller/TeamMember", json={"modules": ["musteri"], "landing": "ozet"}, headers=hdr2).status_code == 403
    assert client.get("/api/v1/yonetim/ozet").status_code == 403
    mngr = next(x for x in gorunumler_admin(client, monkeypatch, hdr2) if x["role"] == "TeamMngr")
    assert "utilizasyon" not in mngr["modules"] and "roller" not in mngr["modules"]  # admin ekraninda da eski Yonetim kimlikleri gorunmez


def gorunumler_admin(client, monkeypatch, hdr):
    _cikis(client, hdr)
    _rol_ile_giris(client, monkeypatch, "admin")
    return client.get("/api/v1/roller").json()["data"]["roles"]


def test_yonetim_uclari_admin_disina_kapali(client, monkeypatch):
    """Yonetim alaninin her ucu (yonetim, tampon, roller, skor) admin olmayana 403 verir; yeni bir uc eklenip korumasi unutulursa bu test kirilir."""
    import re

    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMngr")
    hdr = login_ok(client)
    yollar = client.get("/openapi.json").json()["paths"]  # test ortaminda acik; tum router'lari duzlestirir
    # Skor talebi acmak herkese acik (kendi talebi); gerisi Yonetim > TAM Utilizasyon'dur.
    acik = {("post", "/api/v1/skor/talepler")}
    sayi = 0
    for yol, islemler in yollar.items():
        if not yol.startswith(("/api/v1/yonetim", "/api/v1/tampon", "/api/v1/roller", "/api/v1/skor")):
            continue
        url = re.sub(r"\{(\w*id)\}", "1", yol)  # sayisal kimlikler
        url = re.sub(r"\{\w+\}", "x", url)  # ad / kaynak / rol gibi metin parcalari
        for yontem in islemler:
            if (yontem, yol) in acik:
                continue
            r = client.request(yontem.upper(), url, headers=hdr, json={} if yontem in {"post", "put", "patch"} else None)
            assert r.status_code == 403, (yontem, yol, r.status_code)
            sayi += 1
    assert sayi >= 40  # tarama gercekten uclari buldu (yeni router eklenirse sayi artar)


def test_grup_yerlesimi_ve_tam_ozet_yok(client):
    login_ok(client)
    nav = client.get("/api/v1/session/me").json()["data"]["navigation"]
    grup = {i["id"]: i["group"] for i in nav}
    assert "ekip" not in grup and "ekip" not in catalog.HOME_ORDER
    for k in ("proje", "sunum", "radar", "rapor", "takvim_ozet", "gelir_uretim"):
        assert grup[k] == "insights", k
    for k in ("musteri", "onedesk", "tamsms", "tamapn", "baglantili", "takvim"):
        assert grup[k] == "work", k  # Izin&Takvim admin menusunde de var (2026-10-14)


def test_baglantili_ve_toptan_musteri_icerigi(client, monkeypatch):
    """2026-10-14: Baglantili Araclar hazir; Toptan yeni modul (Benim Yerim grubunda). Ikisi de herkese acik, sunumda kendi alani var."""
    from app.sunum.servis import KAYNAKLAR

    _rol_ile_giris(client, monkeypatch, "TeamMember")
    nav = {i["id"]: i for i in client.get("/api/v1/session/me").json()["data"]["navigation"]}
    for k in ("baglantili", "toptan"):
        assert nav[k]["ready"] is True and nav[k]["group"] == "work", k
        assert catalog.get(k).table == "customers" and k in catalog.HOME_ORDER
        assert k in KAYNAKLAR and KAYNAKLAR[k].modul == k
    assert (nav["toptan"]["label"], nav["toptan"]["label_en"], nav["toptan"]["icon"]) == ("Toptan", "Wholesale", "store")
    assert client.get("/api/v1/musteri/portfoy").status_code == 200  # ekranin verisi Musteri Yonetimi ile ayni uctan


def test_ingilizce_etiketler(client):
    """Arayuz English iken menu, ana sayfa kartlari ve rol ekrani catalog'daki EN adlari kullanir; TR alanlar aynen kalir."""
    assert all(m.title_en for m in catalog.MODULES) and all(p[3] for p in navigation.PRESENTATION.values())
    login_ok(client)
    nav = {i["id"]: i for i in client.get("/api/v1/session/me").json()["data"]["navigation"]}
    assert (nav["musteri"]["label"], nav["musteri"]["label_en"]) == ("Müşteri Yönetimi", "Customer Management")
    assert nav["takvim_ozet"]["label_en"] == "TAM Calendar" and nav["tamsms"]["description_en"]
    assert nav["yonetim"]["label_en"] == "Administration"
    assert all(c["label_en"] and c["description_en"] for c in nav["yonetim"]["children"])
    kartlar = {c["key"]: c for c in client.get("/api/v1/home").json()["data"]}
    assert (catalog.get("takvim").title, catalog.get("takvim").title_en) == ("İzin&Takvim Yönetimi", "Leave & Calendar Management") and "takvim" in kartlar
    assert all(c["title_en"] for c in kartlar.values())
    assert all(m["title_en"] for m in client.get("/api/v1/modules").json()["data"])
    roller = client.get("/api/v1/roller").json()["data"]
    assert all(m["label_en"] for m in roller["catalog"]) and all(y["label_en"] for y in roller["permission_catalog"])
