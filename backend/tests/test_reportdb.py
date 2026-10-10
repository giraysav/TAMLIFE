"""Oracle kaynak katmani, ReportDB alarm senkronu ve veri iscisi (uretim test_reportdb_tampon.py uyarlamasi).

oracledb hic yuklenmez: oracle._oracledb sahte modulle degistirilir; gercek Oracle'a baglanilmaz. Veri uydurmadir (ORNEK-*).
"""

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import isci
from app.db import engine
from app.models import Customer, IngestBatch, OnedeskRecord
from app.onedesk import ice_al
from app.ortak import simdi
from app.tampon import dagitim, depo, oracle, reportdb
from app.tampon.models import DistributionLog, DistributionRule
from app.yonetim.models import FaultEvent
from tests.conftest import login_ok

BASLIK = ["Musteri No", "Musteri Unvani", "Aktif Alarm", "Biletli Aktif Alarm", "Kapanan Alarm", "Biletli Kapanan Alarm",
          "En Eski Alarm", "Son Kapanis", "Veri Zamani"]  # fmt: skip
GIZLI = {"HOST": "ornek-host.invalid", "SERVICE_NAME": "ORNEKSRV", "USER": "ornek_kullanici", "PASSWORD": "ornek-parola-123"}


def satir(no, unvan, aktif=0, kapanan=0, b_aktif=0, b_kapanan=0):
    return [no, unvan, aktif, b_aktif, kapanan, b_kapanan, "2026-05-14 15:00:00", "2026-10-06 12:00:00", "2026-10-06 12:30:00"]


# --- sahte oracledb -------------------------------------------------------------------------------------------------
class _Imlec:
    def __init__(self, s):
        self.s, self.arraysize, self.description, self._kalan = s, 100, None, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, binds=None):
        self.s.sorgular.append((sql, dict(binds or {})))
        self.description = [(c,) for c in self.s.sutunlar]
        self._kalan = list(self.s.satirlar)

    def fetchone(self):
        return (1,)

    def fetchmany(self, n):
        parca, self._kalan = self._kalan[:n], self._kalan[n:]
        return parca


class _Baglanti:
    def __init__(self, s):
        self.s, self.call_timeout, self.outputtypehandler = s, None, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        self.s.zaman_asimi.append(self.call_timeout)
        return _Imlec(self.s)


class SahteOracle(SimpleNamespace):
    def __init__(self):
        super().__init__(DB_TYPE_CLOB=object(), DB_TYPE_NCLOB=object(), DB_TYPE_BLOB=object(), DB_TYPE_LONG=object(),
                         DB_TYPE_LONG_RAW=object(), baglantilar=[], sorgular=[], zaman_asimi=[], istemci=[],
                         sutunlar=["X"], satirlar=[], hata=None)  # fmt: skip

    def connect(self, **kw):
        self.baglantilar.append(kw)
        if self.hata:
            raise self.hata
        return _Baglanti(self)

    def init_oracle_client(self, **kw):
        self.istemci.append(kw)
        if self.hata:
            raise self.hata


@pytest.fixture
def sahte(monkeypatch):
    s = SahteOracle()
    monkeypatch.setattr(oracle, "_oracledb", lambda: s)
    monkeypatch.delenv("ORACLE_CLIENT_DIR", raising=False)
    return s


@pytest.fixture
def acik(monkeypatch):
    """ORACLE_REPORTDB acik + zorunlu anahtarlar (uydurma degerler)."""
    monkeypatch.setenv("ORACLE_REPORTDB_ENABLED", "true")
    for ad, deger in GIZLI.items():
        monkeypatch.setenv(f"ORACLE_REPORTDB_{ad}", deger)


@pytest.fixture
def kapali(monkeypatch):
    for ad in ("ENABLED", *GIZLI):
        monkeypatch.delenv(f"ORACLE_REPORTDB_{ad}", raising=False)


def kart(ad, no=None, alarm=0, kapanan=0):
    with Session(engine()) as db:
        c = Customer(external_key=f"ORNEK-{ad}", name=ad, customer_no=no, alarm_count=alarm, alarm_closed_count=kapanan)
        db.add(c)
        db.commit()
        return c.id


def sayilar(cid):
    with Session(engine()) as db:
        c = db.get(Customer, cid)
        return c.alarm_count, c.alarm_closed_count


def doldur(*satirlar):
    with Session(engine()) as db:
        p = reportdb.tampona_yaz(db, BASLIK, list(satirlar), 1.5)
        return p.id, p.status


def uygula():
    with Session(engine()) as db:
        son = db.scalar(select(func.max(IngestBatch.id)).where(IngestBatch.source_key == reportdb.KAYNAK, IngestBatch.status == "ready"))
        return reportdb.kartlara_uygula(db, son)


def kurallari_ac(etkin=True):
    with Session(engine()) as db:
        for k in reportdb.kurallari_hazirla(db):
            k.enabled = etkin
        db.commit()


