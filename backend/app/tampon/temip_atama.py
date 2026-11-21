"""TEMIP Musteri No'sunu karta ELLE atama (2026-10-18 kullanici istegi: "bazi musterilerde CRM kaynakli unvan hatasi var; eslesmeyen
musterileri manuel atamak icin fonksiyon ekle").

Kural degismez: eslesme yalniz numarayla. Atama numarayi kartin Musteri No alanina EKLER (varsa dokunmaz); kayitlar hemen o karta
baglanir, kart sayaclari yenilenir (Oracle'a gidilmez). Numara kartta durdugu icin sonraki iceri alma turlari ve Ham Musteri Verisi
aktarimlari (numaralar birikir, silinmez) atamayi korur. Elle atamalar ayarda listelenir; geri alma yalniz bu listedeki numarayi
karttan siler. Yalniz admin (Veri Girisi).
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import musteri_alani
from app.models import AppSetting, AppUser, Customer, OnedeskRecord
from app.onedesk.sayac import sayaclari_yenile
from app.ortak import UygulamaHatasi, iso, simdi
from app.session import Principal
from app.tampon import temip_kayit
from app.tampon.eslestirme import anahtar, musteri_anahtarlari

ATAMA_AYARI = "temip.manuel_atamalar"
# Fark > "Musteri Radar" (2026-10-25 kullanici istegi: "Fark'ta Musteri Radar'i bir personel gibi calistir; Radar'a gelenleri manuel
# atayayim"): Radar yalniz buraya gonderilen kartsiz numaralari gosterir. Numara karta baglaninca Radar'dan kendiliginden duser
# (kayitlar kartli); elle atamasi geri alininca yeniden Radar'da gorunur.
RADAR_AYARI = "radar.atananlar"
_NO = re.compile(r"^\d{8}$")
NO_ALANI_UZUNLUK = 200  # customer.customer_no


class AtamaHata(UygulamaHatasi):
    pass


def _liste(db: Session, ayar: str = ATAMA_AYARI) -> list[dict[str, Any]]:
    a = db.get(AppSetting, ayar)
    return list(a.value) if a is not None and isinstance(a.value, list) else []


def _liste_yaz(db: Session, liste: list[dict[str, Any]], kullanici: str, ayar: str = ATAMA_AYARI) -> None:
    a = db.get(AppSetting, ayar)
    if a is None:
        db.add(AppSetting(key=ayar, value=liste, updated_by=kullanici, updated_at=simdi()))
    else:
        a.value, a.updated_by, a.updated_at = liste, kullanici, simdi()


def surum_tazele(db: Session) -> None:
    """Eslesme / Radar onbellekleri TEMIP surumune bakar: kart baglantisi degisti."""
    a = db.get(AppSetting, temip_kayit.SURUM_AYARI)
    deger = dict(a.value) if a is not None and isinstance(a.value, dict) else {}
    deger["an"] = simdi().isoformat()
    if a is None:
        db.add(AppSetting(key=temip_kayit.SURUM_AYARI, value=deger, updated_by="temip_atama", updated_at=simdi()))
    else:
        a.value, a.updated_at = deger, simdi()


def bagla(db: Session) -> dict[str, int]:
    etkilenen: set[int] = set()
    degisen = temip_kayit.yeniden_bagla(db, temip_kayit.harita(db), etkilenen)
    sayaclari_yenile(db, etkilenen)
    surum_tazele(db)
    return {"yeniden_baglanan": degisen, "etkilenen_kart": len(etkilenen)}


def _dogrula(db: Session, musteri_no: str) -> tuple[str, int, str]:
    """(numara, kayit sayisi, TEMIP unvani). Numara 8 haneli, TEMIP kaydi olan ve HICBIR kartta yazili olmayan numara olmali."""
    no = (musteri_no or "").strip()
    if not _NO.match(no):
        raise AtamaHata(400, "Müşteri No 8 haneli olmalı.")
    kosul = (OnedeskRecord.source == temip_kayit.KAYNAK_ADI, OnedeskRecord.customer_no == no)
    kayit = db.scalar(select(func.count()).select_from(OnedeskRecord).where(*kosul))
    if not kayit:
        raise AtamaHata(404, "Bu Müşteri No için TEMIP kaydı yok.")
    return no, kayit, db.scalar(select(func.max(OnedeskRecord.customer_label)).where(*kosul)) or ""


def _numara_sahipleri(db: Session, no: str) -> list[Customer]:
    k = anahtar(no)
    return [c for c in db.scalars(select(Customer).where(Customer.customer_no.is_not(None))) if k in musteri_anahtarlari(c.customer_no)]


def _girdi(db: Session, no: str, unvan: str, kayit: int, kart: Customer, kullanici: str, yeni_kart: bool) -> dict[str, Any]:
    tam = db.get(AppUser, kart.owner_id) if kart.owner_id else None
    return {"musteri_no": no, "temip_unvan": unvan, "kart_id": kart.id, "kart": kart.name, "personel": (tam.display_name or tam.username) if tam else "",
            "yeni_kart": yeni_kart, "kayit": kayit, "kim": kullanici, "zaman": iso(simdi())}  # fmt: skip


def listeye_ekle(db: Session, girdiler: list[dict[str, Any]], kullanici: str) -> None:
    """Elle atama listesine (en yeni ustte, en cok 500) ekler; ayni numaranin eski girdisi duser."""
    nolar = {g["musteri_no"] for g in girdiler}
    _liste_yaz(db, ([*girdiler, *(a for a in _liste(db) if a.get("musteri_no") not in nolar)])[:500], kullanici)


def _kaydet(db: Session, girdi: dict[str, Any], kart: Customer, kullanici: str) -> dict[str, Any]:
    listeye_ekle(db, [girdi], kullanici)
    sonuc = bagla(db)
    db.commit()
    return {
        "musteri_no": girdi["musteri_no"],
        "kart_id": kart.id,
        "kart": kart.name,
        "kart_musteri_no": kart.customer_no,
        "yeni_kart": girdi["yeni_kart"],
        "kayit": girdi["kayit"],
        **sonuc,
    }


@musteri_alani.tum_alanlarda
def ata(db: Session, musteri_no: str, kart_id: int, kullanici: str) -> dict[str, Any]:
    """Isim karisikligi: TEMIP Musteri No'sunu (personelin) MEVCUT kartina ekler ve kayitlari baglar. Numara baska kartta yaziliysa 409."""
    no, kayit, unvan = _dogrula(db, musteri_no)
    kart = db.get(Customer, kart_id)
    if kart is None:
        raise AtamaHata(404, "Kart bulunamadı.")
    if kart.parent_id is not None:  # 2026-10-25 kullanici: "istiraklere atama yapilmamali" (yalniz ana / cati kart)
        raise AtamaHata(400, "İştirak kartına atama yapılamaz; ana (çatı) kartı seçin.")
    sahipler = _numara_sahipleri(db, no)
    if any(c.id == kart.id for c in sahipler):
        raise AtamaHata(409, "Bu numara zaten bu kartta yazılı.")
    if sahipler:
        raise AtamaHata(409, f"Bu numara başka kartta yazılı: {', '.join(c.name for c in sahipler)}. Önce o karttan çıkarın.")
    onceki = (kart.customer_no or "").strip()
    yeni = f"{onceki}, {no}" if onceki else no
    if len(yeni) > NO_ALANI_UZUNLUK:
        raise AtamaHata(409, "Kartın Müşteri No alanı dolu (200 karakter); önce gereksiz numaraları temizleyin.")
    kart.customer_no = yeni
    db.flush()
    return _kaydet(db, _girdi(db, no, unvan, kayit, kart, kullanici, yeni_kart=False), kart, kullanici)


