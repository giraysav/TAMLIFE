# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""TAM Utilizasyon > Musteri Listesi: tum musterileri (cati ve istirak) listeler, toplu ekler, secilenleri ya da hepsini siler.

Yalniz admin (router duzeyinde require_admin). Is kurali musteri/servis.py'dedir: ekleme `musteri_ekle`, silme `agaci_sil`
(bagli rapor, taslak, gonderim, skor, dagitim gunlugu kayitlariyla; geri alinamaz).
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppUser, Customer
from app.musteri import servis as ms
from app.ortak import UygulamaHatasi
from app.session import Principal

EN_FAZLA_SILINECEK = 5000
EN_FAZLA_EKLENECEK = 500
HEPSINI_SIL_ONAYI = "SIL"


class ListeHata(UygulamaHatasi):
    """kod = HTTP durumu."""


def liste(db: Session) -> dict:
    """Tum musteriler, agac sirasiyla: cati (ada gore), altinda istirakleri. Her satirda bagli oldugu cati ve sorumlu TAM adi."""
    musteriler = list(db.scalars(select(Customer).order_by(Customer.name, Customer.id)))
    adlar = {m.id: m.name for m in musteriler}
    ust = {m.id: m.parent_id for m in musteriler}
    sahipler = {u.id: u.display_name or u.username for u in db.scalars(select(AppUser))}
    istirak_sayisi = Counter(m.parent_id for m in musteriler if m.parent_id)

    def kok(k: int) -> int:
        for _ in range(len(ust)):  # sinirli: bozuk veride (dongu) sonsuza gitme
            ata = ust.get(k)
            if ata is None or ata not in ust:
                break
            k = ata
        return k

    sirali = sorted(musteriler, key=lambda m: ((adlar[kok(m.id)] or "").lower(), kok(m.id), m.parent_id is not None, (m.name or "").lower(), m.id))
    return {
        "total": len(sirali),
        "items": [
            {
                "id": m.id,
                "name": m.name,
                "segment": m.segment or "",
                "parent_id": m.parent_id,
                "parent_name": adlar.get(m.parent_id) if m.parent_id else None,
                "owner_id": m.owner_id,
                "owner": sahipler.get(m.owner_id) if m.owner_id else None,
                "affiliates": istirak_sayisi.get(m.id, 0),
                "score": round(m.score, 1) if m.score is not None else None,
            }
            for m in sirali
        ],
    }


def _onay_tamam(onay: object) -> bool:
    return isinstance(onay, str) and onay.strip().upper().replace("İ", "I") == HEPSINI_SIL_ONAYI


def sil(db: Session, kimlikler: list[int], hepsi: bool, onay: object) -> dict:
    """Secilenleri (ve istiraklerini) ya da `hepsi` ile TUM musterileri siler. Hepsi icin onay metni 'SIL' gerekir."""
    if hepsi:
        if not _onay_tamam(onay):
            raise ListeHata(400, "Tüm müşterileri silmek için onay kutusuna SİL yazın.")
        hedef = list(db.scalars(select(Customer.id)))
    else:
        hedef = list(dict.fromkeys(kimlikler))
        if not hedef:
            raise ListeHata(400, "Silinecek müşteri seçilmedi.")
        if len(hedef) > EN_FAZLA_SILINECEK:
            raise ListeHata(400, f"Tek seferde en fazla {EN_FAZLA_SILINECEK} müşteri silinebilir.")
    silinen = ms.agaci_sil(db, hedef)
    return {"silinen": silinen, "istenen": len(hedef), "hepsi": hepsi}


def toplu_ekle(db: Session, admin: Principal, satirlar: list[dict], ust_id: int | None, tam_id: int | None) -> dict:
    """Her satir {name, segment?}. Ayni unvan varsa ya da satir gecersizse o satir atlanir (neden dondurulur), digerleri eklenir.
    `ust_id` verilirse hepsi o catinin istiraki olur; verilmezse cati. `tam_id` bossa sorumlu: istirakte catinin, catida ekleyen."""
    if not satirlar:
        raise ListeHata(400, "Eklenecek müşteri yok.")
    if len(satirlar) > EN_FAZLA_EKLENECEK:
        raise ListeHata(400, f"Tek seferde en fazla {EN_FAZLA_EKLENECEK} müşteri eklenebilir.")
    eklenen: list[int] = []
    atlanan: list[dict] = []
    for satir in satirlar:
        govde = {"name": satir.get("name"), "segment": satir.get("segment"), "parent_id": ust_id, "owner_id": tam_id}
        try:
            eklenen.append(ms.musteri_ekle(db, admin, govde)["id"])
        except ms.MusteriHata as hata:
            if hata.kod in {401, 403}:
                raise
            if ust_id and hata.kod == 404 and "Üst müşteri" in hata.mesaj:
                raise  # secilen cati yoksa hicbir satir eklenemez; satir satir hata yigmayalim
            if tam_id and hata.kod == 404 and "Personel" in hata.mesaj:
                raise
            atlanan.append({"ad": str(satir.get("name") or ""), "sebep": hata.mesaj})
    return {"eklenen": len(eklenen), "idler": eklenen, "atlanan": atlanan}
