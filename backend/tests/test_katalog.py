"""Ham katalog (tampon/katalog): agac kurali (es ad -> hedef + onekli es, gorunum -> dayandigi, bolum), ornek ve profil, kisisel
nesnede satir okunmamasi, panel okumasi ve 'Yenile'nin ayri surec baslatmasi. Oracle'a baglanilmaz: sahte imlec sorguya gore cevaplar."""

from __future__ import annotations

import re
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.tampon import katalog
from app.tampon.models import SourceCatalog, SourceCatalogObject
from tests.conftest import login_ok

SUTUN = ("TABLE_NAME", "COLUMN_ID", "COLUMN_NAME", "DATA_TYPE", "DATA_LENGTH", "DATA_PRECISION", "DATA_SCALE", "NULLABLE")


class SahteImlec:
    def __init__(self):
        self.sorgular: list[str] = []
        self.description: list[tuple] = []
        self._satirlar: list[tuple] = []
        self.arama_binds: list[dict] = []
        self.son_binds: dict = {}

    def _cevap(self, sql: str):
        if "USER_TAB_PRIVS_RECD" in sql:
            return ("OWNER", "TABLE_NAME"), [
                ("TEMIP", "ALARM_S1"),
                ("TEMIP", "ALARM_S2"),
                ("TEMIP", "GECMIS"),
                ("TEMIP", "LOG"),
                ("BASKA", "X"),
            ]
        if "FROM ALL_OBJECTS" in sql:
            return ("OBJECT_NAME", "OBJECT_TYPE"), [("ALARM_S1", "TABLE"), ("ALARM_S2", "TABLE"), ("GECMIS", "TABLE"), ("LOG", "TABLE"),
                                                    ("OZET_V", "VIEW")]  # fmt: skip
        if "FROM ALL_SYNONYMS" in sql:
            return ("OWNER", "SYNONYM_NAME", "TABLE_OWNER", "TABLE_NAME"), [("TEMIP", "ALARM", "TEMIP", "ALARM_S1")]
        if "FROM ALL_TAB_COLUMNS" in sql:
            satir = []
            for t in ("ALARM_S1", "ALARM_S2"):
                satir += [(t, 1, "NO", "VARCHAR2", 20, None, None, "Y"), (t, 2, "ZAMAN", "DATE", 7, None, None, "N"),
                          (t, 3, "NETWORK", "VARCHAR2", 40, None, None, "Y")]  # fmt: skip
            satir += [("GECMIS", 1, "EVENTTIME", "DATE", 7, None, None, "N"), ("GECMIS", 2, "ADET", "NUMBER", 22, 10, 0, "Y"),
                      ("LOG", 1, "AD", "VARCHAR2", 50, None, None, "Y"), ("OZET_V", 1, "NO", "VARCHAR2", 20, None, None, "Y")]  # fmt: skip
            return SUTUN, satir
        if "FROM ALL_COL_COMMENTS" in sql:
            return ("TABLE_NAME", "COLUMN_NAME", "COMMENTS"), [("GECMIS", "ADET", "olay sayisi")]
        if "FROM ALL_TAB_COMMENTS" in sql:
            return ("TABLE_NAME", "COMMENTS"), [("GECMIS", "Kapanan alarmlar")]
        if "FROM ALL_TABLES" in sql:
            return ("TABLE_NAME", "NUM_ROWS", "LA", "PARTITIONED"), [
                ("ALARM_S1", 3, "2026-10-17", "NO"),
                ("GECMIS", 2_086_341_100, "2026-03-01", "YES"),
            ]
        if "FROM ALL_PART_KEY_COLUMNS" in sql:
            return ("NAME", "COLUMN_NAME"), [("GECMIS", "EVENTTIME")]
        if "FROM ALL_TAB_PARTITIONS" in sql:
            return ("TABLE_NAME", "PARTITION_NAME", "PARTITION_POSITION", "NUM_ROWS", "LA", "ADET", "RN"), [
                ("GECMIS", f"P{i}", 20 - i, 10, "", 20, i) for i in range(1, 21)]  # fmt: skip
        if "FROM ALL_IND_COLUMNS" in sql:
            return ("TABLE_NAME", "INDEX_NAME", "COLUMN_NAME"), [("GECMIS", "GECMIS_NDX1", "EVENTTIME")]
        if "FROM ALL_DEPENDENCIES" in sql:
            return ("NAME", "REFERENCED_OWNER", "REFERENCED_NAME"), [("OZET_V", "TEMIP", "GECMIS")]
        if '"__D"' in sql:  # aralik cekimi: baslangictan bugune domain + arama metni iceren satirlar
            self.arama_binds.append(self.son_binds)
            if '"OZET_V"' in sql:
                return ("__D", "NO"), [("(domain sütunu yok)", "nw_li_cust_v")]
            return ("__D", "NO", "ZAMAN", "NETWORK"), [("NOC DESTECH", "nw_li_cust_ornek_1", datetime(2026, 10, 18), "NOC DESTECH")]  # noqa: DTZ001
        if " AS D, COUNT(*) AS N" in sql:  # arama toplamasi: domain basina satir + metin sutunu basina isabet
            h = len(re.findall(r'"H\d+"', sql))
            if "REPLACE(" in sql:
                return ("D", "N", "HERHANGI", *[f"H{i}" for i in range(h)]), [
                    ("NOC DESTECH", 10, 4, 4, *[0] * (h - 1)),
                    ("ACCESS", 5, 0, *[0] * h),
                ]
            return ("D", "N", "HERHANGI", *[f"H{i}" for i in range(h)]), [("(domain sütunu yok)", 3, 0, *[0] * h)]
        if sql.startswith("SELECT * FROM") and "INSTR(LOWER(" in sql:  # domain + arama filtreli ornek
            self.arama_binds.append(self.son_binds)
            return ("NO", "ZAMAN", "NETWORK"), [("nw_li_cust_ornek_1", datetime(2026, 10, 18), "NOC DESTECH")]  # noqa: DTZ001
        if sql.startswith("SELECT * FROM"):
            if '"GECMIS" WHERE "EVENTTIME" >= SYSDATE' in sql:
                return ("EVENTTIME", "ADET"), [(datetime(2026, 10, 18, 10, 0), 5), (datetime(2026, 10, 18, 10, 5), None)]  # noqa: DTZ001 - Oracle DATE dilimsiz gelir
            if '"OZET_V"' in sql:
                return ("NO",), []
            return ("NO", "ZAMAN"), [
                ("10000001", datetime(2026, 10, 18)),  # noqa: DTZ001 - Oracle DATE dilimsiz gelir
                ("10000001", datetime(2026, 10, 18)),  # noqa: DTZ001 - Oracle DATE dilimsiz gelir
                (None, datetime(2026, 10, 18)),  # noqa: DTZ001 - Oracle DATE dilimsiz gelir
            ]
        raise AssertionError(f"beklenmeyen sorgu: {sql[:80]}")

    def execute(self, sql, binds=None):
        self.sorgular.append(sql)
        self.son_binds = dict(binds or {})
        basliklar, self._satirlar = self._cevap(sql)
        self.description = [(b,) for b in basliklar]

    def fetchall(self):
        satirlar, self._satirlar = list(self._satirlar), []
        return satirlar

    def fetchmany(self, n):
        parca, self._satirlar = list(self._satirlar[:n]), list(self._satirlar[n:])
        return parca


