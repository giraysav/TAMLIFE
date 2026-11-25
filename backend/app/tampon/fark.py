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
Siralama ve silme (2026-10-25 kullanici istegi: "fark'a gelenleri buyukten kucuge ya da alfabetik siralayamiyorum; hem atayabilmeli hem
silebilmeliyim"): liste sutuna gore siralanir (SIRALAMALAR); silinen numara AppSetting SILINEN_AYARI'na yazilir ve Fark'ta / Radar'da
listelenmez (TEMIP kayitlarina dokunulmaz: sonraki iceri almada yeniden gelirdi). Silme geri alinabilir.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import musteri_alani
from app.models import Customer
from app.ortak import UygulamaHatasi, iso, normal, simdi
from app.session import Principal
from app.tampon import temip_atama, temip_kayit

FARK_DURUMLARI = ("radar", "belirsiz", "kart_personelsiz")
SAYFA = 50
TOPLU_AZAMI = 200
SILINEN_AYARI = "fark.silinenler"
# sutun -> siralama anahtari (metinler harf / Turkce karakter farksiz)
SIRALAMALAR = {
    "toplam": lambda m: m["toplam"],
    "acik": lambda m: m["acik"],
    "musteri_no": lambda m: m["musteri_no"],
    "unvan": lambda m: normal(m["temip_unvan"] or ""),
    "durum": lambda m: m["durum"],
    "kart": lambda m: normal(m["panel_unvan"] or m["aday_kartlar"] or ""),
    "segment": lambda m: m.get("segment") or "~",
}


def silinen_numaralar(db: Session) -> set[str]:
    return {str(a.get("musteri_no")) for a in temip_atama._liste(db, SILINEN_AYARI)}


@musteri_alani.tum_alanlarda
def liste(db: Session, tur: str = "", q: str = "", sayfa: int = 1, sirala: str = "", yon: str = "") -> dict[str, Any]:
    """Eslesmeyen musteri numaralari (vars. acik kaydi cok olan once). tur: FARK_DURUMLARI'ndan biri ya da bos (hepsi).
    sirala: SIRALAMALAR anahtari, yon: artan | azalan (bos: sayilar azalan, metinler artan)."""
    r = temip_kayit.eslesme_raporu(db)
    radarda = temip_atama.radar_numaralari(db)  # Radar'a atanan kartsiz numara Radar'in (personele atanmis gibi)
    silinen = silinen_numaralar(db)
    fark = [
        m for m in r["musteriler"]
        if m["durum"] in FARK_DURUMLARI and m["musteri_no"] not in silinen and not (m["durum"] == "radar" and m["musteri_no"] in radarda)
    ]  # fmt: skip
    radar_sayisi = sum(1 for m in r["musteriler"] if m["durum"] == "radar" and m["musteri_no"] in radarda and m["musteri_no"] not in silinen)
    silinen_sayisi = sum(1 for m in r["musteriler"] if m["durum"] in FARK_DURUMLARI and m["musteri_no"] in silinen)
    ozet = {d: {"musteri": 0, "kayit": 0, "acik": 0} for d in FARK_DURUMLARI}
    for m in fark:
        o = ozet[m["durum"]]
        o["musteri"] += 1
        o["kayit"] += m["toplam"]
        o["acik"] += m["acik"]
    # Segment (2026-11-25 kullanici): kartli numarada kartin segmenti, kartsizda CMDB segmenti (envanter turu yazar)
    from app.musteri.envanter import segment_haritasi
    from app.tampon.eslestirme import anahtar as no_anahtari

    harita = segment_haritasi(db)
    kart_seg = {cid: s or "" for cid, s in db.execute(select(Customer.id, Customer.segment))}
    fark = [{**m, "segment": (kart_seg.get(m["kart_id"]) if m["kart_id"] else "") or harita.get(no_anahtari(m["musteri_no"]), "")} for m in fark]
    if tur in FARK_DURUMLARI:
        fark = [m for m in fark if m["durum"] == tur]
    if aranan := normal(q.strip()):  # harf / Turkce karakter farksiz (kart aramasiyla ayni)
        fark = [
            m for m in fark if aranan in m["musteri_no"] or aranan in normal(f"{m['temip_unvan']} {m['panel_unvan']} {m['aday_kartlar']} {m['segment']}")
        ]
    if anahtar := SIRALAMALAR.get(sirala):
        azalan = yon == "azalan" if yon in ("artan", "azalan") else sirala in ("toplam", "acik")
        fark = sorted(fark, key=lambda m: (anahtar(m), m["musteri_no"]), reverse=azalan)
    toplam = len(fark)
    sayfa = max(1, min(sayfa, (toplam + SAYFA - 1) // SAYFA or 1))
    bas = (sayfa - 1) * SAYFA
    return {
        "ozet": ozet,
        "radarda": radar_sayisi,
        "silinen": silinen_sayisi,
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


@musteri_alani.tum_alanlarda
def sil(db: Session, user: Principal, musteri_nolar: list[str]) -> dict[str, Any]:
    """Secilen numaralari Fark'tan siler (gizler): yalniz su an fark listesinde olan numara; Radar'daysa Radar'dan da cikar."""
    nolar = list(dict.fromkeys(n.strip() for n in musteri_nolar if n and n.strip()))
    if not nolar:
        raise temip_atama.AtamaHata(400, "Müşteri No seçin.")
    farkta = {m["musteri_no"]: m for m in temip_kayit.eslesme_raporu(db)["musteriler"] if m["durum"] in FARK_DURUMLARI}
    liste = temip_atama._liste(db, SILINEN_AYARI)
    var = {a.get("musteri_no") for a in liste}
    yeni = [
        {"musteri_no": no, "temip_unvan": farkta[no]["temip_unvan"], "durum": farkta[no]["durum"], "toplam": farkta[no]["toplam"],
         "kim": user.username, "zaman": iso(simdi())}
        for no in nolar if no in farkta and no not in var
    ]  # fmt: skip
    atlanan = [{"musteri_no": no, "neden": "Zaten silinmiş." if no in var else "Fark listesinde yok."} for no in nolar if no not in farkta or no in var]
    if yeni:
        temip_atama._liste_yaz(db, [*yeni, *liste], user.username, SILINEN_AYARI)
        silinenler = {g["musteri_no"] for g in yeni}
        radar = temip_atama.radar_listesi(db)
        if any(a.get("musteri_no") in silinenler for a in radar):
            temip_atama._liste_yaz(db, [a for a in radar if a.get("musteri_no") not in silinenler], user.username, temip_atama.RADAR_AYARI)
        temip_atama.surum_tazele(db)
        db.commit()
    return {"silinen": len(yeni), "atlanan": atlanan}


def silineni_geri_al(db: Session, user: Principal, musteri_nolar: list[str]) -> dict[str, Any]:
    nolar = {n.strip() for n in musteri_nolar if n and n.strip()}
    liste = temip_atama._liste(db, SILINEN_AYARI)
    kalan = [a for a in liste if a.get("musteri_no") not in nolar]
    if len(kalan) == len(liste):
        raise temip_atama.AtamaHata(404, "Bu numara silinenlerde yok.")
    temip_atama._liste_yaz(db, kalan, user.username, SILINEN_AYARI)
    temip_atama.surum_tazele(db)
    db.commit()
    return {"geri_alinan": len(liste) - len(kalan)}


def silinenler(db: Session) -> list[dict[str, Any]]:
    return temip_atama._liste(db, SILINEN_AYARI)
