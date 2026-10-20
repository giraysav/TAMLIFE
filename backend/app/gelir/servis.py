"""ICT SMS gelirleri, APN kurulum gelirleri ve APN musteri calismalari.

Kayitlar TAM'in kendi DB dosyasindadir (app.db.kullanici_oturumu). Gorunurluk (uretim ad_benim): admin ve Manager tum dosyalari;
Member yalniz kendi dosyasini gorur ve degistirir. Kaydin TAM'i yalniz ortak personel kumesinden (kullanicilar.personel) olur: acik secilir,
secilmediyse musterinin sorumlu TAM'inden turetilir, o da yoksa bos kalir (admin TAM degildir, sunumda tek '—' satiri); duzenlemede mevcut TAM korunur. Disariya verilen kimlik dosyalar arasi tekildir (app.db.dis_kimlik). Tutarlar: SMS icin TRY/USD/EUR, APN kurulum icin TL.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.authz import is_admin
from app.db import dis_kimlik, kimlik_coz, kullanici_dosyasi, kullanici_oturumu, mevcut_oturumlar
from app.kullanicilar import kullanici_kaydi, modul_sahibi, personel, personel_mi
from app.models import ApnRevenue, ApnWork, AppUser, Customer, SmsRevenue
from app.ortak import UygulamaHatasi, eslestirme_anahtari, simdi
from app.session import Principal

PARA_BIRIMLERI = ("TRY", "USD", "EUR")
EN_COK_KAYIT = 2000
EN_BUYUK_TUTAR = 1e13
_TARIH_TR = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_BIN_AYRACLI = re.compile(r"^\d{1,3}(\.\d{3})+$")


class GelirHata(UygulamaHatasi):
    """kod = HTTP durumu."""


# --- dogrulama -------------------------------------------------------------------------------------
def _metin(govde: dict, alan: str, etiket: str, azami: int, zorunlu: bool = False) -> str:
    deger = str(govde.get(alan) or "").strip()
    if zorunlu and not deger:
        raise GelirHata(400, f"{etiket} zorunlu.")
    if len(deger) > azami:
        raise GelirHata(400, f"{etiket} en fazla {azami} karakter olabilir.")
    return deger


def _tutar(govde: dict, alan: str = "tutar", etiket: str = "Gelir") -> float:
    ham = govde.get(alan, 0)
    if isinstance(ham, bool):
        raise GelirHata(400, f"{etiket} sayı olmalı.")
    if isinstance(ham, str):
        t = ham.replace(" ", "").replace("₺", "").replace("TL", "")
        if "," in t:
            t = t.replace(".", "").replace(",", ".")
        elif _BIN_AYRACLI.match(t):
            t = t.replace(".", "")  # "1.250" Turkce'de bin ayracidir (1250); "1250.5" ondalik kalir
        ham = t or "0"
    try:
        deger = float(ham)
    except (TypeError, ValueError):
        raise GelirHata(400, f"{etiket} sayı olmalı.") from None
    if math.isnan(deger) or not 0 <= deger <= EN_BUYUK_TUTAR:
        raise GelirHata(400, f"{etiket} 0 ile {EN_BUYUK_TUTAR:.0f} arasında olmalı.")
    return round(deger, 2)


def _tarih(govde: dict, alan: str, etiket: str, zorunlu: bool = False) -> date | None:
    ham = govde.get(alan)
    if ham in (None, ""):
        if zorunlu:
            raise GelirHata(400, f"{etiket} zorunlu.")
        return None
    metin = str(ham).strip()
    try:
        tr = _TARIH_TR.match(metin)
        return date(int(tr.group(3)), int(tr.group(2)), int(tr.group(1))) if tr else datetime.strptime(metin[:10], "%Y-%m-%d").date()
    except ValueError:
        raise GelirHata(400, f"{etiket} geçerli bir tarih olmalı (GG.AA.YYYY).") from None


def _tamsayi(govde: dict, alan: str, etiket: str, en_az: int, en_cok: int, varsayilan: int) -> int:
    ham = govde.get(alan)
    if ham in (None, ""):
        return varsayilan
    try:
        deger = int(ham)
    except (TypeError, ValueError):
        raise GelirHata(400, f"{etiket} tam sayı olmalı.") from None
    if not en_az <= deger <= en_cok:
        raise GelirHata(400, f"{etiket} {en_az}-{en_cok} arasında olmalı.")
    return deger


# --- gorunurluk ve dosya secimi ------------------------------------------------------------------------
GELIR_MODULLERI = ("tamsms", "tamapn")


def _yonetici(db: Session, user: Principal) -> bool:
    """2026-10-20 kullanici karari: ICT SMS ve APN yonetimli modul. Yazma (API'de modul_yoneticisi_mi kapisi) yalniz admin ve modulun
    sahibinde; yazan TAM secer, kaydi baskasinin dosyasina yazar. Okuma herkese acik (tum dosyalar)."""
    return is_admin(user) or modul_sahibi(db, user) in GELIR_MODULLERI


def _sahip(db: Session, user: Principal, tam_adi: str = "") -> AppUser:
    """Kaydin yazilacagi dosyanin sahibi: yonetici bir TAM sectiyse (ya da musteriden turediyse) o kisi, degilse kaydi giren."""
    if tam_adi and _yonetici(db, user):
        kisi = db.scalar(select(AppUser).where(or_(AppUser.display_name == tam_adi, AppUser.username == tam_adi)).limit(1))
        if kisi is not None:
            return kisi
    return kullanici_kaydi(db, user)


def tam_adlari(db: Session, user: Principal) -> list[str]:
    """Secilebilir TAM'lar: ortak personel kumesi (etkin TeamMember; yonetici ve admin TAM degildir)."""
    kisiler = personel(db)
    return [k.display_name or k.username for k in kisiler]


def _musteri_tami(db: Session, musteri: str) -> str:
    """Musterinin sorumlu TAM'i (kart sahibi; istirakte catinin sahibi); personel degilse ya da musteri yoksa bos."""
    anahtar = eslestirme_anahtari(musteri)
    musteriler = {c.id: c for c in db.scalars(select(Customer))}
    for c in musteriler.values():
        if eslestirme_anahtari(c.name or "") != anahtar:
            continue
        cati = musteriler.get(c.parent_id) if c.parent_id else None
        for uid in (c.owner_id, cati.owner_id if cati else None):
            kisi = db.get(AppUser, uid) if uid else None
            if personel_mi(kisi):
                return kisi.display_name or kisi.username
    return ""


def _ad(db: Session, user: Principal) -> str:
    return kullanici_kaydi(db, user).display_name or user.username


def _topla(db: Session, user: Principal, model: Any) -> list[tuple[int, Any]]:
    """Tum dosyalardaki kayitlar: (sahip id, satir). 2026-10-20: herkes hepsini gorur."""
    kisiler = {u.username: u.id for u in db.scalars(select(AppUser))}
    cikti: list[tuple[int, Any]] = []
    for ad, k in mevcut_oturumlar(kisiler):
        cikti += [(kisiler[ad], r) for r in k.scalars(select(model).limit(EN_COK_KAYIT))]
        k.expunge_all()
    return cikti


@contextmanager
def _kayit(db: Session, user: Principal, model: Any, kimlik: int) -> Iterator[tuple[AppUser, Session, Any]]:
    uid, yerel = kimlik_coz(kimlik)
    sahip = db.get(AppUser, uid)
    if sahip is None or not kullanici_dosyasi(sahip.username).is_file():
        raise GelirHata(404, "Kayıt bulunamadı.")  # varligi sizdirilmaz
    with kullanici_oturumu(sahip.username) as k:
        kayit = k.get(model, yerel)
        if kayit is None:
            raise GelirHata(404, "Kayıt bulunamadı.")
        yield sahip, k, kayit


def _ekle(db: Session, user: Principal, model: Any, alanlar: dict, cikti: Callable[[int, Any], dict]) -> dict:
    sahip = _sahip(db, user, alanlar.get("tam_name", ""))
    with kullanici_oturumu(sahip.username) as k:
        kayit = model(**alanlar, created_by=user.username[:100], created_at=simdi())
        k.add(kayit)
        k.commit()
        return cikti(sahip.id, kayit)


def _guncelle(db: Session, user: Principal, model: Any, kimlik: int, uret: Callable[[str | None], dict], cikti: Callable[[int, Any], dict]) -> dict:
    """uret(onceki_tam): dogrulanmis alanlar; onceki_tam kayitta saklanan TAM (TAM'i olmayan model icin None)."""
    with _kayit(db, user, model, kimlik) as (sahip, k, kayit):
        onceki = getattr(kayit, "tam_name", None)
        alanlar = uret(onceki)
        if not _yonetici(db, user):
            alanlar.pop("tam_name", None)
        for alan, deger in alanlar.items():
            setattr(kayit, alan, deger)
        yeni = _sahip(db, user, alanlar.get("tam_name", ""))
        if "tam_name" not in alanlar or alanlar["tam_name"] == onceki or yeni.id == sahip.id:  # TAM ayni kaldiysa dosya degismez
            k.commit()
            return cikti(sahip.id, kayit)
        degerler = {c.key: getattr(kayit, c.key) for c in model.__table__.columns if c.key != "id"}
        k.delete(kayit)  # TAM degisti: kayit yeni sahibin dosyasina tasinir
        k.commit()
    with kullanici_oturumu(yeni.username) as k:
        tasinan = model(**degerler)
        k.add(tasinan)
        k.commit()
        return cikti(yeni.id, tasinan)


def _sil(db: Session, user: Principal, model: Any, kimlik: int) -> dict:
    with _kayit(db, user, model, kimlik) as (_, k, kayit):
        k.delete(kayit)
        k.commit()
    return {"silinen": kimlik}


def musteri_adlari(db: Session, user: Principal) -> list[str]:
    """Form onerileri: musteri unvanlari (herkes hepsini gorur)."""
    sorgu = select(Customer.name)
    return sorted({n for n in db.scalars(sorgu.order_by(Customer.name).limit(1000)) if n})


def _toplamlar(ciftler) -> dict[str, float]:
    t: dict[str, float] = defaultdict(float)
    for para, tutar in ciftler:
        t[para] += tutar or 0
    return {p: round(v, 2) for p, v in t.items()}


def _tam(db: Session, user: Principal, govde: dict, musteri: str, onceki: str | None = None) -> str:
    """Kaydin TAM'i. Member yalniz kendisi. Yonetici: secilen kisi personel olmali (onceki kayitla ayniysa degismemis sayilir); secilmediyse
    duzenlemede mevcut TAM korunur, yeni kayitta musterinin sorumlu TAM'i, o da yoksa bos ('—')."""
    if not _yonetici(db, user):
        return _ad(db, user)[:100]
    secilen = _metin(govde, "tam", "TAM", 100)
    if secilen:
        if secilen == onceki:
            return secilen
        eslesen = next((k for k in personel(db) if eslestirme_anahtari(secilen) in (eslestirme_anahtari(k.display_name or ""), eslestirme_anahtari(k.username))), None)
        if eslesen is None:
            raise GelirHata(400, "TAM, personel listesinden seçilmeli.")
        return (eslesen.display_name or eslesen.username)[:100]
    if onceki is not None:
        return onceki
    return _musteri_tami(db, musteri)[:100]


# --- ICT SMS ----------------------------------------------------------------------------------------
def _sms(uid: int, r: SmsRevenue) -> dict:
    return {"id": dis_kimlik(uid, r.id), "musteri": r.customer_name, "proje": r.project or "", "tutar": r.amount, "para_birimi": r.currency, "tam": r.tam_name, "yil": r.year, "ay": r.month}


def sms_liste(db: Session, user: Principal, yil: int | None = None) -> dict:
    tumu = _topla(db, user, SmsRevenue)
    yillar = sorted({r.year for _, r in tumu}, reverse=True)
    satirlar = sorted((x for x in tumu if not yil or x[1].year == yil), key=lambda x: (-x[1].year, -x[1].month, x[1].customer_name))[:EN_COK_KAYIT]
    return {"items": [_sms(u, r) for u, r in satirlar], "toplam": _toplamlar((r.currency, r.amount) for _, r in satirlar), "yillar": yillar}


def _sms_alanlari(db: Session, user: Principal, govde: dict, onceki: str | None = None) -> dict:
    para = str(govde.get("para_birimi") or "TRY").upper()
    if para not in PARA_BIRIMLERI:
        raise GelirHata(400, "Para birimi TRY, USD ya da EUR olmalı.")
    an = simdi()
    musteri = _metin(govde, "musteri", "Müşteri adı", 200, zorunlu=True)
    return {
        "customer_name": musteri,
        "project": _metin(govde, "proje", "Proje bilgisi", 200, zorunlu=True),
        "amount": _tutar(govde),
        "currency": para,
        "year": _tamsayi(govde, "yil", "Yıl", 2000, 2100, an.year),
        "month": _tamsayi(govde, "ay", "Ay", 1, 12, an.month),
        "tam_name": _tam(db, user, govde, musteri, onceki),
    }


def sms_ekle(db: Session, user: Principal, govde: dict) -> dict:
    return _ekle(db, user, SmsRevenue, _sms_alanlari(db, user, govde), _sms)


def sms_guncelle(db: Session, user: Principal, kayit_id: int, govde: dict) -> dict:
    return _guncelle(db, user, SmsRevenue, kayit_id, lambda onceki: _sms_alanlari(db, user, govde, onceki), _sms)


def sms_sil(db: Session, user: Principal, kayit_id: int) -> dict:
    return _sil(db, user, SmsRevenue, kayit_id)


# --- APN kurulum ------------------------------------------------------------------------------------
def _kurulum(uid: int, r: ApnRevenue) -> dict:
    return {
        "id": dis_kimlik(uid, r.id),
        "musteri": r.customer_name,
        "apn_adi": r.apn_name or "",
        "talep_tarihi": r.request_date.isoformat() if r.request_date else None,
        "teslim_tarihi": r.delivery_date.isoformat() if r.delivery_date else None,
        "tutar": r.amount,
        "tam": r.tam_name,
    }


def kurulum_liste(db: Session, user: Principal, yil: int | None = None) -> dict:
    tumu = [x for x in _topla(db, user, ApnRevenue) if not yil or (x[1].request_date and x[1].request_date.year == yil)]
    satirlar = sorted(tumu, key=lambda x: (x[1].request_date or date.min, x[1].id), reverse=True)[:EN_COK_KAYIT]
    teslim = sum(1 for _, r in satirlar if r.delivery_date)
    return {"items": [_kurulum(u, r) for u, r in satirlar], "toplam": round(sum(r.amount or 0 for _, r in satirlar), 2), "teslim_edilen": teslim, "bekleyen": len(satirlar) - teslim}


def _kurulum_alanlari(db: Session, user: Principal, govde: dict, onceki: str | None = None) -> dict:
    talep = _tarih(govde, "talep_tarihi", "Talep tarihi", zorunlu=True)
    teslim = _tarih(govde, "teslim_tarihi", "Teslim tarihi")
    if teslim and talep and teslim < talep:
        raise GelirHata(400, "Teslim tarihi talep tarihinden önce olamaz.")
    donem = teslim or talep or simdi().date()
    musteri = _metin(govde, "musteri", "Müşteri adı", 200, zorunlu=True)
    return {
        "customer_name": musteri,
        "apn_name": _metin(govde, "apn_adi", "APN adı", 200, zorunlu=True),
        "request_date": talep,
        "delivery_date": teslim,
        "amount": _tutar(govde, "tutar", "Gelir (TL)"),
        "currency": "TRY",
        "year": donem.year,
        "month": donem.month,
        "tam_name": _tam(db, user, govde, musteri, onceki),
    }


def kurulum_ekle(db: Session, user: Principal, govde: dict) -> dict:
    return _ekle(db, user, ApnRevenue, _kurulum_alanlari(db, user, govde), _kurulum)


def kurulum_guncelle(db: Session, user: Principal, kayit_id: int, govde: dict) -> dict:
    return _guncelle(db, user, ApnRevenue, kayit_id, lambda onceki: _kurulum_alanlari(db, user, govde, onceki), _kurulum)


def kurulum_sil(db: Session, user: Principal, kayit_id: int) -> dict:
    return _sil(db, user, ApnRevenue, kayit_id)


# --- APN musteri calismalari --------------------------------------------------------------------------
def _calisma(uid: int, r: ApnWork) -> dict:
    return {
        "id": dis_kimlik(uid, r.id),
        "musteri": r.customer_name,
        "toplanti_konusu": r.meeting_subject,
        "toplanti_tarihi": r.meeting_date.isoformat() if r.meeting_date else None,
        "planli_tarih": r.planned_date.isoformat() if r.planned_date else None,
        "apn_adi": r.apn_name or "",
    }


def calisma_liste(db: Session, user: Principal) -> dict:
    satirlar = sorted(
        _topla(db, user, ApnWork), key=lambda x: (x[1].planned_date is None, x[1].planned_date or date.min, -(x[1].meeting_date or date.min).toordinal())
    )[:EN_COK_KAYIT]
    bugun = simdi().date()
    yaklasan = sum(1 for _, r in satirlar if r.planned_date and r.planned_date >= bugun)
    return {"items": [_calisma(u, r) for u, r in satirlar], "yaklasan": yaklasan}


def _calisma_alanlari(govde: dict) -> dict:
    toplanti = _tarih(govde, "toplanti_tarihi", "Toplantı tarihi", zorunlu=True)
    planli = _tarih(govde, "planli_tarih", "Planlı çalışma tarihi")
    if planli and toplanti and planli < toplanti:
        raise GelirHata(400, "Planlı çalışma tarihi toplantı tarihinden önce olamaz.")
    return {
        "customer_name": _metin(govde, "musteri", "Müşteri", 200, zorunlu=True),
        "meeting_subject": _metin(govde, "toplanti_konusu", "Toplantı konusu", 300, zorunlu=True),
        "meeting_date": toplanti,
        "planned_date": planli,
        "apn_name": _metin(govde, "apn_adi", "APN adı", 200),
    }


def calisma_ekle(db: Session, user: Principal, govde: dict) -> dict:
    return _ekle(db, user, ApnWork, _calisma_alanlari(govde), _calisma)


def calisma_guncelle(db: Session, user: Principal, kayit_id: int, govde: dict) -> dict:
    return _guncelle(db, user, ApnWork, kayit_id, lambda _onceki: _calisma_alanlari(govde), _calisma)


def calisma_sil(db: Session, user: Principal, kayit_id: int) -> dict:
    return _sil(db, user, ApnWork, kayit_id)


# --- musteri karti ve unvan degisikligi (musteri paketi kullanir) ---------------------------------------
def tum_gelirler(db: Session, model: Any) -> list[Any]:
    """Tum dosyalardaki gelir kayitlari (musteri kartinda unvana gore suzulur)."""
    cikti: list[Any] = []
    for _, k in mevcut_oturumlar(db.scalars(select(AppUser.username))):
        cikti += k.scalars(select(model)).all()
        k.expunge_all()
    return cikti


def unvan_tasi(db: Session, eski_anahtar: str, yeni_ad: str) -> None:
    """Gelirler musteriye UNVAN METNIYLE baglidir; yeniden adlandirmada her dosyada guncellenir."""
    for _, k in mevcut_oturumlar(db.scalars(select(AppUser.username))):
        for model in (SmsRevenue, ApnRevenue):
            for gelir in k.scalars(select(model)):
                if eslestirme_anahtari(gelir.customer_name or "") == eski_anahtar:
                    gelir.customer_name = yeni_ad
        k.commit()
