"""Rol gorunumleri: hangi rol hangi modul/alt modulu gorur ve hangi sayfayla acilir.

Admin her sey icin yetki verir (admin ekraninda Rol Yonetimi). Admin her zaman tum sayfalari gorur.
Kayit yoksa varsayilan: butun moduller (TAM Utilizasyon ve Rol Yonetimi dahil), giris sayfasi 'ozet'.
Veritabani okunamazsa yonetici olmayan kullanici kapali kalir (yalniz genel bakis ve profil).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.authz import is_admin
from app.catalog import MODULES
from app.models import AppUser, RoleView
from app.ortak import UygulamaHatasi, iso
from app.session import Principal

DUZENLENEBILIR = ("TeamMngr", "TeamMember")


@dataclass(frozen=True)
class Yetki:
    """Modul gorunumunun disindaki eylem yetkisi. Admin verir, admin her zaman hepsine sahiptir; diger roller icin varsayilan kapali.
    alan: Rol Yonetimi'nde yetkinin duzenlendigi ayri bolum ("sunum" = Ceyrek Bazli Sunum); bos ise rol kartindaki Ek yetkiler."""

    etiket: str
    etiket_en: str
    aciklama: str  # ne saglar (duz dil)
    aciklama_en: str
    nerede: str  # hangi ekranda kullanilir
    nerede_en: str
    alan: str = ""


SUNUM_YETKISI = "sunum.gonder"
TALEP_YETKISI = "talep.yonet"
YETKILER: dict[str, Yetki] = {
    SUNUM_YETKISI: Yetki(
        "Çeyrek bazlı sunumu yönet",
        "Manage the quarterly presentation",
        "Çeyrek sunumuna öğe gönderebilir, sabitleyebilir ya da kaldırabilir; sunuma kendiliğinden akacak modül ve raporları seçebilir.",
        "Can send, pin or remove presentation items and choose which modules and reports flow into the presentation automatically.",
        "TAM Takvim › grafik › “Çeyrek bazlı sunuma gönder”; Çeyrek Bazlı Sunum sayfası; Rol Yönetimi › Çeyrek Bazlı Sunum",
        "TAM Calendar › chart › “Send to quarterly presentation”; Quarterly Presentation page; Role Management › Quarterly Presentation",
        alan="sunum",
    ),
    TALEP_YETKISI: Yetki(
        "Geliştirme taleplerini yönet",
        "Manage development requests",
        "Herkesin açtığı talepleri görür; durum, atanan kişi, hedef sürüm ve yönetici notunu değiştirebilir. Yöneticiler (TeamMngr) bu yetkiye zaten sahiptir.",
        "Sees everyone's requests and can change status, assignee, target version and the manager note. Managers (TeamMngr) already have it.",
        "Hesap menüsü › Geliştirme Talepleri › İş Listesi",
        "Account menu › Development Requests › Work list",
    ),
}
ESKI_YETKILER = {"takvim.sunuma_gonder": SUNUM_YETKISI}  # 0004 tasir; tasinmamis kayit da okunur
ROL_ETIKET = {"admin": "Admin", "TeamMngr": "Manager", "TeamMember": "Member"}
GIRIS_VARSAYILAN = "ozet"


class RolHata(UygulamaHatasi):
    """kod = HTTP durumu."""


@dataclass(frozen=True)
class Gorunum:
    izinli: frozenset[str] | None  # None = hepsi (admin)
    landing: str
    guvenli_kapali: bool = False
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
    return tum_kimlikler()


def _rol_icin(rol: str, kimlikler: list[str]) -> list[str]:
    """personel_only moduller (kisisel takvim) yalniz TeamMember'a verilir; TeamMngr kaydinda varsa dusurulur."""
    if rol == "TeamMember":
        return kimlikler
    kapali = {m.key for m in MODULES if m.personel_only}
    return [k for k in kimlikler if k.split("/")[0] not in kapali]


def etkin(db: Session, user: Principal) -> Gorunum:
    if is_admin(user):
        return Gorunum(None, GIRIS_VARSAYILAN, yetkiler=frozenset(YETKILER))
    if user.role not in DUZENLENEBILIR:
        return Gorunum(frozenset(), GIRIS_VARSAYILAN, guvenli_kapali=True)
    try:
        satir = db.scalar(select(RoleView).where(RoleView.role == user.role))
    except SQLAlchemyError:
        return Gorunum(frozenset(), GIRIS_VARSAYILAN, guvenli_kapali=True)
    moduller = list(satir.modules) if satir else varsayilan_moduller()
    gecerli = set(tum_kimlikler())  # admin_only (Yonetim) kimlikleri eski kayitta olsa bile role acilmaz
    izinli = frozenset(k for k in moduller if k in gecerli)
    landing = satir.landing if satir and (satir.landing == GIRIS_VARSAYILAN or satir.landing in izinli) else GIRIS_VARSAYILAN
    return Gorunum(izinli, landing, yetkiler=_gecerli_yetkiler(satir.permissions if satir else []) | _kisi_yetkileri(db, user))


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
        cikti.append(
            {
                "role": rol,
                "label": ROL_ETIKET[rol],
                "editable": True,
                "modules": _rol_icin(rol, [k for k in satir.modules if k in evren] if satir else varsayilan_moduller()),
                "landing": satir.landing if satir else GIRIS_VARSAYILAN,
                "permissions": sorted(_gecerli_yetkiler(satir.permissions) if satir else []),
                "saved": satir is not None,
            }
        )
    return cikti


def kisiler(db: Session) -> list[dict]:
    """Rol ekraninin personel listesi: panelde kaydi olan etkin kisiler (AD ile giren ya da yoneticinin actigi) ve kisiye ozel yetkileri.
    Her satir kendi rolunun altinda gosterilir; Ceyrek Bazli Sunum yetkisi kisi bazinda buradan verilir."""
    satirlar = db.scalars(select(AppUser).where(AppUser.active.is_(True)).order_by(AppUser.display_name, AppUser.username))
    return [
        {
            "id": k.id,
            "username": k.username,
            "display_name": k.display_name or k.username,
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
            "personel_only": m.personel_only,
            "children": [{"id": f"{m.key}/{c.key}", "label": c.title, "label_en": c.title_en} for c in m.children],
        }
        for m in MODULES
        if m.in_nav and not m.admin_only  # Yonetim alani role verilemez, listede de cikmaz
    ]


def kaydet(db: Session, rol: str, moduller: object, landing: object, actor: str, yetkiler: object = None) -> dict:
    """yetkiler=None: mevcut eylem yetkileri korunur (eski istemciler)."""
    if rol not in DUZENLENEBILIR:
        raise RolHata(404, "Rol duzenlenemez.")
    if not isinstance(moduller, list) or not all(isinstance(x, str) for x in moduller) or len(moduller) > 500:
        raise RolHata(400, "Modul listesi gecersiz.")
    evren = set(tum_kimlikler())
    if any(k not in evren for k in moduller):
        raise RolHata(400, "Gecersiz modul.")  # admin_only (Yonetim) kimlikleri de buraya duser
    temiz = _rol_icin(rol, sorted(set(moduller), key=tum_kimlikler().index))
    if not isinstance(landing, str) or (landing != GIRIS_VARSAYILAN and landing not in temiz):
        raise RolHata(400, "Giris sayfasi verilen modullerden biri olmali.")
    if yetkiler is not None and (not isinstance(yetkiler, list) or not all(isinstance(x, str) and x in YETKILER for x in yetkiler)):
        raise RolHata(400, "Yetki listesi gecersiz.")
    satir = db.scalar(select(RoleView).where(RoleView.role == rol))
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
