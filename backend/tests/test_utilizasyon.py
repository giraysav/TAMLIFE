"""TAM Utilizasyon: metrik kaynaklari (panel, Urun-Tutar Excel, kriter veri kaynagi secimi), oncelik, agac / personel agirligi,
siralama ve Urun-Tutar yuklemesi. Uretim davranis ornekleri: tests/test_skor_motoru.py, test_urun_tutar.py (uydurma ORNEK-* veri)."""

import io
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser, Customer, Report, ScoreDetail, UrunTutarOzet
from app.skor import kaynak_secimi, kaynaklar, servis, urun_tutar
from app.tampon import depo
from tests.conftest import login_ok

YIL = datetime.now(UTC).year
BASLIKLAR = ["Müşteri Adı", "Sözleşme Detayı Status", "Sözleşme Detayı Kodu", "Devre Numarası", "Tam Adres",
             "Ürün Tipi Grubu Level 3", "Müşteri No", "NCST", "Ürün Tipi", "Hesaplanmış Fiyat"]  # fmt: skip


def _satir(ad, durum, devre, adres, grup, no, ncst, fiyat):
    return [ad, durum, "K1", devre, adres, grup, no, ncst, "SOL", fiyat]


ORNEK = [
    _satir("ORNEK Cati A.S.", "ACT_END", "D1", "Adres 1", "METROETHERNET", "0000100", None, 1000),
    _satir("ORNEK Cati A.S.", "ACT_END", "D2", "adres  1", "MPLS", "100", None, 500.5),  # ayni adres
    _satir("ORNEK Cati A.S.", "ACT_END", "D3", "Adres 2", "GSHDSL", "100", None, 250),
    _satir("ORNEK Cati A.S.", "ACT_END", None, "Adres 3", "VOIP", "100", None, 100),  # devresiz: lokasyon degil
    _satir("ORNEK Cati A.S.", "DEACT_END", "D9", "Adres 9", "BULUT", "100", None, 99999),  # kapali: sayilmaz
    _satir("ORNEK Cati A.S.", "ACT_INPROGRESS", None, "Adres 4", "GARIP GRUP", "100", None, 10),
    _satir("ORNEK Cati A.S.", "ACT_END", None, "Adres 4", "N/A", "100", None, 0),
    _satir("ORNEK Istirak Ltd", "ACT_END", "D5", "Adres 5", "BULUT", "x", 777, 2000),  # NCST ile istirake
    _satir("Baska Sirket", "ACT_END", None, "Adres 6", "MANAGED WIFI", "999", None, 300),  # eslesmez -> secilen musteriye
]


def _excel(satirlar=ORNEK, basliklar=BASLIKLAR, ust_bosluk=0) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for _ in range(ust_bosluk):
        ws.append([])
    ws.append(basliklar)
    for s in satirlar:
        ws.append(s)
    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


@pytest.fixture
def veri(client):
    with Session(engine()) as db:
        db.add_all(
            [
                AppUser(id=1, username="admin", display_name="Admin", role="admin", is_admin=True),
                AppUser(id=2, username="ornek.tam1", display_name="ORNEK TAM Bir", role="TeamMember"),
                AppUser(id=3, username="ornek.tam2", display_name="ORNEK TAM Iki", role="TeamMember"),
                AppUser(id=4, username="ornek.mngr", display_name="ORNEK Yonetici", role="TeamMngr"),
            ]
        )
        db.flush()
        db.add_all(
            [
                Customer(id=1, external_key="ORNEK-1", name="ORNEK Cati", segment="MA", owner_id=2, customer_no="100", inventory_count=25,
                         complaint_count=3, complaint_closed_count=2, request_count=1, request_closed_count=4, ft_volume="1.234.567,89 ₺"),
                Customer(id=2, external_key="ORNEK-2", name="ORNEK Beta", segment="Kurumsal", owner_id=3, inventory_count=0, ft_volume="0,00 ₺"),
                Customer(id=3, external_key="ORNEK-3", name="ORNEK Gama", segment="SMB", owner_id=4, score=40.0),
                Customer(id=4, external_key="ORNEK-4", name="ORNEK Delta", segment="PA", owner_id=None, score=80.0),
                Customer(id=5, external_key="ORNEK-5", name="ORNEK Istirak Ltd", segment="MA", owner_id=2, parent_id=1, ncst="777"),
                Customer(id=6, external_key="ORNEK-6", name="ORNEK Ayri Istirak", segment="MA", owner_id=2, parent_id=1, separate_report=True),
            ]
        )  # fmt: skip
        db.flush()
        rapor = lambda cid, ay, yil=YIL: Report(customer_id=cid, user_id=2, report_month=ay, report_year=yil)
        db.add_all([rapor(1, 1), rapor(1, 2), rapor(1, 2), rapor(5, 3), rapor(6, 4), rapor(1, 5, YIL - 1)])
        db.commit()
    return client


