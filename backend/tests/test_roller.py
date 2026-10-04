"""Rol gorunumleri: admin hangi rolun hangi modulu gorecegini ve giris sayfasini belirler."""

import dataclasses

from sqlalchemy import text

from app import catalog, navigation, rolgorunum
from app.deps import engine
from tests.conftest import login_ok


def _cikis(client, hdr):
    assert client.post("/api/v1/session/logout", headers=hdr).status_code == 200


def _rol_ile_giris(client, monkeypatch, rol):
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    return login_ok(client)


def _nav_idleri(client):
    return {i["id"] for i in client.get("/api/v1/session/me").json()["data"]["navigation"]}


def test_toptan_kaldirildi_ve_yeni_adlar():
    anahtarlar = {m.key for m in catalog.MODULES}
    assert "toptan" not in anahtarlar and "toptan" not in catalog.HOME_ORDER
    basliklar = {m.key: m.title for m in catalog.MODULES}
    assert basliklar["tamsms"] == "ICT Sms & Gelir"
    assert basliklar["tamapn"] == "APN Gelir ve Kurulum"
    assert basliklar["gelir_uretim"] == "Gelir Faydası Sağlanan İşler"
    assert basliklar["sunum"] == "Çeyrek Bazlı Sunum"
    assert basliklar["onedesk"] == "Onedesk"
    assert not any("TAM Toptan" in t or "OneDesk" in t for t in basliklar.values())


def test_varsayilan_gorunum_ve_giris(client, monkeypatch):
    hdr = login_ok(client)
    _cikis(client, hdr)
    _rol_ile_giris(client, monkeypatch, "TeamMember")
    data = client.get("/api/v1/session/me").json()["data"]
    assert data["landing"] == "ozet"
    ids = {i["id"] for i in data["navigation"]}
    assert "musteri" in ids and "talep" in ids
    assert not ids & {"utilizasyon", "roller", "admin", "integrations", "veri"}