@pytest.fixture
def sahte(monkeypatch, tmp_path):
    imlec = SahteImlec()
    monkeypatch.setattr(katalog, "HAM_DIZIN", tmp_path / "ham")

    def _tara(a, semalar, adet, p=None, yazici=None, nabiz=None):
        izin = katalog._sorgu(imlec, "SELECT OWNER, TABLE_NAME FROM USER_TAB_PRIVS_RECD")
        sahipler = sorted({r["owner"] for r in izin} & ({s.upper() for s in semalar} if semalar else {"TEMIP"}))
        return [n for s in sahipler for n in katalog._sema(imlec, s, adet, p, yazici, nabiz)]

    monkeypatch.setattr(katalog, "_tara", _tara)
    return imlec


def _tara(kullanici="admin"):
    with Session(engine()) as db:
        return katalog.tara(db, kullanici).id


def test_agac_es_ad_hedef_ve_onekli_es_gorunum_bagimlisi_bolumler(client, sahte):
    _tara()
    with Session(engine()) as db:
        a = katalog.agac(db)
    assert a["katalog"]["durum"] == "ready" and a["katalog"]["ozet"]["nesne"] == 6 and not a["calisiyor"]
    [sema] = a["semalar"]
    ust = {d["ad"]: d for d in sema["nesneler"]}
    assert list(ust) == ["ALARM", "OZET_V", "LOG"]  # es ad > gorunum > tablo; alt nesneler ana listede yok
    assert [c["ad"] for c in ust["ALARM"]["alt"]] == ["ALARM_S1", "ALARM_S2"] and ust["ALARM"]["es_ad"] == "TEMIP.ALARM_S1"
    assert [c["ad"] for c in ust["OZET_V"]["alt"]] == ["GECMIS"]
    gecmis = ust["OZET_V"]["alt"][0]
    assert (gecmis["satir"], gecmis["bolum_sayisi"], gecmis["bolum_anahtari"], gecmis["aciklama"]) == (
        2_086_341_100,
        20,
        ["EVENTTIME"],
        "Kapanan alarmlar",
    )
    assert ust["ALARM"]["sutun_sayisi"] == 3  # es adin sutunlari hedefinden