# --- Oracle katmani -------------------------------------------------------------------------------------------------
def test_oracledb_yalniz_baglanirken_yuklenir():
    kod = "import sys, app.main, app.isci, app.tampon.reportdb; print('oracledb' in sys.modules)"
    p = subprocess.run([sys.executable, "-c", kod], cwd=str(oracle.BACKEND), capture_output=True, text=True, check=False)
    assert p.stdout.strip() == "False", p.stderr


def test_sorgu_temizle_yalniz_tek_select():
    assert oracle.sorgu_temizle("  select 1 from dual ; ") == "select 1 from dual"
    assert oracle.sorgu_temizle("WITH a AS (SELECT 1 x FROM dual) SELECT x FROM a").startswith("WITH")
    for kotu in ("", None, "DELETE FROM t", "SELECT 1 FROM dual; DROP TABLE t", "selectx", "x" * 20_001):
        with pytest.raises(oracle.OracleHata):
            oracle.sorgu_temizle(kotu)


def test_hata_metni_sir_tasimaz_ve_ipucu_verir():
    gizli = ("ornek-parola-123", "ornek-host.invalid", "ORNEKSRV", "ornek_kullanici")
    hata = Exception("ORA-12514: Service ORNEKSRV is not registered with the listener at host 10.1.2.3 port 1521 password=xyz\nikinci satir")
    mesaj, ipucu = oracle.hata_metni(hata, gizli)
    assert "ORA-12514" in mesaj and "ikinci" not in mesaj and ipucu == "Servis adı (SERVICE_NAME) bulunamadı."
    for iz in ("ORNEKSRV", "10.1.2.3", "xyz"):
        assert iz not in mesaj
    mesaj, _ = oracle.hata_metni(Exception("DPY-6005: (DESCRIPTION=(ADDRESS=(HOST=ornek-host.invalid)(PORT=1521))) user ornek_kullanici"), gizli)
    assert "ornek-host" not in mesaj and "ornek_kullanici" not in mesaj
    assert oracle.hata_metni(Exception("DPY-3015: password verifier type 0x939"))[1].startswith("Hesabın parola kaydı")
    assert oracle.hata_metni(RuntimeError())[0] == "RuntimeError"


def test_deger_json_uyumlu():
    assert oracle.deger(Decimal(12)) == 12 and isinstance(oracle.deger(Decimal(12)), int)
    assert oracle.deger(Decimal("12.5")) == 12.5
    assert oracle.deger(datetime(2026, 10, 1, 9, 30)) == "2026-10-01 09:30:00"  # noqa: DTZ001 - Oracle saat dilimsiz dondurur
    assert oracle.deger(datetime(2026, 10, 1)) == "2026-10-01"  # noqa: DTZ001
    assert (oracle.deger(b"\x01\xff"), oracle.deger("  a "), oracle.deger("  "), oracle.deger(None)) == ("01ff", "a", None, None)


def test_kapali_kaynak_baglanmaz(sahte, kapali, monkeypatch):
    assert oracle.baglanti_testi("oracle_reportdb", senkron=True)["mesaj"].startswith("Kaynak kapalı")
    monkeypatch.setenv("ORACLE_REPORTDB_ENABLED", "false")  # dolu ama 'true' degil: kapali (eski kodda acik sayiliyordu)
    for ad, deger in GIZLI.items():
        monkeypatch.setenv(f"ORACLE_REPORTDB_{ad}", deger)
    assert oracle.baglanti_testi("oracle_reportdb")["ok"] is False
    with pytest.raises(oracle.OracleHata) as h:
        next(oracle.ayar("oracle_reportdb").akis("SELECT 1 FROM dual", 5))
    assert h.value.kod == 409 and sahte.baglantilar == []
    with pytest.raises(oracle.OracleHata):
        oracle.ayar("yok")


def test_eksik_anahtar_adlari_ve_port_varsayilan(sahte, acik, monkeypatch):
    monkeypatch.delenv("ORACLE_REPORTDB_PORT", raising=False)
    assert oracle.ayar("oracle_reportdb").PORT == 1521
    assert oracle.durum("oracle_reportdb")["hazir"] is True
    monkeypatch.delenv("ORACLE_REPORTDB_USER")
    sonuc = oracle.baglanti_testi("oracle_reportdb", senkron=True)
    assert sonuc["mesaj"] == "Bağlantı ayarı eksik: ORACLE_REPORTDB_USER" and sahte.baglantilar == []