def _metrikler(kriterler=None):
    with Session(engine()) as db:
        liste = list(db.scalars(select(Customer).order_by(Customer.id)))
        return kaynaklar.birlesik_metrikler(db, liste, kriterler)


def test_panel_kaynagi_dev_veritabanindan(veri):
    m, uyarilar = _metrikler()
    assert uyarilar == []
    c1 = m[1]
    assert c1["sikayet_talep"] == {"deger": 10, "kaynak": "Panel (kart + aylık rapor)"}  # acik + bu yil kapanan sikayet ve talep
    assert c1["lokasyon_sayisi"]["deger"] == 25 and c1["segment"]["deger"] == "MA"
    assert c1["fatura_bedeli"]["deger"] == 1234567.89  # FT Hacim (Turkce bicim)
    assert c1["rapor_sayisi"]["deger"] == 3  # 2 ay kendi + 1 ay dahil istirak; ayri raporlu istirak ve gecen yil sayilmaz
    assert m[6]["rapor_sayisi"]["deger"] == 1 and m[5]["rapor_sayisi"]["deger"] == 0
    assert "segment" not in m[2] and "fatura_bedeli" not in m[2]  # SEGMENTLER disi / 0 TL = veri yok
    assert "servisler" not in c1 and "baglanti" not in c1  # yalniz Urun-Tutar


def test_segmentler_musteri_paketiyle_ayni():
    from app.musteri.servis import SEGMENTLER

    assert kaynaklar.SEGMENTLER == SEGMENTLER


def test_db_kaynagi_ayarliysa_uyari_ayarli_degilse_sessiz(veri, monkeypatch):
    with Session(engine()) as db:
        durum = {k["ad"]: k for k in kaynaklar.kaynak_durumlari(db, [])}
    assert durum["REPORTDB"]["hazir"] is False and "ORACLE_REPORTDB_ENABLED" in durum["REPORTDB"]["neden"]
    assert "Ürün-Tutar" not in durum  # Urun-Tutar DB kaldirildi (2026-10-10); Excel kalir
    assert durum["Panel (kart + aylık rapor)"]["hazir"] is True and durum["Seçilen veri kaynağı"]["hazir"] is False
    for ad, deger in (("ENABLED", "true"), ("HOST", "ornek.invalid"), ("SERVICE_NAME", "ORNEK"), ("USER", "ornek"), ("PASSWORD", "ornek-parola")):
        monkeypatch.setenv(f"ORACLE_REPORTDB_{ad}", deger)
    m, uyarilar = _metrikler()
    assert any("REPORTDB" in u and "sorgu henüz yazılmadı" in u for u in uyarilar)
    assert m[1]["sikayet_talep"]["kaynak"].startswith("Panel")  # hata veren kaynak atlanir, siradaki besler


def test_urun_tutar_ozeti_ve_eslemeler():
    satirlar = urun_tutar.satirlari_oku(_excel(ORNEK[:7], ust_bosluk=2))
    o = urun_tutar.ozetle(satirlar)
    assert (o["satir"], o["aktif_satir"]) == (7, 6)  # DEACT_END sayilmaz
    assert o["lokasyon_sayisi"] == 2 and o["devre_sayisi"] == 3 and o["fatura_bedeli"] == 1860.5
    assert o["servisler"] == ["Data", "Ses"] and o["baglanti"] == ["DSL", "ME", "MPLS"] and o["eslesmeyen_gruplar"] == ["GARIP GRUP"]
    assert urun_tutar._ilk_eslesen(urun_tutar.SERVIS_ESLEME, "social media") is None  # kelime siniri
    assert urun_tutar._ilk_eslesen(urun_tutar.SERVIS_ESLEME, "klasik veri merkezi") == "Co-Location"
    from app.skor.motor import SERVIS_PUANLARI

    assert {h for _, h in urun_tutar.SERVIS_ESLEME} <= set(SERVIS_PUANLARI)
    assert urun_tutar._cekirdek("DOĞUŞ Teknoloji Hiz. ve Tic. A.Ş.") == "dogus teknoloji"
    with pytest.raises(urun_tutar.DosyaHatasi):
        urun_tutar.satirlari_oku(_excel(basliklar=["A", "B", "C"]))
    with pytest.raises(urun_tutar.DosyaHatasi):
        urun_tutar.satirlari_oku(b"excel degil")


