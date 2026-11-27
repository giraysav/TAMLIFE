# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Gelir Faydasi Saglanan Isler is kurallari: kayit CRUD, liste + suzgec + ozet, ceyrek sunum ozeti.

Gorme: modul_erisim("gelir_uretim") (rol gorunumune bagli). Excel ice aktarma: yalniz admin (deps.require_veri_yazma, API katmaninda).
Onay akisi (2026-10-15 kullanici istegi): modulu goren herkes yeni is girer; kayit 'bekliyor' olur ve modul sahibinin (app_setting
'gelir_uretim.sahip', admin atar) onayina duser (sahibin ve admin'in kendi girisi dogrudan onaylidir). Sahip ya da admin onaylar (canliya alir) veya gerekceyle reddeder. Bekleyen/reddedilen
kaydi yalniz giren kisi (duzeltip yeniden gonderir) ve sahip/admin gorur; toplamlara, Excel/PDF raporuna ve ceyrek sunumuna yalniz
ONAYLI isler girer. Onayli kaydi duzenleme ve silme sahip/admin isidir. Akistan onceki kayitlar ve Excel ice aktarma onaylidir.
Zorunlu alanlar (kullanicinin Excel basliklari, ZORUNLU): yeni giriste hepsi dolu olmali (sayilar 0 olabilir). Duzenlemede onceden bos
olan alan bos kalabilir (eski kayitlar duzenlenebilsin), dolu alan bosaltilamaz; bekleyen/reddedilen kayitta hepsi zorunludur.
Kisiler yalniz app.kullanicilar.personel kumesinden (etkin TeamMember) baglanir; yonetici ve admin hicbir kisi listesinde yoktur.
Zaman kurali: isin calisma araligi [baslangic, bitis]; bitis bos = devam ediyor (acik uclu). Baslangici olmayan is zamana
yerlestirilemez, yil/ceyrek suzgecinde ve sunum ozetinde yer almaz. Bitis tarihi olmayan TAMAMLANMIS is yalniz baslangic gununde sayilir
(tamamlanmis isin sonsuza dek "devam eden" sayilmamasi icin). Iptal edilen isler listede gorunur ama toplamlara girmez.
"""

from __future__ import annotations

import math
from datetime import date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.authz import is_admin
from app.dil import m
from app.gelir_uretim.ayristir import katla
from app.gelir_uretim.models import RevenueBenefit, RevenueBenefitPerson
from app.kullanicilar import kullanici_kaydi, personel
from app.models import AppSetting, AppUser
from app.ortak import UygulamaHatasi, iso, simdi
from app.session import Principal
from app.takvim.servis import donem_araligi

TURLER = ("proje", "inisiyatif")
FAYDA_TURLERI = ("gelir", "tasarruf", "verimlilik")
DURUMLAR = ("baslamadi", "devam", "tamamlandi", "iptal")
PARALAR = ("TRY", "USD", "EUR")
DONEMLER = ("ay", "yil", "tek_sefer")
ONAY_DURUMLARI = ("bekliyor", "onayli", "reddedildi")
SAHIP_ANAHTARI = "gelir_uretim.sahip"

# alan -> (Turkce ad, Ingilizce ad, azami uzunluk)
METIN_ALANLARI = {
    "title": ("Başlık", "Title", 300),
    "status_note": ("Güncel durum", "Current status", 4000),
    "roadmap": ("Yol haritası", "Roadmap", 4000),
    "description": ("Detaylı açıklama", "Description", 8000),
    "customers": ("Etkilenen müşteriler", "Affected customers", 500),
    "revenue_note": ("Tutar notu", "Amount note", 500),
    "hours_note": ("Efor notu", "Effort note", 500),
    "extra_note": ("Ek açıklamalar", "Additional notes", 4000),
    "other_people": ("Diğer kişiler", "Other people", 300),
}
SAYI_ALANLARI = {
    "revenue_amount": ("Gelir tutarı", "Revenue amount", 1e13),
    "year_revenue": ("Yıl içi gelir", "In-year revenue", 1e13),
    "hours_per_month": ("Aylık efor kazancı", "Monthly effort saved", 1e6),
    "hours_per_year": ("Yıllık efor kazancı", "Yearly effort saved", 1e7),
}
ALANLAR = (
    "kind", "benefit_type", "title", "status", "status_note", "description", "customers", "revenue_amount", "revenue_currency",
    "revenue_period", "revenue_note", "year_revenue", "hours_per_month", "hours_note", "extra_note", "start_date", "end_date", "other_people",
    "roadmap", "hours_per_year",
)  # fmt: skip
# Kullanicinin Excel basliklari sirasiyla zorunlu alanlar: alan -> (Turkce, Ingilizce). "people" = Ilgili TAM (personel ya da diger kisiler).
ZORUNLU = {
    "people": ("İlgili TAM", "Responsible TAM"),
    "title": ("İşin özeti", "Work summary"),
    "status_note": ("Güncel durum", "Current status"),
    "roadmap": ("Yol haritası", "Roadmap"),
    "description": ("Detaylı açıklaması", "Description"),
    "customers": ("Hangi müşteri/müşterileri etkilediği", "Affected customers"),
    "revenue_amount": ("Aylık gelir faydası (TL/ay)", "Monthly revenue benefit"),
    "year_revenue": ("Yıllık gelir faydası (TL/12 ay)", "Yearly revenue benefit"),
    "hours_per_month": ("Aylık verimlilik faydası (saat/ay)", "Monthly efficiency benefit (hours)"),
    "hours_per_year": ("Yıllık verimlilik faydası (saat/12 ay)", "Yearly efficiency benefit (hours)"),
    "extra_note": ("Ek açıklamalar", "Additional notes"),
    "start_date": ("Başlangıç tarihi", "Start date"),
    "end_date": ("Bitiş tarihi", "End date"),
}
TUR_SIRASI = {"proje": 0, "inisiyatif": 1}


class GelirUretimHata(UygulamaHatasi):
    """kod = HTTP durumu."""


def kisi_adi(kisi: AppUser | None) -> str:
    return (kisi.display_name or kisi.username) if kisi else ""


def _gecersiz(ad: str, etiketler: tuple[str, str]) -> GelirUretimHata:
    return GelirUretimHata(400, m(f"Geçersiz değer: {etiketler[0]}.", f"Invalid value: {etiketler[1]}."))


# --- dogrulama ---------------------------------------------------------------------------------------------------
def temizle(girdi: dict) -> dict:
    """Alan degerlerini siniflar ve dogrular (API'deki Pydantic gecilmis olsa da servis tek basina guvenlidir). Hata: 400."""
    v: dict = {}
    for ad, secenekler, varsayilan, etiket in (
        ("kind", TURLER, "proje", ("Tür", "Type")),
        ("benefit_type", FAYDA_TURLERI, "gelir", ("Fayda türü", "Benefit type")),
        ("status", DURUMLAR, "devam", ("Durum", "Status")),
        ("revenue_currency", PARALAR, "TRY", ("Para birimi", "Currency")),
        ("revenue_period", DONEMLER, "ay", ("Dönem", "Period")),
    ):
        deger = girdi.get(ad, varsayilan)
        if deger not in secenekler:
            raise _gecersiz(ad, etiket)
        v[ad] = deger
    for ad, (tr, en, sinir) in METIN_ALANLARI.items():
        deger = str(girdi.get(ad) or "").strip()
        if len(deger) > sinir:
            raise GelirUretimHata(400, m(f"{tr} en fazla {sinir} karakter olabilir.", f"{en} can be at most {sinir} characters."))
        v[ad] = deger
    if not v["title"]:
        raise GelirUretimHata(400, m("İş başlığı boş olamaz.", "The title cannot be empty."))
    for ad, (tr, en, ust) in SAYI_ALANLARI.items():
        deger = girdi.get(ad)
        if deger is None or deger == "":
            v[ad] = None
            continue
        if isinstance(deger, bool) or not isinstance(deger, (int, float)) or not math.isfinite(deger) or deger < 0 or deger > ust:
            raise GelirUretimHata(400, m(f"{tr} sıfır ya da pozitif bir sayı olmalı.", f"{en} must be zero or a positive number."))
        v[ad] = float(deger)
    for ad, etiket in (("start_date", ("Başlangıç tarihi", "Start date")), ("end_date", ("Bitiş tarihi", "End date"))):
        deger = girdi.get(ad)
        if deger is not None and not isinstance(deger, date):
            raise _gecersiz(ad, etiket)
        v[ad] = deger.date() if isinstance(deger, datetime) else deger
    if v["start_date"] and v["end_date"] and v["end_date"] < v["start_date"]:
        raise GelirUretimHata(400, m("Bitiş tarihi başlangıçtan önce olamaz.", "The end date cannot be before the start date."))
    return v


def eksik_alanlar(temiz: dict, kisi_var: bool) -> list[str]:
    """ZORUNLU alanlardan bos olanlar (sirasiyla). Sayi 0 dolu sayilir."""
    eksik = []
    for ad in ZORUNLU:
        if ad == "people":
            bos = not kisi_var and not temiz.get("other_people")
        else:
            deger = temiz.get(ad)
            bos = deger is None or (isinstance(deger, str) and not deger.strip())
        if bos:
            eksik.append(ad)
    return eksik


def zorunlu_dogrula(temiz: dict, kisi_var: bool, hos_gorulen: set[str] | frozenset[str] = frozenset()) -> None:
    """Eksik zorunlu alan varsa 400; hos_gorulen: duzenlemede onceden de bos olan (eski kayit) alanlar."""
    eksik = [a for a in eksik_alanlar(temiz, kisi_var) if a not in hos_gorulen]
    if eksik:
        raise GelirUretimHata(
            400,
            m(
                "Zorunlu alanlar boş: " + ", ".join(ZORUNLU[a][0] for a in eksik) + ". Sayısal alanlara fayda yoksa 0 yazın.",
                "Required fields are empty: " + ", ".join(ZORUNLU[a][1] for a in eksik) + ". Enter 0 in number fields when there is no benefit.",
            ),
        )


# --- modul sahibi ve yetki -----------------------------------------------------------------------------------------
def sahip_id(db: Session) -> int | None:
    kayit = db.get(AppSetting, SAHIP_ANAHTARI)
    deger = kayit.value if kayit is not None and isinstance(kayit.value, dict) else {}
    kimlik = deger.get("user_id")
    return kimlik if isinstance(kimlik, int) and not isinstance(kimlik, bool) else None


def sahip(db: Session) -> AppUser | None:
    kimlik = sahip_id(db)
    kisi = db.get(AppUser, kimlik) if kimlik is not None else None
    return kisi if kisi is not None and kisi.active is not False else None


def sahip_adaylari(db: Session) -> list[dict]:
    """Modul sahibi secenekleri: etkin hesaplar (admin hesaplari haric; admin zaten onaylayabilir)."""
    kisiler = db.scalars(select(AppUser).where(AppUser.active.is_not(False)).order_by(AppUser.display_name, AppUser.username))
    return [{"id": k.id, "ad": kisi_adi(k)} for k in kisiler if not (k.is_admin or k.role == "admin")]


def sahip_kaydet(db: Session, kimlik: int | None, yapan: str) -> AppUser | None:
    if kimlik is not None and kimlik not in {a["id"] for a in sahip_adaylari(db)}:
        raise GelirUretimHata(400, m("Modül sahibi etkin bir panel kullanıcısı olmalı.", "The module owner must be an active panel user."))
    kayit = db.get(AppSetting, SAHIP_ANAHTARI)
    if kayit is None:
        kayit = AppSetting(key=SAHIP_ANAHTARI)
        db.add(kayit)
    kayit.value = {"user_id": kimlik}
    kayit.updated_by, kayit.updated_at = yapan[:120], simdi()
    db.flush()
    return sahip(db)


def _kim(db: Session, user: Principal) -> AppUser | None:
    """Oturumdaki kisinin satiri (olusturmaz: yalniz okuma)."""
    return db.scalar(select(AppUser).where(AppUser.username == user.username))


def yonetebilir(db: Session, user: Principal) -> bool:
    """Onay, onayli kaydi duzenleme ve silme: admin ya da modul sahibi."""
    if is_admin(user):
        return True
    kimlik = sahip_id(db)
    kisi = _kim(db, user)
    return kimlik is not None and kisi is not None and kisi.id == kimlik


def _kendi(db: Session, user: Principal, r: RevenueBenefit) -> bool:
    kisi = _kim(db, user)
    return kisi is not None and r.created_by_id == kisi.id


def gorebilir(db: Session, user: Principal, r: RevenueBenefit, yonetici: bool | None = None) -> bool:
    if r.approval == "onayli":
        return True
    return (yonetebilir(db, user) if yonetici is None else yonetici) or _kendi(db, user, r)


def _kisileri_dogrula(db: Session, idler: list[int], izinli_ek: set[int] | None = None) -> list[int]:
    """Yalniz etkin TAM personeli (kisi listelerinin tek kumesi). Guncellemede isin zaten bagli kisileri de gecer (sonradan pasif olmus olabilir)."""
    tekil = list(dict.fromkeys(idler))
    if not tekil:
        return []
    gecerli = {k.id for k in personel(db)} | (izinli_ek or set())
    if any(i not in gecerli for i in tekil):
        raise GelirUretimHata(400, m("Yalnızca etkin TAM personeli seçilebilir.", "Only active TAM staff can be selected."))
    return tekil


def _bul(db: Session, kayit_id: int) -> RevenueBenefit:
    satir = db.get(RevenueBenefit, kayit_id)
    if satir is None:
        raise GelirUretimHata(404, m("Kayıt bulunamadı.", "Record not found."))
    return satir


def _bagli_idler(db: Session, kayit_id: int) -> set[int]:
    return set(db.scalars(select(RevenueBenefitPerson.user_id).where(RevenueBenefitPerson.item_id == kayit_id)))


# --- yazma -------------------------------------------------------------------------------------------------------
def ekle(
    db: Session, yapan: str, temiz: dict, kisi_idleri: list[int], *, onay: str = "onayli", yapan_id: int | None = None
) -> RevenueBenefit:
    """Temizlenmis alanlarla kayit ekler (flush eder, commit etmez). Excel ice aktarma da bunu kullanir (onayli); kisi idleri onceden dogrulanmis olmali."""
    an = simdi()
    satir = RevenueBenefit(
        **temiz, created_by=yapan, created_at=an, updated_by=yapan, updated_at=an, approval=onay, created_by_id=yapan_id,
        approved_by=yapan if onay == "onayli" else "", approved_at=an if onay == "onayli" else None,
    )  # fmt: skip
    db.add(satir)
    db.flush()
    for kisi_id in kisi_idleri:
        db.add(RevenueBenefitPerson(item_id=satir.id, user_id=kisi_id))
    db.flush()
    return satir


def olustur(db: Session, user: Principal, girdi: dict, kisi_idleri: list[int]) -> RevenueBenefit:
    """Yeni giris: tum zorunlu alanlar dolu olmali. Personelin girisi sahibin onayina duser ('bekliyor'); onay yetkisi olanin
    (modul sahibi ya da admin) girisi dogrudan onaylidir."""
    temiz = temizle(girdi)
    idler = _kisileri_dogrula(db, kisi_idleri)
    zorunlu_dogrula(temiz, bool(idler))
    onay = "onayli" if yonetebilir(db, user) else "bekliyor"
    kisi = kullanici_kaydi(db, user)
    return ekle(db, kisi_adi(kisi), temiz, idler, onay=onay, yapan_id=kisi.id)


def _yazma_yetkisi(db: Session, user: Principal, satir: RevenueBenefit) -> bool:
    """Sahip/admin her kaydi; giren kisi yalniz kendi bekleyen ya da reddedilen kaydini degistirir."""
    return yonetebilir(db, user) or (satir.approval != "onayli" and _kendi(db, user, satir))


def _bul_yazilabilir(db: Session, user: Principal, kayit_id: int) -> RevenueBenefit:
    satir = _bul(db, kayit_id)
    if not gorebilir(db, user, satir):
        raise GelirUretimHata(404, m("Kayıt bulunamadı.", "Record not found."))
    if not _yazma_yetkisi(db, user, satir):
        raise GelirUretimHata(
            403,
            m(
                "Onaylı kaydı yalnızca modül sahibi ya da admin değiştirebilir.",
                "Only the module owner or an admin can change an approved record.",
            ),
        )
    return satir


def guncelle(db: Session, user: Principal, kayit_id: int, girdi: dict, kisi_idleri: list[int]) -> list[str]:
    """Kaydin tum alanlarini degistirir; degisen alan adlarini (deger degil) dondurur. Degisiklik yoksa guncelleme izi yazilmaz.
    Reddedilen kaydi giren kisi duzeltince kayit yeniden onaya duser ('bekliyor')."""
    satir = _bul_yazilabilir(db, user, kayit_id)
    temiz = temizle(girdi)
    mevcut = _bagli_idler(db, kayit_id)
    idler = _kisileri_dogrula(db, kisi_idleri, izinli_ek=mevcut)
    onceki = {ad: getattr(satir, ad) for ad in ALANLAR}
    hos = frozenset() if satir.approval != "onayli" else frozenset(eksik_alanlar(onceki, bool(mevcut)))
    zorunlu_dogrula(temiz, bool(idler), hos)
    degisen = [ad for ad in ALANLAR if getattr(satir, ad) != temiz[ad]]
    for ad in degisen:
        setattr(satir, ad, temiz[ad])
    if set(idler) != mevcut:
        degisen.append("person_ids")
        db.execute(delete(RevenueBenefitPerson).where(RevenueBenefitPerson.item_id == kayit_id, RevenueBenefitPerson.user_id.not_in(idler or [0])))
        for kisi_id in idler:
            if kisi_id not in mevcut:
                db.add(RevenueBenefitPerson(item_id=kayit_id, user_id=kisi_id))
    if degisen:
        satir.updated_by = kisi_adi(kullanici_kaydi(db, user))
        satir.updated_at = simdi()
        if satir.approval == "reddedildi":
            satir.approval = "bekliyor"
            degisen.append("approval")
    db.flush()
    return degisen


def onay_ver(db: Session, user: Principal, kayit_id: int, karar: str, gerekce: str = "") -> str:
    """karar: onayla | reddet (gerekce zorunlu) | geri_al (onayli kaydi yeniden beklemeye alir). Yalniz sahip/admin. Donus: yeni durum."""
    if not yonetebilir(db, user):
        raise GelirUretimHata(403, m("Onay yalnızca modül sahibi ya da admin yetkisindedir.", "Only the module owner or an admin can approve."))
    satir = _bul(db, kayit_id)
    gerekce = gerekce.strip()
    if len(gerekce) > 2000:
        raise GelirUretimHata(400, m("Gerekçe en fazla 2000 karakter olabilir.", "The reason can be at most 2000 characters."))
    if karar == "reddet" and not gerekce:
        raise GelirUretimHata(400, m("Ret gerekçesi yazın.", "Write a reason for rejecting."))
    yeni = {"onayla": "onayli", "reddet": "reddedildi", "geri_al": "bekliyor"}.get(karar)
    if yeni is None:
        raise GelirUretimHata(400, m("Geçersiz karar.", "Invalid decision."))
    if yeni == "onayli":
        zorunlu_dogrula(
            {ad: getattr(satir, ad) for ad in ALANLAR}, bool(_bagli_idler(db, kayit_id)), frozenset() if satir.created_by_id else frozenset(ZORUNLU)
        )
    satir.approval = yeni
    satir.approval_note = gerekce if yeni == "reddedildi" else ""
    satir.approved_by = kisi_adi(kullanici_kaydi(db, user))
    satir.approved_at = simdi()
    db.flush()
    return yeni


def sil(db: Session, user: Principal, kayit_id: int) -> None:
    satir = _bul_yazilabilir(db, user, kayit_id)
    db.execute(delete(RevenueBenefitPerson).where(RevenueBenefitPerson.item_id == kayit_id))  # SQLite'ta FK zinciri kapali olabilir: acikca silinir
    db.delete(satir)
    db.flush()


# --- zaman ---------------------------------------------------------------------------------------------------------
def calisma_araligi(r: RevenueBenefit) -> tuple[date, date | None] | None:
    """(baslangic, bitis); bitis None = devam ediyor. Baslangic yoksa None (zamana yerlestirilemez)."""
    if r.start_date is None:
        return None
    if r.end_date is not None:
        return r.start_date, max(r.end_date, r.start_date)
    if r.status == "tamamlandi":
        return r.start_date, r.start_date
    return r.start_date, None


def aralik_kesisir(r: RevenueBenefit, bas: date, son: date) -> bool:
    aralik = calisma_araligi(r)
    return aralik is not None and aralik[0] <= son and (aralik[1] is None or aralik[1] >= bas)


# --- okuma ---------------------------------------------------------------------------------------------------------
def _kisi_haritasi(db: Session, idler: list[int]) -> dict[int, list[AppUser]]:
    harita: dict[int, list[AppUser]] = {i: [] for i in idler}
    if not idler:
        return harita
    sorgu = (
        select(RevenueBenefitPerson.item_id, AppUser)
        .join(AppUser, AppUser.id == RevenueBenefitPerson.user_id)
        .where(RevenueBenefitPerson.item_id.in_(idler))
        .order_by(AppUser.display_name, AppUser.username)
    )
    for kayit_id, kisi in db.execute(sorgu):
        harita[kayit_id].append(kisi)
    return harita


def kayit_sozlugu(r: RevenueBenefit, kisiler: list[AppUser]) -> dict:
    return {
        "id": r.id,
        "kind": r.kind,
        "benefit_type": r.benefit_type,
        "title": r.title,
        "status": r.status,
        "status_note": r.status_note,
        "description": r.description,
        "customers": r.customers,
        "revenue_amount": r.revenue_amount,
        "revenue_currency": r.revenue_currency,
        "revenue_period": r.revenue_period,
        "revenue_note": r.revenue_note,
        "year_revenue": r.year_revenue,
        "hours_per_month": r.hours_per_month,
        "hours_note": r.hours_note,
        "hours_per_year": r.hours_per_year,
        "roadmap": r.roadmap,
        "extra_note": r.extra_note,
        "start_date": r.start_date.isoformat() if r.start_date else None,
        "end_date": r.end_date.isoformat() if r.end_date else None,
        "other_people": r.other_people,
        "people": [{"id": k.id, "name": kisi_adi(k)} for k in kisiler],
        "created_by": r.created_by,
        "created_at": iso(r.created_at),
        "updated_by": r.updated_by,
        "updated_at": iso(r.updated_at),
        "created_by_id": r.created_by_id,
        "approval": r.approval,
        "approval_note": r.approval_note,
        "approved_by": r.approved_by,
        "approved_at": iso(r.approved_at) if r.approved_at else None,
        "eksik": eksik_alanlar({ad: getattr(r, ad) for ad in ALANLAR}, bool(kisiler)),
    }


def _toplamlara_girer(r: RevenueBenefit) -> bool:
    return r.status != "iptal" and r.approval == "onayli"


def ozet_hesapla(kayitlar: list[RevenueBenefit], toplam_is: int) -> dict:
    """Gosterilen ONAYLI kayitlarin ozeti (bekleyen/reddedilen sayilmaz). Iptal edilenler sayida gorunur, tutar/saat toplamlarina girmez.
    Kur cevirisi yok: para birimi basina toplanir."""
    kayitlar = [r for r in kayitlar if r.approval == "onayli"]
    aylik: dict[str, float] = {}
    yillik: dict[str, float] = {}
    tek: dict[str, float] = {}
    yil_ici = 0.0
    saat = 0.0
    yil_saat = 0.0
    for r in kayitlar:
        if not _toplamlara_girer(r):
            continue
        if r.revenue_amount is not None:
            hedef = {"ay": aylik, "yil": yillik, "tek_sefer": tek}[r.revenue_period]
            hedef[r.revenue_currency] = round(hedef.get(r.revenue_currency, 0.0) + r.revenue_amount, 2)
        yil_ici += r.year_revenue or 0.0
        saat += r.hours_per_month or 0.0
        yil_saat += r.hours_per_year or 0.0
    return {
        "is_sayisi": len(kayitlar),
        "toplam_is": toplam_is,
        "durum_sayilari": {d: sum(1 for r in kayitlar if r.status == d) for d in DURUMLAR},
        "aylik_gelir": aylik,
        "yillik_gelir": yillik,
        "tek_seferlik_gelir": tek,
        "yil_ici_gelir": round(yil_ici, 2),
        "aylik_saat": round(saat, 2),
        "yillik_saat": round(yil_saat, 2),
    }


def _sirala(kayitlar: list[RevenueBenefit]) -> list[RevenueBenefit]:
    """Once projeler, sonra TAM inisiyatifleri; her grupta en yeni baslangic ustte, tarihsizler sonda."""
    return sorted(
        kayitlar,
        key=lambda r: (TUR_SIRASI.get(r.kind, 9), r.start_date is None, -(r.start_date.toordinal() if r.start_date else 0), -r.id),
    )


def personel_secenekleri(db: Session) -> list[dict]:
    return [{"id": k.id, "ad": kisi_adi(k)} for k in personel(db)]


def _suz(
    db: Session,
    *,
    q: str = "",
    tur: str | None = None,
    durum: str | None = None,
    fayda: str | None = None,
    tam: int | None = None,
    yil: int | None = None,
    onay: str | None = None,
) -> tuple[list[RevenueBenefit], dict[int, list[AppUser]]]:
    """Suzgeclere uyan kayitlar (sirali) ve kisileri. Gorme kurali cagirandadir."""
    sorgu = select(RevenueBenefit)
    if tur:
        sorgu = sorgu.where(RevenueBenefit.kind == tur)
    if durum:
        sorgu = sorgu.where(RevenueBenefit.status == durum)
    if fayda:
        sorgu = sorgu.where(RevenueBenefit.benefit_type == fayda)
    if onay:
        sorgu = sorgu.where(RevenueBenefit.approval == onay)
    if tam:
        sorgu = sorgu.where(RevenueBenefit.id.in_(select(RevenueBenefitPerson.item_id).where(RevenueBenefitPerson.user_id == tam)))
    kayitlar = list(db.scalars(sorgu))
    if yil:
        bas, son = donem_araligi(yil, 0)
        kayitlar = [r for r in kayitlar if aralik_kesisir(r, bas, son)]
    kisiler = _kisi_haritasi(db, [r.id for r in kayitlar])
    anahtar = katla(q).strip()
    if anahtar:
        kayitlar = [
            r
            for r in kayitlar
            if anahtar
            in katla(" ".join([r.title, r.customers, r.description, r.status_note, r.roadmap, r.extra_note, r.other_people, *(kisi_adi(k) for k in kisiler[r.id])]))
        ]
    return _sirala(kayitlar), kisiler


def liste(
    db: Session,
    user: Principal,
    *,
    q: str = "",
    tur: str | None = None,
    durum: str | None = None,
    fayda: str | None = None,
    tam: int | None = None,
    yil: int | None = None,
    onay: str | None = None,
) -> dict:
    """Suzulmus liste + ozet + secenekler. q: baslik, musteri, aciklama, durum, yol haritasi, ek not ve kisi adlarinda (Turkce harf/buyuk-kucuk
    farksiz) arar. yil: calisma araligi o yila degen isler (baslangici olmayanlar elenir). Bekleyen/reddedilen kayitlar yalniz girene ve
    sahip/admin'e listelenir; ozet yalniz onaylilari toplar. bekleyen: sahip/admin icin onay bekleyen kayit sayisi (suzgecsiz)."""
    yonetici = yonetebilir(db, user)
    kayitlar, kisiler = _suz(db, q=q, tur=tur, durum=durum, fayda=fayda, tam=tam, yil=yil, onay=onay)
    kayitlar = [r for r in kayitlar if gorebilir(db, user, r, yonetici)]
    yillar = {simdi().year}
    for baslangic, bitis in db.execute(select(RevenueBenefit.start_date, RevenueBenefit.end_date)):
        yillar.update(t.year for t in (baslangic, bitis) if t)
    kisi = _kim(db, user)
    sahibi = sahip(db)
    return {
        "items": [kayit_sozlugu(r, kisiler[r.id]) for r in kayitlar],
        "ozet": ozet_hesapla(kayitlar, db.scalar(select(func.count(RevenueBenefit.id)).where(RevenueBenefit.approval == "onayli")) or 0),
        "secenekler": {"personel": personel_secenekleri(db), "yillar": sorted(yillar, reverse=True)},
        "onay": {
            "sahip": {"id": sahibi.id, "ad": kisi_adi(sahibi)} if sahibi else None,
            "yonetebilir": yonetici,
            "bekleyen": (db.scalar(select(func.count(RevenueBenefit.id)).where(RevenueBenefit.approval == "bekliyor")) or 0) if yonetici else 0,
            "benim": kisi.id if kisi else None,
        },
    }


def tum_kayitlar(db: Session, **suzgec: object) -> list[tuple[RevenueBenefit, list[AppUser]]]:
    """Excel/PDF rapor icin: suzgece uyan ONAYLI kayitlar (sirali) ve kisileri."""
    kayitlar, kisiler = _suz(db, **{**suzgec, "onay": "onayli"})  # type: ignore[arg-type]
    return [(r, kisiler[r.id]) for r in kayitlar]


# --- ceyrek sunum ozeti ------------------------------------------------------------------------------------------
def _kpi(ad: str, ad_en: str, deger: float | None, birim: str = "", alt: str = "") -> dict:
    return {"ad": ad, "ad_en": ad_en, "deger": deger, "birim": birim, "alt": alt}


def _sutun(ad: str, ad_en: str, birim: str = "") -> dict:
    return {"ad": ad, "ad_en": ad_en, "birim": birim}


def sunum_ozeti(db: Session, yil: int, ceyrek: int) -> dict:
    """Sunum modulunun genel kart yuku. ceyrek 0 = tum yil. O doneme calisma araligi degen, iptal edilmemis ONAYLI isler.

    Hucreler dil bagimsizdir (ceyrek gecmisse kart dondurulur): is adi, kisi adlari, ISO tarih, sayilar. Tutarlar para birimi basina ayri
    sutun/KPI'dir (kur cevirisi yok); yalniz AYLIK tutarlar toplanir, yillik ve tek seferlik tutarlar bu kartta yer almaz."""
    bas, son = donem_araligi(yil, ceyrek)
    secilen = [r for r in db.scalars(select(RevenueBenefit)) if _toplamlara_girer(r) and aralik_kesisir(r, bas, son)]
    secilen = sorted(secilen, key=lambda r: (r.start_date or date.max, r.title.lower(), r.id))
    kisiler = _kisi_haritasi(db, [r.id for r in secilen])
    aylik_paralar = [p for p in PARALAR if any(r.revenue_amount is not None and r.revenue_period == "ay" and r.revenue_currency == p for r in secilen)] or ["TRY"]
    yil_ici = [r.year_revenue for r in secilen if r.year_revenue is not None]
    saatler = [r.hours_per_month for r in secilen if r.hours_per_month is not None]

    def aylik(r: RevenueBenefit, para: str) -> float | None:
        return r.revenue_amount if r.revenue_amount is not None and r.revenue_period == "ay" and r.revenue_currency == para else None

    def aylik_toplam(para: str) -> float:
        return round(sum(aylik(r, para) or 0.0 for r in secilen), 2)

    kpi = [
        _kpi("Fayda sağlanan iş", "Work delivering benefit", len(secilen)),
        _kpi("Tamamlanan", "Completed", sum(1 for r in secilen if r.status == "tamamlandi")),
        *(_kpi(f"Aylık gelir {p}", f"Monthly revenue {p}", aylik_toplam(p), birim=p) for p in aylik_paralar),
    ]
    if yil_ici:
        kpi.append(_kpi("Yıl içi gelir", "In-year revenue", round(sum(yil_ici), 2), birim="TRY"))
    if saatler:
        kpi.append(_kpi("Aylık efor kazancı (saat)", "Monthly effort saved (hours)", round(sum(saatler), 2)))
    yil_saatler = [r.hours_per_year for r in secilen if r.hours_per_year is not None]
    if yil_saatler:
        kpi.append(_kpi("Yıllık efor kazancı (saat)", "Yearly effort saved (hours)", round(sum(yil_saatler), 2)))
    satirlar = []
    for r in secilen:
        adlar = [kisi_adi(k) for k in kisiler[r.id]] + ([r.other_people] if r.other_people else [])
        satirlar.append(
            [
                r.title,
                ", ".join(adlar) or "—",
                r.start_date.isoformat() if r.start_date else None,
                r.end_date.isoformat() if r.end_date else None,
                *(aylik(r, p) for p in aylik_paralar),
                r.year_revenue,
                r.hours_per_month,
            ]
        )
    return {
        "kpi": kpi,
        "tablo": {
            "sutunlar": [
                _sutun("İş", "Work"),
                _sutun("TAM", "TAM"),
                _sutun("Başlangıç", "Start"),
                _sutun("Bitiş", "End"),
                *(_sutun(f"Aylık gelir {p}", f"Monthly revenue {p}", p) for p in aylik_paralar),
                _sutun("Yıl içi gelir", "In-year revenue", "TRY"),
                _sutun("Saat/ay", "Hours/month"),
            ],
            "satirlar": satirlar,
        },
    }
