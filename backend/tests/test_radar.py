"""Musteri Radar: panelde karti olmayan (numara ya da unvan cekirdegi eslesmeyen) musteriler, alarm toplamina gore ilk 10."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db import engine
from app.models import Customer, RoleView
from app.tampon import reportdb
from tests.conftest import login_ok
from tests.test_reportdb import BASLIK, satir


def _parti(*satirlar) -> None:
    with Session(engine()) as db:
        reportdb.tampona_yaz(db, BASLIK, list(satirlar), 1.0)


def test_veri_yoksa_bos_ve_aciklamali(client):
    login_ok(client)
    veri = client.get("/api/v1/radar").json()["data"]
    assert veri == {"var": False, "taze": False, "veri_zamani": None, "satirlar": []}


def test_panelde_olanlar_numara_ya_da_unvanla_dislanir_siralama_toplam(client):
    login_ok(client)
    with Session(engine()) as db:
        db.add_all(
            [
                Customer(id=1, external_key="k1", name="Kartli Numara A.S.", customer_no="10000001; 10000009"),
                Customer(id=2, external_key="k2", name="Doğuş Teknoloji Hiz. ve Tic. A.Ş."),
            ]
        )
        db.commit()
    _parti(
        satir("10000001", "KARTLI NUMARA", 50, 50),  # numarayla kartta
        satir("10000009", "IKINCI NUMARA", 40, 0),  # kartin ikinci numarasi
        satir("10000002", "DOGUS TEKNOLOJI HIZMETLERI AS", 30, 30),  # unvan cekirdegi kartla ayni
        satir("10000003", "ALFA LOJISTIK", 5, 20),
        satir("10000004", "BETA ENERJI", 30, 0),
        satir("10000005", "SIFIR KAYIT", 0, 0),
        *[satir(f"2000000{i}", f"DIGER {i}", 1, i) for i in range(10)],
    )
    veri = client.get("/api/v1/radar").json()["data"]
    assert veri["var"] is True and veri["taze"] is True and veri["veri_zamani"] == "2026-10-06 12:30:00"
    satirlar = veri["satirlar"]
    assert len(satirlar) == 10 and [s["sira"] for s in satirlar] == list(range(1, 11))
    assert satirlar[0] == {"sira": 1, "musteri_no": "10000004", "unvan": "BETA ENERJI", "aktif": 30, "kapanan": 0, "toplam": 30}
    assert satirlar[1]["unvan"] == "ALFA LOJISTIK" and satirlar[1]["toplam"] == 25
    adlar = {s["unvan"] for s in satirlar}
    assert adlar.isdisjoint({"KARTLI NUMARA", "IKINCI NUMARA", "DOGUS TEKNOLOJI HIZMETLERI AS", "SIFIR KAYIT"})


def test_rol_gorunumunde_yoksa_403(client, monkeypatch):
    with Session(engine()) as db:
        db.add(RoleView(role="TeamMember", modules=["musteri"], landing="ozet", permissions=[]))
        db.commit()
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    login_ok(client)
    assert client.get("/api/v1/radar").status_code == 403