def test_baglanti_testi_ayni_surecte(sahte, acik, monkeypatch):
    monkeypatch.setenv("ORACLE_REPORTDB_TIMEOUT", "7")
    assert oracle.baglanti_testi("oracle_reportdb", senkron=True) == {"ok": True, "mesaj": "SELECT 1 FROM DUAL → 1", "ipucu": ""}
    kw = sahte.baglantilar[0]
    assert kw["dsn"] == "ornek-host.invalid:1521/ORNEKSRV" and kw["tcp_connect_timeout"] == 7 and sahte.zaman_asimi == [7000]
    sahte.hata = Exception("ORA-01017: invalid credential; logon denied ornek-parola-123")
    sonuc = oracle.baglanti_testi("oracle_reportdb", senkron=True)
    assert sonuc["ok"] is False and sonuc["ipucu"] == "Kullanıcı adı ya da parola hatalı." and "ornek-parola" not in sonuc["mesaj"]


def test_istemci_hazirla_bir_kez_hata_engellemez(sahte, monkeypatch):
    monkeypatch.setattr(oracle, "_istemci_denendi", False)
    monkeypatch.setenv("ORACLE_CLIENT_DIR", r"C:\ornek\instantclient")
    sahte.hata = OSError("DPI-1047")
    oracle.istemci_hazirla(sahte)
    oracle.istemci_hazirla(sahte)
    assert sahte.istemci == [{"lib_dir": r"C:\ornek\instantclient"}]


def test_akis_rownum_sarmali_ve_bloklar(sahte, acik, monkeypatch):
    monkeypatch.setenv("ORACLE_REPORTDB_IMPORT_TIMEOUT", "60")
    sahte.sutunlar, sahte.satirlar = ["A", "B"], [(i, "x") for i in range(5)]
    akis = oracle.ayar("oracle_reportdb").akis("SELECT a, b FROM t WHERE (:customer_no IS NULL OR c = :customer_no)", 10, blok=2)
    assert next(akis) == ["A", "B"]
    assert [len(b) for b in akis] == [2, 2, 1]
    sql, binds = sahte.sorgular[0]
    assert sql.startswith("SELECT * FROM (SELECT a, b FROM t") and sql.endswith("WHERE ROWNUM <= :kaynak_limit")
    assert binds == {"kaynak_limit": 10, "customer_no": None} and sahte.zaman_asimi == [60000]


