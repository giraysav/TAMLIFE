"""Rol gorunumleri: hangi rol hangi modul/alt modulu gorur ve hangi sayfayla acilir.

Admin her sey icin yetki verir (admin ekraninda Rol Yonetimi). Admin her zaman tum sayfalari gorur.
Kayit yoksa varsayilan: butun moduller (TAM Utilizasyon ve Rol Yonetimi dahil), giris sayfasi 'ozet'.
Veritabani okunamazsa yonetici olmayan kullanici kapali kalir (yalniz genel bakis ve profil).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.authz import is_admin
from app.catalog import MODULES
from app.models import RoleView
from app.ortak import UygulamaHatasi
from app.session import Principal

DUZENLENEBILIR = ("TeamMngr", "TeamMember")
# Modul gorunumunun disindaki eylem yetkileri: kimlik -> (etiket, etiket_en). Admin verir, admin her zaman hepsine sahiptir. Varsayilan: rol icin kapali.
YETKILER: dict[str, tuple[str, str]] = {
    "takvim.sunuma_gonder": ("TAM Takvim: çeyrek bazlı sunuma gönder", "TAM Calendar: send to quarterly presentation"),
}
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
    """Modul anahtarlari ve 'modul/alt' kimlikleri. admin_only moduller yonetici_dahil ile gelir (varsayilan olarak acik; yonetim sayfasi yine admin'e ozel)."""
    sonuc: list[str] = []
    for m in MODULES:
        if m.admin_only and not yonetici_dahil:
            continue
        sonuc.append(m.key)
        sonuc.extend(f"{m.key}/{c.key}" for c in m.children)
    return sonuc


def varsayilan_moduller() -> list[str]:
    return tum_kimlikler(yonetici_dahil=True)


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
    gecerli = set(tum_kimlikler(yonetici_dahil=True))
    izinli = frozenset(k for k in moduller if k in gecerli)
    landing = satir.landing if satir and (satir.landing == GIRIS_VARSAYILAN or satir.landing in izinli) else GIRIS_VARSAYILAN
    return Gorunum(izinli, landing, yetkiler=_gecerli_yetkiler(satir.permissions if satir else []))


def _gecerli_yetkiler(ham: object) -> frozenset[str]:
    return frozenset(k for k in ham if isinstance(k, str) and k in YETKILER) if isinstance(ham, list) else frozenset()


def gorunumler(db: Session) -> list[dict]:
    """Admin ekrani: uc rolun kayitli/varsayilan gorunumu."""
    kayitlar = {r.role: r for r in db.scalars(select(RoleView))}
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
                "modules": list(satir.modules) if satir else varsayilan_moduller(),
                "landing": satir.landing if satir else GIRIS_VARSAYILAN,
                "permissions": sorted(_gecerli_yetkiler(satir.permissions) if satir else []),
                "saved": satir is not None,
            }
        )
    return cikti


def yetki_katalogu() -> list[dict]:
    return [{"id": k, "label": tr, "label_en": en} for k, (tr, en) in YETKILER.items()]


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
        if m.in_nav
    ]


def kaydet(db: Session, rol: str, moduller: object, landing: object, actor: str, yetkiler: object = None) -> dict:
    """yetkiler=None: mevcut eylem yetkileri korunur (eski istemciler)."""
    if rol not in DUZENLENEBILIR:
        raise RolHata(404, "Rol duzenlenemez.")
    if not isinstance(moduller, list) or not all(isinstance(x, str) for x in moduller) or len(moduller) > 500:
        raise RolHata(400, "Modul listesi gecersiz.")
    evren = set(tum_kimlikler(yonetici_dahil=True))
    if any(k not in evren for k in moduller):
        raise RolHata(400, "Gecersiz modul.")
    temiz = sorted(set(moduller), key=tum_kimlikler(yonetici_dahil=True).index)
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
