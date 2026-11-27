"""Devre trafigi (MSSQL LOE): IMT -> rrdid eslesmesi ve saatlik toplama (sahte imlec), olcum noktalarina birlesme, hata yalitimi,
Kurum Baglantilari karti (parola yok). Canli MSSQL'e baglanilmaz."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

import pytest
from conftest import giris, kullanici_ekle

from app.db import oturum
from app.models import CustomerCi, ReportCmdb
from app.rapor import loe, loe_trafik
from app.tampon import mssql

ORTAM = {
    "MSSQL_LOE_ENABLED": "true", "MSSQL_LOE_HOST": "mssql.test", "MSSQL_LOE_PORT": "1433", "MSSQL_LOE_USER": "okur",
    "MSSQL_LOE_PASSWORD": "Gizli-Parola-1", "MSSQL_LOE_DBNAME": "vt_bir,vt_iki",
}  # fmt: skip


class SahteImlec:
    """SQL metnine gore sabit satir donen imlec. vt_bir: IMT 111 iki rrdid'ye (10, 11) dagilmis; tempcilist'te ci-a -> 10 (IMT ile
    ayni grafik: ci_imt), ci-b -> 20 (yalniz CI adi), ci-c IMT 333 tempcilist'te yok -> rrdid 30 (yalniz IMT). vt_iki: esleme yok."""

    sorgular: list[str] = []

    def __init__(self) -> None:
        self.vt, self.satirlar = "", []

    def execute(self, sql: str, *parametre):
        SahteImlec.sorgular.append(sql)
        bir = self.vt == "vt_bir"
        if sql.startswith("USE "):
            self.vt, self.satirlar = sql[5:-1], []
        elif "name IN ('tempcilist'" in sql:
            self.satirlar = [("tempcilist",)] if bir else []
        elif "FROM dbo.tempcilist" in sql:
            self.satirlar = [(c, r) for c, r in (("ci-a", 10), ("ci-b", 20)) if c in parametre]
        elif "details[0-9]" in sql:
            self.satirlar = [("details2026",)]
        elif "data[0-9]" in sql:
            self.satirlar = [("data20261110",)]
        elif "FROM dbo.details2026" in sql:
            self.satirlar = [(r, i) for r, i in ((10, "100000000111"), (11, "100000000111"), (30, "100000000333")) if i in parametre] if bir else []
        elif "FROM dbo.data20261110" in sql:
            olcum = [(10, 9, 100.0, 50.0), (11, 9, 20.0, 5.0), (10, 10, 40.0, None), (20, 9, 7.0, 3.0), (30, 23, 1.0, 2.0)]
            self.satirlar = [(r, datetime(2026, 11, 10, h), g, c) for r, h, g, c in olcum if r in parametre]
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


ARALIK = (datetime(2026, 11, 1), datetime(2026, 12, 1))


def test_eslesme_once_ci_adi_sonra_imt(mssql_acik):
    sonuc = loe_trafik.saatlik_trafik({"ci-a": "100000000111", "ci-b": "100000000222", "ci-c": "100000000333", "ci-yok": "100000000999"}, *ARALIK)
    assert set(sonuc) == {"ci-a", "ci-b", "ci-c"}  # eslesmeyen sessizce atlanir
    assert {c: v["eslesme"] for c, v in sonuc.items()} == {"ci-a": "ci_imt", "ci-b": "ci", "ci-c": "imt"}
    # ci-a CI adiyla rrdid 10'a eslesti: IMT'nin ikinci arayuzu (11) bu CI'ya eklenmez
    assert sonuc["ci-a"]["seri"][datetime(2026, 11, 10, 9)] == (100.0, 50.0)
    assert sonuc["ci-a"]["seri"][datetime(2026, 11, 10, 10)] == (40.0, 0.0)
    assert sonuc["ci-b"]["seri"][datetime(2026, 11, 10, 9)] == (7.0, 3.0)