def test_baglanti_testi_ayri_surecte_ve_uc(client, acik, monkeypatch):
    cagri = {}

    def sahte_run(argv, **kw):
        cagri.update(argv=argv, **kw)
        return SimpleNamespace(stdout='log\n{"ok": false, "mesaj": "ORA-12541: host ornek-host.invalid", "ipucu": "x"}\n')

    monkeypatch.setattr(oracle.subprocess, "run", sahte_run)
    hdr = login_ok(client)
    r = client.post("/api/v1/tampon/kaynaklar/oracle_reportdb/test", headers=hdr)
    assert r.status_code == 200, r.text
    assert cagri["argv"][1:] == ["-m", "app.tampon.oracle", "test", "oracle_reportdb"] and cagri["timeout"] == 35
    assert r.json()["data"]["ok"] is False and all(v not in r.text for v in GIZLI.values())
    assert client.post("/api/v1/tampon/kaynaklar/yok/test", headers=hdr).status_code == 404
    assert client.post("/api/v1/tampon/kaynaklar/oracle_reportdb/test").status_code == 403  # CSRF'siz

    def zaman_asimi(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(oracle.subprocess, "run", zaman_asimi)
    assert "zaman aşımı" in oracle.baglanti_testi("oracle_reportdb")["mesaj"]


def test_ayri_surec_gercekten_calisir_kapaliyken_baglanmaz(kapali):
    sonuc = oracle._ayri_surecte_test("oracle_reportdb", 5)  # alt surec: python -m app.tampon.oracle test ...
    assert sonuc["ok"] is False and sonuc["mesaj"].startswith("Kaynak kapalı")


def test_kaynak_listesi_hazir_ve_sir_yok(client, acik):
    login_ok(client)
    r = client.get("/api/v1/tampon/kaynaklar")
    k = {x["anahtar"]: x for x in r.json()["data"]}["oracle_reportdb"]
    assert (k["hazir"], k["yapilandirma"], k["eksik"]) == (True, "tamam", [])
    assert k["reportdb"] == {"kartlara_yaz": False, "kural": 0, "yas_dk": None, "taze": False, "tazelik_dk": 20}
    assert all(v not in r.text for v in GIZLI.values())
    ozet = client.get("/api/v1/yonetim/ozet").json()["data"]
    assert next(b for b in ozet["baglantilar"] if b["id"] == "oracle_reportdb")["configured"] is True


# --- ReportDB: sorgular ---------------------------------------------------------------------------------------------
def test_sorgu_yalniz_tek_select_ve_kurumsal_kapsamli():
    s = oracle.sorgu_temizle(reportdb.SORGU)
    for parca in ("TEMIP.ACTIVEALARMS_5DK", "TEMIP.VIEW_REPORT_ACTIVE", "IN ('NOC DESTECH')", "TRUNC(SYSDATE, 'YYYY')",
                  "EVENTTIME < TRUNC(SYSDATE) + 1", "REGEXP_LIKE(INFORMATION1,'^[0-9]{8}$')"):  # fmt: skip
        assert parca in s
    assert sum(s.upper().count(k) for k in ("INSERT", "UPDATE", "DELETE")) == 0
    assert all(f'"{kolon}"' in s for kolon in reportdb.GEREKLI)
    assert "EVENTTIME < TRUNC(SYSDATE) + 1" in reportdb.SORGU.split("FROM TEMIP.VIEW_REPORT_ACTIVE")[1]  # kapanan taraf ust sinirli


def test_kayit_sorgulari_gecerli_ve_yalniz_8_haneli_numara():
    kapanan = oracle.sorgu_temizle(reportdb.kayit_sorgusu(False, ["10000001", "00000012"]))
    acik_ = oracle.sorgu_temizle(reportdb.kayit_sorgusu(True, ["10000001"]))
    for parca in ("TEMIP.VIEW_REPORT_ACTIVE", "EVENTTIME < TRUNC(SYSDATE) + 1", "IN ('10000001', '00000012')",
                  "ROW_NUMBER() OVER (PARTITION BY INFORMATION1", "RN <= 500", "IN ('NOC DESTECH')"):  # fmt: skip
        assert parca in kapanan
    assert "CLOSEDBY" not in kapanan  # kisisel veri alinmaz
    assert "ORIGINALEVENTTIME" in acik_ and "VIEW_REPORT" not in acik_
    for kotu in ([], ["1' OR '1'='1"], ["1234567"], ["123456789"], ["abcdefgh"]):
        with pytest.raises(reportdb.ReportdbHata):
            reportdb.kayit_sorgusu(False, kotu)


def test_kayit_basliklari_onedesk_sutunlariyla_eslesir():
    basliklar = ["Müşteri No", "Müşteri Adı", "Kayıt Türü", "Durum", *[b for _, _, b in reportdb._kolonlar(False)]]
    s = ice_al.sutunlari_bul(basliklar)
    for alan, beklenen in (("no", "Çağrı No"), ("musteri", "Müşteri Adı"), ("musteri_no", "Müşteri No"), ("tur", "Kayıt Türü"),
                           ("durum", "Durum"), ("lokasyon", "CI Adı"), ("kategori", "Kategori"), ("acilis", "Açılış Tarihi"),
                           ("kapanis", "Kapanış Tarihi")):  # fmt: skip
        assert basliklar[s[alan]] == beklenen, alan


# --- ReportDB: tampon -----------------------------------------------------------------------------------------------
def test_tampona_yaz_tekillestirir(client):
    pid, durum = doldur(satir("10000001", "ORNEK-A", 3, 100), satir("10000001", "ORNEK-A TEKRAR", 9, 9),
                        satir(" 05 ", "ORNEK-SIFIR", 1, 2), satir("", "ORNEK-NOSUZ", 1, 1), satir("10000002", None, "x", -4))  # fmt: skip
    assert durum == "ready"
    with Session(engine()) as db:
        p = db.get(IngestBatch, pid)
        rows = list(depo.satirlari_oku(db, pid))
    assert p.row_count == 3 and p.columns == BASLIK and "veri 2026-10-06 12:30:00" in p.label
    assert rows[0][:5] == ["10000001", "ORNEK-A", 3, 0, 100] and rows[1][0] == "05"
    assert rows[2][:5] == ["10000002", "10000002", 0, 0, 0]  # unvansiz: numara; okunamayan/negatif sayi 0


def test_eksik_sutun_ve_bos_sonuc_hata(client):
    for basliklar, satirlar in ((["Musteri No"], [["1"]]), (BASLIK, []), (BASLIK, [satir("", "x")])):
        with pytest.raises(reportdb.ReportdbHata), Session(engine()) as db:
            reportdb.tampona_yaz(db, basliklar, satirlar)
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(IngestBatch)) == 0


def test_yarim_sonuc_reddedilir_kartlara_yazilmaz(client):
    c = kart("ORNEK-A", "10000000", 7, 70)
    doldur(*[satir(str(10000000 + i), f"M{i}", 1, 1) for i in range(300)])
    kurallari_ac()
    pid, durum = doldur(*[satir(str(10000000 + i), f"M{i}", 5, 5) for i in range(100)])
    assert durum == "rejected"
    with Session(engine()) as db:
        assert reportdb.kartlara_uygula(db, pid) == {"uygulandi": False, "neden": "tampon_bos"}
    assert sayilar(c) == (7, 70)
    assert doldur(*[satir(str(10000000 + i), f"M{i}", 5, 5) for i in range(200)])[1] == "ready"  # %50 ve ustu kabul


