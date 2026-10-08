"""ICT SMS gelirleri, APN kurulum gelirleri ve APN musteri calismalari.

Gorunurluk (uretim ad_benim): admin ve Manager tum kayitlari; Member yalniz kendi olusturdugu ya da TAM adi kendisi olan kayitlari
gorur ve degistirir. Tutarlar: SMS icin TRY/USD/EUR, APN kurulum icin TL.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from sqlalchemy import extract, or_, select
from sqlalchemy.orm import Session

from app.kullanicilar import kullanici_kaydi
from app.models import ApnRevenue, ApnWork, Customer, SmsRevenue
from app.ortak import UygulamaHatasi, simdi
from app.session import Principal

PARA_BIRIMLERI = ("TRY", "USD", "EUR")
EN_COK_KAYIT = 2000
EN_BUYUK_TUTAR = 1e13
_TARIH_TR = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_BIN_AYRACLI = re.compile(r"^\d{1,3}(\.\d{3})+$")


class GelirHata(UygulamaHatasi):
    """kod = HTTP durumu."""


def yonetici_mi(user: Principal) -> bool:
    return bool(user.is_admin or user.role in {"admin", "TeamMngr"})


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
        return date(int(tr.group(3)), int(tr.group(2)), int(tr.group(1))) if tr else datetime.strptime(metin[:10], "%Y-%m-%d").date()  # noqa: DTZ007
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


# --- gorunurluk -------------------------------------------------------------------------------------
def _ben(db: Session, user: Principal) -> tuple[str, str]:
    kisi = kullanici_kaydi(db, user)
    return user.username, kisi.display_name or user.username


def _kapsam(db: Session, user: Principal, model: Any):
    """Member icin satir kosulu (None = kisit yok). TAM adi ya da olusturan kendisi."""
    if yonetici_mi(user):
        return None
    kullanici, ad = _ben(db, user)
    kosul = [model.created_by == kullanici]
    if hasattr(model, "tam_name"):
        kosul.append(model.tam_name == ad)
    return or_(*kosul)


def _erisilebilir(db: Session, user: Principal, kayit: Any) -> bool:
    if yonetici_mi(user):
        return True
    kullanici, ad = _ben(db, user)
    return kayit.created_by == kullanici or getattr(kayit, "tam_name", None) == ad


def _getir(db: Session, user: Principal, model: Any, kayit_id: int) -> Any:
    kayit = db.get(model, kayit_id)
    if kayit is None or not _erisilebilir(db, user, kayit):
        raise GelirHata(404, "Kayıt bulunamadı.")  # varligi sizdirilmaz
    return kayit


def musteri_adlari(db: Session, user: Principal) -> list[str]:
    """Form onerileri: kullanicinin gorebildigi musteri unvanlari."""
    sorgu = select(Customer.name)
    if not yonetici_mi(user):
        uid = kullanici_kaydi(db, user).id
        benim = select(Customer.id).where(Customer.owner_id == uid)
        sorgu = sorgu.where(or_(Customer.owner_id == uid, Customer.parent_id.in_(benim)))
    return sorted({n for n in db.scalars(sorgu.order_by(Customer.name).limit(1000)) if n})


# --- ICT SMS ----------------------------------------------------------------------------------------
def _sms(r: SmsRevenue) -> dict:
    return {"id": r.id, "musteri": r.customer_name, "proje": r.project or "", "tutar": r.amount, "para_birimi": r.currency, "tam": r.tam_name, "yil": r.year, "ay": r.month}


def sms_liste(db: Session, user: Principal, yil: int | None = None) -> dict:
    sorgu = select(SmsRevenue)
    kosul = _kapsam(db, user, SmsRevenue)
    if kosul is not None:
        sorgu = sorgu.where(kosul)
    yillar = sorted({y for y in db.scalars(sorgu.with_only_columns(SmsRevenue.year).distinct())}, reverse=True)
    if yil:
        sorgu = sorgu.where(SmsRevenue.year == yil)
    satirlar = db.scalars(sorgu.order_by(SmsRevenue.year.desc(), SmsRevenue.month.desc(), SmsRevenue.customer_name).limit(EN_COK_KAYIT)).all()
    return {"items": [_sms(r) for r in satirlar], "toplam": _toplamlar((r.currency, r.amount) for r in satirlar), "yillar": yillar}


def _toplamlar(ciftler) -> dict[str, float]:
    t: dict[str, float] = defaultdict(float)
    for para, tutar in ciftler:
        t[para] += tutar or 0
    return {p: round(v, 2) for p, v in t.items()}


def _sms_alanlari(db: Session, user: Principal, govde: dict) -> dict:
    para = str(govde.get("para_birimi") or "TRY").upper()
    if para not in PARA_BIRIMLERI:
        raise GelirHata(400, "Para birimi TRY, USD ya da EUR olmalı.")
    an = simdi()
    alanlar = {
        "customer_name": _metin(govde, "musteri", "Müşteri adı", 200, zorunlu=True),
        "project": _metin(govde, "proje", "Proje bilgisi", 200, zorunlu=True),
        "amount": _tutar(govde),
        "currency": para,
        "year": _tamsayi(govde, "yil", "Yıl", 2000, 2100, an.year),
        "month": _tamsayi(govde, "ay", "Ay", 1, 12, an.month),
    }
    alanlar["tam_name"] = (_metin(govde, "tam", "TAM", 100) if yonetici_mi(user) else "") or _ben(db, user)[1][:100]
    return alanlar


def sms_ekle(db: Session, user: Principal, govde: dict) -> dict:
    kayit = SmsRevenue(**_sms_alanlari(db, user, govde), created_by=user.username[:100], created_at=simdi())
    db.add(kayit)
    db.flush()
    return _sms(kayit)


def sms_guncelle(db: Session, user: Principal, kayit_id: int, govde: dict) -> dict:
    kayit = _getir(db, user, SmsRevenue, kayit_id)
    for k, v in _sms_alanlari(db, user, govde).items():
        if k == "tam_name" and not yonetici_mi(user):
            continue  # Member TAM adini degistiremez
        setattr(kayit, k, v)
    db.flush()
    return _sms(kayit)


def sms_sil(db: Session, user: Principal, kayit_id: int) -> dict:
    db.delete(_getir(db, user, SmsRevenue, kayit_id))
    return {"silinen": kayit_id}


# --- APN kurulum ------------------------------------------------------------------------------------
def _kurulum(r: ApnRevenue) -> dict:
    return {
        "id": r.id,
        "musteri": r.customer_name,
        "apn_adi": r.apn_name or "",
        "talep_tarihi": r.request_date.isoformat() if r.request_date else None,
        "teslim_tarihi": r.delivery_date.isoformat() if r.delivery_date else None,
        "tutar": r.amount,
        "tam": r.tam_name,
    }


def kurulum_liste(db: Session, user: Principal, yil: int | None = None) -> dict:
    sorgu = select(ApnRevenue)
    kosul = _kapsam(db, user, ApnRevenue)
    if kosul is not None:
        sorgu = sorgu.where(kosul)
    if yil:
        sorgu = sorgu.where(extract("year", ApnRevenue.request_date) == yil)
    satirlar = db.scalars(sorgu.order_by(ApnRevenue.request_date.desc(), ApnRevenue.id.desc()).limit(EN_COK_KAYIT)).all()
    teslim = sum(1 for r in satirlar if r.delivery_date)
    return {"items": [_kurulum(r) for r in satirlar], "toplam": round(sum(r.amount or 0 for r in satirlar), 2), "teslim_edilen": teslim, "bekleyen": len(satirlar) - teslim}


def _kurulum_alanlari(db: Session, user: Principal, govde: dict) -> dict:
    talep = _tarih(govde, "talep_tarihi", "Talep tarihi", zorunlu=True)
    teslim = _tarih(govde, "teslim_tarihi", "Teslim tarihi")
    if teslim and talep and teslim < talep:
        raise GelirHata(400, "Teslim tarihi talep tarihinden önce olamaz.")
    donem = teslim or talep or simdi().date()
    alanlar = {
        "customer_name": _metin(govde, "musteri", "Müşteri adı", 200, zorunlu=True),
        "apn_name": _metin(govde, "apn_adi", "APN adı", 200, zorunlu=True),
        "request_date": talep,
        "delivery_date": teslim,
        "amount": _tutar(govde, "tutar", "Gelir (TL)"),
        "currency": "TRY",
        "year": donem.year,
        "month": donem.month,
    }
    alanlar["tam_name"] = (_metin(govde, "tam", "TAM", 100) if yonetici_mi(user) else "") or _ben(db, user)[1][:100]
    return alanlar


def kurulum_ekle(db: Session, user: Principal, govde: dict) -> dict:
    kayit = ApnRevenue(**_kurulum_alanlari(db, user, govde), created_by=user.username[:100], created_at=simdi())
    db.add(kayit)
    db.flush()
    return _kurulum(kayit)


def kurulum_guncelle(db: Session, user: Principal, kayit_id: int, govde: dict) -> dict:
    kayit = _getir(db, user, ApnRevenue, kayit_id)
    for k, v in _kurulum_alanlari(db, user, govde).items():
        if k == "tam_name" and not yonetici_mi(user):
            continue
        setattr(kayit, k, v)
    db.flush()
    return _kurulum(kayit)


def kurulum_sil(db: Session, user: Principal, kayit_id: int) -> dict:
    db.delete(_getir(db, user, ApnRevenue, kayit_id))
    return {"silinen": kayit_id}


# --- APN musteri calismalari --------------------------------------------------------------------------
def _calisma(r: ApnWork) -> dict:
    return {
        "id": r.id,
        "musteri": r.customer_name,
        "toplanti_konusu": r.meeting_subject,
        "toplanti_tarihi": r.meeting_date.isoformat() if r.meeting_date else None,
        "planli_tarih": r.planned_date.isoformat() if r.planned_date else None,
        "apn_adi": r.apn_name or "",
    }


def calisma_liste(db: Session, user: Principal) -> dict:
    sorgu = select(ApnWork)
    kosul = _kapsam(db, user, ApnWork)
    if kosul is not None:
        sorgu = sorgu.where(kosul)
    satirlar = db.scalars(sorgu.order_by(ApnWork.planned_date.is_(None), ApnWork.planned_date, ApnWork.meeting_date.desc()).limit(EN_COK_KAYIT)).all()
    bugun = simdi().date()
    yaklasan = sum(1 for r in satirlar if r.planned_date and r.planned_date >= bugun)
    return {"items": [_calisma(r) for r in satirlar], "yaklasan": yaklasan}


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
    kayit = ApnWork(**_calisma_alanlari(govde), created_by=user.username[:100], created_at=simdi())
    db.add(kayit)
    db.flush()
    return _calisma(kayit)


def calisma_guncelle(db: Session, user: Principal, kayit_id: int, govde: dict) -> dict:
    kayit = _getir(db, user, ApnWork, kayit_id)
    for k, v in _calisma_alanlari(govde).items():
        setattr(kayit, k, v)
    db.flush()
    return _calisma(kayit)


def calisma_sil(db: Session, user: Principal, kayit_id: int) -> dict:
    db.delete(_getir(db, user, ApnWork, kayit_id))
    return {"silinen": kayit_id}
