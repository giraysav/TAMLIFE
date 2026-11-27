# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Aylik rapor: onceki ay donemi, iki dilli hazir metinler, SLA Excel'i (yalniz adet/sure grafikleri, ileti eki),
GALAPAGOS gorselleri, ek dosyalar, SLA analizi (yerlesik + YZ) ve personel metninin cevirisi."""

import base64
import io
import json
import zipfile
from datetime import UTC, datetime
from email import message_from_bytes
from email.policy import default

import openpyxl
import pytest
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser, Customer
from app.onedesk import yz
from app.ortak import MONTH_LABELS_TR, rapor_donemi
from app.rapor import ceviri
from app.rapor import metin as rapor_metin
from app.rapor import servis as rapor_servis
from tests_v35.conftest import login_ok

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
URL = "/api/v1/musteri/1/rapor"


@pytest.fixture
def veri(client, monkeypatch, tmp_path):
    monkeypatch.setenv("TAMLIFE_REPORT_DIR", str(tmp_path / "raporlar"))
    with Session(engine()) as db:
        db.add(AppUser(id=1, username="admin", display_name="Admin Kisi", role="admin", is_admin=True))
        db.flush()
        db.add(Customer(id=1, external_key="t-a", name="Alfa Test A.S.", segment="MA", owner_id=1))
        db.commit()
    return client


def _cizim_ekle(xlsx: bytes, sayfa_no: int, sutunlar: list[int]) -> bytes:
    """openpyxl Pillow'suz gorsel yazamaz: cizimi zip'e elle ekler (Excel'in yazdigi yapiyla ayni yollar)."""
    kaynak = zipfile.ZipFile(io.BytesIO(xlsx))
    cikti = io.BytesIO()
    capalar = "".join(
        f"<xdr:oneCellAnchor><xdr:from><xdr:col>{s - 1}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>20</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>"
        f'<xdr:ext cx="1" cy="1"/><xdr:pic><xdr:blipFill><a:blip r:embed="rId{i}"/></xdr:blipFill></xdr:pic><xdr:clientData/></xdr:oneCellAnchor>'
        for i, s in enumerate(sutunlar, start=1)
    )
    cizim = (
        '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">{capalar}</xdr:wsDr>'
    )
    iliski = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{}</Relationships>'
    cizim_rels = iliski.format(
        "".join(f'<Relationship Id="rId{i}" Type="image" Target="../media/image{i}.png"/>' for i in range(1, len(sutunlar) + 1))
    )
    sayfa_rels = iliski.format('<Relationship Id="rIdD" Type="drawing" Target="/xl/drawings/drawing1.xml"/>')
    with zipfile.ZipFile(cikti, "w") as z:
        for ad in kaynak.namelist():
            z.writestr(ad, kaynak.read(ad))
        z.writestr("xl/drawings/drawing1.xml", cizim)
        z.writestr("xl/drawings/_rels/drawing1.xml.rels", cizim_rels)
        z.writestr(f"xl/worksheets/_rels/sheet{sayfa_no}.xml.rels", sayfa_rels)
        for i in range(1, len(sutunlar) + 1):
            z.writestr(f"xl/media/image{i}.png", PNG)
    return cikti.getvalue()


def _sla_excel(donem: str, musteri: str | None = None) -> bytes:
    """musteri verilirse Detay sayfasina OneDesk ciktisindaki gibi 'Müşteri Adı' sutunu eklenir."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Alarm Analiz"
    ws["B4"] = "Aylık Kapanan Alarm Adetleri"
    ws["B5"], ws["C5"], ws["D5"], ws["E5"] = (
        "Kapanış Ayı",
        "Alarm Adedi",
        "Çağrı Ortalama Çözüm Süresi (dk)",
        "Çağrı Ortalama İlk Müdahale Süresi (dk)",
    )
    for i, (ay, adet, cozum, ilk) in enumerate([("2026-07", 4, 120, 10), (donem, 7, "no data returned", 12), ("Total", 11, 0, 0)], start=6):
        (
            ws.cell(row=i, column=2, value=ay),
            ws.cell(row=i, column=3, value=adet),
            ws.cell(row=i, column=4, value=cozum),
            ws.cell(row=i, column=5, value=ilk),
        )
    detay = wb.create_sheet("Alarm Detay")
    detay.append(["No", "CI Adı", "Kategori", "Çağrı Servisi", "Kök Sebep", "Çözüm Açıklaması", "Kapanış Ayı", *(["Müşteri Adı"] if musteri else [])])
    for no, (ci, kat, kok, ay) in enumerate(
        [
            ("IST-HAT-1", "Hat Down 1", "Fiber kesik", "2026-07"),
            ("IST-HAT-1", "Hat Down 2", "Fiber kesik", donem),
            ("ANK-SW-3", "CPU yüksek", "Kapasite", donem),
            ("ACIK-KAYIT", "Hat Down", "", None),  # kapanmamis: analize girmez
        ],
        start=1,
    ):
        detay.append([no, ci, kat, "Data", kok, "Ekip yonlendirildi", ay, *([musteri] if musteri else [])])
    hat = wb.create_sheet("Hat Availability")
    hat.append(["Devre", "Availability"])
    hat.append(["D-1", 99.5])
    hat.append(["D-2", 100])
    tampon = io.BytesIO()
    wb.save(tampon)
    return _cizim_ekle(tampon.getvalue(), 1, [2, 9])  # gomulu gorseller (pasta vb.) rapora girmemeli


def test_rapor_donemi_onceki_aydir(monkeypatch):
    assert rapor_donemi(datetime(2026, 10, 11)) == (2026, 9)
    assert rapor_donemi(datetime(2027, 1, 3)) == (2026, 12)
    monkeypatch.setattr(rapor_servis, "simdi", lambda: datetime(2026, 10, 1, tzinfo=UTC))
    assert rapor_servis.donem() == (2026, 9)


def test_taslak_iki_dilli_hazir_metin_ve_panel_dili(veri):
    login_ok(veri)
    t = veri.get(f"{URL}/taslak").json()["data"]
    yil, ay = rapor_servis.donem()
    assert (t["yil"], t["ay"]) == (yil, ay) and t["alanlar"]["dil"] == "tr" and t["sla"] is None
    assert set(t["varsayilanlar"]) == {"tr", "en"}
    en = t["varsayilanlar"]["en"]
    assert en["olumlu"] == rapor_metin.VARSAYILAN_METINLER["en"]["olumlu"] and en["bilgi"] == rapor_metin.BASLANGIC_METINLERI["en"]["bilgi"]
    assert en["konu"].startswith("TAM Monthly Report") and "Technical Account Manager" in en["imza"]
    assert t["varsayilanlar"]["tr"]["konu"].startswith("TAM Aylık Rapor")
    # kayitli taslak yokken panel Ingilizce ise rapor da Ingilizce acilir
    t_en = veri.get(f"{URL}/taslak", headers={"X-Dil": "en"}).json()["data"]
    assert t_en["alanlar"]["dil"] == "en" and t_en["alanlar"]["kritik"] == rapor_metin.VARSAYILAN_METINLER["en"]["kritik"]


def test_sla_excel_grafikleri_sinirsiz_ve_donem_sayilari(veri):
    hdr = login_ok(veri)
    yil, ay = rapor_servis.donem()
    donem = f"{yil}-{ay:02d}"
    assert veri.put(f"{URL}/sla", content=b"bozuk", headers=hdr).status_code == 400
    r = veri.put(f"{URL}/sla", params={"dosya": "OneDesk SLA.xlsx"}, content=_sla_excel(donem), headers=hdr)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    g = {x["anahtar"]: x for x in d["analiz"]["grafikler"]}
    assert list(g) == ["alarm-adet", "alarm-sure"]  # yalniz kapanan adet + yaninda sure ortalamalari; gomulu gorseller yok
    assert all(x["gorsel"] is None for x in g.values())  # seri tarayicida cizilir
    assert g["alarm-adet"]["aylar"] == ["2026-07", donem] and g["alarm-adet"]["seriler"]["adet"] == [4, 7]
    assert g["alarm-adet"]["pivot"] == "Aylık Kapanan Alarm Adetleri"
    assert g["alarm-sure"]["seriler"] == {"ilk": [10, 12], "cozum": [120, None]}  # metin hucre sahte sifir olmaz
    assert g["alarm-adet"]["baslik"]["en"] == "Monthly Closed Alarm Count"
    assert g["alarm-sure"]["baslik"]["tr"] == "Aylık Kapanan Alarm İlk Müdahale ve Çözüm Süre Ortalamaları"
    assert d["analiz"]["sayilar"]["alarm"] == {"donem": 2, "toplam": 4} and "Şikayet Detay" in d["analiz"]["eksik"]
    assert d["ozet"]["dosya"] == "OneDesk SLA.xlsx" and d["ozet"]["grafik"] == 2
    assert veri.get(f"{URL}/taslak").json()["data"]["sla"]["dosya"] == "OneDesk SLA.xlsx"


def test_gorsel_ekle_sil_ve_gonderimde_ekler(veri):
    hdr = login_ok(veri)
    yil, ay = rapor_servis.donem()
    assert veri.post(f"{URL}/gorsel", content=b"metin", headers=hdr).status_code == 400  # gorsel degil
    r = veri.post(f"{URL}/gorsel", params={"baslik": "MRTG  Ana hat"}, content=PNG, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["ekler"][0]["baslik"] == "MRTG Ana hat"
    no = r.json()["data"]["ekler"][0]["no"]
    assert veri.post(f"{URL}/gorsel", content=PNG, headers=hdr).json()["data"]["ekler"][1]["no"] == no + 1
    assert veri.delete(f"{URL}/gorsel/{no}", headers=hdr).json()["data"]["ekler"][0]["no"] == no + 1
    assert veri.delete(f"{URL}/gorsel/{no}", headers=hdr).status_code == 404
    xlsx = _sla_excel(f"{yil}-{ay:02d}")
    assert veri.put(f"{URL}/sla", params={"dosya": "sla.xlsx"}, content=xlsx, headers=hdr).status_code == 200

    pdf = base64.b64encode(b"%PDF-1.4 rapor").decode()
    r = veri.post(f"{URL}/gonder", json={"onay": True, "to": "a@example.com", "lang": "en", "pdf_base64": pdf}, headers=hdr)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    msg = message_from_bytes(base64.b64decode(d["eml_base64"]), policy=default)
    ekler = {e.get_filename(): e for e in msg.iter_attachments()}
    assert set(ekler) == set(d["ekler"]) == {d["eml_adi"][:-4] + ".pdf", "sla.xlsx"}
    assert ekler["sla.xlsx"].get_content_type() == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert ekler["sla.xlsx"].get_content() == xlsx
    assert msg["Subject"].startswith("TAM Monthly Report")  # konu bos: rapor dilinde hazir konu
    # gonderilen donemin ekleri degismez
    assert veri.put(f"{URL}/sla", content=xlsx, headers=hdr).status_code == 409
    assert veri.delete(f"{URL}/sla", headers=hdr).status_code == 409
    assert veri.post(f"{URL}/gorsel", content=PNG, headers=hdr).status_code == 409


def test_sla_sil_ekleri_korur(veri):
    hdr = login_ok(veri)
    yil, ay = rapor_servis.donem()
    veri.put(f"{URL}/sla", content=_sla_excel(f"{yil}-{ay:02d}"), headers=hdr)
    veri.post(f"{URL}/gorsel", content=PNG, headers=hdr)
    d = veri.delete(f"{URL}/sla", headers=hdr).json()["data"]
    assert d["analiz"] is None and len(d["ekler"]) == 1 and d["ozet"]["dosya"] is None
    r = veri.post(f"{URL}/gonder", json={"onay": True}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["ekler"] == []  # SLA yok, PDF gonderilmedi


def test_ek_dosya_ekle_sil_ve_iletide(veri):
    hdr = login_ok(veri)
    url = f"{URL}/dosya"
    assert veri.post(url, params={"ad": "kur.exe"}, content=b"MZ", headers=hdr).status_code == 400  # calistirilabilir
    assert veri.post(url, params={"ad": "bos.txt"}, content=b"", headers=hdr).status_code == 400
    d = veri.post(url, params={"ad": "..\\gizli/Tutanak Eylül.docx"}, content=b"PK-docx", headers=hdr).json()["data"]
    assert d["dosyalar"] == [{"no": 1, "ad": "Tutanak Eylül.docx", "boyut": 7}]  # yol parcasi atilir
    assert veri.post(url, params={"ad": "tutanak eylül.DOCX"}, content=b"x", headers=hdr).status_code == 409  # ayni ad
    assert veri.post(url, params={"ad": "not.txt"}, content=b"merhaba", headers=hdr).status_code == 200
    assert veri.delete(f"{url}/1", headers=hdr).json()["data"]["dosyalar"] == [{"no": 2, "ad": "not.txt", "boyut": 7}]
    assert veri.delete(f"{url}/1", headers=hdr).status_code == 404
    r = veri.post(f"{URL}/gonder", json={"onay": True}, headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["ekler"] == ["not.txt"]
    msg = message_from_bytes(base64.b64decode(r.json()["data"]["eml_base64"]), policy=default)
    ek = next(msg.iter_attachments())
    assert ek.get_content_type() == "text/plain" and ek.get_payload(decode=True) == b"merhaba"
    assert veri.post(url, params={"ad": "gec.txt"}, content=b"x", headers=hdr).status_code == 409  # gonderilen donem kilitli
    assert veri.delete(f"{url}/2", headers=hdr).status_code == 409


def test_sla_analizi_yerlesik_ozet_ve_yz(veri, monkeypatch):
    hdr = login_ok(veri)
    yil, ay = rapor_servis.donem()
    assert veri.post(f"{URL}/sla/analiz", json={}, headers=hdr).status_code == 404  # once Excel
    veri.put(f"{URL}/sla", content=_sla_excel(f"{yil}-{ay:02d}"), headers=hdr)
    d = veri.post(f"{URL}/sla/analiz", json={"dil": "tr"}, headers=hdr).json()["data"]
    a = d["analiz"]
    assert a["toplam"] == 3 and a["donem_toplam"] == {"alarm": 2} and a["ci_sayisi"] == 2 and a["tekrarlayan_ci"] == 1
    assert a["ciler"][0]["ci"] == "IST-HAT-1" and a["ciler"][0]["tekrarlar"][0]["adet"] == 2  # sayi farki ayni grup
    assert "Hattın fiziksel katmanını" in a["ciler"][0]["tekrarlar"][0]["oneriler"][0]  # fiber kurali
    assert a["availability"]["devre_sayisi"] == 2 and a["availability"]["en_dusuk_devre"] == "D-1"
    b = d["ozet"]["bilgi"]
    assert f"• Alarm (SLA raporu, {MONTH_LABELS_TR[ay]} {yil}): 7 kayıt kapatılmış, ortalama ilk müdahale süresi 12 dk." in b  # Excel pivotu
    assert "2 alarm kaydı kapatılmıştır" in b and ".\n\n• " in b  # maddeler arasinda bos satir
    dv = d["ozet"]["devam"]
    assert "• 4 numaralı alarm kaydı (ACIK-KAYIT, Hat Down) açık durumdadır; çalışmalar devam etmektedir." in dv
    # 2026-11-03: Devam Eden Calismalar yalniz acik kayitlar; tekrar eden sorun Bilgilendirme'ye
    assert "IST-HAT-1" not in dv and "IST-HAT-1 için" in b and "2 kez kaydedilmiştir" in b
    assert "Hattın fiziksel" not in b + dv  # musteriye oneri yazilmaz
    assert d["yz"] == {"hazir": False, "yorum": None, "neden": ""}
    en = veri.post(f"{URL}/sla/analiz", json={"dil": "en", "yz": True}, headers=hdr).json()["data"]
    assert (
        "2 alarm records were closed" in en["ozet"]["bilgi"]
        and "Alarm record no. 4 (ACIK-KAYIT, Hat Down) is still open" in en["ozet"]["devam"]
    )
    assert en["yz"]["yorum"] is None and "TAMLIFE_YZ_SAGLAYICI" in en["yz"]["neden"]
    # YZ acik: modele musteri adi gitmez, ozet gider
    monkeypatch.setenv("TAMLIFE_YZ_SAGLAYICI", "anthropic")
    monkeypatch.setenv("TAMLIFE_YZ_VERI_PAYLASIMI", "izinli")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anahtar-degil-gercek")
    giden = {}

    def sahte(icerik, **k):
        giden["icerik"], giden["sistem"] = icerik, k["sistem"]
        return "• Dönem değerlendirmesi"

    monkeypatch.setattr(yz, "tamamla", sahte)
    d = veri.post(f"{URL}/sla/analiz", json={"dil": "tr", "yz": True}, headers=hdr).json()["data"]
    assert d["yz"]["yorum"] == "• Dönem değerlendirmesi" and "IST-HAT-1" in giden["icerik"]
    assert "Alfa Test" not in giden["icerik"] and json.loads(giden["icerik"])["donemde_kapanan"] == {"alarm": 2}
    assert json.loads(giden["icerik"])["acik_kayitlar"][0]["no"] == "4" and "öneri ya da tavsiye YAZMA" in giden["sistem"]
    assert "Türkçe" in giden["sistem"]


def test_metin_cevirisi(veri, monkeypatch, tmp_path):
    hdr = login_ok(veri)
    url = f"{URL}/cevir"
    monkeypatch.setenv("TAMLIFE_CEVIRI_MODEL_DIZINI", str(tmp_path / "yok"))
    r = veri.post(url, json={"alanlar": {"olumlu": "Hat düzeldi."}}, headers=hdr)
    assert r.status_code == 503 and "ceviri_kur.ps1" in r.text  # model yok, YZ kapali: ne gerektigini soyler
    assert veri.post(url, json={"alanlar": "x"}, headers=hdr).status_code == 400
    # model varsa ayri surec kullanilir (burada sahte); bilinmeyen alan gonderilmez
    kok = tmp_path / "model"
    (kok / "model").mkdir(parents=True)
    (kok / "model" / "model.bin").write_bytes(b"0")
    (kok / "sentencepiece.model").write_bytes(b"0")
    monkeypatch.setenv("TAMLIFE_CEVIRI_MODEL_DIZINI", str(kok))
    monkeypatch.setattr(ceviri, "_modelle", lambda d: {k: f"EN:{v}" for k, v in d.items()})
    d = veri.post(url, json={"alanlar": {"olumlu": "Hat düzeldi.", "kritik": "", "baska": "x"}}, headers=hdr).json()["data"]
    assert d == {"alanlar": {"olumlu": "EN:Hat düzeldi.", "kritik": ""}, "kaynak": "model"}

    # model coker / kutuphane yok, YZ acik: YZ ile cevrilir
    def coker(d):
        raise ceviri.CeviriYok("kutuphane")

    monkeypatch.setattr(ceviri, "_modelle", coker)
    monkeypatch.setenv("TAMLIFE_YZ_SAGLAYICI", "anthropic")
    monkeypatch.setenv("TAMLIFE_YZ_VERI_PAYLASIMI", "izinli")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anahtar-degil-gercek")
    monkeypatch.setattr(yz, "tamamla", lambda icerik, **k: 'Tamam: {"olumlu": "The line was fixed."}')
    d = veri.post(url, json={"alanlar": {"olumlu": "Hat düzeldi."}}, headers=hdr).json()["data"]
    assert d == {"alanlar": {"olumlu": "The line was fixed."}, "kaynak": "yz"}


def test_gonderilen_metin_saklanir_ve_takip_alanlari_sonraki_aya_gecer(veri, monkeypatch):
    hdr = login_ok(veri)
    monkeypatch.setattr(rapor_servis, "simdi", lambda: datetime(2026, 10, 5, tzinfo=UTC))  # donem: Eylul
    alanlar = {"devam": "• 1234 numaralı kayıt açık.", "kritik": "Ana hat yedeksiz.", "olumlu": "Hat yenilendi.", "imza": "Giray Sav"}
    r = veri.post(f"{URL}/gonder", json={"onay": True, "alanlar": alanlar}, headers=hdr)
    assert r.status_code == 200, r.text
    t = veri.get(f"{URL}/taslak").json()["data"]  # taslak kaydedilmeden gonderildi: metin yine de kalir
    assert t["alanlar"]["devam"] == alanlar["devam"] and t["alanlar"]["olumlu"] == "Hat yenilendi." and t["gonderim"]
    monkeypatch.setattr(rapor_servis, "simdi", lambda: datetime(2026, 11, 3, tzinfo=UTC))  # donem: Ekim
    t = veri.get(f"{URL}/taslak").json()["data"]
    assert (t["yil"], t["ay"]) == (2026, 10) and t["devreden"] == {"donem": "2026-09", "alanlar": ["devam", "kritik", "imza"]}
    assert t["alanlar"]["devam"] == alanlar["devam"] and t["alanlar"]["kritik"] == "Ana hat yedeksiz."
    assert t["alanlar"]["olumlu"] == rapor_metin.VARSAYILAN_METINLER["tr"]["olumlu"]  # olumlu gelismeler tasinmaz
    # yeni donemde taslak kaydedilince devir biter, kayitli metin gecerli olur
    veri.put(f"{URL}/taslak", json={"alanlar": {"devam": "Güncellendi."}}, headers=hdr)
    t = veri.get(f"{URL}/taslak").json()["data"]
    assert t["devreden"] is None and t["alanlar"]["devam"] == "Güncellendi."


def test_sla_dosyasi_musteri_unvani_denetlenmez(veri):
    """2026-11-02 kullanici: "musteri eslesmesi kuralini kaldir, isteyen istedigi SLA excelini yuklesin" (2026-10-26 unvan kurali
    kalkti). Baska unvanli dosya da yuklenir; grafik ve sayilar her zamanki gibi cikar."""
    hdr = login_ok(veri)
    yil, ay = rapor_servis.donem()
    donem = f"{yil}-{ay:02d}"
    r = veri.put(f"{URL}/sla", params={"dosya": "Beta.xlsx"}, content=_sla_excel(donem, "BETA LOJİSTİK LİMİTED ŞİRKETİ"), headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["analiz"]["musteriler"] == ["BETA LOJİSTİK LİMİTED ŞİRKETİ"] and r.json()["data"]["analiz"]["grafikler"]
    r = veri.put(f"{URL}/sla", params={"dosya": "Alfa.xlsx"}, content=_sla_excel(donem, "ALFA TEST ANONİM ŞİRKETİ"), headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["analiz"]["musteriler"] == ["ALFA TEST ANONİM ŞİRKETİ"]