def yeni_kart_ac(db: Session, user: Principal, musteri_no: str, tam_id: int, unvan: str = "") -> dict[str, Any]:
    """Musteri hicbir kartta yoksa: secilen personel (TAM) adina YENI kart acar (unvan: verilen ya da TEMIP unvani; Musteri No ile).
    Kart 'Musteri ekle' kurallariyla acilir (ayni unvanli kart varsa 409, personel gecerli olmali). Hata yazmadan once dogar;
    baglama ve commit cagiranda (tekil: personele_ata, toplu: fark.toplu_ata). Elle atama girdisini doner."""
    no, kayit, temip_unvan = _dogrula(db, musteri_no)
    if sahipler := _numara_sahipleri(db, no):
        raise AtamaHata(409, f"Bu numara zaten kartta yazılı: {', '.join(c.name for c in sahipler)}.")
    ad = " ".join((unvan or temip_unvan).split())[:150]
    if not ad:
        raise AtamaHata(400, "Kart ünvanı gerekli.")
    from app.musteri import servis as ms

    yeni = ms.musteri_ekle(db, user, {"name": ad, "owner_id": tam_id})
    kart = db.get(Customer, yeni["id"])
    kart.customer_no = no
    db.flush()
    return _girdi(db, no, temip_unvan, kayit, kart, user.username, yeni_kart=True)


@musteri_alani.tum_alanlarda
def personele_ata(db: Session, user: Principal, musteri_no: str, tam_id: int, unvan: str = "") -> dict[str, Any]:
    girdi = yeni_kart_ac(db, user, musteri_no, tam_id, unvan)
    return _kaydet(db, girdi, db.get(Customer, girdi["kart_id"]), user.username)


def personeller(db: Session) -> list[dict[str, Any]]:
    """Atanabilir personel: Musteri Yonetimi personel listesi (TAM; modul sahipleri haric)."""
    from app.kullanicilar import musteri_personeli

    return [{"id": u.id, "ad": u.display_name or u.username} for u in musteri_personeli(db)]


