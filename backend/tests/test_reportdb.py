"""Oracle kaynak katmani, ReportDB tur durumu ve veri iscisi (uretim test_reportdb_tampon.py uyarlamasi).

oracledb hic yuklenmez: oracle._oracledb sahte modulle degistirilir; gercek Oracle'a baglanilmaz. Veri uydurmadir (ORNEK-*).
2026-11-23 (834d541, 8d90b8f): eski alarm OZET sorgusu, tampon partisi ve kartlara dagitimi kaldirildi; 30 dk'lik isci turu yalniz TEMIP
alarm kayitlarini (tampon/temip_kayit; kendi testleri test_temip_kayit.py) calistirir ve sonucu reportdb.durum_yaz ile kaydeder.
2026-11-21 (763662d): 'cek' (<ON EK>_IMPORT_QUERY -> tampon partisi) komutu kaldirildi.
"""

import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import isci
from app.db import engine
from app.models import Customer, IngestBatch
from app.tampon import oracle, reportdb, temip_kayit
from app.yonetim.models import FaultEvent
from tests.conftest import login_ok

GIZLI = {"HOST": "ornek-host.invalid", "SERVICE_NAME": "ORNEKSRV", "USER": "ornek_kullanici", "PASSWORD": "ornek-parola-123"}


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
    assert oracle.deger(datetime(2026, 10, 1, 9, 30)) == "2026-10-01 09:30:00"
    assert oracle.deger(datetime(2026, 10, 1)) == "2026-10-01"
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


def test_giris_tetikleyicisi_ve_sure_dolumu_ipuclari():
    """Parola dogru olsa da ORA-00604 > ORA-20099 (logon tetikleyicisi) gelebilir: ipucu parola sifirlamanin cozmedigini soyler."""
    ilk, ipucu = oracle.hata_metni(Exception("ORA-00604: error occurred at recursive SQL level 1\nORA-20099: Access denied\nORA-06512: at line 17\nORA-04088: error during execution of trigger 'X.T'"))
    assert ilk.startswith("ORA-00604") and "giriş tetikleyicisi" in ipucu and "Parola sıfırlamak çözmez" in ipucu
    assert "tetikleyicisi" in oracle.hata_metni(Exception("ORA-04088: error during execution of trigger"))[1]
    assert "süresi dolmuş" in oracle.hata_metni(Exception("ORA-28001: the password has expired"))[1]
    assert oracle.hata_metni(Exception("ORA-01017: invalid credential"))[1] == "Kullanıcı adı ya da parola hatalı."


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
    assert "reportdb" not in k  # ozet yasi / 'Kartlara yaz' gostergesi kalkti (834d541, 8d90b8f)
    assert all(v not in r.text for v in GIZLI.values())
    ozet = client.get("/api/v1/yonetim/ozet").json()["data"]
    assert next(b for b in ozet["baglantilar"] if b["id"] == "oracle_reportdb")["configured"] is True


# --- ReportDB: tur durumu (eski hata partisi yerine; Veri Ozeti / Veri Akisi bunu okur) ------------------------------------
def test_durum_yaz_basari_ve_yalniz_son_hata(client, monkeypatch):
    zaman = iter(datetime(2026, 11, 23, 9, d, tzinfo=UTC) for d in range(30))
    monkeypatch.setattr(reportdb, "simdi", lambda: next(zaman))
    with Session(engine()) as db:
        assert reportdb.durum_oku(db) == {} and reportdb.son_hata({}) == ""
        reportdb.durum_yaz(db)
        basari = reportdb.durum_oku(db)["son_basari"]
        reportdb.durum_yaz(db, "ORA-20099: erisim yok")
        reportdb.durum_yaz(db, "ORA-12541: dinleyici yok " + "x" * 600)
        d = reportdb.durum_oku(db)
        assert d["son_basari"] == basari and d["son_deneme"] > basari  # hata son basariyi silmez
        assert d["hata"].startswith("ORA-12541") and len(d["hata"]) == 500 and reportdb.son_hata(d) == d["hata"]  # yalniz son hata
        reportdb.durum_yaz(db)
        d = reportdb.durum_oku(db)
        assert d["hata"] == "" and d["son_basari"] == d["son_deneme"] and reportdb.son_hata(d) == ""
        assert db.scalar(select(IngestBatch.id).limit(1)) is None  # tampon partisi yazilmaz


def _partiler():
    with Session(engine()) as db:
        return [(p.source_key, p.status, p.error) for p in db.scalars(select(IngestBatch).order_by(IngestBatch.id))]


def test_isci_kapaliyken_hicbir_sey_yapmaz(client, sahte, kapali, monkeypatch):
    cagrilar = _sahte_temip(monkeypatch)
    assert isci.main(["reportdb"]) == 1
    assert sahte.baglantilar == [] and _partiler() == [] and cagrilar == []
    with Session(engine()) as db:
        assert reportdb.durum_oku(db) == {}
    with pytest.raises(SystemExit):
        isci.main(["cek", "oracle_onent"])  # 'cek' komutu kaldirildi (763662d)


def _sahte_temip(monkeypatch):
    """temip_kayit.calistir yerine: cagrilan kipleri toplar, ozet doner (TEMIP kayit akisi test_temip_kayit.py'de)."""
    cagrilar = []

    def sahte(db, kip="artimli", gun=30):
        cagrilar.append(kip)
        return {"kip": kip, "eklenen": 1, "guncellenen": 0, "acik_satir": 1, "dusen_acik": 0, "kapanan_sorgu": 0, "yeniden_baglanan": 0, "etkilenen_kart": 1}

    monkeypatch.setattr(temip_kayit, "calistir", sahte)
    monkeypatch.setattr(temip_kayit, "otomatik_kip", lambda db: "artimli")
    return cagrilar


