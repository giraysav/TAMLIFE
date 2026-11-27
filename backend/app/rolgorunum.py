# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Rol gorunumleri: rolun giris sayfasi ve eylem yetkileri.

Kullanici karari (2026-10-14): Yonetim alani (admin_only) disindaki her modul varsayilan olarak her personel (TeamMember) ve
yonetici (TeamMngr) tarafindan gorulur. Admin Rol Yonetimi'nde rol kaydindan modul cikarirsa o rol o modulu acamaz (etkin()). Ekleme, degistirme ve silme herkesin KENDI verisindedir (2026-10-19; toplu islemler admin)
(deps.require_veri_yazma, modullerin kendi uclari). Admin Rol Yonetimi'nde giris sayfasini ve ek yetkileri verir.
Veritabani okunamazsa yonetici olmayan kullanici kapali kalir (yalniz genel bakis ve profil).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.authz import is_admin
from app.catalog import MODULES
from app.kullanicilar import _profil_degeri, ad_soyad, tam_ad_uret
from app.models import AppUser, RoleView
from app.ortak import UygulamaHatasi, iso
from app.session import Principal

DUZENLENEBILIR = ("TeamMngr", "TeamMember")


@dataclass(frozen=True)
class Yetki:
    """Modul gorunumunun disindaki eylem yetkisi. Admin verir, admin her zaman hepsine sahiptir; diger roller icin varsayilan kapali.
    alan: Rol Yonetimi'nde yetkinin duzenlendigi ayri bolum ("sunum" = Ceyrek Sunum); bos ise rol kartindaki Ek yetkiler."""

    etiket: str
    etiket_en: str
    aciklama: str  # ne saglar (duz dil)
    aciklama_en: str
    nerede: str  # hangi ekranda kullanilir
    nerede_en: str
    alan: str = ""


SUNUM_YETKISI = "sunum.gonder"
TALEP_YETKISI = "talep.yonet"
UTILIZASYON_YETKISI = "utilizasyon.yonet"
YETKILER: dict[str, Yetki] = {
    SUNUM_YETKISI: Yetki(
        "Çeyrek sunumu yönet",
        "Manage the quarterly presentation",
        "Çeyrek sunumuna öğe gönderebilir, sabitleyebilir ya da kaldırabilir; sunuma kendiliğinden akacak modül ve raporları seçebilir.",
        "Can send, pin or remove presentation items and choose which modules and reports flow into the presentation automatically.",
        "TAM Takvim › grafik › “Çeyrek sunuma gönder”; Çeyrek Sunum sayfası; Rol Yönetimi › Çeyrek Sunum",
        "TAM Calendar › chart › “Send to quarterly presentation”; Quarterly Presentation page; Role Management › Quarterly Presentation",
    ),
    TALEP_YETKISI: Yetki(
        "Geliştirme taleplerini yönet",
        "Manage development requests",
        "Herkesin açtığı talepleri görür; durum, atanan kişi, hedef sürüm ve yönetici notunu değiştirebilir. Yöneticiler (TeamMngr) bu yetkiye zaten sahiptir.",
        "Sees everyone's requests and can change status, assignee, target version and the manager note. Managers (TeamMngr) already have it.",
        "Hesap menüsü › Geliştirme Talepleri › İş Listesi",
        "Account menu › Development Requests › Work list",
    ),
    UTILIZASYON_YETKISI: Yetki(
        "TAM Utilizasyon'u yönet",
        "Manage TAM Utilization",
        "Yönetim konsolunda YALNIZ TAM Utilizasyon bölümü açılır: final skor kriterleri, toplu atama, skor ağacı, ürün tutarları, skor talep kararları ve müşteri listesi (toplu ekleme / silme). Diğer yönetim bölümleri (veritabanı, roller, günlükler vb.) açılmaz.",
        "Opens ONLY the TAM Utilization section of the admin console: final score criteria, bulk assignment, score tree, product amounts, score request decisions and the customer list (bulk add / delete). Other admin sections (database, roles, logs, etc.) stay closed.",
        "Hesap menüsü › Yönetim konsolu › TAM Utilizasyon",
        "Account menu › Admin console › TAM Utilization",
        alan="utilizasyon",
    ),
}
ESKI_YETKILER = {"takvim.sunuma_gonder": SUNUM_YETKISI}  # 0004 tasir; tasinmamis kayit da okunur
ROL_ETIKET = {"admin": "Sistem Yöneticisi", "TeamMngr": "MANAGER", "TeamMember": "MEMBER"}  # 2026-11-12: KTS_TEAM_ADMIN / _MNGR / _MEMBER adlari
GIRIS_VARSAYILAN = "ozet"