def test_urun_tutar_yukleme_aileye_esler_ve_skora_kaynak_olur(veri):
    hdr = login_ok(veri)
    r = veri.put("/api/v1/skor/urun-tutar/1?dosya=ornek.xlsx", content=_excel(), headers=hdr)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    ozet = {m["id"]: m for m in d["musteriler"]}
    assert ozet[5]["servisler"] == ["Cloud"]  # NCST ile istirake
    assert "WIFI" in ozet[1]["servisler"] and ozet[1]["lokasyon_sayisi"] == 2  # eslesmeyen satir secilen musteriye
    assert d["kart_musteri_no"] == "100" and d["dosyadaki_adet"] == 3
    m, _ = _metrikler()
    assert m[1]["lokasyon_sayisi"] == {"deger": 2, "kaynak": "Ürün-Tutar (Excel)"}  # Panel envanterinin (25) onune gecer
    assert m[1]["baglanti"]["deger"] == ["DSL", "ME", "MPLS"] and m[1]["fatura_bedeli"]["deger"] == 2160.5
    assert m[1]["segment"]["kaynak"].startswith("Panel")  # Excel segment vermez
    liste = veri.get("/api/v1/skor/urun-tutar").json()["data"]
    assert {x["id"] for x in liste} == {1, 5} and liste[0]["dosya"] == "ornek.xlsx" and liste[0]["yukleyen"] == "admin"
    # ikinci yukleme ayni musterinin ozetini degistirir; aktif satiri olmayan ozet veri sayilmaz (Panel'e duser)
    kapali = [_satir("ORNEK Cati", "DEACT_END", "D1", "A", "MPLS", "100", None, 10)]
    assert veri.put("/api/v1/skor/urun-tutar/1", content=_excel(kapali), headers=hdr).status_code == 200
    m, _ = _metrikler()
    assert m[1]["lokasyon_sayisi"]["kaynak"].startswith("Panel") and "baglanti" not in m[1]
    assert veri.put("/api/v1/skor/urun-tutar/1", content=b"bozuk", headers=hdr).status_code == 400
    assert veri.put("/api/v1/skor/urun-tutar/999", content=_excel(), headers=hdr).status_code == 404
    with Session(engine()) as db:
        assert db.get(UrunTutarOzet, 1).file_name == "urun_tutar.xlsx"


def _parti(kaynak, basliklar, satirlar):
    with Session(engine()) as db:
        parti = depo.parti_olustur(db, kaynak, "ornek", "test")
        db.commit()
        return depo.ice_al(db, parti, basliklar, satirlar).id


SIKAYET_SECIMI = {"kaynak": "csv_ornek_olay", "eslesme": [{"sutun": "Musteri No", "alan": "customer_no"}], "islem": "say", "sutun": "",
                  "filtreler": [{"sutun": "Durum", "islec": "esit", "deger": "Acik"}]}  # fmt: skip


