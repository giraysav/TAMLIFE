# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Analiz: hangi sutun musteri kartlariyla (Musteri No / NCST / unvan) kac % eslesiyor. Veriyi DEGISTIRMEZ, yalniz rapor uretir.

Maliyet: tum sutunlar x 3 alan x ORNEK_SATIR; 300 bin satirlik partide bile yalniz ilk ORNEK_SATIR satir taranir.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, IngestBatch
from app.tampon import depo
from app.tampon.eslestirme import alan_anahtarlari

ORNEK_SATIR = 20_000
FARKLI_AZAMI = 20_000
ALANLAR = ("customer_no", "ncst", "name")
ONERI_ADEDI = 6


def musteri_dizini(db: Session) -> dict[str, dict[str, list[int]]]:
    """{alan: {anahtar: [musteri_id]}} - bir anahtar birden cok karta dusuyorsa liste uzundur (belirsiz)."""
    dizin: dict[str, dict[str, list[int]]] = {alan: defaultdict(list) for alan in ALANLAR}
    for kimlik, no, ncst, ad in db.execute(select(Customer.id, Customer.customer_no, Customer.ncst, Customer.name)):
        for alan, deger in (("customer_no", no), ("ncst", ncst), ("name", ad)):
            for k in alan_anahtarlari(alan, deger):
                if kimlik not in dizin[alan][k]:
                    dizin[alan][k].append(kimlik)
    return {alan: dict(d) for alan, d in dizin.items()}


def analiz_et(db: Session, parti: IngestBatch) -> dict[str, Any]:
    """Anahtar onerileri; sonuc partinin profile['analiz'] alanina yazilir (commit cagiranda)."""
    dizin = musteri_dizini(db)
    musteri_sayisi = len({i for d in dizin["name"].values() for i in d})
    uyarilar: list[str] = []
    if musteri_sayisi == 0:
        uyarilar.append("Panelde müşteri kartı yok: eşleşme hesaplanamadı.")
    elif not dizin["customer_no"]:
        uyarilar.append("Hiçbir müşteri kartında Müşteri No yok: numara eşleşmesi mümkün değil.")

    basliklar = list(parti.columns)
    farkli: list[dict[str, set[str]]] = [{alan: set() for alan in ALANLAR} for _ in basliklar]
    incelenen = 0
    for satir in depo.satirlari_oku(db, parti.id):
        incelenen += 1
        for i, hucre in enumerate(satir[: len(basliklar)]):
            if hucre in (None, ""):
                continue
            for alan in ALANLAR:
                kume = farkli[i][alan]
                if len(kume) < FARKLI_AZAMI:
                    kume.update(alan_anahtarlari(alan, hucre))
        if incelenen >= ORNEK_SATIR:
            break

    oneriler = []
    for i, ad in enumerate(basliklar):
        for alan in ALANLAR:
            anahtarlar = farkli[i][alan]
            if not anahtarlar:
                continue
            eslesen = sum(1 for k in anahtarlar if k in dizin[alan])
            if eslesen:
                oneriler.append(
                    {
                        "kolon": ad,
                        "alan": alan,
                        "farkli": len(anahtarlar),
                        "eslesen": eslesen,
                        "oran": round(eslesen * 100 / len(anahtarlar), 1),
                    }
                )
    # Numara/NCST eslesmesi unvandan once gelir (unvan degisebilir; uretimde de karar: eslesme numarayla); sonra eslesen adet, oran.
    oneriler.sort(key=lambda o: (o["alan"] == "name", -o["eslesen"], -o["oran"]))  # type: ignore[operator]
    if musteri_sayisi and not oneriler:
        uyarilar.append("Hiçbir sütun müşteri kartlarıyla eşleşmedi: anahtar sütununu ve kartlardaki Müşteri No'yu kontrol edin.")
    sonuc = {
        "ornek_satir": incelenen,
        "toplam_satir": parti.row_count,
        "musteri_sayisi": musteri_sayisi,
        "oneriler": oneriler[:ONERI_ADEDI],
        "uyarilar": uyarilar,
    }
    parti.profile = {**(parti.profile or {}), "analiz": sonuc}
    return sonuc