def test_admin_rolu_kisitlar_ve_giris_sayfasi_belirler(client, monkeypatch):
    hdr = login_ok(client)
    r = client.put("/api/v1/roller/TeamMngr", json={"modules": ["musteri", "talep"], "landing": "musteri"}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["landing"] == "musteri"
    listede = client.get("/api/v1/roller").json()["data"]
    mngr = next(x for x in listede["roles"] if x["role"] == "TeamMngr")
    assert mngr["modules"] == ["musteri", "talep"] and mngr["saved"] is True
    assert next(x for x in listede["roles"] if x["role"] == "TeamMember")["saved"] is False
    _cikis(client, hdr)

    _rol_ile_giris(client, monkeypatch, "TeamMngr")
    data = client.get("/api/v1/session/me").json()["data"]
    assert data["landing"] == "musteri"
    assert {i["id"] for i in data["navigation"]} == {"musteri", "talep"}
    assert client.get("/api/v1/modules/musteri").status_code == 200
    assert client.get("/api/v1/modules/rapor").status_code == 403
    assert {m["key"] for m in client.get("/api/v1/modules").json()["data"]} == {"musteri", "talep"}
    assert {c["key"] for c in client.get("/api/v1/home").json()["data"]} == {"musteri"}
    # Member etkilenmez
    _cikis(client, {"X-CSRF-Token": client.cookies.get("tamlife_csrf")})
    _rol_ile_giris(client, monkeypatch, "TeamMember")
    assert "rapor" in _nav_idleri(client)


def test_rol_kaydi_dogrulamalari(client, monkeypatch):
    hdr = login_ok(client)
    put = lambda rol, **g: client.put(f"/api/v1/roller/{rol}", json=g, headers=hdr)
    assert put("TeamMngr", modules=["utilizasyon", "roller"], landing="ozet").status_code == 200  # hicbir modul kilitli degil
    assert put("TeamMngr", modules=["yok"], landing="ozet").status_code == 400
    assert put("TeamMngr", modules=["musteri"], landing="rapor").status_code == 400  # giris verilenlerden biri olmali
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
    alt = (catalog.SubModule("liste", "Müşteri Listesi", "açıklama", True), catalog.SubModule("kart", "Müşteri Kartı"))
    yeni = tuple(dataclasses.replace(m, children=alt) if m.key == "musteri" else m for m in catalog.MODULES)
    for yer in (catalog, navigation, rolgorunum):
        monkeypatch.setattr(yer, "MODULES", yeni)
    import app.main as ana

    monkeypatch.setattr(ana, "MODULES", yeni)
    monkeypatch.setattr(catalog, "BY_KEY", {m.key: m for m in yeni})

    hdr = login_ok(client)
    nav = client.get("/api/v1/session/me").json()["data"]["navigation"]
    kok = next(i for i in nav if i["id"] == "musteri")
    assert [c["id"] for c in kok["children"]] == ["musteri/liste", "musteri/kart"]
    assert client.get("/api/v1/modules/musteri/liste").status_code == 200
    assert client.get("/api/v1/modules/musteri/yok").status_code == 404

    # Manager yalniz ana modulu ve bir alt modulu gorur
    assert client.put("/api/v1/roller/TeamMngr", json={"modules": ["musteri", "musteri/liste"], "landing": "musteri"}, headers=hdr).status_code == 200
    assert client.put("/api/v1/roller/TeamMngr", json={"modules": ["musteri/yok"], "landing": "ozet"}, headers=hdr).status_code == 400
    _cikis(client, hdr)
    _rol_ile_giris(client, monkeypatch, "TeamMngr")
    nav = client.get("/api/v1/session/me").json()["data"]["navigation"]
    assert [c["id"] for c in next(i for i in nav if i["id"] == "musteri")["children"]] == ["musteri/liste"]
    assert client.get("/api/v1/modules/musteri/liste").status_code == 200
    assert client.get("/api/v1/modules/musteri/kart").status_code == 403


def test_yonetim_modulleri_role_verilebilir_ama_tam_yetki_admin_de(client, monkeypatch):
    hdr = login_ok(client)
    r = client.put("/api/v1/roller/TeamMngr", json={"modules": ["musteri", "utilizasyon", "roller"], "landing": "utilizasyon"}, headers=hdr)
    assert r.status_code == 200
    _cikis(client, hdr)
    hdr2 = _rol_ile_giris(client, monkeypatch, "TeamMngr")
    nav = {i["id"]: i for i in client.get("/api/v1/session/me").json()["data"]["navigation"]}
    assert set(nav) == {"musteri", "utilizasyon", "roller"}
    assert nav["utilizasyon"]["group"] == "work" and nav["roller"]["group"] == "work"  # Yonetim sayfasi admin'e ozel, menude Benim Yerim
    assert client.get("/api/v1/modules/utilizasyon").status_code == 200
    # Rol ekrani salt okunur: goruntuler, degistiremez
    assert client.get("/api/v1/roller").status_code == 200
    assert client.put("/api/v1/roller/TeamMember", json={"modules": ["musteri"], "landing": "ozet"}, headers=hdr2).status_code == 403
    assert client.get("/api/v1/admin").status_code == 403
    # Member'a verilmedi: gormez, rol ekranina da giremez
    _cikis(client, hdr2)
    _rol_ile_giris(client, monkeypatch, "TeamMember")
    assert "utilizasyon" not in _nav_idleri(client)
    assert client.get("/api/v1/modules/utilizasyon").status_code == 403
    assert client.get("/api/v1/roller").status_code == 403


def test_grup_yerlesimi_ve_tam_ozet_yok(client):
    login_ok(client)
    nav = client.get("/api/v1/session/me").json()["data"]["navigation"]
    grup = {i["id"]: i["group"] for i in nav}
    assert "ekip" not in grup and "ekip" not in catalog.HOME_ORDER
    for k in ("proje", "sunum", "radar", "rapor", "takvim_ozet", "gelir_uretim"):
        assert grup[k] == "insights", k
    for k in ("musteri", "takvim", "onedesk", "tamsms", "tamapn", "baglantili"):
        assert grup[k] == "work", k