def test_ornek_bolum_budamali_profil_ve_kisisel_nesne_okunmaz(client, sahte):
    _tara()
    assert not any('"LOG"' in s for s in sahte.sorgular if s.startswith("SELECT * FROM"))  # kisisel: satir okunmaz
    assert any('"OZET_V" WHERE ROWNUM' in s for s in sahte.sorgular)
    with Session(engine()) as db:
        n = {o.name: o for o in db.scalars(select(SourceCatalogObject))}
        g = katalog.nesne(db, n["GECMIS"].id)
        assert g["ornek_notu"] == "2 satır · son 1 saat (EVENTTIME)"
        assert g["ayrinti"]["bolumler"]["adet"] == 20 and len(g["ayrinti"]["bolumler"]["son"]) == katalog.BOLUM_ADEDI
        assert g["ayrinti"]["indeksler"] == {"GECMIS_NDX1": ["EVENTTIME"]}
        adet = next(s for s in g["sutunlar"] if s["ad"] == "ADET")
        assert (adet["tip"], adet["aciklama"], adet["doluluk"], adet["farkli"]) == ("NUMBER(10,0)", "olay sayisi", 50.0, 1)
        s1 = katalog.nesne(db, n["ALARM_S1"].id)
        no = next(s for s in s1["sutunlar"] if s["ad"] == "NO")
        assert no["doluluk"] == 66.7 and no["ornekler"] == [{"deger": "10000001", "adet": 2}]
        assert katalog.ornek(db, n["GECMIS"].id)["satirlar"] == [["2026-10-18 10:00:00", 5], ["2026-10-18 10:05:00", None]]
        log = katalog.nesne(db, n["LOG"].id)
        assert log["ornek_satir"] == 0 and log["ornek_notu"].startswith("Kişisel veri") and katalog.ornek(db, n["LOG"].id)["satirlar"] == []
        assert katalog.ornek(db, n["OZET_V"].id)["not"] == "0 satır · ilk satırlar (sırasız)"