def test_yalniz_imt_ile_arayuzler_toplanir_ve_carpan(mssql_acik, monkeypatch):
    sonuc = loe_trafik.saatlik_trafik({"ci-z": "100000000111"}, *ARALIK)  # tempcilist'te yok: IMT'nin iki arayuzu toplanir
    assert sonuc["ci-z"]["eslesme"] == "imt" and sonuc["ci-z"]["seri"][datetime(2026, 11, 10, 9)] == (120.0, 55.0)
    monkeypatch.setenv("MSSQL_LOE_TRAFIK_CARPAN", "8")
    assert loe_trafik.saatlik_trafik({"ci-z": "100000000111"}, *ARALIK)["ci-z"]["seri"][datetime(2026, 11, 10, 9)] == (960.0, 440.0)


def test_ip_sutunlari_hic_sorgulanmaz(mssql_acik):
    SahteImlec.sorgular.clear()
    loe_trafik.saatlik_trafik({"ci-a": "100000000111", "ci-b": "100000000222"}, *ARALIK)
    metin = " ".join(SahteImlec.sorgular).upper()
    assert "IP_ADDRESS" not in metin and "GRAPH_NAME" not in metin and "SELECT *" not in metin


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
        db.add(ReportCmdb(ciname="ci-a", customer_key="1", fields={"IMT": "100000000111"}, search_text="ci-a"))
        db.add(CustomerCi(customer_key="1", ci_name="ci-a", attrs={"imt": "-"}))  # envanterde yer tutucu IMT: CMDB'deki kullanilir
        db.commit()
        gruplar = {"ci-a": [_satir(9), _satir(11)]}
        bulunan = loe._trafik_ekle(db, gruplar, *ARALIK)
        db.rollback()
    assert bulunan == {"ci-a": "ci_imt"}
    noktalar = loe.noktalar(gruplar["ci-a"])
    saatler = {datetime.fromtimestamp(n[0] / 1000, loe.TR).hour: n for n in noktalar}
    assert saatler[9][6:8] == [100.0, 50.0]  # CI adiyla eslesen arayuz
    assert saatler[11][6:8] == [None, None]  # 11:00 icin trafik yok
    assert saatler[10][6:8] == [40.0, 0.0] and saatler[10][1] is None and saatler[10][5] == 0  # Oracle olcumu olmayan saat: yalniz trafik
    assert saatler[9][1] == 1.0 and saatler[9][2] == 5.0  # Oracle metrikleri yerinde


def test_devre_imti_once_envanterden(mssql_acik):
    with oturum() as db:
        db.add(ReportCmdb(ciname="ci-a", customer_key="1", fields={"IMT": "100000000111"}, search_text="ci-a"))
        db.add(CustomerCi(customer_key="1", ci_name="ci-a", attrs={"imt": "100005049268"}))
        db.add(CustomerCi(customer_key="1", ci_name="ci-b", attrs={"imt": "1"}))
        db.commit()
        assert loe.devre_imtleri(db, ["ci-a", "ci-b", "ci-yok"]) == {"ci-a": "100005049268", "ci-b": "", "ci-yok": ""}


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


# --- IMT ile grafik (API) ve rapor kazanci -----------------------------------------------------------------
def _imtli_musteri() -> int:
    from conftest import musteri_ekle

    cati = musteri_ekle("Imt Musteri")
    istirak = musteri_ekle("Imt Istirak", ust=cati)
    with oturum() as db:
        from app.models import Customer

        db.get(Customer, cati).customer_no = "5001"
        db.get(Customer, istirak).customer_no = "5002"
        db.add(CustomerCi(customer_key="5002", ci_name="ci-ana", service="KURUMSAL INTERNET", status="ACTIVE", attrs={"imt": "100005049268"}))
        db.add(CustomerCi(customer_key="5002", ci_name="ci-yedek", service="KURUMSAL INTERNET", status="ACTIVE", attrs={"imt": "100005049268"}))
        db.add(CustomerCi(customer_key="9999", ci_name="ci-baskasi", attrs={"imt": "100009999999"}))
        db.add(CustomerCi(customer_key="5001", ci_name="ci-yer-tutucu", attrs={"imt": "1"}))
        db.commit()
    return cati


