"""Rol gorunumu uclari: rolun gorecegi sayfalar ve giris sayfasi. Okuma ve yazma: yalniz admin (Yonetim alani)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import kullanicilar
from app.audit import audit_log
from app.db import get_db
from app.deps import require_admin
from app.ortak import KimlikTipi, ok
from app.rolgorunum import gorunumler, katalog, kaydet, kisi_yetkisi_kaydet, kisiler, yetki_katalogu
from app.session import Principal, kullanici_oturumlarini_kapat

router = APIRouter(prefix="/api/v1/roller", tags=["roller"])


class RolGovde(BaseModel):
    modules: list[str] = Field(max_length=500)
    landing: str = Field(max_length=80)
    permissions: list[str] | None = Field(default=None, max_length=50)  # bos birakilirsa mevcut eylem yetkileri korunur


@router.get("")
def roller(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    izin = kullanicilar.silebilir_mi(admin)
    # `deletable`: bu oturum o kisiyi silebilir mi (yalniz silme yetkilisi hesap; kendini silemez). Arayuz dugmeyi buna gore gosterir, sunucu yine zorlar.
    kisi_listesi = [{**k, "deletable": izin and k["username"].strip().lower() != admin.username.strip().lower()} for k in kisiler(db)]
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