class RolHata(UygulamaHatasi):
    """kod = HTTP durumu."""


@dataclass(frozen=True)
class Gorunum:
    izinli: frozenset[str] | None  # None = hepsi (admin)
    landing: str
    yetkiler: frozenset[str] = frozenset()  # eylem yetkileri; admin icin hepsi

    def yetkili_mi(self, yetki: str) -> bool:
        return yetki in self.yetkiler


def tum_kimlikler(yonetici_dahil: bool = False) -> list[str]:
    """Modul anahtarlari ve 'modul/alt' kimlikleri. admin_only moduller (Yonetim alani) yalniz yonetici_dahil ile gelir: admin gorunumu icindir, role verilemez."""
    sonuc: list[str] = []
    for m in MODULES:
        if m.admin_only and not yonetici_dahil:
            continue
        sonuc.append(m.key)
        sonuc.extend(f"{m.key}/{c.key}" for c in m.children)
    return sonuc


def varsayilan_moduller() -> list[str]:
    """Rol kaydi yoksa personel ve yoneticinin gordugu moduller: Yonetim alani disindaki hepsi."""
    return tum_kimlikler()


def etkin(db: Session, user: Principal) -> Gorunum:
    if is_admin(user):
        return Gorunum(None, GIRIS_VARSAYILAN, yetkiler=frozenset(YETKILER))
    if user.role not in DUZENLENEBILIR:
        return Gorunum(frozenset(), GIRIS_VARSAYILAN)
    try:
        satir = db.scalar(select(RoleView).where(RoleView.role == user.role))
    except SQLAlchemyError:
        return Gorunum(frozenset(), GIRIS_VARSAYILAN)
    gecerli = set(tum_kimlikler())
    moduller = list(satir.modules) if (satir and satir.modules is not None) else varsayilan_moduller()
    izinli = frozenset(k for k in moduller if k in gecerli)
    return Gorunum(izinli, GIRIS_VARSAYILAN, yetkiler=_gecerli_yetkiler(satir.permissions if satir else []) | _kisi_yetkileri(db, user))


def _kisi_yetkileri(db: Session, user: Principal) -> frozenset[str]:
    """Yoneticinin bu kisiye ozel verdigi ek yetkiler; rolden gelenlere eklenir. Okunamazsa ek yetki yok sayilir (kapali)."""
    try:
        ham = db.scalar(select(AppUser.permissions).where(func.lower(AppUser.username) == user.username.strip().lower()))
    except SQLAlchemyError:
        return frozenset()
    return _gecerli_yetkiler(ham)


def _gecerli_yetkiler(ham: object) -> frozenset[str]:
    if not isinstance(ham, list):
        return frozenset()
    return frozenset(y for y in (ESKI_YETKILER.get(k, k) for k in ham if isinstance(k, str)) if y in YETKILER)


def gorunumler(db: Session) -> list[dict]:
    """Admin ekrani: uc rolun kayitli/varsayilan gorunumu."""
    kayitlar = {r.role: r for r in db.scalars(select(RoleView))}
    evren = set(tum_kimlikler())
    cikti = [
        {
            "role": "admin",
            "label": ROL_ETIKET["admin"],
            "editable": False,
            "modules": tum_kimlikler(yonetici_dahil=True),
            "landing": GIRIS_VARSAYILAN,
            "permissions": list(YETKILER),
            "saved": False,
        }
    ]
    for rol in DUZENLENEBILIR:
        satir = kayitlar.get(rol)
        mods = [k for k in satir.modules if k in evren] if (satir and satir.modules is not None) else varsayilan_moduller()
        cikti.append(
            {
                "role": rol,
                "label": ROL_ETIKET[rol],
                "editable": True,
                "modules": mods,
                "landing": GIRIS_VARSAYILAN,
                "permissions": sorted(_gecerli_yetkiler(satir.permissions) if satir else []),
                "saved": satir is not None,
            }
        )
    return cikti