def test_imt_ile_arama_istirak_envanterinden_ci_bulur(istemci):
    kullanici_ekle("yonetici", "admin")
    mid = _imtli_musteri()
    giris(istemci, "yonetici")
    r = istemci.get(f"/api/v1/musteri/{mid}/rapor/devre-ara", params={"q": "100005049268"}).json()["data"]
    assert r["imt"] == "100005049268" and [s["ci"] for s in r["sonuclar"]] == ["ci-ana", "ci-yedek"]
    assert ("IMT", "100005049268") in [tuple(a) for a in r["sonuclar"][0]["alanlar"]]
    yer_tutucu = istemci.get(f"/api/v1/musteri/{mid}/rapor/devre-ara", params={"q": "100000000111"}).json()["data"]
    assert yer_tutucu["imt"] is None  # 3 haneli metin IMT sayilmaz, envanter yoluna girmez


def test_imt_ile_grafik_tum_devreler_ve_tum_metrikler(istemci):
    kullanici_ekle("yonetici", "admin")
    mid = _imtli_musteri()
    giris(istemci, "yonetici")
    r = istemci.post(f"/api/v1/musteri/{mid}/rapor/devreler", json={"imt": "100005049268"})
    assert r.status_code == 200, r.text
    assert sorted(e["ci"] for e in r.json()["data"]["eklenen"]) == ["ci-ana", "ci-yedek"]
    t = istemci.get(f"/api/v1/musteri/{mid}/rapor/trafik").json()["data"]
    assert t["ayar"]["metrikler"] == ["erisim", "trafik", "kayip", "jitter", "gecikme"]
    assert {d["ci"] for d in t["devreler"]} == {"ci-ana", "ci-yedek"} and "IMT" not in t["devreler"][0]["baslik"]
    # baska musterinin IMT'si bu karta eklenemez; gecersiz bicim dogrulamada reddedilir
    assert istemci.post(f"/api/v1/musteri/{mid}/rapor/devreler", json={"imt": "100009999999"}).status_code == 404
    assert istemci.post(f"/api/v1/musteri/{mid}/rapor/devreler", json={"imt": "-"}).status_code == 422


def test_rapor_kazanci_cati_ve_istirak_toplami(istemci):
    from conftest import musteri_ekle

    kullanici_ekle("yonetici", "admin")
    a = musteri_ekle("Cati A")
    musteri_ekle("Istirak A1", ust=a)
    musteri_ekle("Istirak A2", ust=a)
    musteri_ekle("Cati B")
    musteri_ekle("Toptan C", segment="WHOLESALE")  # baska alandaki kart da sayilir
    giris(istemci, "yonetici")
    k = istemci.get("/api/v1/rapor/durum").json()["data"]["kazanc"]
    assert (k["cati"], k["istirak"], k["musteri"], k["dakika"]) == (3, 2, 5, 15)
    assert k["saat_ay"] == 1.2 and k["adam_gun_ay"] == 0.2 and "5 müşteri (3 çatı + 2 iştirak)" in k["metin"]


def test_kopya_saatler_atilir_ayni_saat_tek_noktada_birlesir():
    kopya = [_satir(9) for _ in range(19)]  # kaynakta birebir tekrarlanan saat
    kesinti = {**_satir(10), "avail": 0.0, "loss": 4.0}  # ayni saatte iki farkli satir: kesinti + normal
    satirlar = loe.tekillestir([*kopya, kesinti, _satir(10)])
    assert len(satirlar) == 3
    n = loe.noktalar(satirlar)
    assert len(n) == 2  # saat basina tek nokta
    assert n[1][1] == 0.5 and n[1][4] == 0.02  # erisim = toplam avail / toplam total; kayip ortalama
    assert loe.ozet(satirlar)["saat"] == 3  # ozet kopyalari saymaz


