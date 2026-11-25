"""PostgreSQL kaynaklari (ONENTDB / ONEDESKDB): ayar / durum (parola disari cikmaz), erisim adimlari, katalog taramasi (sahte baglanti:
yapi + ornek, kisisel sutun gizli, yetkisiz tablo yapisiyla kalir), agac / nesne uclari ve yenile kurallari. Uydurma veri; ag yok."""

import socket
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.db import engine
from app.tampon import postgres
from tests.conftest import login_ok

ON = "ONENTDB_PG"


@pytest.fixture
def pg_ayar(monkeypatch):
    for ad, v in {"ENABLED": "true", "HOST": "pg.ornek.test", "PORT": "5433", "DBNAME": "ONENT", "USER": "okuyucu", "PASSWORD": "gizli-parola-1"}.items():
        monkeypatch.setenv(f"{ON}_{ad}", v)


class _Imlec:
    def __init__(self, satirlar, adlar=()):
        self._s, self.description = satirlar, [SimpleNamespace(name=a) for a in adlar]

    def fetchall(self):
        return self._s

    def fetchone(self):
        return self._s[0]


class _Sahte:
    def __init__(self):
        self.sorgular: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, q):
        metin = q if isinstance(q, str) else q.as_string(None)
        self.sorgular.append(metin)
        if "count(*)" in metin:
            return _Imlec([(9, 3)])  # sunucuda okunamayan 9 nesne; nesnesi olan 3 sema
        if "FROM pg_class c JOIN pg_namespace" in metin and "pg_attribute" not in metin:
            return _Imlec([("public", "musteri", "r", 120, "Müşteriler"), ("public", "v_ozet", "v", -1, None), ("gizli", "maas", "r", 5, None)])
        if "pg_attribute" in metin:
            return _Imlec([("public", "musteri", "id", "integer", False, None), ("public", "musteri", "unvan", "text", True, "Ünvan"),
                           ("public", "musteri", "telefon", "text", True, None), ("public", "v_ozet", "adet", "bigint", True, None),
                           ("gizli", "maas", "tutar", "numeric", True, None)])  # fmt: skip
        if '"gizli"."maas"' in metin:
            raise RuntimeError("permission denied for table maas")
        if '"public"."musteri"' in metin:
            assert "LIMIT 20" in metin
            return _Imlec([(1, "Alfa A.S.", "05550000000"), (2, "Beta", None)], ("id", "unvan", "telefon"))
        return _Imlec([(7,)], ("adet",))


def test_durum_bilgiler_parolayi_vermez_eksikleri_adla_soyler(pg_ayar, monkeypatch):
    # 2026-11-21 (763662d): <ON EK>_IMPORT_QUERY yolu kaldirildi; durumda sorgu alani yok
    assert postgres.durum("pg_onent") == {"acik": True, "eksik": [], "hazir": True, "state": "ready"}
    b = postgres.bilgiler("pg_onent")
    assert b == {"sunucu": "pg.ornek.test", "port": 5433, "veritabani": "ONENT", "kullanici": "okuyucu", "parola": True, "ssl": "prefer", "zaman_asimi": 10}
    monkeypatch.delenv(f"{ON}_PASSWORD")
    assert postgres.durum("pg_onent")["eksik"] == ["ONENTDB_PG_PASSWORD"]
    assert postgres.durum("pg_onedesk")["state"] == "disabled"
    assert postgres.erisim_adimlari("pg_onedesk")[0]["baslik"] == "ONEDESKDB_PG_ENABLED=true değil"
    with pytest.raises(postgres.PgHata):
        postgres.ayar("oracle_reportdb")


def test_erisim_adimlari_tcp_kirilinca_durur(pg_ayar, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("10.0.0.1", 0))])

    def kapali(*a, **k):
        raise TimeoutError("timed out")

    monkeypatch.setattr(socket, "create_connection", kapali)
    adimlar = postgres.erisim_adimlari("pg_onent")
    assert [a["adim"] for a in adimlar] == ["ayar", "dns", "tcp"] and adimlar[-1]["durum"] == "hata" and "5433" in adimlar[-1]["baslik"]
    assert "gizli-parola-1" not in str(adimlar)