def test_kriter_veri_kaynagi_secimi_tampondan(veri):
    hdr = login_ok(veri)
    satirlar = [["0100", "Açık", "MPLS"], ["100", "acik", "VOIP"], ["100", "Kapali", "BULUT"], ["555", "Acik", "MPLS"]]
    pid = _parti("csv_ornek_olay", ["Musteri No", "Durum", "Grup"], satirlar)
    kriterler = [
        {"title": "Şikayet/Talep", "weight": 50, "kaynak_secimi": SIKAYET_SECIMI},
        {"title": "Servis Çeşitliliği", "weight": 50, "b30": "1-9", "b100": "10+",
         "kaynak_secimi": {"kaynak": "csv_ornek_olay", "eslesme": [{"sutun": "Musteri No", "alan": "customer_no"}], "islem": "esle_liste",
                           "sutun": "Grup", "esleme": [["mpls", "Data"], ["voip", "Ses"], ["bulut", "Cloud"]]}},
    ]  # fmt: skip
    m, uyarilar = _metrikler(kriterler)
    assert uyarilar == []
    assert m[1]["sikayet_talep"] == {"deger": 2, "kaynak": f"csv_ornek_olay #{pid}"}  # secim Panel'in (10) onune gecer; kosul normalize
    assert m[1]["servisler"]["deger"] == ["Cloud", "Data", "Ses"]
    assert m[2]["sikayet_talep"]["kaynak"].startswith("Panel")  # partide olmayan musteri siradaki kaynaga duser
    # yeni parti gelince sonuc kendiliginden yenilenir (onbellek anahtari parti)
    pid2 = _parti("csv_ornek_olay", ["Musteri No", "Durum", "Grup"], [*satirlar, ["100", "Acik", "SOC"]])
    m, _ = _metrikler(kriterler)
    assert m[1]["sikayet_talep"] == {"deger": 3, "kaynak": f"csv_ornek_olay #{pid2}"}
    # kayit: secim dogrulanir (partide olmayan sutun / tipi uymayan islem 400), gecerli secim saklanir
    yanlis = {**SIKAYET_SECIMI, "filtreler": [{"sutun": "Yok", "islec": "esit", "deger": "x"}]}
    r = veri.put("/api/v1/skor/kriterler/parent", json={"criteria": [{"title": "Şikayet", "weight": 1, "kaynak_secimi": yanlis}]}, headers=hdr)
    assert r.status_code == 400 and "Yok" in r.json()["detail"]
    r = veri.put("/api/v1/skor/kriterler/parent", json={"criteria": [{"title": "Şikayet", "weight": 1, "kaynak_secimi": {**SIKAYET_SECIMI, "islem": "liste", "sutun": "Grup"}}]}, headers=hdr)
    assert r.status_code == 400
    r = veri.put("/api/v1/skor/kriterler/parent", json={"criteria": [{"title": "Şikayet", "weight": 1, "metric": "m", "kaynak_secimi": SIKAYET_SECIMI}]}, headers=hdr)
    assert r.status_code == 200
    kayit = veri.get("/api/v1/skor/kriterler/parent").json()["data"]["criteria"][0]
    assert kayit["kaynak_secimi"]["islem"] == "say" and kayit["metric"] == "m" and kayit["type"] == "auto_onedesk"
    # onizleme (yazmaz) ve meta
    on = veri.post("/api/v1/skor/kaynak-onizle", json={"satir": {"title": "Şikayet", "kaynak_secimi": SIKAYET_SECIMI}}, headers=hdr).json()["data"]
    assert on["musteri"] == 1 and on["eslesmeyen"] == 1 and on["ornek"][0]["deger"] == 3
    yok = veri.post("/api/v1/skor/kaynak-onizle", json={"satir": {"title": "Şikayet", "kaynak_secimi": {**SIKAYET_SECIMI, "kaynak": "csv_yok"}}}, headers=hdr)
    assert yok.status_code == 400
    meta = veri.get("/api/v1/skor/meta").json()["data"]
    assert meta["partiler"][0]["kaynak"] == "csv_ornek_olay" and meta["partiler"][0]["sutunlar"] == ["Musteri No", "Durum", "Grup"]
    assert meta["sabit_puan_turleri"] == ["auto_sozlesme", "auto_rapor"] and "esle_liste" in meta["tur_islemleri"]["servis_cesitliligi"]


def test_kaynak_secimi_dogrulama():
    with pytest.raises(kaynak_secimi.KuralHatasi):
        kaynak_secimi.dogrula("auto_kaynaksiz", SIKAYET_SECIMI)  # tur basliktan anlasilamadi
    with pytest.raises(kaynak_secimi.KuralHatasi):
        kaynak_secimi.dogrula("auto_onedesk", {**SIKAYET_SECIMI, "eslesme": []})
    with pytest.raises(kaynak_secimi.KuralHatasi):
        kaynak_secimi.dogrula("auto_onedesk", {**SIKAYET_SECIMI, "islem": ["say"]})
    with pytest.raises(kaynak_secimi.KuralHatasi):
        kaynak_secimi.dogrula("auto_onedesk", {**SIKAYET_SECIMI, "filtreler": [{"sutun": "Tutar", "islec": "buyuk", "deger": "abc"}]})
    t = kaynak_secimi.dogrula("auto_sozlesme", {**SIKAYET_SECIMI, "islem": "topla", "sutun": "Tutar"}, ["Musteri No", "Durum", "Tutar"])
    assert t["islem"] == "topla" and set(t) == {"kaynak", "eslesme", "islem", "sutun", "filtreler", "esleme"}


