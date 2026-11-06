"""Rol gorunumu uclari: rolun giris sayfasi ve eylem yetkileri (moduller herkese acik). Okuma ve yazma: yalniz admin (Yonetim alani)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import kullanicilar
from app.audit import audit_log
from app.db import get_db
from app.deps import require_admin
from app.models import AppUser
from app.ortak import KimlikTipi, ok
from app.rolgorunum import (
    gorunumler,
    katalog,
    kaydet,
    kisi_adi_kaydet,
    kisi_onceden_ekle,
    kisi_rolu_kaydet,
    kisi_yetkisi_kaydet,
    kisiler,
    yetki_katalogu,
)
from app.session import Principal, kullanici_oturumlarini_kapat

router = APIRouter(prefix="/api/v1/roller", tags=["roller"])


class RolGovde(BaseModel):
    modules: list[str] | None = Field(default=None, max_length=500)  # 2026-10-14: yok sayilir, her modul personele ve yoneticiye acik
    landing: str | None = Field(default=None, max_length=80)  # 2026-10-14: yok sayilir, herkes Genel Bakis'la acar
    permissions: list[str] | None = Field(default=None, max_length=50)  # bos birakilirsa mevcut eylem yetkileri korunur


@router.get("")
def roller(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    izin = kullanicilar.silebilir_mi(admin)
    # `deletable`: bu oturum o kisiyi silebilir mi (yalniz silme yetkilisi hesap; kendini silemez). Arayuz dugmeyi buna gore gosterir, sunucu yine zorlar.
    # `self`: oturum sahibinin kendi satiri (kendi rolu degistirilemez, silinemez).
    kisi_listesi = [{**k, "deletable": izin and k["username"].strip().lower() != admin.username.strip().lower(), "self": k["username"].strip().lower() == admin.username.strip().lower()} for k in kisiler(db)]
    return ok(
        {
            "roles": gorunumler(db),
            "catalog": katalog(),
            "permission_catalog": yetki_katalogu(),
            "users": kisi_listesi,
            "can_delete_users": izin,
            "delete_account": kullanicilar.silme_yetkilisi_ad(),
        }
    )

@router.put("/{rol}")
def roller_kaydet(rol: str, body: RolGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    sonuc = kaydet(db, rol, body.modules, body.landing, admin.username, body.permissions)
    db.commit()
    audit_log.remember(
        actor=admin.username,
        action="roller.kaydet",
        outcome="allow",
        module_key="roller",
        detail=f"rol={rol} adet={len(sonuc['modules'])} giris={sonuc['landing']} yetki={','.join(sonuc['permissions'])}",
    )
    return ok(sonuc)


class KisiGovde(BaseModel):
    permissions: list[str] = Field(max_length=50)  # kisiye ozel ek yetkilerin TAM listesi (roldekilere eklenir)


@router.put("/kisiler/{kullanici_id}")
def kisi_yetkisi(kullanici_id: KimlikTipi, body: KisiGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    sonuc = kisi_yetkisi_kaydet(db, kullanici_id, body.permissions)
    db.commit()
    audit_log.remember(
        actor=admin.username,
        action="roller.kisi_yetki",
        outcome="allow",
        module_key="roller",
        detail=f"kisi={sonuc['username']} yetki={','.join(sonuc['permissions']) or '-'}",
    )
    return ok(sonuc)


class KisiRolGovde(BaseModel):
    role: str = Field(max_length=20)


class KisiEkleGovde(BaseModel):
    username: str = Field(max_length=80)
    role: str = Field(max_length=20)
    permissions: list[str] | None = Field(default=None, max_length=50)


@router.post("/kisiler")
def kisi_ekle(body: KisiEkleGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    """Giris yapmasi beklenen kisiyi onceden acar (rol + istege bagli ek yetki); kisi ilk AD girisinde hazir gelir."""
    sonuc = kisi_onceden_ekle(db, body.username, body.role, body.permissions)
    db.commit()
    audit_log.remember(actor=admin.username, action="roller.kisi_ekle", outcome="allow", module_key="roller", detail=f"kisi={sonuc['username']} rol={sonuc['role']} yetki={','.join(sonuc['permissions']) or '-'}")
    return ok(sonuc)


class KisiAdGovde(BaseModel):
    first_name: str = Field(max_length=200)
    last_name: str = Field(default="", max_length=200)


@router.put("/kisiler/{kullanici_id}/ad")
def kisi_adi(kullanici_id: KimlikTipi, body: KisiAdGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    onceki = db.get(AppUser, kullanici_id)
    eski = (onceki.display_name or onceki.username) if onceki is not None else "-"
    sonuc = kisi_adi_kaydet(db, kullanici_id, body.first_name, body.last_name)
    db.commit()
    audit_log.remember(actor=admin.username, action="roller.kisi_ad", outcome="allow", module_key="roller", detail=f"kisi={sonuc['username']} ad='{eski}'->'{sonuc['display_name']}'")
    return ok(sonuc)


@router.put("/kisiler/{kullanici_id}/rol")
def kisi_rolu(kullanici_id: KimlikTipi, body: KisiRolGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    sonuc = kisi_rolu_kaydet(db, admin, kullanici_id, body.role)
    db.commit()
    kapanan = kullanici_oturumlarini_kapat(sonuc["username"]) if sonuc["onceki"] != sonuc["role"] else 0
    audit_log.remember(
        actor=admin.username,
        action="roller.kisi_rol",
        outcome="allow",
        module_key="roller",
        detail=f"kisi={sonuc['username']} rol={sonuc['onceki']}->{sonuc['role']} oturum={kapanan}",
    )
    return ok({"id": sonuc["id"], "username": sonuc["username"], "role": sonuc["role"]})


@router.delete("/kisiler/{kullanici_id}")
def kisi_sil(kullanici_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    """Panel kullanicisini siler. Yonetim alani zaten admin'e ozel; silme ayrica YALNIZ silme yetkilisi hesaba acik (admin rolu yetmez)."""
    try:
        sonuc = kullanicilar.sil(db, admin, kullanici_id)
    except kullanicilar.SilmeHata as hata:
        db.rollback()
        audit_log.remember(actor=admin.username, action="roller.kisi_sil", outcome="deny", module_key="roller", detail=f"hedef={kullanici_id} {hata.mesaj}")
        raise
    db.commit()
    kapanan = kullanici_oturumlarini_kapat(sonuc["username"])
    audit_log.remember(
        actor=admin.username,
        action="roller.kisi_sil",
        outcome="allow",
        module_key="roller",
        detail=f"kisi={sonuc['username']} devredilen={sonuc['devredilen']} bosaltilan={sonuc['bosaltilan']} silinen={sonuc['silinen']} oturum={kapanan}",
    )
    return ok(sonuc)
