# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Musteri Erken Uyari: puan kurallari (saf), sinyal toplama (DB) ve portfoy gorunurlugu (API)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import giris, kayit_ekle, kullanici_ekle, musteri_ekle

from app.db import oturum
from app.musteri import erken_uyari as eu
from app.ortak import simdi


def puan(**alan) -> dict:
    return eu._puanla(eu._Sinyal(**alan))


# --- puan kurallari ------------------------------------------------------------------------------------
def test_sinyalsiz_musteri_normal():
    assert puan() == {"puan": 0, "seviye": "normal", "nedenler": []}


def test_alarm_ivmesi_oranla_puanlanir():
    # son 14 gunde 30 alarm, onceki 56 gunde 40 (14 gunluk ortalama 10) -> x3 -> (3-1)*10 = 20
    p = puan(alarm_son=30, alarm_taban=40)
    assert p["puan"] == 20 and p["nedenler"][0]["tur"] == "alarm"
    assert "×3,0" in p["nedenler"][0]["metin"]


@pytest.mark.parametrize(("son", "taban"), [(4, 0), (20, 56), (12, 40)])
def test_alarm_ivmesi_esik_alti_puan_vermez(son, taban):
    # 5'ten az alarm ya da artis x1,5'in altinda: sinyal yok
    assert puan(alarm_son=son, alarm_taban=taban)["puan"] == 0


def test_sikayet_yeni_ve_acik_ayri_sayilir():
    p = puan(sikayet_son=2, sikayet_acik=1)
    assert p["puan"] == 2 * 7 + 5
    assert "2 yeni şikayet" in p["nedenler"][0]["metin"] and "1 şikayet hâlâ açık" in p["nedenler"][0]["metin"]


def test_neden_metninde_sifir_parca_yok():
    metin = puan(bekleyen_alarm=3)["nedenler"][0]["metin"]
    assert "talep" not in metin and "3 alarm" in metin


@pytest.mark.parametrize(("adet", "beklenen"), [(3, 7), (6, 14), (19, 14), (20, 20), (500, 20)])
def test_tekrarlayan_ariza_en_kotu_ciya_gore(adet, beklenen):
    # musteri buyuklugu (CI sayisi) puani sisirmez: 40 CI'da 3'er alarm yine 7 puan
    assert puan(tekrar={"ci-a": adet})["puan"] == beklenen
    assert puan(tekrar={f"ci-{i}": 3 for i in range(40)})["puan"] == 7


def test_devre_esigi():
    assert puan(devre=[("d1", 0.999, 0.0001)])["puan"] == 0
    kotu = puan(devre=[("d1", 0.99, 0.0001), ("d2", 0.5, 0.5)])
    assert kotu["puan"] == eu.TAVAN["devre"] and "%99,00" in kotu["nedenler"][0]["metin"]


def test_toplam_100de_kirpilir_ve_nedenler_buyukten_kucuge():
    p = puan(alarm_son=500, alarm_taban=10, sikayet_son=9, sikayet_acik=9, bekleyen_is=9, tekrar={"x": 99}, devre=[("d", 0.1, 0.9)])
    assert p["puan"] == 100 and p["seviye"] == "kritik"
    katkilar = [n["puan"] for n in p["nedenler"]]
    assert katkilar == sorted(katkilar, reverse=True)


@pytest.mark.parametrize(("deger", "seviye"), [(0, "normal"), (14, "normal"), (15, "izle"), (34, "izle"), (35, "yuksek"), (59, "yuksek"), (60, "kritik")])
def test_seviye_esikleri(deger, seviye):
    assert eu.seviye(deger) == seviye


# --- sinyal toplama (veritabani) -----------------------------------------------------------------------------
def test_planli_calisma_haric_istirak_catiya_toplanir():
    cati = musteri_ekle("Cati AS")
    istirak = musteri_ekle("Istirak AS", ust=cati)
    kayit_ekle(istirak, "alarm", gun_once=2, adet=6, ci="ci-1")
    kayit_ekle(istirak, "alarm", gun_once=2, adet=50, ci="ci-2", kategori=eu.PLANLI)
    with oturum() as db:
        s = eu._sinyaller(db)
    assert set(s) == {cati}
    assert s[cati].alarm_son == 6 and s[cati].tekrar == {"ci-1": 6}


def test_silinmis_karta_bagli_kayit_yok_sayilir():
    kayit_ekle(None, "sikayet", gun_once=1, durum="open")
    with oturum() as db:
        assert eu._sinyaller(db) == {}


def test_gecmis_an_o_anki_acik_durumu_kullanir():
    # 20 gun once acilip 1 gun once kapanan sikayet: bugun kapali, 10 gun once ACIKTI (geriye donuk dogrulamada sizinti olmasin)
    m = musteri_ekle("Musteri")
    kayit_ekle(m, "sikayet", gun_once=20, kapanis_gun_once=1)
    with oturum() as db:
        assert m not in eu._sinyaller(db) or eu._sinyaller(db)[m].sikayet_acik == 0
        gecmis = eu._sinyaller(db, simdi() - timedelta(days=10))
    assert gecmis[m].sikayet_acik == 1 and gecmis[m].bekleyen_is == 1