@musteri_alani.tum_alanlarda
def kaldir(db: Session, musteri_no: str, kullanici: str) -> dict[str, Any]:
    """Elle atamayi geri alir: numara karttan silinir, kayitlar yeniden baglanir (TAM Radar'a doner). Atamayla acilan kart SILINMEZ
    (karta sonradan veri girilmis olabilir); gerekiyorsa Musteri Yonetimi'nden silinir."""
    no = (musteri_no or "").strip()
    liste = _liste(db)
    atama = next((a for a in liste if a.get("musteri_no") == no), None)
    if atama is None:
        raise AtamaHata(404, "Bu numara için elle atama yok.")
    kart = db.get(Customer, int(atama["kart_id"]))
    if kart is not None and kart.customer_no:
        k = anahtar(no)
        parcalar = [p.strip() for p in re.split(r"[,;/\n]+", kart.customer_no) if p.strip() and anahtar(p) != k]
        kart.customer_no = ", ".join(parcalar) or None
    _liste_yaz(db, [a for a in liste if a.get("musteri_no") != no], kullanici)
    db.flush()
    sonuc = bagla(db)
    db.commit()
    return {"musteri_no": no, "kart_id": atama["kart_id"], **sonuc}


@musteri_alani.tum_alanlarda
def atamalar(db: Session) -> list[dict[str, Any]]:
    return _liste(db)


@musteri_alani.tum_alanlarda
def kart_ara(db: Session, q: str, tam_id: int | None = None, adet: int = 15) -> list[dict[str, Any]]:
    """Atama icin kart arama (unvan ya da numara; harf / Turkce karakter farksiz). tam_id: yalniz o personelin kartlari (bos arama
    o personelin tum kartlarini listeler). Yalniz ana (cati) kartlar: istirak karta atama yapilmaz (2026-10-25)."""
    from app.ortak import normal

    aranan = normal(q or "")
    if len(aranan) < 2 and not tam_id:
        return []
    sorgu = select(Customer).where(Customer.parent_id.is_(None)).order_by(Customer.name)
    if tam_id:
        sorgu = sorgu.where(Customer.owner_id == tam_id)
    sonuc = []
    for c in db.scalars(sorgu):
        if not aranan or aranan in normal(c.name or "") or aranan in (c.customer_no or ""):
            sonuc.append({"id": c.id, "ad": c.name, "musteri_no": c.customer_no or ""})
            if len(sonuc) >= adet:
                break
    return sonuc


# --- Musteri Radar (Fark'ta personel gibi secilen hedef) ------------------------------------------------------------------
def radar_listesi(db: Session) -> list[dict[str, Any]]:
    return _liste(db, RADAR_AYARI)


def radar_numaralari(db: Session) -> set[str]:
    return {str(a.get("musteri_no")) for a in radar_listesi(db)}


@musteri_alani.tum_alanlarda
def radara_gonder(db: Session, musteri_nolar: list[str], kullanici: str) -> dict[str, Any]:
    """Kartsiz numaralari Musteri Radar'a gonderir (kart acilmaz, kayitlar kartsiz kalir). Kartta yazili, TEMIP kaydi olmayan ya da zaten
    Radar'da olan numara atlanir (neden listelenir)."""
    liste = radar_listesi(db)
    var = {a.get("musteri_no") for a in liste}
    atanan: list[dict[str, Any]] = []
    atlanan: list[dict[str, str]] = []
    for ham in dict.fromkeys(n.strip() for n in musteri_nolar if n and n.strip()):
        try:
            no, kayit, unvan = _dogrula(db, ham)
            if no in var:
                raise AtamaHata(409, "Zaten Müşteri Radar'da.")
            if sahipler := _numara_sahipleri(db, no):
                raise AtamaHata(409, f"Bu numara zaten kartta yazılı: {', '.join(c.name for c in sahipler)}.")
        except UygulamaHatasi as hata:
            atlanan.append({"musteri_no": ham, "neden": hata.mesaj})
            continue
        var.add(no)
        atanan.append({"musteri_no": no, "temip_unvan": unvan, "kayit": kayit, "kim": kullanici, "zaman": iso(simdi())})
    if atanan:
        _liste_yaz(db, [*atanan, *liste], kullanici, RADAR_AYARI)
        surum_tazele(db)  # Radar / Fark onbellekleri
        db.commit()
    return {"atanan": len(atanan), "atlanan": atlanan}


def radardan_cikar(db: Session, musteri_nolar: list[str], kullanici: str) -> dict[str, Any]:
    """Numaralari Musteri Radar'dan cikarir; kartsizsa yeniden Fark'ta listelenir."""
    nolar = {n.strip() for n in musteri_nolar if n and n.strip()}
    liste = radar_listesi(db)
    kalan = [a for a in liste if a.get("musteri_no") not in nolar]
    if len(kalan) == len(liste):
        raise AtamaHata(404, "Bu numara Müşteri Radar'da değil.")
    _liste_yaz(db, kalan, kullanici, RADAR_AYARI)
    surum_tazele(db)
    db.commit()
    return {"cikarilan": len(liste) - len(kalan)}
