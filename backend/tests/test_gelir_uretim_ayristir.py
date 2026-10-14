"""Gelir Faydasi Saglanan Isler: Excel hucre ayristiricilari (saf fonksiyonlar). Kural: guvenle cevrilemeyen metin sayiya cevrilmez, nota kalir."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.gelir_uretim import ayristir as a

BUGUN = date(2026, 10, 13)


# --- tutar (F sutunu) ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "metin,miktar,para,donem",
    [
        ("88,2 KTL/ay", 88200.0, "TRY", "ay"),  # ondalik virgul + K carpani, kayan nokta hatasi yok
        ("512K TL /ay", 512000.0, "TRY", "ay"),
        ("3,7K TL/ay", 3700.0, "TRY", "ay"),
        ("120K TL /ay", 120000.0, "TRY", "ay"),
        ("52K TL / ay", 52000.0, "TRY", "ay"),
        ("7210 TL/ay", 7210.0, "TRY", "ay"),
        ("118.425 TL/ay", 118425.0, "TRY", "ay"),  # TR binlik noktasi
        ("1.234.567 TL/ay", 1234567.0, "TRY", "ay"),
        ("1.234,56 TL/ay", 1234.56, "TRY", "ay"),
        ("1,7 M TL / Aylık", 1700000.0, "TRY", "ay"),
        ("5,148M TL/ay", 5148000.0, "TRY", "ay"),  # ondalik virgul + uc hane ancak carpanla ondalik sayilir
        ("2.5 M TL/ay", 2500000.0, "TRY", "ay"),
        ("140bin ₺ / Aylık", 140000.0, "TRY", "ay"),
        ("3 milyon TL / yıllık", 3000000.0, "TRY", "yil"),
        ("1250,75 $ / ay", 1250.75, "USD", "ay"),
        ("250 USD/ay", 250.0, "USD", "ay"),
        ("900 eurox4 adet (tek seferlik)", 3600.0, "EUR", "tek_sefer"),  # adet carpani
        ("900 eurox3 adet (tek seferlik)", 2700.0, "EUR", "tek_sefer"),
        ("12000 TL tek seferlik", 12000.0, "TRY", "tek_sefer"),
        ("40 K TL/yıl", 40000.0, "TRY", "yil"),
    ],
)
def test_tutar_bicimleri(metin, miktar, para, donem):
    t = a.tutar_ayristir(metin)
    assert (t.miktar, t.para, t.donem, t.neden) == (miktar, para, donem, "")


def test_tutar_sayisal_hucre_tl_ay_sayilir():
    assert a.tutar_ayristir(7210) == a.Tutar(miktar=7210.0, para="TRY", donem="ay")
    assert a.tutar_ayristir(1250.5).miktar == 1250.5


def test_tutar_kalan_metin_nota_gider():
    t = a.tutar_ayristir("88,2 KTL/ay (son ölçüm) -düzenli artıyor.")
    assert t.miktar == 88200.0 and t.ek == "(son ölçüm) -düzenli artıyor."
    assert a.tutar_ayristir("500 TL/ay").ek == ""
    # adetle carpilan tutarda hesabin gorunmesi icin asil metin kalir
    assert a.tutar_ayristir("900 eurox4 adet (tek seferlik)").ek == "900 eurox4 adet (tek seferlik)"


@pytest.mark.parametrize(
    "metin,neden",
    [
        ("Çalışma sürüyor", "sayi_yok"),
        ("yok/hesaplanamıyor", "sayi_yok"),
        ("Müşteriden bilgi bekleniyor.", "sayi_yok"),
        ("Devam ediyor", "sayi_yok"),
        ("Tasarruf ", "sayi_yok"),
        ("gider tasarrufu olduğundan verimliliğe yazıldı", "sayi_yok"),
        ("yok", "sayi_yok"),
        ("15,8 KTL", "donem_yok"),  # donem yoksa aylik sayilmaz
        ("2,1 M TL", "donem_yok"),
        ("318,500 ₺ + KDV", "sayi_belirsiz"),  # tek virgul + 3 hane, carpansiz: binlik mi ondalik mi belli degil
        ("12.5.2026 itibariyle 5 TL/ay", "coklu"),
        ("450K TL/ay\n18 ay top.:8.100.000 TL", "coklu"),  # birden fazla sayi
        ("5,148M TL/ay + 412,7K TL/ay", "coklu"),
        ("Her biri 5 gün: 1200x2100=2,5 milyon TL etki\n380K TL/ay", "coklu"),
        ("100 TL ve 20 USD /ay", "coklu"),  # birden fazla para birimi
        ("100 TL aylık yıllık", "coklu"),  # birden fazla donem
    ],
)
def test_tutar_ayristirilamayan_nota_kalir(metin, neden):
    t = a.tutar_ayristir(metin)
    assert t.miktar is None and t.neden == neden
    assert t.ek == " ".join(metin.split())  # metin kaybolmaz


def test_tutar_bos_degerler():
    for bos in (None, "", "   ", "-", "—", "."):
        assert a.tutar_ayristir(bos) == a.Tutar()
    assert a.tutar_ayristir(-5).miktar is None  # negatif sayisal hucre kabul edilmez


# --- sayi jetonu -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "jeton,carpanli,beklenen",
    [
        ("88,2", False, "88.2"),
        ("118.425", False, "118425"),
        ("1.234,56", False, "1234.56"),
        ("1,234.56", False, "1234.56"),
        ("1,234,567", False, "1234567"),
        ("2.2", False, "2.2"),
        ("5,148", True, "5.148"),
        ("5,148", False, None),  # belirsiz
        ("7.10.2026", False, None),  # tarih sayi degildir
        ("1.2345", False, None),
        ("abc", False, None),
    ],
)
def test_sayi_degeri(jeton, carpanli, beklenen):
    sonuc = a.sayi_degeri(jeton, carpanli)
    assert (None if sonuc is None else str(sonuc)) == beklenen


# --- saat (G sutunu) -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("metin,saat", [("36 Saat / Ay", 36.0), ("12,5 saat/ay", 12.5), ("8 saat aylık", 8.0), (40, 40.0)])
def test_saat_bicimleri(metin, saat):
    s = a.saat_ayristir(metin)
    assert s.saat == saat and s.neden == ""


@pytest.mark.parametrize(
    "metin,neden",
    [
        ("Çalışma sürüyor", "sayi_yok"),
        ("yok", "sayi_yok"),
        ("Otomasyonla iş gücü tasarrufu: yaklaşık 2,4 adamgün/ay beklenir.", "birim"),  # adamgun -> saat donusumu yapilmaz
        ("98,5K TL/ay elde edildi.", "birim"),  # para saat sutununa yazilmis
        ("12 saat", "donem_yok"),
        ("120 saat/yıl", "donem_yok"),
        ("36 saat ve 4 saat / ay", "coklu"),
        ("420 şube yenilemesi ile 2,6 MTL tasarruf edildi", "coklu"),
    ],
)
def test_saat_ayristirilamayan_nota_kalir(metin, neden):
    s = a.saat_ayristir(metin)
    assert s.saat is None and s.neden == neden and s.ek == " ".join(metin.split())


# --- yil ici gelir (K sutunu) ----------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "metin,tutar",
    [
        ("2026 yılı içi gelir: 1 MTL", 1_000_000.0),
        ("2026 yılı içi gelir: 3,4 MTL", 3_400_000.0),
        ("2026 yılı içi gelir: 275,6 KTL", 275_600.0),
        ("2026 yılı içi gelir: 120 KTL", 120_000.0),
        ("2026 yılı içi gelir: 75 KTL (listeyi güncelle)", 75_000.0),
        (12000, 12000.0),
    ],
)
def test_yil_ici_gelir(metin, tutar):
    assert a.yil_ici_ayristir(metin).tutar == tutar


def test_yil_ici_gelir_kalan_not_ve_reddedilenler():
    assert a.yil_ici_ayristir("2026 yılı içi gelir: 75 KTL (listeyi güncelle)").ek == "(listeyi güncelle)"
    assert a.yil_ici_ayristir("2026 yılı içi gelir: 1.000 USD").neden == "para"  # TL disi para birimi TL sutununa yazilmaz
    assert a.yil_ici_ayristir("bilinmiyor").neden == "sayi_yok"
    assert a.yil_ici_ayristir("2026 yılı içi gelir: 1 MTL + 2 MTL").neden == "coklu"
    assert a.yil_ici_ayristir(None) == a.YilIci()


# --- tarih (I / J sutunlari) -----------------------------------------------------------------------------------------
def test_tarih_hucreleri_ve_metinler():
    assert a.tarih_ayristir(datetime(2026, 4, 1)).tarih == date(2026, 4, 1)
    assert a.tarih_ayristir(date(2026, 4, 1)).tarih == date(2026, 4, 1)
    assert a.tarih_ayristir(" 15.05.2026").tarih == date(2026, 5, 15)
    assert a.tarih_ayristir("1/2/2026").tarih == date(2026, 2, 1)  # gun/ay/yil
    assert a.tarih_ayristir("2026-05-01").tarih == date(2026, 5, 1)
    ilk = a.tarih_ayristir("6.08.2026 (revize 22.9.2026 tarihli)")
    assert ilk.tarih == date(2026, 8, 6) and ilk.ek == "(revize 22.9.2026 tarihli)"
    # ay + yil: baslangicta ayin ilk, bitiste ayin son gunu
    assert a.tarih_ayristir("Ağustos 2026").tarih == date(2026, 8, 1)
    assert a.tarih_ayristir("Eylul 2026", son=True).tarih == date(2026, 9, 30)
    assert a.tarih_ayristir("February 2028", son=True).tarih == date(2028, 2, 29)
    # gecersiz ya da tanimsiz metin tarih olmaz, metin kaybolmaz
    assert a.tarih_ayristir("31.02.2026") == a.Tarih(ek="31.02.2026")
    assert a.tarih_ayristir("bilinmiyor") == a.Tarih(ek="bilinmiyor")
    assert a.tarih_ayristir(None) == a.Tarih() and a.tarih_ayristir("  ") == a.Tarih()


@pytest.mark.parametrize(
    "metin,isaret,ek",
    [
        ("devam ediyor", "devam", ""),
        ("Devam Ediyor", "devam", ""),
        ("başlamadı", "baslamadi", ""),
        ("Tamamlandı", "tamamlandi", ""),
        ("Proje iptal edildi; talep sahibine bildirildi.", "iptal", "Proje iptal edildi; talep sahibine bildirildi."),
    ],
)
def test_tarih_durum_ipuclari(metin, isaret, ek):
    t = a.tarih_ayristir(metin)
    assert t.tarih is None and t.isaret == isaret and t.ek == ek


# --- durum -----------------------------------------------------------------------------------------------------------
def _d(c, i=None, j=None, bugun=BUGUN):
    return a.durum_cikar(c, a.tarih_ayristir(i), a.tarih_ayristir(j, son=True), bugun)


def test_durum_guncel_durum_ilk_sozcuk_kazanir():
    assert _d("Devam ediyor.//7.10.2026") == "devam"
    assert _d("Devam Ediyor //7.10.2026") == "devam"
    assert _d("Tamamlandı. //18.8.2026") == "tamamlandi"
    assert _d("Tamamlandı//22.9.2026") == "tamamlandi"
    assert _d("\nTamamlandı") == "tamamlandi"
    assert _d("Başlanmadı, bütçe bekleniyor") == "baslamadi"
    assert _d("İptal edildi") == "iptal"
    # cumle ortasindaki sozcuk durum degildir: bitis sutunu belirler
    assert _d("Alfa geçişi tamamlandı. Diğerleri sürüyor.", j="devam ediyor") == "devam"
    # "Devam ediyor" ilk sozcukse bitisteki iptal ipucunu da gecer (acik durum metni onceliklidir)
    assert _d("Devam ediyor", j="iptal") == "devam"


def test_durum_yedekleri():
    assert _d("Ücretsiz yenileme kararı...", j="Proje iptal edildi; talep sahibine bildirildi.") == "iptal"
    assert _d("Pilot bekleniyor", i="başlamadı") == "baslamadi"
    assert _d("Pilot bekleniyor", j="devam ediyor") == "devam"
    assert _d("Kurulum yapıldı", j=date(2026, 5, 1)) == "tamamlandi"  # gecmis bitis tarihi
    assert _d("Kurulum yapıldı", j=date(2027, 5, 1)) == "devam"  # gelecek bitis tarihi
    assert _d("", i=date(2026, 4, 1)) == "devam"
    assert a.durum_oneki("hiçbir şey") is None


# --- kisi adlari -----------------------------------------------------------------------------------------------------
def test_kisi_bolme():
    assert a.kisi_bol("Ali Örnek, Veli Deneme, Ayşe Test Soyad") == ["Ali Örnek", "Veli Deneme", "Ayşe Test Soyad"]
    assert a.kisi_bol("Ali Örnek- Veli Deneme") == ["Ali Örnek", "Veli Deneme"]
    assert a.kisi_bol("Ali Örnek-Veli Deneme") == ["Ali Örnek", "Veli Deneme"]
    assert a.kisi_bol("Ali Örnek & Veli Deneme & Can Test") == ["Ali Örnek", "Veli Deneme", "Can Test"]
    assert a.kisi_bol("Ali Örnek ve Veli Deneme") == ["Ali Örnek", "Veli Deneme"]
    assert a.kisi_bol("Ali Örnek; Veli Deneme / Can Test + Ece Deneme") == ["Ali Örnek", "Veli Deneme", "Can Test", "Ece Deneme"]
    assert a.kisi_bol("Ali Örnek\nVeli Deneme") == ["Ali Örnek", "Veli Deneme"]
    assert a.kisi_bol("  Selim Deneme  ") == ["Selim Deneme"]
    assert a.kisi_bol("Ali Örnek, ali örnek , ALİ ÖRNEK") == ["Ali Örnek"]  # yinelenen atilir (harf farksiz)
    assert a.kisi_bol(None) == [] and a.kisi_bol("") == [] and a.kisi_bol(" , - ") == [] and a.kisi_bol("A") == []
    assert a.kisi_bol("Veli Deneme VE Ali") == ["Veli Deneme", "Ali"]


# --- baslik haritasi ve bolum satiri ---------------------------------------------------------------------------------
def test_baslik_haritasi_kaynak_basliklari():
    satir = [
        "İlgili TAM",
        "İşin özeti",
        "Güncel durum",
        "Detaylı açıklaması",
        "Hangi müşteri/müşterileri etkilediği",
        "Aylık gelir faydası (TL/ay)",
        "Aylık verimlilik faydası (saat efor kazancı/ay)",
        "Ek açıklamalar",
        "Proje/çalışma başlangıç tarihi",
        "Proje/çalışma bitiş tarihi",
        None,
    ]
    assert a.baslik_haritasi(satir) == {
        "tam": 0, "baslik": 1, "durum": 2, "aciklama": 3, "musteri": 4, "gelir": 5, "verimlilik": 6, "ek": 7, "baslangic": 8, "bitis": 9,
    }  # fmt: skip


def test_baslik_haritasi_disa_aktarim_basliklari_ve_buyuk_kucuk_farki():
    from app.gelir_uretim.excel import BASLIKLAR

    h = a.baslik_haritasi(list(BASLIKLAR))
    assert h["yil_ici"] == 10 and h["fayda_turu"] == 11 and h["baslik"] == 1 and h["ek"] == 7
    assert a.baslik_haritasi(["ILGILI tam", "ISIN OZETI", "GUNCEL DURUM"]) == {"tam": 0, "baslik": 1, "durum": 2}
    assert a.baslik_haritasi(["Foo", "Bar", None]) == {}


def test_bolum_turu():
    assert a.bolum_turu("Tam Gelir Artırıcı Aldığımız İnsiyatifler") == "inisiyatif"
    assert a.bolum_turu("TAM inisiyatifleri") == "inisiyatif"
    assert a.bolum_turu("Planlı projeler") == "proje"
    assert a.bolum_turu("Diğer") is None


def test_baslik_anahtari_turkce_ve_bosluk_farksiz():
    assert a.baslik_anahtari("  İşin   ÖZETİ ") == a.baslik_anahtari("isin ozeti")
    assert a.katla("ÇĞİÖŞÜ ıi") == "cgiosu ii"
    assert len(a.katla("Ağaç İ")) == len("Ağaç İ")  # konumlar korunur


# --- "deger yok" isaretleri ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("metin", ["yok", "Yok", "YOK.", " yok ", "yoktur", "-", "--", "–", "—", "n/a", "N/A", "\xa0yok\xa0"])
def test_bos_isareti_hucrenin_tamami_isaretse_dogru(metin):
    assert a.bos_isareti(metin) is True


@pytest.mark.parametrize("metin", ["", None, "ek gelir yok", "yok ama izleniyor", "yoktu", "1 yok", "Çalışma sürüyor", "na", "...", 0, "0 TL/ay"])
def test_bos_isareti_cumleler_ve_degerler_isaret_degildir(metin):
    assert a.bos_isareti(metin) is False
