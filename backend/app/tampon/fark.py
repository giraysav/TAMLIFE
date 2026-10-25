"""Fark alani (Veri Girisi > Fark, 2026-10-24 kullanici istegi: "canli DB'den alinan verilerle panelde musteri kartinda eslesmeyenler
icin bir fark alani olustur; bunlari manuel olarak personele atayabileyim").

Canli DB (ReportDB TEMIP) kayitlarinin kartla ya da TAM ile eslesmeyen musteri numaralari tek listede:
- radar: numara hicbir kartta yok (kayitlar TAM Radar'da),
- belirsiz: numara birden cok kartta yazili (kayit hicbir karta baglanmaz),
- kart_personelsiz: karta baglanir ama kartin ve catisinin TAM'i yok.
Tekil atama temip_atama (/temip/ata) ile yapilir; bu modul toplu atamayi (secilen numaralar -> personel adina yeni kartlar, TEK yeniden
baglama) ve personelsiz karta TAM secmeyi ekler. Yalniz admin (Veri Girisi).
Musteri Radar personel gibi secilebilir (2026-10-25): secilen kartsiz numaralar kart acilmadan Radar'a gider ve Fark'tan duser; Radar
sayfasinda personele atanir (temip_atama.radara_gonder).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app import musteri_alani
from app.models import Customer
from app.ortak import UygulamaHatasi, normal
from app.session import Principal
from app.tampon import temip_atama, temip_kayit

FARK_DURUMLARI = ("radar", "belirsiz", "kart_personelsiz")
SAYFA = 50
TOPLU_AZAMI = 200


@musteri_alani.tum_alanlarda
def liste(db: Session, tur: str = "", q: str = "", sayfa: int = 1) -> dict[str, Any]:
    """Eslesmeyen musteri numaralari (acik kaydi cok olan once). tur: FARK_DURUMLARI'ndan biri ya da bos (hepsi)."""
    r = temip_kayit.eslesme_raporu(db)
    radarda = temip_atama.radar_numaralari(db)  # Radar'a atanan kartsiz numara Radar'in (personele atanmis gibi)
    fark = [m for m in r["musteriler"] if m["durum"] in FARK_DURUMLARI and not (m["durum"] == "radar" and m["musteri_no"] in radarda)]
    radar_sayisi = sum(1 for m in r["musteriler"] if m["durum"] == "radar" and m["musteri_no"] in radarda)
    ozet = {d: {"musteri": 0, "kayit": 0, "acik": 0} for d in FARK_DURUMLARI}
    for m in fark:
        o = ozet[m["durum"]]
        o["musteri"] += 1
        o["kayit"] += m["toplam"]
        o["acik"] += m["acik"]
    if tur in FARK_DURUMLARI:
        fark = [m for m in fark if m["durum"] == tur]
    if aranan := normal(q.strip()):  # harf / Turkce karakter farksiz (kart aramasiyla ayni)
        fark = [
            m for m in fark if aranan in m["musteri_no"] or aranan in normal(f"{m['temip_unvan']} {m['panel_unvan']} {m['aday_kartlar']}")
        ]
    toplam = len(fark)
    sayfa = max(1, min(sayfa, (toplam + SAYFA - 1) // SAYFA or 1))
    bas = (sayfa - 1) * SAYFA
    return {
        "ozet": ozet,
        "radarda": radar_sayisi,
        "toplam_kayit": sum(m["toplam"] for m in r["musteriler"]),
        "toplam": toplam,
        "sayfa": sayfa,
        "adet": SAYFA,
        "satirlar": [{**m, "kaynak": "TEMIP"} for m in fark[bas : bas + SAYFA]],
    }


@musteri_alani.tum_alanlarda
def toplu_ata(db: Session, user: Principal, musteri_nolar: list[str], tam_id: int) -> dict[str, Any]:
    """Secilen kartsiz numaralar: her biri icin personel adina TEMIP unvaniyla YENI kart (temip_atama.personele_ata kurallari).
    Uymayan numara atlanir (neden listelenir); kayitlar sonda TEK seferde baglanir."""
    nolar = list(dict.fromkeys(n.strip() for n in musteri_nolar if n and n.strip()))
    if not nolar:
        raise temip_atama.AtamaHata(400, "Müşteri No seçin.")
    if len(nolar) > TOPLU_AZAMI:
        raise temip_atama.AtamaHata(400, f"Tek seferde en çok {TOPLU_AZAMI} numara atanabilir.")
    atanan: list[dict[str, Any]] = []
    atlanan: list[dict[str, str]] = []
    for no in nolar:
        try:  # yeni_kart_ac hatayi yazmadan once dogurur: atlanan numara yarim kart birakmaz
            atanan.append(temip_atama.yeni_kart_ac(db, user, no, tam_id))
        except UygulamaHatasi as hata:
            atlanan.append({"musteri_no": no, "neden": hata.mesaj})
    sonuc = {"yeniden_baglanan": 0, "etkilenen_kart": 0}
    if atanan:
        temip_atama.listeye_ekle(db, atanan, user.username)
        sonuc = temip_atama.bagla(db)
    db.commit()
    return {"atanan": len(atanan), "atlanan": atlanan, "kartlar": [a["kart"] for a in atanan], **sonuc}


@musteri_alani.tum_alanlarda
def kart_sahibi(db: Session, user: Principal, kart_id: int, tam_id: int) -> dict[str, Any]:
    """Personelsiz karta TAM sec (Musteri Yonetimi'ndeki sorumlu devriyle ayni kural); eslesme ekranlari tazelenir."""
    from app.musteri import servis as ms

    kart = db.get(Customer, kart_id)
    if kart is None:
        raise temip_atama.AtamaHata(404, "Kart bulunamadı.")
    sonuc = ms.tam_degistir(db, user, kart_id, tam_id)
    temip_atama.surum_tazele(db)
    db.commit()
    return {"kart_id": kart_id, "kart": kart.name, "personel": sonuc["full_name"]}
