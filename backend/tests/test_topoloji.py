"""TopoMaker: kolon eslemesi, altyapi kurallari, grafik/SPoF, il dagilimi, dosya sinirlari ve erisim."""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from app.topoloji import servis

BASLIK = "Lokasyon_Adi;Il;Devre_Altyapisi;Uplink SW IP;WAN IP;BB_Router_Hostname"
SATIRLAR = [
    "Merkez;istanbul;SOL Fiber;10.0.0.1;192.168.1.1;ist-bb-01.tcell.net",
    "Merkez;istanbul;TT Metro;10.0.0.2;192.168.1.1;ist-bb-01.tcell.net",  # ayni BB, farkli altyapi -> SPoF
    "Merkez;istanbul;4.5G LTE;;192.168.1.9;",
    "Şube;İZMİR;ADSL;;172.16.0.1;izm-bb-02",
    "Şube;İZMİR;;10.1.0.1;172.16.0.2;izm-bb-02",
    ";Ankara;SOL;10.9.9.9;1.1.1.1;x",  # lokasyonsuz satir yok sayilir
]


def _csv(satirlar=SATIRLAR, baslik=BASLIK, kod="utf-8") -> bytes:
    return "\n".join([baslik, *satirlar]).encode(kod)


def _giris(client, monkeypatch, kullanici="ayse", rol="TeamMember") -> dict[str, str]:
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", kullanici)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    r = client.post("/api/v1/session/login", json={"username": kullanici, "password": "test-parola-1"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""}


@pytest.mark.parametrize(
    ("deger", "beklenen"),
    [
        ("VDSL", ("xDSL", "backup")),
        ("Radyo Link", ("RL", "backup")),
        ("SOL-ME", ("SOL Fiber", "primary")),
        ("4.5G", ("4.5G", "backup")),
        ("Türk Telekom", ("TT Fiber", "primary")),
        ("Superonline", ("SOL Fiber", "primary")),
        ("", ("Fiber/RL", "primary")),
    ],
)
def test_altyapi_kurallari(deger, beklenen):
    assert servis.altyapi_bul(deger) == beklenen


def test_kolon_eslemesi_tam_once_belirsizlik_hata():
    assert servis.kolon_bul(["Site Adresi", "Lokasyon"], "loc") == "Lokasyon"  # tam eslesme icermeden once
    assert servis.kolon_bul(["Ana Lokasyon Kodu"], "loc") == "Ana Lokasyon Kodu"
    assert servis.kolon_bul(["Fiyat"], "loc") == ""
    with pytest.raises(servis.TopolojiHata):
        servis.kolon_bul(["Ana Site", "Yedek Site"], "loc")


def test_grafik_spof_ve_il_dagilimi():
    s = servis.analiz(_csv())
    assert s["satir"] == 6 and s["lokasyon"] == 2
    dugum = {d["id"]: d for d in s["dugumler"]}
    assert set(dugum) == {
        "ISP_CLOUD",
        "R_Merkez_192.168.1.1", "SW_Merkez_10.0.0.1", "SW_Merkez_10.0.0.2", "R_Merkez_192.168.1.9",
        "R_Şube_172.16.0.1", "R_Şube_172.16.0.2", "SW_Şube_10.1.0.1",
    }
    kenar = {(k["kaynak"], k["hedef"]): k for k in s["kenarlar"]}
    k = kenar[("ISP_CLOUD", "SW_Merkez_10.0.0.1")]
    assert (k["altyapi"], k["etiket"], k["yedek"], k["renk"]) == ("SOL Fiber", "ist-bb-01", False, "#1A6FA6")
    assert kenar[("ISP_CLOUD", "SW_Merkez_10.0.0.2")]["renk"] == "#B03A2E"
    k = kenar[("ISP_CLOUD", "R_Merkez_192.168.1.9")]
    assert (k["altyapi"], k["etiket"], k["yedek"]) == ("4.5G", "4.5G", True)  # BB yoksa etiket altyapi
    assert kenar[("SW_Merkez_10.0.0.1", "R_Merkez_192.168.1.1")]["altyapi"] == "LAN"
    # Sube: ADSL + varsayilan Fiber/RL ayni BB'de -> o da SPoF
    assert s["spof"] is True and s["spof_noktalari"] == [
        {"lokasyon": "Merkez", "bb": "ist-bb-01", "altyapilar": ["SOL Fiber", "TT Fiber"]},
        {"lokasyon": "Şube", "bb": "izm-bb-02", "altyapilar": ["Fiber/RL", "xDSL"]},
    ]
    assert [(c["il"], c["adet"]) for c in s["sehirler"]] == [("İSTANBUL", 4), ("İZMİR", 3)]
    assert s["kolonlar"]["loc"] == "Lokasyon_Adi" and "ci" not in s["kolonlar"]


def test_spof_yok_ve_bilinmeyen_il():
    s = servis.analiz(_csv(["A;Bilecik;SOL;1.1.1.1;2.2.2.2;bb1", "A;Bilecik;4.5G;;3.3.3.3;bb2"]))
    assert s["spof"] is False and s["sehirler"] == [] and s["konumsuz_iller"] == ["Bilecik"]


def test_xlsx_ve_ansi_csv():
    wb = Workbook()
    ws = wb.active
    ws.append([])
    ws.append(BASLIK.split(";"))
    for satir in SATIRLAR[:3]:
        ws.append(satir.split(";"))
    tampon = io.BytesIO()
    wb.save(tampon)
    assert servis.analiz(tampon.getvalue())["spof"] is True
    assert servis.analiz(_csv(SATIRLAR[3:5], kod="cp1254"))["lokasyon"] == 1


def test_hatalar():
    with pytest.raises(servis.TopolojiHata, match="Lokasyon kolonu"):
        servis.analiz(b"Fiyat;Adet\n1;2\n")
    with pytest.raises(servis.TopolojiHata, match="seçilmedi"):
        servis.analiz(b"")
    with pytest.raises(servis.TopolojiHata, match="okunamadı"):
        servis.analiz(b"PK\x03\x04bozuk")


def test_uc_erisim_ve_sinirlar(client, monkeypatch):
    assert client.put("/api/v1/topoloji/analiz", content=_csv()).status_code in (401, 403)  # oturum/CSRF yok
    hdr = _giris(client, monkeypatch)
    r = client.put("/api/v1/topoloji/analiz?dosya=envanter.csv", content=_csv(), headers={**hdr, "Content-Type": "text/csv"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["spof"] is True
    r = client.put("/api/v1/topoloji/analiz?dosya=x.pdf", content=_csv(), headers=hdr)
    assert r.status_code == 400 and r.json()["detail"] == "CSV veya XLSX dosyası seçin."
    r = client.put("/api/v1/topoloji/analiz", content=b"a" * (servis.AZAMI_BAYT + 1), headers=hdr)
    assert r.status_code == 413
    r = client.put("/api/v1/topoloji/analiz", content=b"Fiyat\n1\n", headers=hdr)
    assert r.status_code == 400 and "Lokasyon" in r.json()["detail"]