def test_agac_personel_agirligi_ve_siralama(veri):
    hdr = login_ok(veri)
    veri.put("/api/v1/skor/istirak/5/final-dahil", json={"dahil": True}, headers=hdr)
    a = veri.get("/api/v1/skor/agac").json()["data"]
    assert a["ozet"] == {"toplam": 5, "cati": 4, "hazir": 0, "istirak": 2, "istirak_dahil": 1}  # varsayilan 7 kriter: Urun-Tutar eksik
    adlar = [(p["ad"], p["tam"]) for p in a["personel"]]
    assert adlar == [("ORNEK TAM Bir", True), ("ORNEK TAM Iki", True)]  # yonetici (ORNEK Yonetici) agacta dugum olmaz: yalniz TeamMember
    tam1 = a["personel"][0]
    ist = {i["id"]: i for i in tam1["musteriler"][0]["istirakler"]}
    assert ist[5]["dahil"] is True and ist[5]["yeni"] is not None and ist[6]["dahil"] is False and ist[6]["yeni"] is None
    assert [m["id"] for m in a["atanmamis"]] == [4, 3]  # sahipsiz (4) ve sahibi yonetici olan (3) musteri atanmamis grubunda
    assert {k["ad"] for k in a["kaynaklar"]} >= {"Panel (kart + aylık rapor)"} and len(a["kriterler"]) == 7
    d = a["dagilim"]
    assert d["ozet"]["tam_sayisi"] == 2 and d["ozet"]["musteri_sayisi"] == 2 and d["satirlar"][0]["istirakli_musteri"] in (0, 1)
    # puanlamaya girmeyen TAM agacta yok, musterisi atanmamis grubunda
    veri.put("/api/v1/skor/puanlama-disi", json={"disi": [2]}, headers=hdr)
    a = veri.get("/api/v1/skor/agac").json()["data"]
    assert "ORNEK TAM Bir" not in [p["ad"] for p in a["personel"]] and {m["id"] for m in a["atanmamis"]} == {1, 3, 4}
    assert next(p for p in a["tum_personel"] if p["id"] == 2)["dahil"] is False and a["dagilim"]["ozet"]["tam_sayisi"] == 1
    with Session(engine()) as db:
        assert db.get(Customer, 5).score is None and db.get(ScoreDetail, 5) is None  # istirak skoru yazilmaz
    with Session(engine()) as db:
        db.get(Customer, 2).score = 55.0
        db.commit()
    s = veri.get("/api/v1/skor/siralama").json()["data"]
    assert [(r["full_name"], r["avg_score"], r["rank"], r["bar_pct"]) for r in s] == [("ORNEK TAM Iki", 55.0, 1, 100)]  # yoneticinin (skor 40) siralamada yeri yok


def test_dagilim_ve_ozet_formulleri():
    p = [AppUser(id=1, username="a", display_name="A"), AppUser(id=2, username="b", display_name="B")]
    c = [Customer(id=1, owner_id=1, score=80.0), Customer(id=2, owner_id=1, score=None), Customer(id=3, owner_id=2, score=60.0)]
    assert servis.tam_skor_ozeti(c[:2]) == {"musteri_sayisi": 2, "skorlu_musteri": 1, "toplam_puan": 80.0, "final_skor": 80.0, "agirlik_puani": 40.0}
    d = servis.personel_agirlik_dagilimi(p, c, {1: [Customer(id=9)]})
    assert d["ozet"] == {"tam_sayisi": 2, "musteri_sayisi": 3, "toplam_puan": 140.0, "hedef_agirlik": 70.0, "ortalama_musteri_puani": 46.7, "skorlu_musteri": 2}
    b = next(s for s in d["satirlar"] if s["id"] == 2)
    assert (b["sira"], b["agirlik_puani"], b["hedef_fark"], b["dengeleme_musteri"]) == (1, 60.0, -10.0, -0.2)
    assert next(s for s in d["satirlar"] if s["id"] == 1)["istirakli_musteri"] == 1


def test_x_kurali_ve_tam_tablo_ile_toplu_atama(veri):
    """Urun-Tutar + panel + X sabit puan: varsayilan 7 kriterde musteri TAMAM olur ve toplu atama yazar."""
    hdr = login_ok(veri)
    assert veri.put("/api/v1/skor/urun-tutar/1", content=_excel(), headers=hdr).status_code == 200
    kriterler = veri.get("/api/v1/skor/kriterler/parent").json()["data"]["criteria"]
    for k in kriterler:
        if k["type"] == "auto_baglanti":
            k.update(b30="DSL", b50="MPLS", b70="ME")
        if k["type"] == "auto_rapor":
            k.update(b30="", b50="X", b70="", b100="")
    r = veri.put("/api/v1/skor/kriterler/parent", json={"criteria": kriterler}, headers=hdr).json()["data"]
    assert [u["id"] for u in r["uygulama"]["uygulanan"]] == [1]
    on = veri.post("/api/v1/skor/toplu/onizleme", json={}, headers=hdr).json()["data"]
    m1 = next(m for m in on["musteriler"] if m["id"] == 1)
    rapor = next(k for k in m1["kriterler"] if k["tur"] == "auto_rapor")
    assert (rapor["puan"], rapor["kaynak"], rapor["deger"]) == (50, "Sabit puan (X işareti)", "X")
    assert m1["tamam"] and m1["mevcut"] == m1["yeni"] and m1["fark"] == 0.0