def test_hata_yaz_yalniz_son_hata_kalir_hazir_parti_korunur(client):
    hazir, _ = doldur(satir("10000001", "A", 1, 1))
    with Session(engine()) as db:
        reportdb.hata_yaz(db, "ORA-20099: erisim yok")
        son = reportdb.hata_yaz(db, "ORA-12541: dinleyici yok")
        partiler = {p.id: (p.status, p.error) for p in db.scalars(select(IngestBatch))}
    assert partiler == {hazir: ("ready", ""), son.id: ("failed", "ORA-12541: dinleyici yok")}


# --- ReportDB: kartlara yaz (dagitim) -------------------------------------------------------------------------------
def test_kartlara_yaz_varsayilan_kapali(client):
    c = kart("A", "11111111", 7, 70)
    doldur(satir("11111111", "A", 1, 2))
    kurallari_ac(etkin=False)
    with Session(engine()) as db:
        kurallar = db.scalars(select(DistributionRule).where(DistributionRule.source_key == reportdb.KAYNAK)).all()
        assert {(k.target, k.operation, k.value_column, k.zero_unmatched, k.max_age_minutes, k.enabled) for k in kurallar} == {
            ("customer.alarm_count", "topla", "Aktif Alarm", True, 20, False),
            ("customer.alarm_closed_count", "topla", "Kapanan Alarm", True, 20, False),
        }
        reportdb.kurallari_hazirla(db)  # ikinci cagri yeni kural acmaz
        assert db.scalar(select(func.count()).select_from(DistributionRule)) == 2
    assert uygula() == {"uygulandi": False, "neden": "kapali"}
    assert sayilar(c) == (7, 70)


def test_acinca_yazar_numarasizlara_dokunmaz_eksige_sifir(client):
    a = kart("A", "11111111", 7, 70)
    b = kart("B", "22222222", 4, 40)  # partide yok -> 0
    z = kart("Z", None, 9, 90)  # numarasiz -> dokunma
    y = kart("Y", "N-33333333", 1, 1)  # rakam disi yok sayilir
    doldur(satir("11111111", "A", 5, 50), satir("33333333", "Y", 2, 3), satir("44444444", "KARTSIZ", 8, 8))
    kurallari_ac()
    assert uygula() == {"uygulandi": True, "kural": 2, "guncellenen": 6, "sifirlanan": 2}
    assert (sayilar(a), sayilar(b), sayilar(z), sayilar(y)) == ((5, 50), (0, 0), (9, 90), (2, 3))
    doldur(satir("11111111", "A", 5, 50), satir("33333333", "Y", 2, 3), satir("44444444", "KARTSIZ", 8, 8))
    assert uygula()["guncellenen"] == 0  # degisen yok
    doldur(satir("11111111", "A", 0, 51))  # aktif alarm azaldi, kapanan artti; Y artik yok -> 0
    assert uygula()["guncellenen"] == 4
    assert (sayilar(a), sayilar(y)) == ((0, 51), (0, 0))


def test_eski_parti_kartlara_yazilmaz(client):
    c = kart("A", "11111111", 7, 70)
    kurallari_ac()
    pid, _ = doldur(satir("11111111", "A", 1, 2))
    with Session(engine()) as db:
        db.get(IngestBatch, pid).received_at = simdi() - timedelta(minutes=reportdb.TAZELIK_DAKIKA + 1)
        db.commit()
        assert reportdb.kartlara_uygula(db, pid)["neden"] == "eski"
        assert reportdb.durum(db)["taze"] is False
    assert sayilar(c) == (7, 70)


def test_birikimli_uygulama_geri_alinca_ilk_degere_doner_elle_degisen_korunur(client, monkeypatch):
    monkeypatch.setenv("TAMLIFE_INGEST_KEEP_BATCHES", "1")
    a = kart("A", "11111111", 7, 70)
    b = kart("B", "22222222", 4, 40)
    kurallari_ac()
    doldur(satir("11111111", "A", 5, 50), satir("22222222", "B", 6, 60))
    uygula()
    doldur(satir("11111111", "A", 9, 90), satir("22222222", "B", 6, 60))
    uygula()  # A ikinci kez degisti; ILK deger (7, 70) saklanmali
    with Session(engine()) as db:
        db.get(Customer, b).alarm_count = 123  # elle degistirildi
        db.commit()
        kayitlar = db.scalars(select(DistributionLog).where(DistributionLog.reverted.is_(False))).all()
        assert len({k.run_id for k in kayitlar}) == 2 and len(kayitlar) == 4  # kural basina TEK uygulama, kart+hedef basina tek kayit
        assert {(k.customer_id, k.target, k.old_value, k.new_value) for k in kayitlar if k.customer_id == a} == {
            (a, "customer.alarm_count", "7", "9"), (a, "customer.alarm_closed_count", "70", "90")}
        assert db.scalar(select(func.count()).select_from(IngestBatch)) == 1  # eski parti serbest kaldi, silindi
        sonuc = [dagitim.geri_al(db, run, "admin") for run in {k.run_id for k in kayitlar}]
        db.commit()
    assert sum(s["geri_alinan"] for s in sonuc) == 3 and sum(s["korunan"] for s in sonuc) == 1
    assert (sayilar(a), sayilar(b)) == ((7, 70), (123, 40))  # elle degisen dokunulmadi


