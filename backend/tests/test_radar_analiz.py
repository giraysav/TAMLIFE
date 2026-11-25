"""Musteri Radar yonetim sunumu (radar.analiz): yalniz Radar'a atanan kartsiz numaralar; ariza profili (kesinti suresi, etki turu, CI
adindan hizmet turu ve yedek hat), satis onerileri, firsat skoru; sikayet / talep erisimi yok; YZ yorumu kapaliysa 503, aciksa saklanir
ve modele musteri / lokasyon adi gitmez."""

from sqlalchemy.orm import Session

from app.db import engine
from app.radar import analiz
from app.tampon import temip_atama
from tests.conftest import login_ok
from tests.test_temip_kayit import SahteTemip, calistir, kart, tsatir

URL = "/api/v1/radar"


def _kur(monkeypatch):
    kart("ORNEK-KARTLI", "10000001")
    t = SahteTemip(monkeypatch)
    s = lambda k, no, ci, baslik="AVAILABILITY", **e: {**tsatir(k, no, unvan="ORNEK LOJISTIK A.S." if no == "30000003" else "ORNEK GIDA", ci=ci, **e), "BASLIK": baslik}
    t.kapali = [
        s("1", "30000003", "nw_li_cust_3g_ornekdepo_yedek_ssr", acilis="2026-10-17 10:00:00", kapanis="2026-10-17 10:03:00", durum="Closed/Auto-Clear"),
        s("2", "30000003", "nw_li_cust_tt_me_vpn_ornekmerkez_sdwan", acilis="2026-10-17 10:00:00", kapanis="2026-10-17 12:00:00", durum="Closed/atm"),
        s("3", "30000003", "nw_li_cust_me_ornekanampls_nw_rt_ne40_01", acilis="2026-10-17 10:00:00", kapanis="2026-10-17 20:00:00"),
        s("4", "30000003", "nw_li_cust_me_ornekanampls_nw_rt_ne40_01", baslik="DELAY", acilis="2026-10-17 10:00:00", kapanis="2026-10-17 10:30:00"),
    ]
    t.acik = [
        s("5", "30000003", "nw_li_cust_tsol_me_int_ornekfabrika"),
        s("6", "40000004", "nw_li_cust_va_sdsl_ornekgida"),
        s("7", "50000005", "nw_li_cust_x"),  # Radar'a atanmamis: sunumda yok
        s("8", "10000001", "nw_li_cust_y"),  # kartli
    ]
    calistir()
    with Session(engine()) as db:
        assert temip_atama.radara_gonder(db, ["30000003", "40000004"], "admin")["atanan"] == 2


def _bilet(no: str, tur: str, durum: str, konu: str, kart_id: int | None = None) -> None:
    from app.models import OnedeskRecord
    from app.onedesk import canli

    with Session(engine()) as db:
        n = db.query(OnedeskRecord).count()
        db.add(OnedeskRecord(source=canli.KAYNAK_ADI, external_key=f"OD-{n}", customer_no=no, customer_id=kart_id, kind=tur, status=durum, category=konu))
        db.commit()