def test_eski_kataloglar_budanir_hata_failed_yazar(client, sahte, monkeypatch):
    for _ in range(katalog.SAKLANAN + 2):
        _tara()
    monkeypatch.setenv("ORACLE_REPORTDB_PASSWORD", "GizliParola9")
    monkeypatch.setattr(katalog, "_tara", lambda *a: (_ for _ in ()).throw(RuntimeError("ORA-01017: GizliParola9 reddedildi")))
    with pytest.raises(RuntimeError):
        _tara()
    with Session(engine()) as db:
        kataloglar = db.scalars(select(SourceCatalog).order_by(SourceCatalog.id)).all()
        assert len([k for k in kataloglar if k.status == "ready"]) == katalog.SAKLANAN
        assert (
            kataloglar[-1].status == "failed"
            and "GizliParola9" not in kataloglar[-1].error
            and kataloglar[-1].error.startswith("ORA-01017")
        )
        canli = {k.id for k in kataloglar}
        assert {o.catalog_id for o in db.scalars(select(SourceCatalogObject))} <= canli
        a = katalog.agac(db)
        assert a["katalog"]["id"] == kataloglar[-2].id and a["son_hata"]  # son hazir katalog gorunur, hata ayrica


def test_uclar_yalniz_admin_ve_yenile_ayri_surec(client, sahte, monkeypatch):
    for yol in ("/api/v1/tampon/katalog", "/api/v1/tampon/katalog/nesne/1", "/api/v1/tampon/katalog/nesne/1/ornek"):
        assert client.get(yol).status_code == 401
    hdr = login_ok(client)
    assert client.get("/api/v1/tampon/katalog").json()["data"]["katalog"] is None
    monkeypatch.setenv("ORACLE_REPORTDB_ENABLED", "false")
    assert client.post("/api/v1/tampon/katalog/yenile", headers=hdr).status_code == 409
    monkeypatch.setenv("ORACLE_REPORTDB_ENABLED", "true")
    baslatilan = []
    monkeypatch.setattr(katalog, "_ayri_baslat", lambda komut, dizin, gunluk: baslatilan.append(komut))
    r = client.post("/api/v1/tampon/katalog/yenile", headers=hdr).json()["data"]
    assert r == {"basladi": True, "calisiyor": True} and baslatilan[0][1:5] == ["-m", "app.isci", "reportdb-katalog", "--kullanici"]
    with Session(engine()) as db:
        db.add(
            SourceCatalog(
                source_key=katalog.KAYNAK, status="receiving", started_at=katalog.simdi(), created_by="admin", summary={}, error=""
            )
        )
        db.commit()
    assert client.post("/api/v1/tampon/katalog/yenile", headers=hdr).json()["data"] == {"basladi": False, "calisiyor": True}
    assert len(baslatilan) == 1 and client.get("/api/v1/tampon/katalog").json()["data"]["calisiyor"] is True
    _tara()
    a = client.get("/api/v1/tampon/katalog").json()["data"]
    nid = a["semalar"][0]["nesneler"][0]["id"]
    assert client.get(f"/api/v1/tampon/katalog/nesne/{nid}").json()["data"]["ad"] == "ALARM"
    assert client.get("/api/v1/tampon/katalog/nesne/99999").status_code == 404