def kisiler(db: Session) -> list[dict]:
    """Rol ekraninin personel listesi: panelde kaydi olan etkin kisiler (AD ile giren ya da yoneticinin actigi) ve kisiye ozel yetkileri.
    Her satir kendi rolunun altinda gosterilir; Ceyrek Sunum yetkisi kisi bazinda buradan verilir."""
    satirlar = db.scalars(select(AppUser).where(AppUser.active.is_(True)).order_by(AppUser.display_name, AppUser.username))
    return [
        {
            "id": k.id,
            "username": k.username,
            "display_name": k.display_name or k.username,
            "first_name": ad_soyad(k)[0],
            "last_name": ad_soyad(k)[1],
            "role": k.role,
            "auth": "AD" if k.is_ad_user else ("Yerel" if k.password_hash else "—"),
            "ad_domain": k.ad_domain,
            "last_login_at": iso(k.last_login_at),
            "permissions": sorted(_gecerli_yetkiler(k.permissions)),
        }
        for k in satirlar
    ]


def kisi_yetkisi_kaydet(db: Session, kullanici_id: int, yetkiler: object) -> dict:
    """Kisiye ozel ek yetkiler (tam liste yazilir). Admin zaten hepsine sahiptir; pasif ya da olmayan kisiye verilmez."""
    if not isinstance(yetkiler, list) or len(yetkiler) > 50 or not all(isinstance(x, str) and x in YETKILER for x in yetkiler):
        raise RolHata(400, "Yetki listesi gecersiz.")
    satir = db.get(AppUser, kullanici_id)
    if satir is None or not satir.active:
        raise RolHata(404, "Personel bulunamadı veya pasif.")
    if satir.role == "admin":
        raise RolHata(400, "Admin zaten tüm yetkilere sahiptir.")
    satir.permissions = sorted(set(yetkiler))
    db.flush()
    return {"id": satir.id, "username": satir.username, "permissions": satir.permissions}


ATANABILIR_ROLLER = ("admin", "TeamMngr", "TeamMember")  # 2026-11-12 kullanici karari: admin rolu de Rol Yonetimi'nden verilebilir (AD girisinde KTS_TEAM_ADMIN eslesmesi yine sart)


def kisi_adi_kaydet(db: Session, kullanici_id: int, ad: object, soyad: object) -> dict:
    """Admin kisinin ad ve soyadini duzeltir; gorunen ad (Takvim, Ekip, sorumlu listeleri) 'Ad Soyad' olur. Ad bos olamaz."""
    try:
        yeni_ad, yeni_soyad = _profil_degeri("first_name", ad), _profil_degeri("last_name", soyad)
    except UygulamaHatasi as hata:
        raise RolHata(400, hata.mesaj) from hata
    if not yeni_ad:
        raise RolHata(400, "Ad boş olamaz.")
    satir = db.get(AppUser, kullanici_id)
    if satir is None or not satir.active:
        raise RolHata(404, "Personel bulunamadı veya pasif.")
    satir.first_name, satir.last_name = yeni_ad, yeni_soyad
    satir.display_name = " ".join(p for p in (yeni_ad, yeni_soyad) if p)
    db.flush()
    return {"id": satir.id, "username": satir.username, "display_name": satir.display_name, "first_name": yeni_ad, "last_name": yeni_soyad}


def kisi_rolu_kaydet(db: Session, yapan: Principal, kullanici_id: int, rol: object) -> dict:
    """Kisiye admin/Manager/Member rolu atar (yeni giren kisi rolsuz/Pending acilir, admin buradan verir). Kendi rolunu degistiremez (yonetimden dusmesin).
    Rol degisince kisinin acik oturumlari kapanir (yeniden giriste yeni rolle acilir); is_admin rolden turetilir."""
    if not isinstance(rol, str) or rol not in ATANABILIR_ROLLER:
        raise RolHata(400, "Rol gecersiz.")
    satir = db.get(AppUser, kullanici_id)
    if satir is None or not satir.active:
        raise RolHata(404, "Personel bulunamadı veya pasif.")
    if satir.username.strip().lower() == yapan.username.strip().lower():
        raise RolHata(400, "Kendi rolünüzü değiştiremezsiniz.")
    onceki = satir.role
    satir.role, satir.is_admin = rol, rol == "admin"
    db.flush()
    return {"id": satir.id, "username": satir.username, "role": rol, "onceki": onceki}


_KULLANICI_ADI = re.compile(r"^[a-z0-9][a-z0-9._-]{1,39}$")