def test_gecmis_an_sonraki_kayitlari_gormez():
    m = musteri_ekle("Musteri")
    kayit_ekle(m, "alarm", gun_once=1, adet=10, ci="ci")
    with oturum() as db:
        assert m not in eu._sinyaller(db, simdi() - timedelta(days=5))


# --- portfoy (API, gorunurluk) -----------------------------------------------------------------------------
def _riskli(sahip: int | None, ad: str) -> int:
    m = musteri_ekle(ad, sahip=sahip)
    kayit_ekle(m, "sikayet", gun_once=1, durum="open", adet=3)
    return m


def test_admin_portfoyde_risk_ve_uyarilari_gorur(istemci):
    kullanici_ekle("yonetici", "admin")
    sakin = musteri_ekle("Aaa Sakin")
    riskli = _riskli(None, "Zzz Riskli")
    assert giris(istemci, "yonetici").status_code == 200
    r = istemci.get("/api/v1/musteri/portfoy", params={"sira": "risk"}).json()["data"]
    assert [i["id"] for i in r["items"]] == [riskli, sakin]  # riske gore: ad sirasinin tersi
    assert r["items"][0]["risk"]["seviye"] != "normal" and r["items"][1]["risk"]["puan"] == 0
    assert [u["id"] for u in r["uyarilar"]] == [riskli]
    ad_sirasi = istemci.get("/api/v1/musteri/portfoy").json()["data"]
    assert [i["id"] for i in ad_sirasi["items"]] == [sakin, riskli]


def test_personel_yalniz_kendi_riskini_gorur(istemci):
    ben = kullanici_ekle("tcben")
    baskasi = kullanici_ekle("tcbaskasi")
    kendi = _riskli(ben, "Benim Musterim")
    baskasinin = _riskli(baskasi, "Baskasinin Musterisi")
    musteri_ekle("Benim Istirakim", sahip=ben, ust=baskasinin)  # baskasinin catisi cerceve olarak gorunur
    assert giris(istemci, "tcben").status_code == 200
    r = istemci.get("/api/v1/musteri/portfoy", params={"sira": "risk"}).json()["data"]
    assert {u["id"] for u in r["uyarilar"]} == {kendi}
    for i in r["items"]:
        assert (i["risk"] is None) == i["cerceve"], i


def test_sira_parametresi_dogrulanir(istemci):
    kullanici_ekle("yonetici", "admin")
    giris(istemci, "yonetici")
    assert istemci.get("/api/v1/musteri/portfoy", params={"sira": "drop table"}).status_code == 422


def test_neden_metni_istegin_dilinde(istemci):
    kullanici_ekle("yonetici", "admin")
    _riskli(None, "Riskli")
    giris(istemci, "yonetici")
    tr = istemci.get("/api/v1/musteri/portfoy").json()["data"]["uyarilar"][0]["nedenler"][0]["metin"]
    en = istemci.get("/api/v1/musteri/portfoy", headers={"X-Dil": "en"}).json()["data"]["uyarilar"][0]["nedenler"][0]["metin"]
    assert "şikayet" in tr and "complaints" in en


# --- bildirim ve musteri alanlari -----------------------------------------------------------------------------
def _kritik(sahip: int | None, ad: str, segment: str = "SA") -> int:
    m = musteri_ekle(ad, sahip=sahip, segment=segment)
    kayit_ekle(m, "sikayet", gun_once=2, durum="open", adet=3)
    kayit_ekle(m, "alarm", gun_once=3, adet=25, ci="ana-hat")
    kayit_ekle(m, "talep", gun_once=10, durum="open", adet=3)
    return m


def _bildirimler() -> list:
    from app.models import UserNotification

    with oturum() as db:
        return [(b.user_id, b.kind, b.ref_id, b.message, b.link) for b in db.query(UserNotification).order_by(UserNotification.id)]


def test_kritik_musterinin_tamina_bildirim_bir_kez():
    tam = kullanici_ekle("tcsorumlu")
    kritik = _kritik(tam, "Kritik Musteri")
    _kritik(None, "Sahipsiz Kritik")
    _riskli(tam, "Yalniz Izle")  # kritik degil: bildirim yok
    with oturum() as db:
        assert eu.bildir(db) == {"kritik": 2, "gonderilen": 1, "atlanan": 1}
        db.commit()
    [(kisi, tur, ref, mesaj, adres)] = _bildirimler()
    assert (kisi, tur, ref) == (tam, eu.BILDIRIM_TURU, kritik)
    assert "Kritik Musteri kritik seviyede" in mesaj and adres == f"#/musteri?m={kritik}"
    with oturum() as db:  # sonraki tur: 7 gun dolmadan tekrar yok
        assert eu.bildir(db)["gonderilen"] == 0
        db.commit()
    assert len(_bildirimler()) == 1