def test_portfoy_ariza_profili_hizmet_oneri_ve_skor(client, monkeypatch):
    _kur(monkeypatch)
    # 3c9e5e2 (karar A): Radar numaralarinin kartsiz sikayet / talep kayitlari musteri basina ozetlenir (eskiden 'erisim yok')
    _bilet("30000003", "sikayet", "open", "Hız")
    _bilet("30000003", "sikayet", "closed", "Hız")
    _bilet("30000003", "talep", "closed", "Nakil")
    _bilet("50000005", "sikayet", "open", "Hız")  # Radar'a atanmamis: sayilmaz
    login_ok(client)
    d = client.get(f"{URL}/sunum").json()["data"]
    assert d["musteri_sayisi"] == 2 and d["toplam_alarm"] == 6 and d["acik_alarm"] == 2
    assert "sikayet_talep" not in d and d["yz"]["hazir"] is False
    m = next(x for x in d["musteriler"] if x["musteri_no"] == "30000003")
    assert m["sikayet_talep"] == {
        "sikayet": 2, "talep": 1, "sikayet_acik": 1, "talep_acik": 0,
        "konular": [{"ad": "Hız", "adet": 2, "sikayet": 2, "talep": 0}, {"ad": "Nakil", "adet": 1, "sikayet": 0, "talep": 1}],
    }  # fmt: skip
    m2 = next(x for x in d["musteriler"] if x["musteri_no"] == "40000004")
    assert m2["sikayet_talep"]["sikayet"] == 0 and m2["sikayet_talep"]["konular"] == []
    assert {x["anahtar"]: x["adet"] for x in m["sure_profili"]} == {"anlik": 1, "kisa": 1, "uzun": 1, "cok_uzun": 1}
    assert [x["anahtar"] for x in m["sure_profili"]] == ["anlik", "kisa", "uzun", "cok_uzun"]  # sabit sira
    assert m["uzun_oran"] == 50.0 and m["anlik_oran"] == 25.0 and m["kalite_oran"] == 20.0 and m["medyan_cozum_dk"] == 75
    assert {x["anahtar"]: x["adet"] for x in m["etki"]} == {"AVAILABILITY": 4, "DELAY": 1}
    assert {h["ad"]: h["lokasyon"] for h in m["hizmetler"]} == {"Mobil erişim (3G/4.5G)": 1, "SD-WAN": 1, "MPLS": 1, "İnternet": 1}
    assert m["lokasyon_sayisi"] == 4 and m["sdwan_oran"] == 25.0 and m["yedek_oran"] == 25.0
    basliklar = [o["baslik"] for o in m["oneriler"]]
    assert basliklar[0].startswith("Mevcut yedek hatların") and "Kapasite artışı ve QoS" in basliklar
    assert 0 <= m["skor"] <= 100 and m["firsat"] in ("yuksek", "orta", "dusuk") and m["ozet"][0].startswith("5 ağ alarmı")
    assert [x["anahtar"] for x in d["sure_profili"]] == ["anlik", "kisa", "uzun", "cok_uzun"]
    assert client.get(f"{URL}/30000003/analiz").json()["data"]["musteri_no"] == "30000003"
    assert client.get(f"{URL}/50000005/analiz").status_code == 404  # Radar'a atanmamis


def test_yz_kapaliyken_503_acikken_saklanir_musteri_adi_gitmez(client, monkeypatch):
    _kur(monkeypatch)
    hdr = login_ok(client)
    for ad in ("TAMLIFE_YZ_SAGLAYICI", "TAMLIFE_YZ_VERI_PAYLASIMI", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(ad, raising=False)
    assert client.post(f"{URL}/30000003/yz", headers=hdr).status_code == 503
    giden = {}
    from app.onedesk import yz

    monkeypatch.setattr(yz, "tamamla", lambda icerik, **k: giden.setdefault("istem", icerik) and "1) Durum: ornek")
    monkeypatch.setattr(yz, "durum", lambda: {"hazir": True, "model": "ornek-model", "eksik": [], "saglayici": "anthropic"})
    r = client.post(f"{URL}/30000003/yz", headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["metin"] == "1) Durum: ornek"
    assert "ORNEK LOJISTIK" not in giden["istem"] and "nw_li_cust" not in giden["istem"] and "Uzun (1–8 sa)" in giden["istem"]
    m = next(x for x in client.get(f"{URL}/sunum").json()["data"]["musteriler"] if x["musteri_no"] == "30000003")
    assert m["yz"]["metin"] == "1) Durum: ornek" and m["yz"]["kim"] == "admin"
    assert client.post(f"{URL}/30000003/yz").status_code == 403  # CSRF'siz


def test_hizmet_turu_ve_sure_sinifi():
    assert analiz.hizmet_turu("nw_li_cust_3g_happycentermuratpasa_yedek_ssr") == "Mobil erişim (3G/4.5G)"
    assert analiz.hizmet_turu("nw_li_cust_tsol_me_int_nazillibelediyebaskanligi_2652") == "İnternet"
    assert analiz.hizmet_turu("nw_li_cust_va_sdsl_littlecaesars_rb1200_01") == "DSL"
    assert analiz.hizmet_turu("nw_li_cust_me_karayollarianasolmempls_nw_rt_ne40_01.34glbl") == "MPLS"
    assert analiz.hizmet_turu("nw_li_cust_printer_x") == "Diğer"  # 'int' bitisik kelimede eslesmez
    assert analiz.yedek_hat_mi("nw_li_cust_3g_x_yedek_ssr") and not analiz.yedek_hat_mi("nw_li_cust_3g_x")
    assert [analiz.sure_sinifi(d) for d in (4, 5, 59, 60, 479, 480)] == ["anlik", "kisa", "kisa", "uzun", "uzun", "cok_uzun"]
