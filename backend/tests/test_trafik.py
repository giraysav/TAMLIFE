"""Devre trafigi (MSSQL LOE): IMT -> rrdid eslesmesi ve saatlik toplama (sahte imlec), olcum noktalarina birlesme, hata yalitimi,
Kurum Baglantilari karti (parola yok). Canli MSSQL'e baglanilmaz."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

import pytest
from conftest import giris, kullanici_ekle

from app.db import oturum
from app.models import ReportCmdb
from app.rapor import loe, loe_trafik
from app.tampon import mssql

ORTAM = {
    "MSSQL_LOE_ENABLED": "true", "MSSQL_LOE_HOST": "mssql.test", "MSSQL_LOE_PORT": "1433", "MSSQL_LOE_USER": "okur",
    "MSSQL_LOE_PASSWORD": "Gizli-Parola-1", "MSSQL_LOE_DBNAME": "vt_bir,vt_iki",
}  # fmt: skip


class SahteImlec:
    """SQL metnine gore sabit satir donen imlec: vt_bir'de IMT 111 iki rrdid'ye (10, 11) dagilmis; vt_iki'de esleme yok."""

    def __init__(self) -> None:
        self.vt, self.satirlar = "", []

    def execute(self, sql: str, *parametre):
        if sql.startswith("USE "):
            self.vt, self.satirlar = sql[5:-1], []
        elif "details[0-9]" in sql:
            self.satirlar = [("details2026",)]
        elif "data[0-9]" in sql:
            self.satirlar = [("data20261110",)]
        elif "FROM dbo.details2026" in sql:
            self.satirlar = [(10, "111"), (11, "111")] if self.vt == "vt_bir" else []
        elif "FROM dbo.data20261110" in sql:
            self.satirlar = [(10, datetime(2026, 11, 10, 9), 100.0, 50.0), (11, datetime(2026, 11, 10, 9), 20.0, 5.0),
                             (10, datetime(2026, 11, 10, 10), 40.0, None)]  # fmt: skip
        return self

    def __iter__(self):
        return iter(self.satirlar)


@pytest.fixture()
def mssql_acik(monkeypatch):
    for k, v in ORTAM.items():
        monkeypatch.setenv(k, v)

    @contextmanager
    def baglan(self):
        class Baglanti:
            def cursor(self_inner):
                return SahteImlec()

        yield Baglanti()

    monkeypatch.setattr(mssql.MssqlKaynak, "baglan", baglan)


def test_saatlik_trafik_rrdleri_toplar_ve_carpani_uygular(mssql_acik, monkeypatch):
    sonuc = loe_trafik.saatlik_trafik({"ci-a": "111", "ci-yok": "999"}, datetime(2026, 11, 1), datetime(2026, 12, 1))
    assert set(sonuc) == {"ci-a"}  # eslesmeyen IMT sessizce atlanir
    assert sonuc["ci-a"][datetime(2026, 11, 10, 9)] == (120.0, 55.0)  # ayni IMT'nin iki arayuzu toplanir
    assert sonuc["ci-a"][datetime(2026, 11, 10, 10)] == (40.0, 0.0)
    monkeypatch.setenv("MSSQL_LOE_TRAFIK_CARPAN", "8")
    assert loe_trafik.saatlik_trafik({"ci-a": "111"}, datetime(2026, 11, 1), datetime(2026, 12, 1))["ci-a"][datetime(2026, 11, 10, 9)] == (960.0, 440.0)


def test_gun_tablolari_sinir_saatleri_icin_onceki_gunu_de_kapsar():
    assert [g.isoformat() for g in loe_trafik._gunler(datetime(2026, 11, 1), datetime(2026, 11, 3))] == ["2026-10-31", "2026-11-01", "2026-11-02", "2026-11-03"]


def test_gecersiz_veritabani_adi_sorguya_girmez(monkeypatch):
    for k, v in {**ORTAM, "MSSQL_LOE_DBNAME": "iyi_vt,kotu]; DROP TABLE x--"}.items():
        monkeypatch.setenv(k, v)
    assert mssql.ayar().veritabanlari == ["iyi_vt"]


def _satir(saat: int) -> dict:
    return {"zaman": datetime(2026, 11, 10, saat), "avail": 3600.0, "total": 3600.0, "delay": 5000.0, "jitter": 400.0, "loss": 0.0, "pencere": True}


def test_trafik_olcum_noktalarina_saatine_gore_yazilir(mssql_acik):
    with oturum() as db:
        db.add(ReportCmdb(ciname="ci-a", customer_key="1", fields={"IMT": "111"}, search_text="ci-a"))
        db.commit()
        gruplar = {"ci-a": [_satir(9), _satir(11)]}
        bulunan = loe._trafik_ekle(db, gruplar, datetime(2026, 11, 1), datetime(2026, 12, 1))
        db.rollback()
    assert bulunan == {"ci-a"}
    noktalar = loe.noktalar(gruplar["ci-a"])
    assert noktalar[0][6:8] == [120.0, 55.0]  # 09:00 trafigi
    assert noktalar[1][6:8] == [None, None]  # 11:00 icin trafik yok
    assert noktalar[0][1] == 1.0 and noktalar[0][2] == 5.0  # Oracle metrikleri yerinde


def test_trafik_hatasi_olcumu_durdurmaz(mssql_acik, monkeypatch):
    def patla(*a, **k):
        raise RuntimeError("baglanti koptu Gizli-Parola-1")

    monkeypatch.setattr(loe_trafik, "saatlik_trafik", patla)
    with oturum() as db:
        gruplar = {"ci-a": [_satir(9)]}
        assert loe._trafik_ekle(db, gruplar, datetime(2026, 11, 1), datetime(2026, 12, 1)) is None
        durum = loe.durum_oku(db)["trafik"]
        db.rollback()
    assert "Gizli-Parola-1" not in durum["hata"] and durum["hata"]
    assert "giris" not in gruplar["ci-a"][0]


def test_kaynak_kapaliyken_trafik_cekilmez(monkeypatch):
    monkeypatch.setenv("MSSQL_LOE_ENABLED", "false")
    with oturum() as db:
        assert loe._trafik_ekle(db, {"ci-a": [_satir(9)]}, datetime(2026, 11, 1), datetime(2026, 12, 1)) is None


def test_kurum_kartinda_mssql_parolasiz(istemci, mssql_acik):
    kullanici_ekle("yonetici", "admin")
    giris(istemci, "yonetici")
    r = istemci.get("/api/v1/yonetim/kurum")
    kart = next(b for b in r.json()["data"]["baglantilar"] if b["id"] == mssql.KAYNAK)
    assert kart["tur"] == "mssql" and kart["state"] == "ready"
    assert kart["bilgiler"]["veritabani"] == "vt_bir, vt_iki" and kart["bilgiler"]["parola"] is True
    assert "Gizli-Parola-1" not in r.text
