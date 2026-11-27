# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Kisiye ozel gorunurluk (2026-10-26 kullanici karari: "panele login olan user sadece kendisine ait olan verileri gorecek; tek istisna:
Benim Yerim yalniz kullaniciya ozel, Raporlar'i herkes gorebilecek").

Kapsam: menunun "Benim Yerim" modulleri (navigation 'work': Musteri Yonetimi, Toptan, Baglantili Araclar, Onedesk, ICT SMS, APN,
TAM Takvim, Talep). "Raporlar" modulleri (Aylik Raporlar, Projeler, Gelir Faydasi, Ceyrek Sunum, Musteri Radar, Takvim Ozeti) ve
Genel Bakis herkese acik kalir (onlarin servisleri bu modulu kullanmaz).

Kim neyi gorur:
- admin ve TeamMngr: hepsini. TeamMngr'in ekibi = tum personel (ekip tablosu yok; tek TeamMngr, kullanici secimi "Admin + TeamMngr ekibi").
- yonetimli modulun sahibi (app_user.module_owner: tamsms, tamapn, toptan, baglantili): o modulun hepsini.
- digerleri (TeamMember): yalniz kendine ait olani. Kart: sorumlusu oldugu kart ya da catisinin sorumlusu oldugu istirak (yazma kurali
  musteri.servis.duzenleyebilir_mi ile ayni sahiplik). Kart verisi (Onedesk kayitlari, aylik rapor taslagi, topoloji) karta baglidir.
  ICT SMS / APN: kendi dosyasindaki (TAM'i oldugu) kayitlar. TAM Takvim ve Talep zaten kisiye ozeldi.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.authz import yonetici_mi
from app.kullanicilar import YONETIMLI_MODULLER, modul_sahibi
from app.models import AppUser, Customer
from app.session import Principal


def tumunu_gorur(db: Session, user: Principal, modul: str | None = None) -> bool:
    """Suzgecsiz gorme: admin / TeamMngr; `modul` yonetimli ise o modulun sahibi de."""
    if yonetici_mi(user):
        return True
    return bool(modul in YONETIMLI_MODULLER and modul_sahibi(db, user) == modul)


def kullanici_kimligi(db: Session, user: Principal) -> int | None:
    return db.scalar(select(AppUser.id).where(AppUser.username == user.username))


def kart_kosulu(uid: int | None):
    """Kisinin kartlari: sorumlusu oldugu kart ya da sorumlusu oldugu catinin istiraki. Kaydi olmayan kullanici hic kart gormez."""
    if uid is None:
        return Customer.id.is_(None)  # her zaman yanlis (id bos olamaz)
    return or_(Customer.owner_id == uid, Customer.parent_id.in_(select(Customer.id).where(Customer.owner_id == uid)))


def cati_kosulu(uid: int | None):
    """Portfoy catilari: sorumlusu oldugu cati ya da icinde sorumlusu oldugu istirak bulunan cati (yalniz cerceve olarak gorunur)."""
    if uid is None:
        return Customer.id.is_(None)
    return or_(Customer.owner_id == uid, Customer.id.in_(select(Customer.parent_id).where(Customer.owner_id == uid, Customer.parent_id.is_not(None))))


def kart_suzgeci(db: Session, user: Principal, alan: str):
    """Kart sorgusuna eklenecek kosul; None = suzgec yok. `alan`: musteri | toptan | baglantili (yonetimli alanda sahibi hepsini gorur)."""
    if tumunu_gorur(db, user, alan):
        return None
    return kart_kosulu(kullanici_kimligi(db, user))


def kart_gorur_mu(db: Session, user: Principal, musteri: Customer) -> bool:
    if tumunu_gorur(db, user, musteri.modul):
        return True
    uid = kullanici_kimligi(db, user)
    if uid is None:
        return False
    if musteri.owner_id == uid:
        return True
    ust = db.get(Customer, musteri.parent_id) if musteri.parent_id else None
    return bool(ust and ust.owner_id == uid)


def kart_kimlikleri(db: Session, user: Principal, alan: str) -> list[int] | None:
    """Gorulebilen kart kimlikleri (secili alanda); None = hepsi. Onedesk gibi karta bagli kayit sorgulari icin."""
    kosul = kart_suzgeci(db, user, alan)
    if kosul is None:
        return None
    return list(db.scalars(select(Customer.id).where(kosul)))


def kapsam_anahtari(db: Session, user: Principal, alan: str) -> str:
    """Onbellek anahtari parcasi: herkese ayni sonuc ('hepsi') ya da kisinin kendi sonucu."""
    return "hepsi" if tumunu_gorur(db, user, alan) else f"kisi:{kullanici_kimligi(db, user)}"