def test_katalog_taramasi_yapi_ornek_kisisel_gizli_ve_uclar(client, pg_ayar):
    sahte = _Sahte()
    with Session(engine()) as db:
        k = postgres.tara(db, "pg_onent", "admin", baglanti=lambda: sahte)
        # gizli.maas: on filtreden gecti ama okunamadi ("permission denied") -> hic alinmaz, yetkisiz sayilir
        assert k.status == "ready" and k.summary == {"semalar": ["public"], "nesne": 2, "sutun": 4, "ornek_adet": 20, "yetkisiz_nesne": 10, "yetkisiz_sema": 2}
    assert all(q.lstrip().upper().startswith("SELECT") for q in sahte.sorgular)  # yalniz SELECT
    assert all("has_table_privilege" in q and "has_schema_privilege" in q for q in sahte.sorgular[:3])  # yetki ilk taramada
    login_ok(client)
    a = client.get("/api/v1/tampon/pg/pg_onent/katalog").json()["data"]
    assert [s["ad"] for s in a["semalar"]] == ["public"] and a["katalog"]["durum"] == "ready" and a["calisiyor"] is False
    musteri = next(n for n in a["semalar"][0]["nesneler"] if n["ad"] == "musteri")
    assert (musteri["tur"], musteri["satir"], musteri["sutun"]) == ("tablo", 120, 3)
    assert next(n for n in a["semalar"][0]["nesneler"] if n["ad"] == "v_ozet")["satir"] is None  # tahmin yok (-1)
    d = client.get(f"/api/v1/tampon/pg/nesne/{musteri['id']}").json()["data"]
    assert d["ornek"]["satirlar"] == [[1, "Alfa A.S.", "***"], [2, "Beta", None]] and "gizlendi" in d["ornek"]["not"]
    assert d["sutunlar"][1] == {"ad": "unvan", "tip": "text", "bos": True, "aciklama": "Ünvan"}
    assert "permission denied" not in str(a).lower()
    liste = client.get("/api/v1/tampon/pg").json()["data"]
    assert [x["id"] for x in liste] == ["pg_onent", "pg_onedesk"] and liste[0]["katalog"]["ozet"]["nesne"] == 2 and liste[1]["state"] == "disabled"
    assert "gizli-parola-1" not in str(liste)
    assert client.get("/api/v1/tampon/pg/yok/katalog").status_code == 404


def test_tarama_hatasi_failed_yazilir_yenile_hazir_degilse_409(client, pg_ayar, monkeypatch):
    def kirik():
        raise OSError("connection to server at pg.ornek.test failed: password authentication failed for user okuyucu")

    with Session(engine()) as db:
        with pytest.raises(postgres.PgHata) as h:
            postgres.tara(db, "pg_onent", "admin", baglanti=kirik)
        assert "pg.ornek.test" not in h.value.mesaj and "okuyucu" not in h.value.mesaj  # adres / kullanici maskeli
        assert postgres.agac(db, "pg_onent")["son"]["durum"] == "failed"
    hdr = login_ok(client)
    assert client.post("/api/v1/tampon/pg/pg_onedesk/katalog/yenile", headers=hdr).status_code == 409  # kapali kaynak
    basladi = []
    monkeypatch.setattr("app.tampon.katalog._ayri_baslat", lambda komut, *a: basladi.append(komut))
    r = client.post("/api/v1/tampon/pg/pg_onent/katalog/yenile", headers=hdr).json()["data"]
    assert r["basladi"] is True and basladi[0][-4:] == ["--kaynak", "pg_onent", "--kullanici", "admin"]


def test_kurum_baglantilari_postgres_karti(client, pg_ayar):
    login_ok(client)
    b = client.get("/api/v1/yonetim/kurum").json()["data"]["baglantilar"]
    pg = {x["id"]: x for x in b if x["tur"] == "postgres"}
    assert set(pg) == {"pg_onent", "pg_onedesk"} and pg["pg_onent"]["state"] == "ready" and pg["pg_onent"]["bilgiler"]["veritabani"] == "ONENT"
    assert "oracle_onent" not in {x["id"] for x in b}  # ONENTDB artik PostgreSQL
    assert "gizli-parola-1" not in str(b)


# --- eski veri hatti (<ON EK>_IMPORT_QUERY -> tampon partisi) 2026-11-21 kaldirildi (763662d): veriyi isciler dogrudan ceker -------
def test_pg_kaynak_satiri_parola_vermez_iceri_alma_yolu_yok(client, pg_ayar, monkeypatch):
    from app import isci

    monkeypatch.setenv(f"{ON}_IMPORT_QUERY", "SELECT 1 AS bir")  # eski anahtar artik okunmaz
    hdr = login_ok(client)
    k = {x["anahtar"]: x for x in client.get("/api/v1/tampon/kaynaklar").json()["data"]}
    assert k["pg_onent"]["tur"] == "postgres" and k["pg_onent"]["hazir"] and k["pg_onent"]["yapilandirma"] == "tamam"
    assert "panel PostgreSQL'e bağlanmaz" in k["pg_onent"]["neden"] and "sorgu_anahtari" not in k["pg_onent"]
    assert k["pg_onedesk"]["yapilandirma"] == "kapalı" and k["pg_onedesk"]["hazir"] is False
    assert "pg_onent_import" not in k and "pg_onedesk_import" not in k
    a = client.get("/api/v1/tampon/akislar").json()["data"]["akislar"]
    assert "gizli-parola-1" not in str(k) + str(a) and "pg.ornek.test" not in str(a)
    assert client.post("/api/v1/tampon/pg/pg_onent/cek", headers=hdr).status_code in (404, 405)  # elle cekim ucu yok
    with pytest.raises(SystemExit):
        isci.main(["pg-cek", "--kaynak", "pg_onent"])  # isci komutu yok