def kisi_onceden_ekle(db: Session, kullanici_adi: object, rol: object, yetkiler: object = None) -> dict:
    """Henuz giris yapmamis kisiyi rolu (ve istenirse kisiye ozel yetkileriyle) onceden acar: ilk AD girisinde rolsuz beklemez, hazir gelir.
    AD kullanicisi olarak acilir (parolayi AD dogrular); kullanici adi tek bicime (kucuk harf) indirilir, ayni ad varsa 409."""
    ad = kullanici_adi.strip().lower() if isinstance(kullanici_adi, str) else ""
    if "\\" in ad:
        ad = ad.rsplit("\\", 1)[1]
    if not _KULLANICI_ADI.fullmatch(ad):
        raise RolHata(400, "Kullanıcı adı geçersiz (harf, rakam, nokta, tire, alt çizgi; en az 2 karakter).")
    if not isinstance(rol, str) or rol not in ATANABILIR_ROLLER:
        raise RolHata(400, "Rol gecersiz.")
    if yetkiler is not None and (not isinstance(yetkiler, list) or not all(isinstance(x, str) and x in YETKILER for x in yetkiler)):
        raise RolHata(400, "Yetki listesi gecersiz.")
    if db.scalar(select(AppUser.id).where(func.lower(AppUser.username) == ad)) is not None:
        raise RolHata(409, "Bu kullanıcı zaten kayıtlı.")
    satir = AppUser(username=ad, display_name=tam_ad_uret(ad), role=rol, is_admin=(rol == "admin"), active=True, is_ad_user=True, permissions=sorted(set(yetkiler or [])))
    db.add(satir)
    db.flush()
    return {"id": satir.id, "username": satir.username, "display_name": satir.display_name, "first_name": ad_soyad(satir)[0], "last_name": ad_soyad(satir)[1], "role": rol, "permissions": satir.permissions}


def yetki_katalogu() -> list[dict]:
    return [
        {"id": k, "label": y.etiket, "label_en": y.etiket_en, "description": y.aciklama, "description_en": y.aciklama_en, "where": y.nerede, "where_en": y.nerede_en, "area": y.alan}
        for k, y in YETKILER.items()
    ]


def katalog() -> list[dict]:
    return [
        {
            "id": m.key,
            "label": m.title,
            "label_en": m.title_en,
            "admin_only": m.admin_only,
            "children": [{"id": f"{m.key}/{c.key}", "label": c.title, "label_en": c.title_en} for c in m.children],
        }
        for m in MODULES
        if m.in_nav and not m.admin_only  # Yonetim alani role verilemez, listede de cikmaz
    ]


def kaydet(db: Session, rol: str, moduller: object, landing: object, actor: str, yetkiler: object = None) -> dict:
    if rol not in DUZENLENEBILIR:
        raise RolHata(404, "Rol duzenlenemez.")
    satir = db.scalar(select(RoleView).where(RoleView.role == rol))
    evren = set(tum_kimlikler())
    if moduller is not None:
        if not isinstance(moduller, list) or not all(isinstance(x, str) for x in moduller) or len(moduller) > 500:
            raise RolHata(400, "Modul listesi gecersiz.")
        temiz = sorted({k for k in moduller if k in evren}, key=tum_kimlikler().index)
    elif satir and satir.modules is not None:
        temiz = [k for k in satir.modules if k in evren]
    else:
        temiz = varsayilan_moduller()

    if landing is not None and not isinstance(landing, str):
        raise RolHata(400, "Giris sayfasi gecersiz.")
    landing = GIRIS_VARSAYILAN
    if yetkiler is not None and (not isinstance(yetkiler, list) or not all(isinstance(x, str) and x in YETKILER for x in yetkiler)):
        raise RolHata(400, "Yetki listesi gecersiz.")
    zaman = datetime.now(UTC)
    if satir is None:
        satir = RoleView(role=rol, modules=temiz, landing=landing, permissions=sorted(set(yetkiler or [])), updated_by=actor[:120], updated_at=zaman)
        db.add(satir)
    else:
        satir.modules, satir.landing, satir.updated_by, satir.updated_at = temiz, landing, actor[:120], zaman
        if yetkiler is not None:
            satir.permissions = sorted(set(yetkiler))
    db.flush()
    return {"role": rol, "modules": temiz, "landing": landing, "permissions": sorted(_gecerli_yetkiler(satir.permissions))}