def test_parametre_agaci_domain_tablo_isabetli_sutun_ve_filtreli_ornek(client, sahte):
    _tara()
    agg = [q for q in sahte.sorgular if " AS D, COUNT(*) AS N" in q]
    assert (
        agg
        and any("INSTR(LOWER(" in q for q in agg)
        and "0 AS HERHANGI" in next(q for q in agg if "GECMIS" in q)
        and any('REPLACE("NETWORK"' in q and "IN (:d0)" in q for q in agg)
    )
    assert not any('"ALARM" ' in q or '"ALARM")' in q for q in agg)  # es ad ayrica taranmaz (hedefi taranir)
    aralik = [q for q in sahte.sorgular if '"__D"' in q]
    assert aralik and all("INSTR(LOWER(t." in q for q in aralik) and not any("GECMIS" in q for q in aralik)  # metin sutunu yok: atlanir
    assert all(b["ara"] == "nw_li_cust" for b in sahte.arama_binds) and any(b.get("d0") == "NOC DESTECH" for b in sahte.arama_binds)
    with Session(engine()) as db:
        a = katalog.agac(db)
        assert a["parametreler"]["ara"] == "nw_li_cust" and a["parametreler"]["degerler"] == ["NOC DESTECH"]  # 2026-10-19: ACCESS kaldirildi
        dallar = {d["domain"]: d for d in a["parametre_agaci"]}
        assert list(dallar) == ["NOC DESTECH"]  # yoklamada isabetsiz, bilinen CI sutunu olmayan gorunum aralikta atlanir
        noc = dallar["NOC DESTECH"]
        assert [(t["ad"], t["ust"], t["isabet"], t["pencere"]) for t in noc["tablolar"]] == [
            ("ALARM_S1", "ALARM", 1, "tüm tablo (tarih sütunu yok)"),
            ("ALARM_S2", "ALARM", 1, "tüm tablo (tarih sütunu yok)"),
        ]
        assert noc["tablolar"][0]["sutunlar"][0]["ad"] == "NO" and noc["tablolar"][0]["sutunlar"][0]["isabet"] == 1
        assert "TEMIP.GECMIS" in a["parametreler"]["eslesmeyen"] or all(t["ad"] != "GECMIS" for t in noc["tablolar"])
        s1 = noc["tablolar"][0]["id"]
        v = katalog.veri(db, s1, ["NOC DESTECH"])  # ham dosyadan (SQL)
        assert v["satirlar"] == [["nw_li_cust_ornek_1", "2026-10-18", "NOC DESTECH"]] and v["sutunlar"] == ["NO", "ZAMAN", "NETWORK"]
        assert katalog.veri(db, s1, ["ACCESS"])["toplam"] == 0
        assert a["katalog"]["ozet"]["ham_satir"] == 2 and not any("OZET_V" in q for q in aralik)
        assert katalog.nesne(db, s1)["ayrinti"]["arama"]["ornek_degerler"]["NO"] == [{"deger": "nw_li_cust_ornek_1", "adet": 1}]


def test_parametre_temizle():
    p = katalog.parametre_temizle({"ara": " NW_LI_ ", "degerler": ["noc_destech", "access"], "saat": 999})
    assert (p["ara"], p["degerler"], p["saat"], p["alan"]) == ("nw_li_", ["NOC DESTECH", "ACCESS"], 48, "NETWORK")
    with pytest.raises(katalog.KatalogHata):
        katalog.parametre_temizle({"alan": "NETWORK; DROP"})


def _ham_nesne() -> int:
    """NOC DESTECH 3 + ACCESS 1 ham satir; BOS sutunu hep bos (gizlenir), NODE1 isabetli (basta)."""
    gruplar = {
        "NOC DESTECH": [[3, "NOC DESTECH", None, "nw_li_cust_b"], [1, "NOC DESTECH", None, "nw_li_cust_a"], [2, "NOC DESTECH", None, None]],
        "ACCESS": [[4, "ACCESS", None, "nw_li_cust_a"]],
    }
    with Session(engine()) as db:
        k = SourceCatalog(source_key=katalog.KAYNAK, status="ready", started_at=katalog.simdi(), created_by="t", summary={}, error="")
        db.add(k)
        db.flush()
        n = SourceCatalogObject(
            catalog_id=k.id, owner="TEMIP", name="ALARM_S1", kind="TABLE", parent="", comment="", analyzed="", columns=[],
            details={"arama": {"ara": "nw_li_", "pencere": "tüm tablo", "gruplar": {"NOC DESTECH": {"satir": 3, "isabet": 2, "sutunlar": {"NODE1": 2}}}}},
            sample_columns=["IDENTIFIER", "NETWORK", "BOS", "NODE1"], sample_rows=0, sample_note="",
            sample_data=katalog._sikistir({"genel": [], "gruplar": gruplar}),
        )  # fmt: skip
        db.add(n)
        db.commit()
        return n.id