def test_bildirim_toptan_kartlarini_da_kapsar():
    tam = kullanici_ekle("tctoptan")
    toptan = _kritik(tam, "Toptan Musteri", segment="WHOLESALE")
    with oturum() as db:
        assert eu.bildir(db)["gonderilen"] == 1
        db.commit()
    assert _bildirimler()[0][4] == f"#/toptan?m={toptan}"


def test_toptan_ekrani_kendi_riskini_gorur(istemci):
    # onbellek musteri alanina gore ayrilir: once Musteri Yonetimi acilsa da Toptan kartinin riski kaybolmaz
    kullanici_ekle("yonetici", "admin")
    _riskli(None, "Normal Alan Musterisi")
    toptan = _kritik(None, "Toptan Riskli", segment="WHOLESALE")
    giris(istemci, "yonetici")
    istemci.get("/api/v1/musteri/portfoy")
    r = istemci.get("/api/v1/musteri/portfoy", headers={"X-Musteri-Alani": "toptan"}).json()["data"]
    assert [u["id"] for u in r["uyarilar"]] == [toptan] and r["uyarilar"][0]["seviye"] == "kritik"


# --- musteri karti ve bildirim yaniti ----------------------------------------------------------------------
def test_cati_kartinda_risk_istirak_kartinda_yok(istemci):
    kullanici_ekle("yonetici", "admin")
    cati = _kritik(None, "Cati Kritik")
    istirak = musteri_ekle("Cati Istirak", ust=cati)
    giris(istemci, "yonetici")
    kart = istemci.get(f"/api/v1/musteri/{cati}").json()["data"]["operasyon"]["erken_uyari"]
    assert kart["seviye"] == "kritik" and kart["nedenler"]
    assert istemci.get(f"/api/v1/musteri/{istirak}").json()["data"]["operasyon"]["erken_uyari"] is None


def _bildirim_uret(tam: int) -> int:
    _kritik(tam, "Kritik Musteri")
    with oturum() as db:
        eu.bildir(db)
        db.commit()
    return _bildirimler()[0]


def test_tam_kendi_bildirimine_yanit_verir_ve_ozete_yansir(istemci):
    from app.models import UserNotification

    tam = kullanici_ekle("tcsorumlu")
    _bildirim_uret(tam)
    with oturum() as db:
        bid = db.query(UserNotification.id).scalar()
    giris(istemci, "tcsorumlu")
    zil = istemci.get("/api/v1/bildirim").json()["data"]["son"][0]
    assert zil["yanitlanir"] is True and zil["yanit"] == ""
    assert istemci.post(f"/api/v1/bildirim/{bid}/yanit", json={"karar": "uydurma"}).status_code == 422
    r = istemci.post(f"/api/v1/bildirim/{bid}/yanit", json={"karar": "ilgilendim"})
    assert r.status_code == 200 and r.json()["data"]["yanit"] == "ilgilendim"
    zil = istemci.get("/api/v1/bildirim").json()["data"]
    assert zil["son"][0]["yanit"] == "ilgilendim" and zil["okunmamis"] == 0
    oz = istemci.get("/api/v1/musteri/portfoy").json()["data"]["uyari_ozet"]
    assert (oz["bildirim"], oz["ilgilendim"], oz["gerekmedi"], oz["yanitsiz"]) == (1, 1, 0, 0)


def test_baskasinin_bildirimine_yanit_verilemez(istemci):
    from app.models import UserNotification

    tam = kullanici_ekle("tcsorumlu")
    kullanici_ekle("tcbaskasi")
    _bildirim_uret(tam)
    with oturum() as db:
        bid = db.query(UserNotification.id).scalar()
    giris(istemci, "tcbaskasi")
    assert istemci.post(f"/api/v1/bildirim/{bid}/yanit", json={"karar": "gerekmedi"}).status_code == 404
    oz = istemci.get("/api/v1/musteri/portfoy").json()["data"]["uyari_ozet"]
    assert oz["bildirim"] == 0  # personel ozette yalniz kendi bildirimlerini gorur


def test_yanitlanamayan_bildirim_turu_404(istemci):
    from app.bildirim import servis as bildirim

    tam = kullanici_ekle("tcsorumlu")
    with oturum() as db:
        bildirim.ekle(db, tam, "talep", "Talebiniz guncellendi", "#/talep", 1)
        db.commit()
    from app.models import UserNotification

    with oturum() as db:
        bid = db.query(UserNotification.id).scalar()
    giris(istemci, "tcsorumlu")
    assert istemci.get("/api/v1/bildirim").json()["data"]["son"][0]["yanitlanir"] is False
    assert istemci.post(f"/api/v1/bildirim/{bid}/yanit", json={"karar": "ilgilendim"}).status_code == 404
