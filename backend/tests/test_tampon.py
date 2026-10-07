"""Veri Girisi hatti: CSV -> tampon -> analiz -> dagitim (kural, onizleme, uygulama, geri alma) ve korumalar."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import engine
from app.models import Customer, IngestBatch
from app.ortak import UygulamaHatasi
from app.tampon import kaynak as kaynak_modulu
from app.tampon.eslestirme import kosul_saglar, musteri_anahtarlari, sayi
from app.tampon.models import DistributionLog, IngestBlock
from tests.conftest import login_ok

CSV = (
    "Müşteri No;Kayıt Türü;Durum;Adet\n"
    "12345;Alarm;Açık;2\n"
    "12345;Alarm;Kapalı;5\n"
    "12345;Şikayet;Açık;1\n"
    "222;Alarm;Açık;3\n"
    "333;Alarm;Açık;4\n"
    "444;Alarm;Açık;9\n"
    "999;Alarm;Açık;1\n"
    ";Alarm;Açık;1\n"
)


@pytest.fixture
def veri(client):
    """5 musteri: c1 (00012345), c2 (222, 333 - iki numara), c3 ve c4 (ikisi de 444: belirsiz), c5 (555: veride yok)."""
    with Session(engine()) as db:
        db.add_all(
            [
                Customer(id=1, external_key="t1", name="Alfa A.S.", customer_no="00012345"),
                Customer(id=2, external_key="t2", name="Beta Ltd", customer_no="222, 333"),
                Customer(id=3, external_key="t3", name="Gama", customer_no="444", alarm_count=7),
                Customer(id=4, external_key="t4", name="Delta", customer_no="444"),
                Customer(id=5, external_key="t5", name="Epsilon", customer_no="555", alarm_count=4),
            ]
        )
        db.commit()
    return client


def _yukle(client, hdr, icerik=CSV, kaynak="alarm", dosya="alarm.csv"):
    govde = icerik if isinstance(icerik, bytes) else icerik.encode("utf-8")
    return client.put(f"/api/v1/tampon/yukle?kaynak={kaynak}&dosya={dosya}", content=govde, headers={**hdr, "Content-Type": "text/csv"})


def _alan(client, no):
    with Session(engine()) as db:
        return db.get(Customer, no)


KURAL_ALARM = {
    "name": "Aktif alarm",
    "source_key": "csv_alarm",
    "match_field": "customer_no",
    "key_column": "Müşteri No",
    "target": "customer.alarm_count",
    "operation": "say",
    "conditions": [{"kolon": "Kayıt Türü", "islec": "esit", "deger": "alarm"}, {"kolon": "Durum", "islec": "esit", "deger": "açık"}],
}


def _kural(client, hdr, **ek):
    r = client.post("/api/v1/tampon/kurallar", json={**KURAL_ALARM, **ek}, headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()["data"]


# --- saf fonksiyonlar ----------------------------------------------------------------------------------------------
def test_sayi_turkce_bicimler():
    assert sayi("1.234,56") == 1234.56 and sayi("1234,5") == 1234.5 and sayi("12.5") == 12.5
    assert sayi("1.234") == 1234 and sayi("1.234.567") == 1234567 and sayi("-3") == -3
    assert sayi("1,234.56") == 1234.56  # sondaki ayrac ondalik
    assert sayi("12 ₺") == 12 and sayi(7) == 7 and sayi(True) is None
    assert sayi("abc") is None and sayi("") is None and sayi(None) is None and sayi("--") is None


def test_musteri_anahtarlari_sifir_ve_ayrac():
    assert musteri_anahtarlari("0012, 34;0012\n56/ x") == ["12", "34", "56"]
    assert musteri_anahtarlari(22135503.0) == ["22135503"] and musteri_anahtarlari(None) == [] and musteri_anahtarlari("000") == []


def test_kosul_turkce_karakter_ve_islecler():
    assert kosul_saglar("Açık", "esit", "ACIK") and kosul_saglar("  Kapalı ", "esit_degil", "açık")
    assert kosul_saglar("Network Operasyon", "icerir", "operasyon") and kosul_saglar("abc", "baslar", "AB")
    assert kosul_saglar("x", "icermez", "y") and kosul_saglar("", "bos", "") and kosul_saglar("a", "dolu", "")
    assert not kosul_saglar("a", "bilinmeyen", "a")


def test_csv_kodlama_ve_ayrac_kendiliginden():
    basliklar, satirlar = kaynak_modulu.csv_oku("Ad;Şehir\nAli;İzmir\n".encode("cp1254"))  # Windows Excel 'CSV' (ANSI)
    assert basliklar == ["Ad", "Şehir"] and list(satirlar) == [["Ali", "İzmir"]]
    basliklar, satirlar = kaynak_modulu.csv_oku(b"\xef\xbb\xbfa,b,a\n1,2,3\n\n,,\n4,,6\n")  # BOM, virgul, tekrar baslik, bos satirlar
    assert basliklar == ["a", "b", "a (2)"] and list(satirlar) == [["1", "2", "3"], [None, None, None], ["4", None, "6"]]
    with pytest.raises(UygulamaHatasi):
        kaynak_modulu.csv_oku(b"\n\n")
    with pytest.raises(UygulamaHatasi):
        kaynak_modulu.csv_oku(b"tek_sutun\n1\n")
    assert (
        kaynak_modulu.kaynak_anahtari("Alarm Özeti (2026)") == "csv_alarm_ozeti_2026" and kaynak_modulu.kaynak_anahtari("") == "csv_dosya"
    )


# --- yetki ---------------------------------------------------------------------------------------------------------
def test_tampon_yalniz_admin_ve_csrf(veri, monkeypatch):
    assert veri.get("/api/v1/tampon/partiler").status_code == 401
    hdr = login_ok(veri)
    assert _yukle(veri, {}).status_code == 403  # CSRF'siz
    assert veri.post("/api/v1/tampon/kurallar", json=KURAL_ALARM).status_code == 403
    veri.post("/api/v1/session/logout", headers=hdr)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    hdr = login_ok(veri)
    assert veri.get("/api/v1/tampon/partiler").status_code == 403
    assert _yukle(veri, hdr).status_code == 403
    assert veri.get("/api/v1/tampon/hedefler").status_code == 403


# --- 1. tampon -----------------------------------------------------------------------------------------------------
def test_csv_yukle_parti_blok_profil(veri):
    hdr = login_ok(veri)
    r = _yukle(veri, hdr)
    assert r.status_code == 200, r.text
    p = r.json()["data"]
    assert p["durum"] == "ready" and p["satir"] == 8 and p["kaynak"] == "csv_alarm" and p["sutun_sayisi"] == 4 and p["olusturan"] == "admin"
    d = veri.get(f"/api/v1/tampon/partiler/{p['id']}").json()["data"]
    assert d["sutunlar"] == ["Müşteri No", "Kayıt Türü", "Durum", "Adet"]
    profil = {s["sutun"]: s for s in d["profil"]}
    assert profil["Müşteri No"]["dolu"] == 7 and profil["Adet"]["tip"] == "tam sayı" and profil["Durum"]["farkli"] == 2
    assert profil["Kayıt Türü"]["en_sik"][0] == ["Alarm", 7]
    s = veri.get(f"/api/v1/tampon/partiler/{p['id']}/satirlar?adet=3&sayfa=2").json()["data"]
    assert s["toplam"] == 8 and s["sayfa"] == 2 and [x[0] for x in s["satirlar"]] == ["222", "333", "444"]  # 4., 5., 6. satir
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(IngestBlock)) == 1
    liste = veri.get("/api/v1/tampon/partiler?kaynak=csv_alarm").json()["data"]
    assert liste["toplam"] == 1 and liste["satirlar"][0]["id"] == p["id"]
    assert veri.get("/api/v1/tampon/partiler/999").status_code == 404


def test_blok_sinirinda_sayfa_okuma(veri, monkeypatch):
    from app.tampon import depo

    monkeypatch.setattr(depo, "BLOK_SATIR", 3)
    hdr = login_ok(veri)
    govde = "No;Deger\n" + "\n".join(f"{i};{i}" for i in range(1, 11)) + "\n"
    p = _yukle(veri, hdr, govde, kaynak="blok").json()["data"]
    assert p["satir"] == 10
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(IngestBlock)) == 4  # 3+3+3+1
    for sayfa, beklenen in ((1, ["1", "2", "3", "4"]), (2, ["5", "6", "7", "8"]), (3, ["9", "10"])):
        g = veri.get(f"/api/v1/tampon/partiler/{p['id']}/satirlar?adet=4&sayfa={sayfa}").json()["data"]
        assert [x[0] for x in g["satirlar"]] == beklenen


def test_bos_ve_bozuk_dosya_reddedilir(veri):
    hdr = login_ok(veri)
    assert _yukle(veri, hdr, "A;B\n").status_code == 400  # satir yok
    assert _yukle(veri, hdr, "tek\n1\n").status_code == 400
    assert veri.get("/api/v1/tampon/partiler?durum=failed").json()["data"]["toplam"] == 1  # satir yok: parti 'failed' kalir
    p = veri.get("/api/v1/tampon/partiler?durum=failed").json()["data"]["satirlar"][0]
    assert p["hata"] == "Veride satır yok." and p["satir"] == 0
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(IngestBlock)) == 0


def test_dosya_boyut_siniri_413(veri, monkeypatch):
    hdr = login_ok(veri)
    monkeypatch.setenv("TAMLIFE_INGEST_MAX_MB", "1")
    r = _yukle(veri, hdr, "A;B\n" + "1;" + "x" * 1_200_000 + "\n")
    assert r.status_code == 413
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(IngestBatch)) == 0  # parti hic acilmadi


def test_satir_siniri_partiyi_failed_yapar(veri, monkeypatch):
    hdr = login_ok(veri)
    monkeypatch.setenv("TAMLIFE_INGEST_MAX_ROWS", "3")
    r = _yukle(veri, hdr)
    assert r.status_code == 413 and "en fazla" in r.json()["detail"]
    p = veri.get("/api/v1/tampon/partiler").json()["data"]["satirlar"][0]
    assert p["durum"] == "failed" and "en fazla" in p["hata"]


def test_kucuklme_korumasi_ve_kabul(veri):
    hdr = login_ok(veri)
    buyuk = "No;Tur\n" + "\n".join(f"{i};a" for i in range(1, 251)) + "\n"
    kucuk = "No;Tur\n" + "\n".join(f"{i};a" for i in range(1, 51)) + "\n"
    assert _yukle(veri, hdr, buyuk, kaynak="k").json()["data"]["durum"] == "ready"
    k = _yukle(veri, hdr, kucuk, kaynak="k").json()["data"]
    assert k["durum"] == "rejected" and "çok küçük" in k["hata"]
    assert veri.post(f"/api/v1/tampon/partiler/{k['id']}/analiz", headers=hdr).status_code == 200  # reddedilmis parti incelenebilir
    kabul = veri.post(f"/api/v1/tampon/partiler/{k['id']}/kabul", headers=hdr)
    assert kabul.status_code == 200 and kabul.json()["data"]["durum"] == "ready" and kabul.json()["data"]["hata"] == ""
    assert veri.post(f"/api/v1/tampon/partiler/{k['id']}/kabul", headers=hdr).status_code == 409  # artik hazir
    diger = _yukle(veri, hdr, kucuk, kaynak="baska").json()["data"]
    assert diger["durum"] == "ready"  # koruma kaynak basinadir


def test_kaynak_basina_son_n_parti_kalir(veri, monkeypatch):
    hdr = login_ok(veri)
    monkeypatch.setenv("TAMLIFE_INGEST_KEEP_BATCHES", "2")
    idler = [_yukle(veri, hdr, f"A;B\n{i};x\n", kaynak="d").json()["data"]["id"] for i in range(4)]
    kalan = {p["id"] for p in veri.get("/api/v1/tampon/partiler?kaynak=csv_d").json()["data"]["satirlar"]}
    assert kalan == set(idler[-2:])
    with Session(engine()) as db:
        assert {b for (b,) in db.execute(select(IngestBlock.batch_id))} == set(idler[-2:])  # bloklar da silindi


def test_kaynaklar_listesi(veri):
    hdr = login_ok(veri)
    _yukle(veri, hdr)
    k = {x["anahtar"]: x for x in veri.get("/api/v1/tampon/kaynaklar").json()["data"]}
    assert {"csv", "ornek", "oracle_reportdb", "oracle_onent", "oracle_urun_tutar", "csv_alarm"} <= set(k)
    assert k["csv_alarm"]["son"]["durum"] == "ready" and k["csv_alarm"]["parti_sayisi"] == 1
    assert k["oracle_reportdb"]["hazir"] is False and "kapalı" in k["oracle_reportdb"]["neden"]
    assert all("password" not in str(v).lower() for v in k.values())


def test_ornek_parti_yerel_veriden_turetilir(veri):
    hdr = login_ok(veri)
    r = veri.post("/api/v1/tampon/ornek", headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["durum"] == "ready" and r.json()["data"]["kaynak"] == "ornek"
    pid = r.json()["data"]["id"]
    d = veri.get(f"/api/v1/tampon/partiler/{pid}").json()["data"]
    assert "gerçek değil" in d["etiket"]
    a = veri.post(f"/api/v1/tampon/partiler/{pid}/analiz", headers=hdr).json()["data"]
    ilk = a["oneriler"][0]
    assert (ilk["kolon"], ilk["alan"]) == ("Müşteri No", "customer_no") and ilk["oran"] > 50  # numara, unvandan once
    assert any(o["alan"] == "name" for o in a["oneriler"][1:])  # unvan da aday ama sonra


# --- 2. analiz -----------------------------------------------------------------------------------------------------
def test_analiz_anahtar_onerir(veri):
    hdr = login_ok(veri)
    pid = _yukle(veri, hdr).json()["data"]["id"]
    a = veri.post(f"/api/v1/tampon/partiler/{pid}/analiz", headers=hdr).json()["data"]
    assert a["musteri_sayisi"] == 5 and a["toplam_satir"] == 8 and a["ornek_satir"] == 8
    onc = a["oneriler"][0]
    # farkli numaralar: 12345, 222, 333, 444, 999 -> 4'u kartlarda (999 yok)
    assert onc == {"kolon": "Müşteri No", "alan": "customer_no", "farkli": 5, "eslesen": 4, "oran": 80.0}
    assert not any(o["kolon"] == "Durum" for o in a["oneriler"])
    d = veri.get(f"/api/v1/tampon/partiler/{pid}").json()["data"]
    assert d["analiz"]["oneriler"][0]["eslesen"] == 4  # sonuc partiye yazildi


def test_analiz_musteri_yokken_uyarir(client):
    hdr = login_ok(client)
    pid = _yukle(client, hdr).json()["data"]["id"]
    a = client.post(f"/api/v1/tampon/partiler/{pid}/analiz", headers=hdr).json()["data"]
    assert a["musteri_sayisi"] == 0 and a["oneriler"] == [] and "müşteri kartı yok" in a["uyarilar"][0]


# --- 3. dagitim ----------------------------------------------------------------------------------------------------
def test_hedef_katalogu_sabit(veri):
    login_ok(veri)
    k = veri.get("/api/v1/tampon/hedefler").json()["data"]
    assert {h["anahtar"] for h in k["hedefler"]} >= {"customer.alarm_count", "customer.sector"}
    assert {i["anahtar"] for i in k["islemler"]} == {"say", "farkli_say", "topla", "ortalama", "en_buyuk", "en_kucuk", "ilk", "en_cok"}
    assert {a["anahtar"] for a in k["eslesme_alanlari"]} == {"customer_no", "ncst", "name"}


def test_kural_dogrulama(veri):
    hdr = login_ok(veri)

    def dene(**ek):
        return veri.post("/api/v1/tampon/kurallar", json={**KURAL_ALARM, **ek}, headers=hdr)

    assert dene(target="customer.yok").status_code == 400  # serbest hedef yok
    assert dene(target="customer.sector").status_code == 400  # say -> metin hedefine olmaz
    assert dene(operation="topla").status_code == 400  # topla icin deger sutunu zorunlu
    assert dene(operation="ilk", value_column="Durum").status_code == 400  # metin islemi sayisal hedefe olmaz
    assert dene(match_field="tc").status_code == 400
    assert dene(name="").status_code == 400
    assert dene(conditions=[{"kolon": "Durum", "islec": "esit", "deger": ""}]).status_code == 400
    assert dene(conditions=[{"kolon": "Durum", "islec": "yok", "deger": "x"}]).status_code == 400
    assert dene(conditions=[{"kolon": "A", "islec": "dolu"}] * 6).status_code == 400
    assert dene(max_age_minutes=0).status_code == 400
    r = dene(conditions=[{"kolon": "Durum", "islec": "dolu"}], max_age_minutes=60)
    assert r.status_code == 200 and r.json()["data"]["etkin"] is False  # varsayilan KAPALI


def test_onizle_uygula_geri_al_akisi(veri):
    hdr = login_ok(veri)
    pid = _yukle(veri, hdr).json()["data"]["id"]
    kural = _kural(veri, hdr)
    kid = kural["id"]

    on = veri.post(f"/api/v1/tampon/kurallar/{kid}/onizle", json={"parti_id": pid}, headers=hdr).json()["data"]
    assert on["toplam_satir"] == 8 and on["kosul_disi"] == 2 and on["eslesen_musteri"] == 2
    assert on["degisecek"] == 2 and on["eslesmeyen_satir"] == 2 and on["belirsiz_satir"] == 1 and on["degismeyen"] == 0
    assert {(o["ad"], o["eski"], o["yeni"]) for o in on["ornek"]} == {("Alfa A.S.", 0, 1), ("Beta Ltd", 0, 2)}  # c2: 222 ve 333 TOPLANIR
    assert "belirsiz" in " ".join(on["uyarilar"])
    assert _alan(veri, 1).alarm_count == 0  # onizleme yazmaz

    assert (
        veri.post(f"/api/v1/tampon/kurallar/{kid}/uygula", json={"parti_id": pid, "onay": True}, headers=hdr).status_code == 409
    )  # kapali
    assert veri.post(f"/api/v1/tampon/kurallar/{kid}/etkin", json={"etkin": True}, headers=hdr).json()["data"]["etkin"] is True
    assert veri.post(f"/api/v1/tampon/kurallar/{kid}/uygula", json={"parti_id": pid}, headers=hdr).status_code == 400  # onaysiz
    assert _alan(veri, 1).alarm_count == 0

    u = veri.post(f"/api/v1/tampon/kurallar/{kid}/uygula", json={"parti_id": pid, "onay": True}, headers=hdr).json()["data"]
    assert u["yazilan"] == 2 and len(u["run_id"]) == 32
    assert (_alan(veri, 1).alarm_count, _alan(veri, 2).alarm_count) == (1, 2)
    assert (_alan(veri, 3).alarm_count, _alan(veri, 4).alarm_count) == (7, 0)  # belirsiz kartlara dokunulmaz
    with Session(engine()) as db:
        kayitlar = db.scalars(select(DistributionLog).where(DistributionLog.run_id == u["run_id"])).all()
        assert {(k.customer_id, k.old_value, k.new_value) for k in kayitlar} == {(1, "0", "1"), (2, "0", "2")}

    tekrar = veri.post(f"/api/v1/tampon/kurallar/{kid}/onizle", json={"parti_id": pid}, headers=hdr).json()["data"]
    assert tekrar["degisecek"] == 0 and tekrar["degismeyen"] == 2  # ayni veri: degisiklik yok
    assert (
        veri.post(f"/api/v1/tampon/kurallar/{kid}/uygula", json={"parti_id": pid, "onay": True}, headers=hdr).json()["data"]["yazilan"] == 0
    )

    liste = veri.get("/api/v1/tampon/uygulamalar").json()["data"]
    assert liste[0]["run_id"] == u["run_id"] and liste[0]["yazilan"] == 2 and liste[0]["geri_alinan"] == 0
    assert liste[0]["kural"] == "Aktif alarm" and liste[0]["hedef_adi"] == "Aktif alarm" and liste[0]["kullanici"] == "admin"

    with Session(engine()) as db:  # c2 sonradan elle degisti
        db.get(Customer, 2).alarm_count = 99
        db.commit()
    g = veri.post(f"/api/v1/tampon/uygulamalar/{u['run_id']}/geri-al", headers=hdr).json()["data"]
    assert g == {"geri_alinan": 1, "korunan": 1}  # yalniz hala yazilan degerde duran geri doner
    assert (_alan(veri, 1).alarm_count, _alan(veri, 2).alarm_count) == (0, 99)
    assert veri.post(f"/api/v1/tampon/uygulamalar/{u['run_id']}/geri-al", headers=hdr).status_code == 200  # korunan kalir
    assert veri.get("/api/v1/tampon/uygulamalar").json()["data"][0]["geri_alinan"] == 1
    assert veri.post("/api/v1/tampon/uygulamalar/zzz/geri-al", headers=hdr).status_code == 400
    assert veri.post(f"/api/v1/tampon/uygulamalar/{'0' * 32}/geri-al", headers=hdr).status_code == 404

    olaylar = {s["olay"] for s in veri.get("/api/v1/yonetim/gunlukler?olay=tampon.").json()["data"]["satirlar"]}
    assert {"tampon.yukle", "tampon.kural_olustur", "tampon.kural_etkin", "tampon.uygula", "tampon.geri_al"} <= olaylar


def test_toplama_ve_turkce_sayi(veri):
    hdr = login_ok(veri)
    csv = "Müşteri No;Tutar\n12345;1.234,50\n12345;10\n222;bozuk\n333;5\n"
    pid = _yukle(veri, hdr, csv, kaynak="tutar").json()["data"]["id"]
    kural = _kural(
        veri, hdr, source_key="csv_tutar", target="customer.inventory_count", operation="topla", value_column="Tutar", conditions=[]
    )
    on = veri.post(f"/api/v1/tampon/kurallar/{kural['id']}/onizle", json={"parti_id": pid}, headers=hdr).json()["data"]
    assert {(o["ad"], o["yeni"]) for o in on["ornek"]} == {
        ("Alfa A.S.", 1245),
        ("Beta Ltd", 5),
    }  # 1244,5 + 10 -> yuvarlanir; 'bozuk' atlanir
    assert "1 hücre sayıya çevrilemedi" in " ".join(on["uyarilar"])


def test_negatif_sonuc_yazilmaz(veri):
    hdr = login_ok(veri)
    pid = _yukle(veri, hdr, "Müşteri No;Fark\n12345;-5\n", kaynak="eksi").json()["data"]["id"]
    kural = _kural(
        veri, hdr, source_key="csv_eksi", target="customer.inventory_count", operation="topla", value_column="Fark", conditions=[]
    )
    on = veri.post(f"/api/v1/tampon/kurallar/{kural['id']}/onizle", json={"parti_id": pid}, headers=hdr).json()["data"]
    assert on["degisecek"] == 0 and on["gecersiz"] == 1


def test_eslesmeyeni_sifirla_belirsizi_korur(veri):
    hdr = login_ok(veri)
    pid = _yukle(veri, hdr).json()["data"]["id"]
    kural = _kural(veri, hdr, zero_unmatched=True)
    on = veri.post(f"/api/v1/tampon/kurallar/{kural['id']}/onizle", json={"parti_id": pid}, headers=hdr).json()["data"]
    assert on["degisecek"] == 3 and on["sifirlanacak"] == 1  # c1, c2 yazilir; c5 (555: veride yok, 4 -> 0) sifirlanir
    sifir = next(o for o in on["ornek"] if o["sifirlama"])
    assert (sifir["ad"], sifir["eski"], sifir["yeni"]) == ("Epsilon", 4, 0)
    assert not any(o["ad"] in ("Gama", "Delta") for o in on["ornek"])  # c3 (7) belirsiz numarada: sifirlanmaz
    veri.post(f"/api/v1/tampon/kurallar/{kural['id']}/etkin", json={"etkin": True}, headers=hdr)
    veri.post(f"/api/v1/tampon/kurallar/{kural['id']}/uygula", json={"parti_id": pid, "onay": True}, headers=hdr)
    assert (_alan(veri, 5).alarm_count, _alan(veri, 3).alarm_count) == (0, 7)


def test_eslesme_alani_unvan_ve_metin_hedefi(veri):
    hdr = login_ok(veri)
    csv = "Unvan;Sektor\nALFA a.s.;Bilişim\nbeta ltd;Enerji\nbeta ltd;Enerji\nbeta ltd;Gıda\nyok firma;X\n"
    pid = _yukle(veri, hdr, csv, kaynak="sektor").json()["data"]["id"]
    kural = _kural(
        veri,
        hdr,
        source_key="csv_sektor",
        match_field="name",
        key_column="Unvan",
        target="customer.sector",
        operation="en_cok",
        value_column="Sektor",
        conditions=[],
    )
    on = veri.post(f"/api/v1/tampon/kurallar/{kural['id']}/onizle", json={"parti_id": pid}, headers=hdr).json()["data"]
    assert {(o["ad"], o["yeni"]) for o in on["ornek"]} == {("Alfa A.S.", "Bilişim"), ("Beta Ltd", "Enerji")}  # en sik deger
    veri.post(f"/api/v1/tampon/kurallar/{kural['id']}/etkin", json={"etkin": True}, headers=hdr)
    u = veri.post(f"/api/v1/tampon/kurallar/{kural['id']}/uygula", json={"parti_id": pid, "onay": True}, headers=hdr).json()["data"]
    assert _alan(veri, 2).sector == "Enerji"
    veri.post(f"/api/v1/tampon/uygulamalar/{u['run_id']}/geri-al", headers=hdr)
    assert _alan(veri, 2).sector is None  # eski deger (bos) geri geldi


def test_kural_parti_uyumsuzlugu_ve_eksik_sutun(veri):
    hdr = login_ok(veri)
    pid = _yukle(veri, hdr).json()["data"]["id"]
    diger = _yukle(veri, hdr, "A;B\n1;2\n", kaynak="baska").json()["data"]["id"]
    kural = _kural(veri, hdr)
    assert (
        veri.post(f"/api/v1/tampon/kurallar/{kural['id']}/onizle", json={"parti_id": diger}, headers=hdr).status_code == 409
    )  # baska kaynak
    assert veri.post(f"/api/v1/tampon/kurallar/{kural['id']}/onizle", json={"parti_id": 999}, headers=hdr).status_code == 404
    eksik = _kural(veri, hdr, key_column="Yok Sutun")
    r = veri.post(f"/api/v1/tampon/kurallar/{eksik['id']}/onizle", json={"parti_id": pid}, headers=hdr)
    assert r.status_code == 400 and "Sütun partide yok" in r.json()["detail"]


def test_parti_cok_eskiyse_uygulanmaz(veri):
    from datetime import UTC, datetime, timedelta

    hdr = login_ok(veri)
    pid = _yukle(veri, hdr).json()["data"]["id"]
    kural = _kural(veri, hdr, max_age_minutes=30)
    veri.post(f"/api/v1/tampon/kurallar/{kural['id']}/etkin", json={"etkin": True}, headers=hdr)
    govde = {"parti_id": pid, "onay": True}
    assert veri.post(f"/api/v1/tampon/kurallar/{kural['id']}/uygula", json=govde, headers=hdr).status_code == 200
    with Session(engine()) as db:
        db.get(IngestBatch, pid).received_at = datetime.now(UTC) - timedelta(minutes=45)
        db.commit()
    r = veri.post(f"/api/v1/tampon/kurallar/{kural['id']}/uygula", json=govde, headers=hdr)
    assert r.status_code == 409 and "çok eski" in r.json()["detail"]


def test_kural_guncelle_sil_ve_gecmis_korumasi(veri):
    hdr = login_ok(veri)
    pid = _yukle(veri, hdr).json()["data"]["id"]
    kural = _kural(veri, hdr)
    kid = kural["id"]
    g = veri.put(
        f"/api/v1/tampon/kurallar/{kid}",
        json={**KURAL_ALARM, "name": "Yeni ad", "operation": "farkli_say", "value_column": "Durum"},
        headers=hdr,
    )
    assert g.status_code == 200 and g.json()["data"]["ad"] == "Yeni ad" and g.json()["data"]["etkin"] is False
    assert veri.put("/api/v1/tampon/kurallar/999", json=KURAL_ALARM, headers=hdr).status_code == 404
    assert [k["id"] for k in veri.get("/api/v1/tampon/kurallar").json()["data"]] == [kid]

    veri.put(f"/api/v1/tampon/kurallar/{kid}", json=KURAL_ALARM, headers=hdr)
    veri.post(f"/api/v1/tampon/kurallar/{kid}/etkin", json={"etkin": True}, headers=hdr)
    u = veri.post(f"/api/v1/tampon/kurallar/{kid}/uygula", json={"parti_id": pid, "onay": True}, headers=hdr).json()["data"]
    assert veri.delete(f"/api/v1/tampon/kurallar/{kid}", headers=hdr).status_code == 409  # gecmisi var
    assert veri.delete(f"/api/v1/tampon/partiler/{pid}", headers=hdr).status_code == 409  # geri alinmamis dagitima bagli
    veri.post(f"/api/v1/tampon/uygulamalar/{u['run_id']}/geri-al", headers=hdr)
    assert veri.delete(f"/api/v1/tampon/partiler/{pid}", headers=hdr).status_code == 200  # geri alindi: silinebilir
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(IngestBlock)) == 0
        assert db.scalar(select(func.count()).select_from(DistributionLog)) == 0  # parti silinince gecmisi de gider
    assert veri.delete(f"/api/v1/tampon/kurallar/{kid}", headers=hdr).status_code == 200
    assert veri.delete("/api/v1/tampon/kurallar/999", headers=hdr).status_code == 404