def test_ham_veri_okuyucu_excel_filtresi_siralama_bos_sutun_ve_deger_listesi(client):
    nid = _ham_nesne()
    hdr = login_ok(client)
    url = f"/api/v1/tampon/katalog/veri?nesne={nid}"
    r = client.get(f"{url}&domain=NOC%20DESTECH", headers=hdr).json()["data"]
    assert r["sutunlar"] == ["NODE1", "IDENTIFIER", "NETWORK"] and r["gizlenen_bos"] == 1  # isabetli basta, bos sutun yok
    assert (r["toplam_ham"], r["toplam"], r["pencere"], r["ara"]) == (3, 3, "tüm tablo", "nw_li_")
    r = client.get(f"{url}&domain=NOC%20DESTECH&domain=ACCESS&sirala=IDENTIFIER&yon=desc").json()["data"]
    assert [s[1] for s in r["satirlar"]] == [4, 3, 2, 1]
    filtre = '{"NODE1": ["nw_li_cust_a", "(Boş)"]}'
    r = client.get(url, params={"nesne": nid, "domain": ["NOC DESTECH", "ACCESS"], "filtre": filtre, "sirala": "IDENTIFIER"}).json()["data"]
    assert [s[1] for s in r["satirlar"]] == [1, 2, 4] and r["filtreli"] == ["NODE1"]
    r = client.get(url, params={"nesne": nid, "domain": ["NOC DESTECH"], "q": "CUST_B"}).json()["data"]
    assert r["toplam"] == 1 and r["satirlar"][0][0] == "nw_li_cust_b"
    assert client.get(url, params={"nesne": nid, "adet": 2, "sayfa": 9, "domain": ["NOC DESTECH"]}).json()["data"]["sayfa"] == 2
    d = client.get("/api/v1/tampon/katalog/veri/degerler", params={"nesne": nid, "sutun": "NODE1", "domain": ["NOC DESTECH", "ACCESS"],
                   "filtre": filtre}).json()["data"]  # fmt: skip
    assert d["degerler"] == [{"deger": "nw_li_cust_a", "adet": 2}, {"deger": "nw_li_cust_b", "adet": 1}, {"deger": "(Boş)", "adet": 1}]
    d = client.get(
        "/api/v1/tampon/katalog/veri/degerler", params={"nesne": nid, "sutun": "IDENTIFIER", "filtre": filtre, "ara": "4"}
    ).json()["data"]
    assert d["degerler"] == [{"deger": "4", "adet": 1}]  # domain secilmezse hepsi; NODE1 filtresi uygulanmis
    assert client.get(url, params={"nesne": nid, "filtre": "{bozuk"}).status_code == 400
    assert client.get(f"/api/v1/tampon/katalog/veri/degerler?nesne={nid}&sutun=YOK").status_code == 404
    client.post("/api/v1/session/logout", headers=hdr)
    assert client.get(url).status_code == 401


