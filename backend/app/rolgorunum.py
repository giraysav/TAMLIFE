"""Rol gorunumleri: hangi rol hangi modul/alt modulu gorur ve hangi sayfayla acilir.

Admin her sey icin yetki verir (admin ekraninda Rol Yonetimi). Admin her zaman tum sayfalari gorur.
Kayit yoksa varsayilan: admin'e ozel olmayan butun moduller, giris sayfasi 'ozet'.
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
from app.session import Principal

DUZENLENEBILIR = ("TeamMngr", "TeamMember")
ROL_ETIKET = {"admin": "Admin", "TeamMngr": "Manager", "TeamMember": "Member"}
GIRIS_VARSAYILAN = "ozet"


class RolHata(Exception):
    def __init__(self, kod: int, mesaj: str) -> None:
        super().__init__(mesaj)
        self.kod = kod
        self.mesaj = mesaj


@dataclass(frozen=True)
class Gorunum:
    izinli: frozenset[str] | None  # None = hepsi (admin)
    landing: str
    guvenli_kapali: bool = False


def tum_kimlikler(yonetici_dahil: bool = False) -> list[str]:
    """Modul anahtarlari ve 'modul/alt' kimlikleri. Admin'e ozel olanlar yonetici_dahil ile gelir."""
    sonuc: list[str] = []
    for m in MODULES:
        if m.admin_only and not yonetici_dahil:
            continue
        sonuc.append(m.key)
        sonuc.extend(f"{m.key}/{c.key}" for c in m.children)
    return sonuc


def varsayilan_moduller() -> list[str]:
    return tum_kimlikler(yonetici_dahil=False)


def etkin(db: Session, user: Principal) -> Gorunum:
    if is_admin(user):
        return Gorunum(None, GIRIS_VARSAYILAN)
    if user.role not in DUZENLENEBILIR:
        return Gorunum(frozenset(), GIRIS_VARSAYILAN, guvenli_kapali=True)
    try:
        satir = db.scalar(select(RoleView).where(RoleView.role == user.role))
    except SQLAlchemyError:
        return Gorunum(frozenset(), GIRIS_VARSAYILAN, guvenli_kapali=True)
    moduller = list(satir.modules) if satir else varsayilan_moduller()
    gecerli = set(tum_kimlikler(yonetici_dahil=False))
    izinli = frozenset(k for k in moduller if k in gecerli)
    landing = satir.landing if satir and (satir.landing == GIRIS_VARSAYILAN or satir.landing in izinli) else GIRIS_VARSAYILAN
    return Gorunum(izinli, landing)


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
                "saved": satir is not None,
            }
        )
    return cikti


def katalog() -> list[dict]:
    return [
        {
            "id": m.key,
            "label": m.title,
            "admin_only": m.admin_only,
            "children": [{"id": f"{m.key}/{c.key}", "label": c.title} for c in m.children],
        }
        for m in MODULES
        if m.in_nav
    ]


def kaydet(db: Session, rol: str, moduller: object, landing: object, actor: str) -> dict:
    if rol not in DUZENLENEBILIR:
        raise RolHata(404, "Rol duzenlenemez.")
    if not isinstance(moduller, list) or not all(isinstance(x, str) for x in moduller) or len(moduller) > 500:
        raise RolHata(400, "Modul listesi gecersiz.")
    izinli_evren = set(tum_kimlikler(yonetici_dahil=False))
    yonetici_ozel = set(tum_kimlikler(yonetici_dahil=True)) - izinli_evren
    bilinmeyen = [k for k in moduller if k not in izinli_evren]
    if bilinmeyen:
        neden = "yalniz admin" if any(k in yonetici_ozel for k in bilinmeyen) else "bilinmeyen modul"
        raise RolHata(400, f"Gecersiz modul ({neden}).")
    temiz = sorted(set(moduller), key=tum_kimlikler(yonetici_dahil=True).index)
    if not isinstance(landing, str) or (landing != GIRIS_VARSAYILAN and landing not in temiz):
        raise RolHata(400, "Giris sayfasi verilen modullerden biri olmali.")
    satir = db.scalar(select(RoleView).where(RoleView.role == rol))
    zaman = datetime.now(UTC)
    if satir is None:
        satir = RoleView(role=rol, modules=temiz, landing=landing, updated_by=actor[:120], updated_at=zaman)
        db.add(satir)
    else:
        satir.modules, satir.landing, satir.updated_by, satir.updated_at = temiz, landing, actor[:120], zaman
    db.flush()
    return {"role": rol, "modules": temiz, "landing": landing}
