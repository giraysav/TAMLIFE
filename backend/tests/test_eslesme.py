"""Veri Girisi > Musteri Eslesmesi (2026-10-24): kaynak bazinda karta / TAM'a eslesme, kartsiz ilk numaralar, onbellek, yetki."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db import engine
from app.gelir_uretim.models import RevenueBenefit
from app.models import OnedeskRecord, UrunTutarOzet
from tests.conftest import login_ok
from tests.test_temip_kayit import kart, kisi, sahip


def _kayit(db, no: str, cid: int | None, kaynak: str = "temip") -> None:
    db.add(OnedeskRecord(kind="alarm", external_key=f"k-{no}-{cid}-{db.new.__len__()}", customer_id=cid, status="open", source=kaynak, customer_no=no,
                         customer_label=f"Unvan {no}"))  # fmt: skip


def test_kaynak_bazinda_kart_ve_tam_eslesmesi(client):
    tam = kisi("tam")
    cati, istirak, sahipsiz = kart("CATI A.S.", "10000001"), kart("ISTIRAK A.S.", "10000002"), kart("SAHIPSIZ A.S.", "10000003")
    sahip(cati, tam)
    sahip(istirak, None, cati=cati)  # istirak TAM'i catisindan devralir
    an = datetime.now(UTC)
    with Session(engine()) as db:
        for no, cid in (("10000001", cati), ("10000002", istirak), ("10000003", sahipsiz), ("70000007", None), ("70000007", None), ("80000008", None)):
            _kayit(db, no, cid)
        _kayit(db, "10000001", cati, kaynak="onedesk")
        db.add(UrunTutarOzet(customer_id=cati, summary={"eslesmeyen_gruplar": ["X", "Y"]}, uploaded_at=an))
        for metin in ("CATI A.S., Bilinmeyen Ltd", "sahipsiz  a.s.", "Hic Kimse", ""):
            db.add(RevenueBenefit(title="is", customers=metin, created_at=an, updated_at=an))
        db.commit()

    login_ok(client)
    d = client.get("/api/v1/tampon/eslesme").json()["data"]
    k = {x["anahtar"]: x for x in d["kaynaklar"]}
    assert {a: k["onedesk:temip"][a] for a in ("toplam", "karta_eslesen", "tam_atanmis", "kartsiz")} == {"toplam": 6, "karta_eslesen": 3, "tam_atanmis": 2, "kartsiz": 3}
    assert k["onedesk:temip"]["oran"] == 33.3 and k["onedesk:temip"]["ad"] == "TEMIP alarm kayıtları"
    assert k["onedesk:onedesk"]["toplam"] == 1 and k["onedesk:onedesk"]["tam_atanmis"] == 1
    assert (k["urun_tutar"]["toplam"], k["urun_tutar"]["karta_eslesen"], k["urun_tutar"]["kartsiz"]) == (3, 1, 2) and "2 grup" in k["urun_tutar"]["not"]
    # Gelir Faydasi: ad eslesmesi (buyuk/kucuk harf ve bosluk yok sayilir); sahipsiz kart eslesir ama TAM'li sayilmaz
    assert (k["gelir_uretim"]["toplam"], k["gelir_uretim"]["karta_eslesen"], k["gelir_uretim"]["tam_atanmis"]) == (4, 2, 1)
    assert d["kartlar"] == {"toplam": 3, "tam_atanmis": 2, "tam_siz": 1}
    assert d["kartsiz_ilk"][0] == {"musteri_no": "70000007", "ad": "Unvan 70000007", "adet": 2} and len(d["kartsiz_ilk"]) == 2

    with Session(engine()) as db:  # yeni kayit onbellegi gecersiz kilar
        _kayit(db, "90000009", None)
        db.commit()
    yeni = {x["anahtar"]: x for x in client.get("/api/v1/tampon/eslesme").json()["data"]["kaynaklar"]}
    assert yeni["onedesk:temip"]["kartsiz"] == 4


def test_eslesme_yalniz_admin(client):
    assert client.get("/api/v1/tampon/eslesme").status_code == 401