def test_ham_dosya_sql_okuyucu_filtre_siralama_arama_ve_degerler(client, monkeypatch, tmp_path):
    """Ham dosya yolu (01.01'den bugune tarama): ayni Excel filtresi kurallari SQLite uzerinde."""
    monkeypatch.setattr(katalog, "HAM_DIZIN", tmp_path)
    with Session(engine()) as db:
        k = SourceCatalog(source_key=katalog.KAYNAK, status="ready", started_at=katalog.simdi(), created_by="t", summary={}, error="")
        db.add(k)
        db.flush()
        y = katalog.HamYazici(k.id)
        tablo = y.tablo_adi("TEMIP", "ALARM_S1")
        y.olustur(tablo, ["IDENTIFIER", "NETWORK", "BOS", "NODE1"])
        y.yaz(tablo, [["NOC DESTECH", 3, "NOC DESTECH", None, "nw_li_cust_b"], ["NOC DESTECH", 1, "NOC DESTECH", None, "nw_li_cust_a"],
                      ["NOC DESTECH", 2, "NOC DESTECH", None, None], ["ACCESS", 4, "ACCESS", None, "nw_li_cust_a"]])  # fmt: skip
        y.indeksle(tablo, ["NODE1"])
        y.kapat()
        arama = {"ara": "nw_li_cust", "pencere": "01.01.2026 00:00 → bugün (EVENTTIME)", "ham_tablo": tablo, "dolu_sutunlar": ["IDENTIFIER", "NETWORK", "NODE1"],
                 "gruplar": {"NOC DESTECH": {"satir": None, "isabet": 2, "sutunlar": {"NODE1": 2}}}}  # fmt: skip
        n = SourceCatalogObject(catalog_id=k.id, owner="TEMIP", name="ALARM_S1", kind="TABLE", parent="", comment="", analyzed="", columns=[],
                                details={"arama": arama}, sample_columns=["IDENTIFIER", "NETWORK", "BOS", "NODE1"], sample_rows=0, sample_note="")  # fmt: skip
        db.add(n)
        db.commit()
        nid = n.id
        v = katalog.veri(db, nid, ["NOC DESTECH"])
        assert v["sutunlar"] == ["NODE1", "IDENTIFIER", "NETWORK"] and v["gizlenen_bos"] == 1 and (v["toplam_ham"], v["toplam"]) == (3, 3)
        v = katalog.veri(db, nid, ["NOC DESTECH", "ACCESS"], sirala="IDENTIFIER", yon="desc")
        assert [s[1] for s in v["satirlar"]] == [4, 3, 2, 1]
        filtre = '{"NODE1": ["nw_li_cust_a", "(Boş)"]}'
        v = katalog.veri(db, nid, ["NOC DESTECH", "ACCESS"], filtre=filtre, sirala="IDENTIFIER")
        assert [s[1] for s in v["satirlar"]] == [1, 2, 4] and v["filtreli"] == ["NODE1"] and v["toplam_ham"] == 4
        assert katalog.veri(db, nid, ["NOC DESTECH"], q="CUST_B")["toplam"] == 1  # LIKE: buyuk/kucuk harf farksiz, _ kacisli
        assert katalog.veri(db, nid, ["NOC DESTECH"], q="%")["toplam"] == 0
        assert katalog.veri(db, nid, ["NOC DESTECH"], adet=2, sayfa=9)["sayfa"] == 2
        d = katalog.degerler(db, nid, ["NOC DESTECH", "ACCESS"], "NODE1", filtre=filtre)
        assert d["degerler"] == [{"deger": "nw_li_cust_a", "adet": 2}, {"deger": "nw_li_cust_b", "adet": 1}, {"deger": "(Boş)", "adet": 1}]
        assert katalog.degerler(db, nid, [], "IDENTIFIER", filtre=filtre, ara="4")["degerler"] == [{"deger": "4", "adet": 1}]
        with pytest.raises(katalog.KatalogHata):
            katalog.degerler(db, nid, [], "BOS")  # gizlenen bos sutun
        (tmp_path / f"katalog_{k.id}.db").unlink()
        with pytest.raises(katalog.KatalogHata) as h:
            katalog.veri(db, nid, ["NOC DESTECH"])
        assert h.value.kod == 410


def test_baslangic_ve_ay_dilimleri():
    assert katalog.parametre_temizle({})["baslangic"] == "2026-01-01 00:00"
    assert katalog.parametre_temizle({"baslangic": "2026-03-15"})["baslangic"] == "2026-03-15 00:00"
    with pytest.raises(katalog.KatalogHata):
        katalog.parametre_temizle({"baslangic": "15.03.2026"})
    d = katalog._ay_dilimleri("2026-01-01 00:00")
    assert d[0] == ("2026-01-01 00:00", "2026-02-01 00:00") and d[-1][1] == "" and len(d) >= 10