def _yan_isler(monkeypatch):
    """reportdb turunun ayni turda cagirdigi LOE / envanter / OneDesk isleri (kendi testleri ayri): yalniz cagrildiklari kaydedilir."""
    cagrilar = []
    for ad in ("rapor_devre", "envanter_turu", "onedesk_kayit_turu"):
        monkeypatch.setattr(isci, ad, lambda *a, _ad=ad, **k: cagrilar.append(_ad) or 0)
    return cagrilar


def test_isci_turu_yalniz_kayit_turunu_calistirir_kart_sayaclarina_dokunmaz(client, sahte, acik, monkeypatch):
    c = kart("A", "11111111", 7, 70)
    cagrilar, yan = _sahte_temip(monkeypatch), _yan_isler(monkeypatch)
    assert isci.main(["reportdb"]) == 0
    assert cagrilar == ["artimli"] and yan == ["rapor_devre", "envanter_turu", "onedesk_kayit_turu"]
    assert _partiler() == [] and sayilar(c) == (7, 70)  # ozet partisi yok; sayaclari yalniz kayitlar yazar (sahte tur yazmadi)
    assert sahte.baglantilar == []  # ozet sorgusu yok: Oracle'a yalniz kayit turu baglanir
    with Session(engine()) as db:
        d = reportdb.durum_oku(db)
    assert d["son_basari"] == d["son_deneme"] and d["hata"] == ""
    gunluk = (Path(os.environ["TAMLIFE_LOG_DIR"]) / "isci.log").read_text(encoding="utf-8")
    assert "reportdb OK" in gunluk and "alarm kayitlari (artimli): +1 yeni" in gunluk


def test_isci_temip_kayit_komutu_kapaliyken_baglanmaz_aciksa_kipi_calistirir(client, sahte, kapali, monkeypatch):
    cagrilar = _sahte_temip(monkeypatch)
    assert isci.main(["temip-kayit", "--kip", "tam"]) == 1 and cagrilar == [] and sahte.baglantilar == []
    monkeypatch.setenv("ORACLE_REPORTDB_ENABLED", "true")
    for ad, deger in GIZLI.items():
        monkeypatch.setenv(f"ORACLE_REPORTDB_{ad}", deger)
    assert isci.main(["temip-kayit", "--kip", "tam"]) == 0 and cagrilar == ["tam"]
    gunluk = (Path(os.environ["TAMLIFE_LOG_DIR"]) / "isci.log").read_text(encoding="utf-8")
    assert "temip-kayit OK" in gunluk


def test_isci_tur_hatasi_maskeli_durum_ve_ariza_yazar_kartlari_korur(client, sahte, acik, monkeypatch, capsys):
    c = kart("A", "11111111", 5, 50)
    _yan_isler(monkeypatch)
    _sahte_temip(monkeypatch)
    assert isci.main(["reportdb"]) == 0
    with Session(engine()) as db:
        basari = reportdb.durum_oku(db)["son_basari"]

    def bozuk(db, kip="artimli", gun=30):
        raise RuntimeError("ORA-12541: no listener at host ornek-host.invalid 10.1.2.3 password=ornek-parola-123")

    monkeypatch.setattr(temip_kayit, "calistir", bozuk)
    assert isci.main(["reportdb"]) == 1
    with Session(engine()) as db:
        d = reportdb.durum_oku(db)
        ariza_ = db.scalars(select(FaultEvent)).one()
    assert d["son_basari"] == basari and "ORA-12541" in d["hata"] and "Dinleyiciye ulaşılamadı" in d["hata"]
    assert reportdb.son_hata(d) == d["hata"]
    assert ariza_.code == "TL-TAM-01" and "alarm kayit turu" in ariza_.message
    cikti = capsys.readouterr().err
    assert all(v not in d["hata"] + cikti + ariza_.message for v in (*GIZLI.values(), "10.1.2.3"))
    assert _partiler() == [] and sayilar(c) == (5, 50)
    with pytest.raises(SystemExit):
        isci.main(["reportdb", "--kuru"])  # reportdb --kuru kalkti (834d541); kuru deneme: temip-kayit --kuru


def test_isci_istemci_yoksa_hata_ve_tek_calisma(client, sahte, acik, tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_CLIENT_DIR", "")  # isci ortami degistirir; test sonunda geri alinsin
    cagrilar, _ = _sahte_temip(monkeypatch), _yan_isler(monkeypatch)
    assert isci.main(["reportdb", "--client", str(tmp_path / "yok")]) == 1 and cagrilar == []
    (tmp_path / "ic").mkdir()
    (tmp_path / "ic" / "oci.dll").write_bytes(b"")
    assert isci.main(["reportdb", "--client", str(tmp_path / "ic")]) == 0 and cagrilar == ["artimli"]
    assert os.environ["ORACLE_CLIENT_DIR"] == str(tmp_path / "ic")
    monkeypatch.setenv("ORACLE_CLIENT_DIR", "")
    kilit = Path(os.environ["TAMLIFE_LOG_DIR"]) / "isci_reportdb.kilit"
    assert isci.kilit_al(kilit) and not isci.kilit_al(kilit)  # taze kilit: ikinci calisma atlanir
    assert isci.main(["reportdb"]) == 2 and cagrilar == ["artimli"]
    eski = time.time() - isci.KILIT_BAYAT_SN - 5
    os.utime(kilit, (eski, eski))
    assert isci.kilit_al(kilit)  # cokme artigi kilit yeniden alinir
