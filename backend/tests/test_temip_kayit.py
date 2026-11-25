"""TEMIP alarm kayitlari (tampon/temip_kayit): karta ya da TAM Radar'a atama, artimli yazim, kapanis, yeniden baglama, Onedesk dislamasi.
Oracle'a baglanilmaz: temip_kayit._cek sorgu metnine gore uydurma satir doner (ORNEK-*)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.ekip import moduller
from app.models import AppUser, Customer, OnedeskRecord
from app.onedesk import servis as onedesk
from app.radar import servis as radar
from app.session import Principal
from app.tampon import oracle, reportdb, temip_atama, temip_kayit
from tests.conftest import login_ok

ADMIN = Principal(username="admin", role="admin", is_admin=True)


def kart(ad: str, no: str | None = None) -> int:
    with Session(engine()) as db:
        c = Customer(external_key=f"ORNEK-{ad}", name=ad, customer_no=no)
        db.add(c)
        db.commit()
        return c.id


def tsatir(
    kimlik,
    mno,
    unvan="ORNEK MUSTERI A.S.",
    ticket="10134000001",
    ci="nw_li_cust_ornek_1",
    acilis="2026-10-17 10:00:00",
    kapanis=None,
    durum="Outstanding/Handled",
):
    return {"KIMLIK": kimlik, "MNO": mno, "UNVAN": unvan, "TICKET": ticket, "CI": ci, "BASLIK": "AVAILABILITY",
            "ACILIS": datetime.fromisoformat(acilis), "KAPANIS": datetime.fromisoformat(kapanis) if kapanis else None, "DURUM": durum}  # fmt: skip


class SahteTemip:
    """Sorgu metnine gore satir: VIEW_REPORT_ACTIVE (kapali), ACTIVEALARMS_5DK (acik), IDENTIFIER IN (dusen aciklarin kapanisi)."""

    def __init__(self, monkeypatch):
        self.kapali, self.acik, self.kimlikle, self.sorgular = [], [], {}, []
        monkeypatch.setattr(temip_kayit, "_cek", self._cek)

    def _cek(self, sorgu):
        oracle.sorgu_temizle(sorgu)  # gercek akista da temizlenir: tek SELECT
        self.sorgular.append(sorgu)
        if " AND IDENTIFIER IN (" in sorgu:
            return [s for k, s in self.kimlikle.items() if f"{k}" in sorgu.split(" AND IDENTIFIER IN (")[1]]
        return list(self.acik if "ACTIVEALARMS_5DK" in sorgu else self.kapali)


def calistir(kip="artimli"):
    with Session(engine()) as db:
        return temip_kayit.calistir(db, kip)


def kayitlar():
    with Session(engine()) as db:
        return {r.external_key: r for r in db.scalars(select(OnedeskRecord).where(OnedeskRecord.source == "temip"))}


def sayac(cid):
    with Session(engine()) as db:
        c = db.get(Customer, cid)
        return c.alarm_count, c.alarm_closed_count


# --- sorgular ---------------------------------------------------------------------------------------------------------
def test_sorgular_tek_select_kurumsal_iki_yonlu_sinirli_kisisel_veri_yok():
    acik = oracle.sorgu_temizle(temip_kayit.acik_sorgusu(date(2026, 1, 1)))
    kapali = oracle.sorgu_temizle(temip_kayit.kapali_sorgusu("DATE '2026-01-01'", "SYSDATE + 1"))
    kimlik = oracle.sorgu_temizle(temip_kayit.kimlik_sorgusu(["43581308", "1"], datetime(2026, 10, 1), datetime(2026, 10, 3)))
    for s in (acik, kapali, kimlik):
        assert "IN ('NOC DESTECH')" in s and "REGEXP_LIKE(INFORMATION1, '^[0-9]{8}$')" in s
        assert "INSTR(LOWER(MANAGEDOBJECT), 'nw_li_cust') > 0 OR INSTR(LOWER(NODE1), 'nw_li_cust') > 0" in s
        assert "CIName:[[:space:]]*" in s and "REGEXP_SUBSTR(ALARMOBJECTOPERATORNO, '^[0-9]+')" in s
        assert sum(s.upper().count(k) for k in (" INSERT ", " UPDATE ", " DELETE ")) == 0
    assert "TEMIP.ACTIVEALARMS_5DK" in acik and "EVENTTIME >= DATE '2026-01-01'" in acik
    assert "TEMIP.VIEW_REPORT_ACTIVE" in kapali and "EVENTTIME >= DATE '2026-01-01' AND EVENTTIME < SYSDATE + 1" in kapali
    assert (
        "IDENTIFIER IN (43581308, 1)" in kimlik
        and "TO_DATE('2026-10-01 00:00:00'" in kimlik
        and "EVENTTIME < TO_DATE('2026-10-03" in kimlik
    )
    assert "WHEN CLOSEUSERIDENTIFIER IN ('atm', 'Auto-Clear') THEN CLOSEUSERIDENTIFIER" in kapali and "ELSE 'operator'" in kapali
    for kotu in ([], ["1 OR 1=1"], ["abc"], ["1)"]):
        with pytest.raises(reportdb.ReportdbHata):
            temip_kayit.kimlik_sorgusu(kotu, datetime(2026, 1, 1), datetime(2026, 1, 2))


def test_baslangic_ayari_ve_ay_dilimleri(monkeypatch):
    monkeypatch.delenv(temip_kayit.BASLANGIC_ANAHTARI, raising=False)
    assert temip_kayit.baslangic() == date(2026, 1, 1)
    monkeypatch.setenv(temip_kayit.BASLANGIC_ANAHTARI, "2026-03-15")
    assert temip_kayit.baslangic() == date(2026, 3, 15)
    monkeypatch.setenv(temip_kayit.BASLANGIC_ANAHTARI, "15.03.2026")
    with pytest.raises(reportdb.ReportdbHata):
        temip_kayit.baslangic()
    assert temip_kayit._aylar(date(2025, 12, 10), date(2026, 2, 1)) == [
        (date(2025, 12, 10), date(2026, 1, 1)), (date(2026, 1, 1), date(2026, 2, 1)), (date(2026, 2, 1), date(2026, 3, 1))]  # fmt: skip


# --- yazim, atama, kapanis --------------------------------------------------------------------------------------------
def test_eslesen_karta_eslesmeyen_radara_tekrar_yazim_idempotent(client, monkeypatch):
    a = kart("ORNEK-A", "10000001")
    kart("ORNEK-NUMARASIZ")
    t = SahteTemip(monkeypatch)
    t.kapali = [
        tsatir("1", "10000001", ticket="10134000001", acilis="2026-10-16 09:00:00", kapanis="2026-10-16 11:00:00", durum="Closed/atm")
    ]
    t.acik = [tsatir("2", "10000001", ticket="10134000002"), tsatir("3", "20000002", unvan="RADAR MUSTERISI", ticket="")]
    ozet = calistir()
    assert (ozet["eklenen"], ozet["acik_satir"], ozet["etkilenen_kart"]) == (3, 2, 1)
    k = kayitlar()
    assert {x: (r.customer_id, r.status, r.kind, r.ticket_no, r.customer_no) for x, r in k.items()} == {
        "1": (a, "closed", "alarm", "10134000001", "10000001"),
        "2": (a, "open", "alarm", "10134000002", "10000001"),
        "3": (None, "open", "alarm", "", "20000002"),
    }
    assert k["1"].location == "nw_li_cust_ornek_1" and k["1"].category == "AVAILABILITY" and k["1"].detail == "Closed/atm"
    assert k["1"].opened_at.replace(tzinfo=UTC) == datetime(2026, 10, 16, 6, 0, tzinfo=UTC)  # TR saati -> UTC
    assert sayac(a) == (1, 1)  # acik 1, bu yil kapanan 1: kayitlardan
    assert calistir()["eklenen"] == 0 and len(kayitlar()) == 3  # ayni veri: cift kayit yok


def test_goruntuden_dusen_acik_kimlikle_kapanir_kapali_yeniden_acilmaz(client, monkeypatch):
    a = kart("ORNEK-A", "10000001")
    t = SahteTemip(monkeypatch)
    t.acik = [tsatir("2", "10000001", acilis="2026-10-10 08:00:00"), tsatir("4", "10000001")]
    calistir()
    t.acik = [tsatir("4", "10000001")]  # 2 goruntuden dustu; kapanisi tarih araligi cok eski oldugu icin artimli kapali sorgusunda yok
    t.kimlikle = {"2": tsatir("2", "10000001", acilis="2026-10-10 08:00:00", kapanis="2026-10-17 12:00:00", durum="Closed/Auto-Clear")}
    ozet = calistir()
    assert ozet["dusen_acik"] == 1 and ozet["kapanan_sorgu"] == 1
    sorgu = next(s for s in t.sorgular if " AND IDENTIFIER IN (" in s)
    assert "IDENTIFIER IN (2)" in sorgu and "TO_DATE('2026-10-09 08:00:00'" in sorgu  # acilis - 1 gun (TR)
    k = kayitlar()
    assert (k["2"].status, k["2"].detail, k["4"].status) == ("closed", "Closed/Auto-Clear", "open")
    t.acik = [tsatir("2", "10000001"), tsatir("4", "10000001")]  # goruntu geride kaldi: kapali kayit acilmaz
    assert calistir()["atlanan"] >= 1 and kayitlar()["2"].status == "closed"
    assert sayac(a) == (1, 1)


def test_kart_numarasi_eklenince_radar_kaydi_karta_gecer_cikinca_doner(client, monkeypatch):
    t = SahteTemip(monkeypatch)
    t.acik = [tsatir("3", "20000002", unvan="RADAR MUSTERISI")]
    calistir()
    assert kayitlar()["3"].customer_id is None
    b = kart("ORNEK-B", "20000002")
    ozet = calistir()
    assert ozet["yeniden_baglanan"] == 0 and kayitlar()["3"].customer_id == b  # yazimda zaten karta duser
    with Session(engine()) as db:
        db.get(Customer, b).customer_no = "99999999"
        db.commit()
    t.acik = []
    t.kimlikle = {}
    ozet = calistir()
    assert ozet["yeniden_baglanan"] == 1 and kayitlar()["3"].customer_id is None and sayac(b) == (0, 0)


def test_ikiz_numara_belirsiz_radara_duser(client, monkeypatch):
    kart("IKIZ-1", "30000003")
    kart("IKIZ-2", "30000003")
    t = SahteTemip(monkeypatch)
    t.acik = [tsatir("5", "30000003")]
    calistir()
    assert kayitlar()["5"].customer_id is None


def test_otomatik_kip_gunde_bir_mutabakat(client, monkeypatch):
    SahteTemip(monkeypatch)
    monkeypatch.setattr(temip_kayit, "simdi", lambda: datetime(2026, 10, 17, 0, 30, tzinfo=UTC))  # TR 03:30
    with Session(engine()) as db:
        assert temip_kayit.otomatik_kip(db) == "mutabakat"
    calistir("mutabakat")
    with Session(engine()) as db:
        assert temip_kayit.otomatik_kip(db) == "artimli"
    monkeypatch.setattr(temip_kayit, "simdi", lambda: datetime(2026, 10, 17, 22, 30, tzinfo=UTC))  # TR ertesi gun 01:30
    with Session(engine()) as db:
        assert temip_kayit.otomatik_kip(db) == "artimli"  # saat 02:00'dan once
    monkeypatch.setattr(temip_kayit, "simdi", lambda: datetime(2026, 10, 18, 0, 0, tzinfo=UTC))  # TR 03:00
    with Session(engine()) as db:
        assert temip_kayit.otomatik_kip(db) == "mutabakat"


# --- Onedesk ve TAM Radar ---------------------------------------------------------------------------------------------
def test_onedesk_radar_kayitlarini_saymaz_radar_musteri_bazinda_listeler(client, monkeypatch):
    a = kart("ORNEK-A", "10000001")
    kart("VODAFONE NET ILETISIM")  # ayni unvan cekirdegi, numarasiz kart: kart adayi
    t = SahteTemip(monkeypatch)
    t.kapali = [tsatir("6", "40000004", unvan="VODAFONE NET ILETISIM A.S.", kapanis="2026-10-17 11:00:00", durum="Closed/atm")]
    t.acik = [
        tsatir("2", "10000001"),
        tsatir("7", "40000004", unvan="VODAFONE NET ILETISIM A.S.", ticket=""),
        tsatir("8", "50000005", unvan="BASKA FIRMA"),
        tsatir("9", "60000006", unvan="RADARA ATANMAMIS"),  # Fark'ta bekler, Radar'da yok
    ]
    calistir()
    with Session(engine()) as db:
        assert temip_atama.radara_gonder(db, ["40000004", "50000005"], "admin")["atanan"] == 2
        d = onedesk.durum(db, ADMIN, "acik")
        assert d["toplam"]["alarm"] == 1 and [m["id"] for m in d["musteriler"]] == [a]  # kartsiz TEMIP kaydi Onedesk'e girmez
        v = radar.adaylar(db, adet=10)
        assert v["kaynak"] == "kayit" and v["toplam_musteri"] == 2 and v["toplam_kayit"] == 3
        ilk = v["satirlar"][0]
        assert (ilk["musteri_no"], ilk["aktif"], ilk["kapanan"], ilk["ticketli"], ilk["sira"]) == ("40000004", 1, 1, 1, 1)
        assert ilk["kart_adayi"]["ad"] == "VODAFONE NET ILETISIM" and v["satirlar"][1]["kart_adayi"] is None
        assert radar.adaylar(db, arama="baska")["toplam_musteri"] == 1
        assert radar.adaylar(db, adet=1, sayfa=2)["satirlar"][0]["musteri_no"] == "50000005"
        assert moduller._ekip_geneli(db, 2026)["radar"]()["deger"] == 2
    login_ok(client)
    r = client.get("/api/v1/radar/40000004/kayitlar").json()["data"]
    assert r["toplam"] == 2 and [k["kimlik"] for k in r["kayitlar"]] == ["7", "6"]  # en yeni once
    assert r["kayitlar"][1] | {"acilis": None, "kapanis": None} == {
        "kimlik": "6", "ticket": "10134000001", "ci": "nw_li_cust_ornek_1", "baslik": "AVAILABILITY", "durum": "closed",
        "ayrinti": "Closed/atm", "acilis": None, "kapanis": None}  # fmt: skip
    assert client.get("/api/v1/radar/10000001/kayitlar").status_code == 404  # karta bagli kayit Radar'da yok
    assert client.get("/api/v1/radar/abc/kayitlar").status_code == 400
    assert client.get("/api/v1/radar/60000006/kayitlar").status_code == 404  # kartsiz ama Radar'a atanmamis
    assert client.get("/api/v1/radar?adet=2&q=VODAFONE").json()["data"]["toplam_musteri"] == 1


# --- eslesme: Musteri No -> unvan -> kart -> sorumlu personel -> acik kayit -------------------------------------------
def kisi(ad: str, rol: str = "TeamMember") -> int:
    with Session(engine()) as db:
        u = AppUser(username=f"ornek_{ad}", display_name=f"Ornek {ad}", role=rol)
        db.add(u)
        db.commit()
        return u.id


def sahip(cid: int, uid: int | None, cati: int | None = None) -> None:
    with Session(engine()) as db:
        c = db.get(Customer, cid)
        c.owner_id, c.parent_id = uid, cati
        db.commit()


def eslesme_satirlari(t: SahteTemip) -> None:
    t.kapali = [tsatir("1", "10000001", kapanis="2026-10-17 11:00:00", durum="Closed/atm")]
    t.acik = [
        tsatir("2", "10000001"),
        tsatir("3", "10000001", ticket=""),
        tsatir("4", "60000006", unvan="ISTIRAK A.S."),
        tsatir("5", "70000007", unvan="MUDUR KARTI"),
        tsatir("6", "30000003"),
        tsatir("7", "20000002", unvan="RADAR MUSTERISI"),
        tsatir("1", "10000001"),  # goruntu geride: kapali olan kazanir, acik sayilmaz
    ]


def test_eslesme_kart_personel_radar_belirsiz_kuru_ve_rapor_ayni(client, monkeypatch):
    tam, mudur = kisi("tam"), kisi("mudur", "TeamMngr")
    a, ist, m = kart("ORNEK-A", "10000001"), kart("ORNEK-ISTIRAK", "60000006"), kart("ORNEK-MUDUR", "70000007")
    kart("IKIZ-1", "30000003")
    kart("IKIZ-2", "30000003")
    kart("UZUN-NO", "123456789")
    sahip(a, tam)
    sahip(ist, None, cati=a)  # istirakin sahibi yok: catinin sorumlusu
    sahip(m, mudur)
    t = SahteTemip(monkeypatch)
    eslesme_satirlari(t)
    with Session(engine()) as db:
        kuru = temip_kayit.onizle(db, "artimli")
    assert kayitlar() == {}  # kuru deneme yazmaz
    calistir()
    with Session(engine()) as db:
        rapor = temip_kayit.eslesme_raporu(db)
    for r in (kuru, rapor):
        assert r["ozet"] == {
            "kart": {"musteri": 2, "acik": 3, "kapali": 1},
            "kart_personelsiz": {"musteri": 1, "acik": 1, "kapali": 0},
            "radar": {"musteri": 1, "acik": 1, "kapali": 0},
            "belirsiz": {"musteri": 1, "acik": 1, "kapali": 0},
        }
        satir = {x["musteri_no"]: x for x in r["musteriler"]}
        assert (satir["10000001"]["personel"], satir["10000001"]["acik"], satir["10000001"]["acik_ticketli"]) == ("Ornek tam", 2, 1)
        assert (satir["60000006"]["personel"], satir["60000006"]["cati"], satir["60000006"]["kart_id"]) == ("Ornek tam", "ORNEK-A", ist)
        assert satir["30000003"]["aday_kartlar"] == "IKIZ-1, IKIZ-2" and satir["20000002"]["kart_id"] == ""
        assert [(p["personel_kullanici"], p["tam"], p["kart"], p["acik"]) for p in r["personel"]] == [
            ("ornek_tam", True, 2, 3), ("ornek_mudur", False, 1, 1)]  # fmt: skip
        assert r["uyari"]["belirsiz_numara"] == ["30000003"] and r["uyari"]["personelsiz_kart"] == ["ORNEK-MUDUR"]
        assert r["uyari"]["bicimsiz_kart_no"] == ["UZUN-NO"]
    assert rapor["bagli_olmayan"] == 0
    with Session(engine()) as db:
        db.get(Customer, ist).customer_no = "61111111"  # numara degisti: kayit sonraki turda Radar'a doner
        db.commit()
        assert temip_kayit.eslesme_raporu(db)["bagli_olmayan"] == 1


def test_isci_temip_eslesme_csv_yazar_oracle_istemez(client, monkeypatch, tmp_path, capsys):
    from app import isci

    sahip(kart("ORNEK-A", "10000001"), kisi("tam"))
    t = SahteTemip(monkeypatch)
    eslesme_satirlari(t)
    calistir()
    monkeypatch.setattr(isci, "Path", lambda *_: tmp_path / "app" / "isci.py")
    monkeypatch.setattr(isci, "_istemci", lambda *_: pytest.fail("Oracle istemcisi aranmamali"))
    assert isci.main(["temip-eslesme", "--csv"]) == 0
    cikti = capsys.readouterr().out
    assert "karta (sorumlu TAM)" in cikti and "Ornek tam" in cikti
    musteri = next((tmp_path / "var" / "kesif").glob("temip-eslesme-*-musteri.csv")).read_text(encoding="utf-8-sig")
    assert musteri.splitlines()[0].startswith("musteri_no;temip_unvan;durum;kart_id") and "10000001;" in musteri


def test_katalogdan_kapananlar_ham_dosyadan_acik_oracle_dan(client, monkeypatch, tmp_path):
    """Ilk yukleme: kapananlar son hazir katalogun ham dosyasindan (kosul ayni: domain, 8 haneli Musteri No, CI'da nw_li_cust),
    sonra son 1 gun + acik goruntu Oracle'dan."""
    from app.tampon import katalog
    from app.tampon.models import SourceCatalog, SourceCatalogObject

    monkeypatch.setattr(katalog, "HAM_DIZIN", tmp_path)
    a = kart("ORNEK-A", "10000001")
    sutunlar = ["IDENTIFIER", "INFORMATION1", "INFORMATION2", "ALARMOBJECTOPERATORNO", "ADDITIONALTEXT", "NODE1", "MANAGEDOBJECT",
                "ALARMHEADER", "EVENTTIME", "CLOSETIMESTAMP", "CLOSEUSERIDENTIFIER"]  # fmt: skip
    with Session(engine()) as db:
        k = SourceCatalog(source_key=katalog.KAYNAK, status="ready", started_at=katalog.simdi(), created_by="t", summary={}, error="")
        db.add(k)
        db.flush()
        y = katalog.HamYazici(k.id)
        t = y.tablo_adi("TEMIP", "VIEW_REPORT_ACTIVE")
        y.olustur(t, sutunlar)
        y.yaz(t, [
            ["NOC DESTECH", 11, "10000001", "ORNEK A.S.", "10134000011 NOT", "AVAILABILITY\nCIName: nw_li_cust_a_1", "nw_li_cust_a_1", "x",
             "AVAILABILITY", "2026-03-01 10:00:00", "2026-03-01 12:00:00", "atm"],
            ["NOC DESTECH", 12, "20000002", "RADAR A.S.", None, "metin", "nw_li_cust_b_2", "x", "AVAILABILITY", "2026-04-01 10:00:00",
             "2026-04-01 10:05:00", "Auto-Clear"],
            ["NOC DESTECH", 13, "ABC", "NUMARASIZ", None, "", "nw_li_cust_c", "x", "AVAILABILITY", "2026-04-01 10:00:00", "2026-04-01 11:00:00", "atm"],
            ["NOC DESTECH", 14, "30000003", "CI YOK", None, "", "baska_node", "baska", "AVAILABILITY", "2026-04-01 10:00:00", "2026-04-01 11:00:00", "atm"],
            ["NOC DESTECH", 15, "10000001", "ORNEK A.S.", None, "", "nw_li_cust_a_1", "x", "AVAILABILITY", "2025-12-31 23:00:00", "2026-01-01 01:00:00", "atm"],
        ])  # fmt: skip
        y.kapat()
        db.add(SourceCatalogObject(catalog_id=k.id, owner="TEMIP", name="VIEW_REPORT_ACTIVE", kind="TABLE", parent="", comment="", analyzed="",
                                   columns=[], details={"arama": {"ham_tablo": t}}, sample_columns=sutunlar, sample_rows=0, sample_note=""))  # fmt: skip
        db.commit()
    tm = SahteTemip(monkeypatch)
    tm.acik = [tsatir("2", "10000001")]
    ozet = calistir("katalogdan")
    assert ozet["katalog_satir"] == 2 and ozet["eklenen"] == 3  # numarasiz, CI'siz ve baslangictan once acilan alinmaz
    k = kayitlar()
    assert (k["11"].customer_id, k["11"].ticket_no, k["11"].location, k["11"].detail, k["11"].status) == (
        a,
        "10134000011",
        "nw_li_cust_a_1",
        "Closed/atm",
        "closed",
    )
    assert (k["12"].customer_id, k["12"].location, k["12"].detail) == (None, "nw_li_cust_b_2", "Closed/Auto-Clear")  # kartsiz: TAM Radar
    assert k["2"].status == "open" and sayac(a) == (1, 1)