def test_birden_cok_numara_sayilar_toplanir(client):
    a = kart("MLP", "11111111, 22222222", 1, 1)
    b = kart("TEK", "33333333")
    c = kart("YOK", "44444444, 55555555", 9, 9)
    doldur(satir("11111111", "MLP 1", 5, 50), satir("22222222", "MLP 2", 7, 70), satir("33333333", "TEK", 1, 2),
           satir("66666666", "KARTSIZ", 4, 4))  # fmt: skip
    kurallari_ac()
    uygula()
    assert (sayilar(a), sayilar(b), sayilar(c)) == ((12, 120), (1, 2), (0, 0))


# --- ReportDB: alarm kayit listeleri -> Onedesk ---------------------------------------------------------------------
def _sahte_kayitlar(monkeypatch, kapanan, acik_):
    cagrilar = []

    def sahte(acik_mi, numaralar):
        cagrilar.append((acik_mi, list(numaralar)))
        if acik_mi:
            return ["Çağrı No", "CI Adı", "Açılış Tarihi"], acik_
        return ["Çağrı No", "CI Adı", "Açılış Tarihi", "Kapanış Tarihi"], kapanan

    monkeypatch.setattr(reportdb, "_kayitlari_cek", sahte)
    return cagrilar


def _kayitlari_yenile():
    with Session(engine()) as db:
        parti, ozet = reportdb.kayit_partisi(db)
        if ozet["musteri"]:
            ozet.update(ice_al.kaynak_yenile(db, parti.id if parti else None, reportdb.ONEDESK_KAYNAGI, "alarm"))
            db.commit()
        return ozet


def test_kayitlar_onedeske_numarayla_yazilir_her_turda_yenilenir(client, monkeypatch):
    a = kart("ORNEK-A", "10000001", 3, 30)
    b = kart("ORNEK-B", "00000012")  # bastaki sifir: Oracle'daki 8 haneli deger aranir
    kart("ORNEK-C")  # numarasiz: dokunulmaz
    kapanan = {"10000001": {"toplam": 9, "satirlar": [["T1", "ci-1", "2026-09-01 10:00:00", "2026-10-01 10:00:00"],
                                                      ["T2", "ci-2", "2026-09-02 10:00:00", "2026-10-02 10:00:00"]]}}  # fmt: skip
    acik_ = {"10000001": {"toplam": 4, "satirlar": [["T3", "ci-1", "2026-10-05 08:00:00"]]}}
    cagrilar = _sahte_kayitlar(monkeypatch, kapanan, acik_)
    ozet = _kayitlari_yenile()
    assert [c[1] for c in cagrilar] == [["00000012", "10000001"]] * 2  # kapanan + acik, sirali
    assert (ozet["musteri"], ozet["kapanan_satir"], ozet["acik_satir"], ozet["eklenen"], ozet["silinen"]) == (2, 2, 1, 3, 0)
    with Session(engine()) as db:
        kayitlar = {r.external_key: r for r in db.scalars(select(OnedeskRecord))}
    assert {k: (r.customer_id, r.status, r.source, r.kind) for k, r in kayitlar.items()} == {
        "T1": (a, "closed", "reportdb", "alarm"), "T2": (a, "closed", "reportdb", "alarm"), "T3": (a, "open", "reportdb", "alarm")}
    assert kayitlar["T3"].location == "ci-1" and kayitlar["T1"].closed_at.month == 10
    assert sayilar(a) == (3, 30) and sayilar(b) == (0, 0)  # sayaclar kayitlardan hesaplanmaz (ozet dagitimi yazar)
    _sahte_kayitlar(monkeypatch, kapanan, {})  # sonraki tur: acik alarm bitti -> eski liste kalmaz
    assert _kayitlari_yenile()["silinen"] == 3
    with Session(engine()) as db:
        assert {r.external_key for r in db.scalars(select(OnedeskRecord))} == {"T1", "T2"}
    _sahte_kayitlar(monkeypatch, {}, {})  # hic kayit yok: liste bosaltilir
    assert _kayitlari_yenile()["silinen"] == 2


def test_numarali_kart_yoksa_sorgu_yapilmaz(client, monkeypatch):
    kart("ORNEK-C")
    cagrilar = _sahte_kayitlar(monkeypatch, {}, {})
    assert _kayitlari_yenile()["musteri"] == 0 and cagrilar == []


