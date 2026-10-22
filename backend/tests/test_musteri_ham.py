"""Ham Musteri Verisi: dosya tanima (.xlsx/.csv, baslik satiri, takma adlar, cati/istirak), sablon, onizleme, uygulama, geri alma."""

from __future__ import annotations

import io

import openpyxl
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser, Customer, CustomerTeam
from app.tampon import musteri_ham as H
from tests.conftest import login_ok

TABAN = "/api/v1/tampon/musteri-ham"


@pytest.fixture
def ham(client):
    """Kartlar: Alfa (no 11111111, TAM ayse), Beta (no 22222222). Personel: ayse (Ayşe Kaya), mehmet (pasif)."""
    hdr = login_ok(client)
    with Session(engine()) as db:
        ayse = AppUser(username="TC1001", display_name="Ayşe Kaya", role="TeamMember", active=True)
        db.add_all([ayse, AppUser(username="TC1002", display_name="Mehmet Pasif", role="TeamMember", active=False)])
        db.flush()
        db.add_all(
            [
                Customer(id=1, external_key="k1", name="Alfa Teknoloji A.Ş.", customer_no="11111111", owner_id=ayse.id, segment="MA"),
                Customer(id=2, external_key="k2", name="Beta Enerji", customer_no="22222222"),
            ]
        )
        db.commit()
    return client, hdr


