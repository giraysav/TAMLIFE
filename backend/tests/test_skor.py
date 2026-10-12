"""Skor motoru: eski panelden alinan sabit vektorlerle esdegerlik.

tests/skor_golden.json eski panelin skor_motoru.py dosyasi calistirilarak uretildi (2026-10-04; 'X:' ile baslayan sabit puan
vakalari 2026-10-10). Eski panel kapatildigi icin canli karsilastirma yoktur; referans bu dosyadir.
"""

import json
import pathlib

import pytest

from app.skor import motor as skor

GOLD = json.loads((pathlib.Path(__file__).with_name("skor_golden.json")).read_text(encoding="utf-8"))


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


def test_x_sabit_puan_kurali():
    soz = {"title": "Sözleşme", "weight": 20, "b30": "1-49.999", "b50": "", "b70": "x", "b100": "1.000.000+"}
    r = skor.musteri_skoru([soz], {})  # veri gerekmez
    assert r["tamam"] and r["skor"] == 70.0 and r["kriterler"][0]["kaynak"] == "Sabit puan (X işareti)" and r["kriterler"][0]["deger"] == "X"
    assert skor.sabit_puan({"title": "Raporlama", "b30": "X", "b50": "X"}) is None  # birden cok X belirsiz
    assert skor.sabit_puan({"title": "Segment", "b100": "X"}) is None  # yalniz Sozlesme / Raporlama
    assert skor.kural_puani({"title": "Raporlama", "b100": "X"}, 0) == (100, 0)
    assert sum(1 for v in GOLD["cases"] if v["ad"].startswith("X:")) >= 10  # golden'da X vakalari var


def test_varsayilan_kriterler_uretim_modeli():
    k = skor.varsayilan_kriterler()
    assert [x["weight"] for x in k] == [20, 20, 5, 5, 15, 20, 15]
    assert [skor.tur_coz(x) for x in k] == [
        "auto_onedesk", "servis_cesitliligi", "auto_servis_sayisi", "auto_baglanti", "auto_segment", "auto_sozlesme", "auto_rapor"
    ]
    k[0]["weight"] = 99
    assert skor.VARSAYILAN_KRITERLER[0]["weight"] == 20  # kopya doner