def test_kayitlar_kartin_tum_numaralarindan_birlesir_en_yeni_once(client, monkeypatch):
    kart("MLP", "11111111, 22222222")
    kapanan = {"11111111": {"toplam": 2, "satirlar": [["T1", "c", "", "2026-09-01 10:00:00"], ["T3", "c", "", "2026-09-03 10:00:00"]]},
               "22222222": {"toplam": 1, "satirlar": [["T2", "c", "", "2026-09-02 10:00:00"]]}}  # fmt: skip
    _sahte_kayitlar(monkeypatch, kapanan, {})
    with Session(engine()) as db:
        parti, _ = reportdb.kayit_partisi(db)
        rows = list(depo.satirlari_oku(db, parti.id))
    assert [(r[0], r[4]) for r in rows] == [("11111111", "T3"), ("22222222", "T2"), ("11111111", "T1")]


def test_onedesk_aktarimi_once_numarayla_belirsizse_unvanla(client):
    a = kart("ORNEK-UNVAN-FARKLI", "10000001")
    kart("ORNEK-IKIZ-1", "20000002")
    ikiz = kart("ORNEK-IKIZ-2", "20000002")
    with Session(engine()) as db:
        p = depo.parti_olustur(db, "csv_ornek", "test", "admin")
        db.commit()
        depo.ice_al(db, p, ["Çağrı No", "Müşteri No", "Müşteri Adı", "Kayıt Türü"],
                    [["K1", "10000001", "BASKA AD", "Alarm"], ["K2", "20000002", "ORNEK-IKIZ-2", "Alarm"]])  # fmt: skip
        ice_al.parti_aktar(db, p.id)
        db.commit()
        assert {r.external_key: r.customer_id for r in db.scalars(select(OnedeskRecord))} == {"K1": a, "K2": ikiz}


# --- Veri iscisi (python -m app.isci) -------------------------------------------------------------------------------
def _partiler():
    with Session(engine()) as db:
        return [(p.source_key, p.status, p.error) for p in db.scalars(select(IngestBatch).order_by(IngestBatch.id))]


def test_isci_kapaliyken_hicbir_sey_yapmaz(client, sahte, kapali):
    assert isci.main(["reportdb"]) == 1
    assert isci.main(["cek", "oracle_onent"]) == 1
    assert sahte.baglantilar == [] and _partiler() == []


def test_isci_senkron_tamponu_yazar_kartlara_yalniz_kural_aciksa(client, acik, monkeypatch):
    c = kart("A", "11111111", 7, 70)
    monkeypatch.setattr(reportdb, "cek", lambda: (BASLIK, [satir("11111111", "A", 5, 50)]))
    cagrilar = _sahte_kayitlar(monkeypatch, {}, {"11111111": {"toplam": 1, "satirlar": [["T9", "ci-9", "2026-10-05 08:00:00"]]}})
    assert isci.main(["reportdb"]) == 0
    assert _partiler() == [("oracle_reportdb", "ready", "")] and sayilar(c) == (7, 70) and cagrilar == []  # kapali: ek sorgu yok
    kurallari_ac()
    assert isci.main(["reportdb"]) == 0
    assert sayilar(c) == (5, 50) and len(cagrilar) == 2
    with Session(engine()) as db:
        assert [r.external_key for r in db.scalars(select(OnedeskRecord))] == ["T9"]
    gunluk = (Path(os.environ["TAMLIFE_LOG_DIR"]) / "isci.log").read_text(encoding="utf-8")
    assert "reportdb OK" in gunluk and "kartlara yazildi" in gunluk and "alarm kayitlari: 1 kart" in gunluk


def test_isci_kuru_calisma_yazmaz(client, acik, monkeypatch, capsys):
    monkeypatch.setattr(reportdb, "cek", lambda: (BASLIK, [satir("11111111", "A", 5, 50)]))
    assert isci.main(["reportdb", "--kuru"]) == 0
    assert "KURU: 1 satir" in capsys.readouterr().out and _partiler() == []


def test_isci_oracle_hatasi_partiyi_ve_kartlari_korur(client, acik, monkeypatch, capsys):
    c = kart("A", "11111111", 7, 70)
    doldur(satir("11111111", "A", 5, 50))
    kurallari_ac()
    uygula()

    def bozuk():
        raise RuntimeError("ORA-12541: no listener at host ornek-host.invalid 10.1.2.3 password=ornek-parola-123")

    monkeypatch.setattr(reportdb, "cek", bozuk)
    assert isci.main(["reportdb"]) == 1
    partiler = _partiler()
    assert [p[:2] for p in partiler] == [("oracle_reportdb", "ready"), ("oracle_reportdb", "failed")]
    assert "ORA-12541" in partiler[1][2] and "Dinleyiciye ulaşılamadı" in partiler[1][2]
    cikti = capsys.readouterr().err
    assert all(v not in partiler[1][2] + cikti for v in (*GIZLI.values(), "10.1.2.3"))
    assert sayilar(c) == (5, 50)