# --- 2026-11-27 ekran hatasi: grafik ayari 422 ("Islem yapilamadi"), tarih sinirlari, IP etiketi -----------------
def test_grafik_ayari_tum_metrikler_ve_sinirsiz_aralik(istemci):
    from conftest import musteri_ekle

    kullanici_ekle("yonetici", "admin")
    mid = musteri_ekle("Musteri")
    giris(istemci, "yonetici")
    tum = ["erisim", "trafik", "kayip", "jitter", "gecikme"]
    r = istemci.put(f"/api/v1/musteri/{mid}/rapor/devre-ayar", json={"metrikler": tum})
    assert r.status_code == 200 and r.json()["data"]["metrikler"] == tum  # Availability isaretlenince 422 veriyordu
    uzun = {"metrikler": tum, "bas_zaman": "2019-01-01T00:00", "bit_zaman": "2026-10-31T23:59"}  # 2024 alti ve 366 gun ustu
    assert istemci.put(f"/api/v1/musteri/{mid}/rapor/devre-ayar", json=uzun).status_code == 200
    ters = {"metrikler": tum, "bas_zaman": "2026-10-31T23:59", "bit_zaman": "2026-10-01T00:00"}
    assert istemci.put(f"/api/v1/musteri/{mid}/rapor/devre-ayar", json=ters).status_code == 400


def test_imt_ile_grafik_raporun_donemine_doner(istemci):
    kullanici_ekle("yonetici", "admin")
    mid = _imtli_musteri()
    giris(istemci, "yonetici")
    ozel = {"metrikler": ["trafik"], "bas_zaman": "2026-09-01T00:00", "bit_zaman": "2026-09-30T23:59"}
    istemci.put(f"/api/v1/musteri/{mid}/rapor/devre-ayar", json=ozel)
    istemci.post(f"/api/v1/musteri/{mid}/rapor/devreler", json={"imt": "100005049268"})
    ayar = istemci.get(f"/api/v1/musteri/{mid}/rapor/trafik").json()["data"]["ayar"]
    assert ayar["aralik"] is None and len(ayar["metrikler"]) == 5


def test_devre_etiketi_ve_arama_ip_gostermez():
    from app.rapor import trafik

    alanlar = {"CINAME": "ci", "SERVICE": "KURUMSAL INTERNET", "IPADDRESS": "10.58.240.34", "MAXIMO_IP_ADDRESS": "10.1.1.1",
               "ADDRESS": "Vadi Istanbul", "DESCRIPTION": "uc 192.168.0.1 port"}  # fmt: skip
    etiket = trafik._etiket(alanlar)
    assert ("SERVICE", "KURUMSAL INTERNET") in etiket and ("ADDRESS", "Vadi Istanbul") in etiket
    assert not any(a in ("IPADDRESS", "MAXIMO_IP_ADDRESS", "DESCRIPTION") for a, _ in etiket)


def test_grafik_adini_kullanici_verir(istemci):
    from conftest import musteri_ekle

    kullanici_ekle("yonetici", "admin")
    mid = _imtli_musteri()
    giris(istemci, "yonetici")
    istemci.post(f"/api/v1/musteri/{mid}/rapor/devreler", json={"imt": "100005049268"})
    devreler = istemci.get(f"/api/v1/musteri/{mid}/rapor/trafik").json()["data"]["devreler"]
    assert all(d["baslik"] == "" for d in devreler)  # envanter / CMDB ayrintisi otomatik yazilmaz
    istemci.post(f"/api/v1/musteri/{mid}/rapor/devreler", json={"imt": "100005049268", "ad": "  Merkez   internet  hatti "})
    devreler = istemci.get(f"/api/v1/musteri/{mid}/rapor/trafik").json()["data"]["devreler"]
    assert {d["baslik"] for d in devreler} == {"Merkez internet hatti"}
    d = devreler[0]
    r = istemci.patch(f"/api/v1/musteri/{mid}/rapor/devreler/{d['id']}", json={"ad": "Yedek hat"})
    assert r.status_code == 200 and r.json()["data"]["ad"] == "Yedek hat"
    assert istemci.patch(f"/api/v1/musteri/{mid}/rapor/devreler/{d['id']}", json={"ad": ""}).json()["data"]["ad"] == ""
    baska = musteri_ekle("Baska Musteri")
    assert istemci.patch(f"/api/v1/musteri/{baska}/rapor/devreler/{d['id']}", json={"ad": "x"}).status_code == 404
