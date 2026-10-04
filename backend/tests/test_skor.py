"""Skor motoru: uretimden alinan sabit vektorlerle esdegerlik.

tests/skor_golden.json uretim skor_motoru.py calistirilarak uretildi (2026-10-04).
Uretim dosyasi bu makinede varsa ayrica canli karsilastirma da yapilir.
"""

import importlib.util
import json
import pathlib

import pytest

from app import skor

GOLD = json.loads((pathlib.Path(__file__).with_name("skor_golden.json")).read_text(encoding="utf-8"))
PROD = pathlib.Path(r"D:\Project\TAM_Life\TAMLIFE\backend\app\kutucuklar\utilizasyon\skor_motoru.py")


def _ozet(r):
    return {
        "skor": r["skor"],
        "eksik": r["eksik"],
        "tamam": r["tamam"],
        "agirlik_toplami": r["agirlik_toplami"],
        "puanlar": [[k["tur"], k["puan"], k["durum"]] for k in r["kriterler"]],
    }


@pytest.mark.parametrize("vaka", GOLD["cases"], ids=lambda v: v["ad"])
def test_musteri_skoru_uretimle_ayni(vaka):
    r = skor.musteri_skoru(vaka["kriterler"], vaka["metrikler"], vaka["manuel"])
    assert json.loads(json.dumps(_ozet(r))) == vaka["beklenen"]


def test_aralik_ve_kategori_ve_normal_ve_tur():
    for girdi, beklenen in GOLD["aralik"]:
        got = skor.aralik_ayikla(girdi)
        assert (list(got) if got else None) == beklenen, girdi
    for girdi, beklenen in GOLD["kategori"]:
        assert sorted(skor.kategori_tokenlari(girdi)) == beklenen, girdi
    for girdi, beklenen in GOLD["normal"]:
        assert skor.normal(girdi) == beklenen
    for baslik, tur in GOLD["tur"]:
        assert skor.tur_coz({"title": baslik}) == tur


def test_barem_sinirlari_ve_ust_sinir():
    k = [{"title": "Şikayet", "weight": 10}]
    puan = lambda n: skor.musteri_skoru(k, {"sikayet_talep": {"deger": n, "kaynak": "t"}})["skor"]
    assert [puan(n) for n in (0, 1, 49, 50, 200, 500)] == [0.0, 30.0, 30.0, 50.0, 70.0, 100.0]
    assert skor.musteri_skoru([{"title": "x", "weight": 10, "type": "auto_onedesk"}], {"sikayet_talep": {"deger": 9999, "kaynak": "t"}})["skor"] <= 100


def test_eksik_kriter_tamam_degil():
    r = skor.musteri_skoru([{"title": "Şikayet", "weight": 10}, {"title": "Rapor", "weight": 10}], {"sikayet_talep": {"deger": 100, "kaynak": "t"}})
    assert r["eksik"] == ["Rapor"] and r["tamam"] is False


@pytest.mark.skipif(not PROD.is_file(), reason="uretim dosyasi bu makinede yok")
def test_canli_uretim_dosyasiyla_ayni():
    spec = importlib.util.spec_from_file_location("prod_skor", PROD)
    prod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prod)
    for vaka in GOLD["cases"]:
        a = skor.musteri_skoru(vaka["kriterler"], vaka["metrikler"], vaka["manuel"])
        b = prod.musteri_skoru(vaka["kriterler"], vaka["metrikler"], vaka["manuel"])
        assert a == b, vaka["ad"]