def test_isci_kart_yazimi_hatasi_partiyi_korur_ariza_yazar(client, acik, monkeypatch):
    c = kart("A", "11111111", 7, 70)
    monkeypatch.setattr(reportdb, "cek", lambda: (BASLIK, [satir("11111111", "A", 5, 50)]))

    def bozuk(db, parti_id):
        raise RuntimeError("db kilitli")

    monkeypatch.setattr(reportdb, "kartlara_uygula", bozuk)
    assert isci.main(["reportdb"]) == 1
    assert _partiler() == [("oracle_reportdb", "ready", "")] and sayilar(c) == (7, 70)
    with Session(engine()) as db:
        ariza_ = db.scalars(select(FaultEvent)).one()
    assert ariza_.code == "TL-TAM-01" and "kartlar/kayitlar yazilamadi" in ariza_.message


def test_isci_istemci_yoksa_hata_ve_tek_calisma(client, acik, tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_CLIENT_DIR", "")  # isci ortami degistirir; test sonunda geri alinsin
    assert isci.main(["reportdb", "--client", str(tmp_path / "yok")]) == 1
    (tmp_path / "ic").mkdir()
    (tmp_path / "ic" / "oci.dll").write_bytes(b"")
    monkeypatch.setattr(reportdb, "cek", lambda: (BASLIK, [satir("11111111", "A", 5, 50)]))
    assert isci.main(["reportdb", "--client", str(tmp_path / "ic"), "--kuru"]) == 0
    assert os.environ["ORACLE_CLIENT_DIR"] == str(tmp_path / "ic")
    monkeypatch.setenv("ORACLE_CLIENT_DIR", "")
    kilit = Path(os.environ["TAMLIFE_LOG_DIR"]) / "isci_reportdb.kilit"
    assert isci.kilit_al(kilit) and not isci.kilit_al(kilit)  # taze kilit: ikinci calisma atlanir
    assert isci.main(["reportdb"]) == 2
    eski = time.time() - isci.KILIT_BAYAT_SN - 5
    os.utime(kilit, (eski, eski))
    assert isci.kilit_al(kilit)  # cokme artigi kilit yeniden alinir


def test_isci_cek_import_query_partisi(client, sahte, monkeypatch):
    monkeypatch.setenv("ONENTDB_DB_ENABLED", "true")
    for ad, deger in GIZLI.items():
        monkeypatch.setenv(f"ONENTDB_DB_{ad}", deger)
    monkeypatch.setenv("ONENTDB_DB_IMPORT_QUERY", "DELETE FROM ORNEK_TABLO")
    assert isci.main(["cek", "oracle_onent"]) == 1 and _partiler() == []  # yalniz SELECT / WITH
    monkeypatch.setenv("ONENTDB_DB_IMPORT_QUERY", "SELECT NO, AD, TUTAR, TARIH FROM ORNEK_TABLO;")
    sahte.sutunlar = ["NO", "AD", "TUTAR", "TARIH"]
    sahte.satirlar = [(Decimal(1), " ORNEK-A ", Decimal("12.5"), datetime(2026, 10, 1, 9, 30)), (Decimal(2), "ORNEK-B", None, None)]  # noqa: DTZ001
    assert isci.main(["cek", "oracle_onent"]) == 0
    with Session(engine()) as db:
        p = db.scalars(select(IngestBatch)).one()
        assert (p.source_key, p.status, p.columns) == ("oracle_onent_import", "ready", ["NO", "AD", "TUTAR", "TARIH"])
        assert list(depo.satirlari_oku(db, p.id)) == [[1, "ORNEK-A", 12.5, "2026-10-01 09:30:00"], [2, "ORNEK-B", None, None]]
    assert sahte.sorgular[0] == ("SELECT * FROM (SELECT NO, AD, TUTAR, TARIH FROM ORNEK_TABLO) WHERE ROWNUM <= :kaynak_limit",
                                 {"kaynak_limit": 300_001})  # fmt: skip
    sahte.hata = Exception("DPY-6005: cannot connect to ornek-host.invalid")
    assert isci.main(["cek", "oracle_onent"]) == 1
    son = _partiler()[-1]
    assert son[:2] == ("oracle_onent_import", "failed") and "DPY-6005" in son[2] and "ornek-host" not in son[2]
    login_ok(client)
    k = {x["anahtar"]: x for x in client.get("/api/v1/tampon/kaynaklar").json()["data"]}
    assert k["oracle_onent_import"]["son"]["durum"] == "failed" and k["oracle_onent_import"]["tur"] == "oracle_parti"


def test_dilimsiz_kaynak_saati_turkiye_saati_sayilir():
    from datetime import UTC, datetime

    from app.onedesk.ice_al import tarih_oku

    assert tarih_oku("10.10.2026 12:00:00") == datetime(2026, 10, 10, 9, 0, tzinfo=UTC)  # Onedesk/Oracle yerel saat -> UTC
    assert tarih_oku(datetime(2026, 10, 10, 12, 0)) == datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
    assert tarih_oku(datetime(2026, 10, 10, 12, 0, tzinfo=UTC)) == datetime(2026, 10, 10, 12, 0, tzinfo=UTC)  # dilimli dokunulmaz