def _xlsx(sayfalar: dict[str, list[list[object]]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for ad, satirlar in sayfalar.items():
        ws = wb.create_sheet(ad)
        for r in satirlar:
            ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _yukle(client, hdr, veri: bytes, dosya: str = "liste.xlsx") -> dict:
    r = client.put(f"{TABAN}/yukle?dosya={dosya}", content=veri, headers={**hdr, "Content-Type": "application/octet-stream"})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _onizle(client, hdr, pid: int, yeni: bool = False) -> dict:
    r = client.post(f"{TABAN}/onizle", json={"parti_id": pid, "yeni_olustur": yeni}, headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_baslik_satiri_ve_sayfa_kendiliginden_bulunur():
    veri = _xlsx(
        {
            "Kapak": [["TAM Müşteri Listesi"], [], ["hazırlayan", "x"]],
            "EKİP & İLETİŞİM": [
                ["Ekim 2026 listesi"],
                [],
                ["Müşteri NO", "TAM Temsilcisi", "Segment", "MÜŞTERİ ADI"],
                ["123", "TC1001", "MA", "Gama"],
            ],
        }
    )
    t = H.dosya_oku(veri, "liste.xlsx")
    assert t["sayfa"] == "EKİP & İLETİŞİM"
    assert t["basliklar"] == ["Müşteri NO", "TAM Temsilcisi", "Segment", "MÜŞTERİ ADI"]
    assert t["satirlar"] == [["123", "TC1001", "MA", "Gama"]]
    u = H.uyum_raporu(t["basliklar"])
    assert u["uyumlu"] and u["bicim"] == "liste" and u["eslesen"] == 4 and not u["fazla"]


def test_tanınmayan_dosya_reddedilir():
    from app.ortak import UygulamaHatasi

    with pytest.raises(UygulamaHatasi):
        H.dosya_oku(_xlsx({"S": [["a", "b"], [1, 2]]}), "x.xlsx")
    with pytest.raises(UygulamaHatasi):
        H.dosya_oku(b"bozuk", "x.xlsx")


def test_sablon_bos_ve_dolu_geri_okunur(ham):
    client, _ = ham
    bos = client.get(f"{TABAN}/sablon.xlsx")
    assert bos.status_code == 200 and "spreadsheetml" in bos.headers["content-type"]
    t = H.dosya_oku(bos.content, "s.xlsx")
    assert t["sayfa"] == H.SAYFA and t["basliklar"] == [b for b, _ in H.SABLON] and t["satirlar"] == []
    dolu_veri = client.get(f"{TABAN}/sablon.xlsx?dolu=true").content
    dolu = H.dosya_oku(dolu_veri, "s.xlsx")
    assert [r[1] for r in dolu["satirlar"]] == ["Alfa Teknoloji A.Ş.", "Beta Enerji"]  # Cati Musteri Unvani
    assert dolu["satirlar"][0][0] == "Ayşe Kaya" and dolu["satirlar"][0][2] == "11111111"  # Sorumlu TAM, Cati Musteri No
    # dolu sablon geri yuklenince hicbir karta degisiklik dusmez
    _, hdr = ham
    p = _yukle(client, hdr, dolu_veri)
    assert p["uyum"]["bicim"] == "genis" and p["uyum"]["uyumlu"] and not p["uyum"]["fazla"]
    o = _onizle(client, hdr, p["id"])
    assert o["ozet"]["guncelle"] == 0 and o["ozet"]["yeni"] == 0 and o["ozet"]["hata"] == 0


def test_kullanici_sablonu_bicim_ve_ice_alma(ham):
    """2026-10-15 kullanici sablonu: tek sayfa, 20 sutun, koyu mavi baslik, C2'den sabit; 'Çatı_to_İştirak Müşteri No' taninir."""
    client, hdr = ham
    wb = openpyxl.load_workbook(io.BytesIO(client.get(f"{TABAN}/sablon.xlsx").content))
    ws = wb[H.SAYFA]
    assert wb.sheetnames == [H.SAYFA] and ws.freeze_panes == "C2" and ws.max_column == 20
    assert ws.auto_filter.ref == "A1:T2" and ws.column_dimensions["A"].width == 24
    assert [c.value for c in ws[1]][:6] == ["Sorumlu TAM", "Çatı Müşteri Ünvanı", "Çatı Müşteri No", "Çatı_to_İştirak Müşteri No",
                                            "İştirak Müşteri Ünvanı", "İştirak Müşteri No"]  # fmt: skip
    assert ws["T1"].value == "Mobil KMT Notu" and ws["A1"].font.b and ws["A1"].fill.fgColor.theme == 4
    satirlar = [
        [b for b, _ in H.SABLON],
        ["TC1001", "Delta Holding", "66666666", None, None, None, "SA", "Holding", "Selin Satış"] + [None] * 11,
        ["TC1001", "Delta Holding", "66666666", None, "Delta Lojistik", "77777777", None, "Lojistik"] + [None] * 12,
        [None, None, None, "66666666", "Delta Enerji", "99999999", None, None] + [None] * 4 + ["tac@delta.com.tr"] + [None] * 7,
    ]
    p = _yukle(client, hdr, _xlsx({H.SAYFA: satirlar}))
    assert p["uyum"]["bicim"] == "genis" and p["uyum"]["uyumlu"] and not p["uyum"]["fazla"]
    o = _onizle(client, hdr, p["id"])
    assert o["ozet"]["yeni"] == 3 and o["ozet"]["hata"] == 0
    r = client.post(f"{TABAN}/uygula", json={"parti_id": p["id"], "plan_ozeti": o["plan_ozeti"], "onay": True}, headers=hdr)
    assert r.status_code == 200, r.text
    with Session(engine()) as db:
        cati = db.scalar(select(Customer).where(Customer.name == "Delta Holding"))
        altlar = {c.name: c for c in db.scalars(select(Customer).where(Customer.parent_id == cati.id))}
        assert set(altlar) == {"Delta Lojistik", "Delta Enerji"} and cati.segment == "SA" and cati.sector == "Holding"
        assert db.get(CustomerTeam, cati.id).sales_manager == "Selin Satış"
        assert db.get(CustomerTeam, altlar["Delta Enerji"].id).tac_email == "tac@delta.com.tr"


def test_onizle_uygula_geri_al(ham):
    client, hdr = ham
    veri = _xlsx(
        {
            H.SAYFA: [
                ["Müşteri Ünvanı", "Müşteri No", "Sorumlu TAM", "Segment", "Envanter", "TAC E-posta", "FT Hacim"],
                ["ALFA TEKNOLOJİ (yeni ad)", "11111111, 33333333", None, "Major Account", 12, "tac@alfa.com.tr", 1500.5],
                ["Beta Enerji", None, None, None, None, "bozuk-adres", None],
                ["Yeni Kurum", "44444444", "Ayşe Kaya", "SMB", None, None, None],
                ["Yeni Kurum", "55555555", None, None, None, None, None],
                ["Pasif Müşteri", None, "Mehmet Pasif", None, None, None, None],
            ]
        }
    )
    p = _yukle(client, hdr, veri)
    assert p["durum"] == "ready" and p["uyum"]["uyumlu"] and p["uyum"]["bicim"] == "sablon"
    assert p["uyum"]["fazla"] == ["Envanter", "FT Hacim"]  # sablonda olmayan sutunlar okunmaz
    o = _onizle(client, hdr, p["id"])
    durum = {r["unvan"]: r for r in o["satirlar"]}
    alfa = durum["ALFA TEKNOLOJİ (yeni ad)"]
    assert alfa["durum"] == "guncelle" and any("Müşteri No ile eşleşti" in u for u in alfa["uyarilar"])
    degisen = {d["alan"]: d["yeni"] for d in alfa["degisiklikler"]}
    # Segment 'Major Account' -> MA: kartta zaten MA, degisiklik sayilmaz
    assert degisen == {"customer_no": "11111111, 33333333", "tac_email": "tac@alfa.com.tr"}
    assert durum["Beta Enerji"]["durum"] == "hata"
    yeni = durum["Yeni Kurum"]
    assert yeni["durum"] == "yeni" and any("birleştirildi" in u for u in yeni["uyarilar"])
    assert durum["Pasif Müşteri"]["durum"] == "hata"
    assert o["ozet"]["uygulanacak"] == 1  # yeni olustur kapali: yalniz Alfa

    # plan ozeti tutmazsa 409; onaysiz 400
    assert client.post(f"{TABAN}/uygula", json={"parti_id": p["id"], "plan_ozeti": "x" * 64, "onay": True}, headers=hdr).status_code == 409
    assert client.post(f"{TABAN}/uygula", json={"parti_id": p["id"], "plan_ozeti": o["plan_ozeti"]}, headers=hdr).status_code == 400

    o2 = _onizle(client, hdr, p["id"], yeni=True)
    r = client.post(
        f"{TABAN}/uygula", json={"parti_id": p["id"], "yeni_olustur": True, "plan_ozeti": o2["plan_ozeti"], "onay": True}, headers=hdr
    )
    assert r.status_code == 200, r.text
    s = r.json()["data"]
    assert s["ozet"]["guncellenen"] == 1 and s["ozet"]["olusturulan"] == 1
    with Session(engine()) as db:
        alfa_k = db.get(Customer, 1)
        assert alfa_k.name == "Alfa Teknoloji A.Ş." and alfa_k.customer_no == "11111111, 33333333" and alfa_k.inventory_count == 0
        assert alfa_k.ft_volume != "1.500,50 ₺" and db.get(CustomerTeam, 1).tac_email == "tac@alfa.com.tr"
        yeni_k = db.scalar(select(Customer).where(Customer.name == "Yeni Kurum"))
        assert yeni_k.customer_no == "44444444, 55555555" and yeni_k.segment == "SMB"
        assert db.get(AppUser, yeni_k.owner_id).username == "TC1001"
        alfa_k.customer_no = "11111111, 33333333, 12121212"  # aktarimdan sonra elle degisen alan geri almada korunur
        alfa_k.inventory_count = 99
        db.commit()

    kayitlar = client.get(f"{TABAN}/aktarimlar").json()["data"]
    assert kayitlar[0]["id"] == s["kayit_id"] and kayitlar[0]["geri_alinan"] is None
    g = client.post(f"{TABAN}/aktarimlar/{s['kayit_id']}/geri-al", headers=hdr)
    assert g.status_code == 200, g.text
    assert g.json()["data"]["silinen_musteri"] == 1 and g.json()["data"]["korunan_alan"] == 1
    with Session(engine()) as db:
        alfa_k = db.get(Customer, 1)
        assert alfa_k.customer_no == "11111111, 33333333, 12121212" and alfa_k.segment == "MA" and alfa_k.inventory_count == 99
        assert db.get(CustomerTeam, 1) is None
        assert db.scalar(select(Customer).where(Customer.name == "Yeni Kurum")) is None
    assert client.post(f"{TABAN}/aktarimlar/{s['kayit_id']}/geri-al", headers=hdr).status_code == 409


def test_cati_istirak_genis_bicimi_csv(ham):
    client, hdr = ham
    csv = (
        "Çatı Müşteri Ünvanı;Çatı Müşteri No;Çatı_to_İştirak;İştirak Müşteri Ünvanı;İştirak Müşteri No;Sorumlu TAM;Sektör\n"
        "Delta Holding;66666666;;Delta Lojistik;77777777;TC1001;Lojistik\n"
        "Delta Holding;66666666;;Delta Gıda;88888888;TC1001;Gıda\n"
        ";;66666666;Delta Enerji;99999999;;\n"
    ).encode("cp1254")
    p = _yukle(client, hdr, csv, "cati.csv")
    assert p["uyum"]["bicim"] == "genis"
    o = _onizle(client, hdr, p["id"])
    assert o["ozet"]["yeni_olustur"] and o["ozet"]["yeni"] == 4 and o["ozet"]["hata"] == 0
    r = client.post(f"{TABAN}/uygula", json={"parti_id": p["id"], "plan_ozeti": o["plan_ozeti"], "onay": True}, headers=hdr)
    assert r.status_code == 200, r.text
    with Session(engine()) as db:
        cati = db.scalar(select(Customer).where(Customer.name == "Delta Holding"))
        altlar = {c.name: c for c in db.scalars(select(Customer).where(Customer.parent_id == cati.id))}
        assert set(altlar) == {"Delta Lojistik", "Delta Gıda", "Delta Enerji"}
        assert altlar["Delta Gıda"].sector == "Gıda" and altlar["Delta Enerji"].owner_id == cati.owner_id
        assert cati.customer_no == "66666666"


def test_hataya_dusen_yeni_catinin_istiraki_de_hata(ham):
    """2026-10-22 canli 500 (KeyError 'anadolu grup'): yeni cati TAM'siz hataya duserken istiraki 'yeni' kaliyor, uygulamada cati karti yoktu."""
    client, hdr = ham
    veri = _xlsx(
        {
            H.SAYFA: [
                ["Müşteri Ünvanı", "Çatı Müşteri Ünvanı", "Sorumlu TAM"],
                ["Anadolu Grup", None, None],
                ["Anadolu Otel", "Anadolu Grup", "TC1001"],
                ["Beta Enerji", None, "TC1001"],
            ]
        }
    )
    p = _yukle(client, hdr, veri)
    o = _onizle(client, hdr, p["id"], yeni=True)
    durum = {r["unvan"]: r for r in o["satirlar"]}
    assert durum["Anadolu Grup"]["durum"] == "hata" and durum["Anadolu Otel"]["durum"] == "hata"
    assert any("Anadolu Grup" in h for h in durum["Anadolu Otel"]["hatalar"])
    assert o["ozet"]["uygulanacak"] == 1
    r = client.post(f"{TABAN}/uygula", json={"parti_id": p["id"], "yeni_olustur": True, "plan_ozeti": o["plan_ozeti"], "onay": True}, headers=hdr)
    assert r.status_code == 200, r.text
    with Session(engine()) as db:
        assert db.scalar(select(Customer).where(Customer.name.in_(["Anadolu Grup", "Anadolu Otel"]))) is None
        assert db.get(AppUser, db.get(Customer, 2).owner_id).username == "TC1001"


def test_yalniz_admin(client):
    hdr = login_ok(client)
    assert client.post("/api/v1/session/logout", headers=hdr).status_code == 200
    assert client.get(f"{TABAN}/sablon.xlsx").status_code in (401, 403)


def test_kaynaklarda_ham_musteri_verisi(ham):
    client, _ = ham
    k = {x["anahtar"]: x for x in client.get("/api/v1/tampon/kaynaklar").json()["data"]}
    assert k["musteri_ham"]["ad"] == "Ham Müşteri Verisi" and "csv" not in k
    en = {x["anahtar"]: x for x in client.get("/api/v1/tampon/kaynaklar", headers={"X-Dil": "en"}).json()["data"]}
    assert en["musteri_ham"]["ad"] == "Raw Customer Data"
