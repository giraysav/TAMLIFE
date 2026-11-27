# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""TopoMaker cizim kural seti (2026-11-24 kullanici: "cizme kural seti olusturalim; ONENT'ten alinan CMDB verilerinde CI Name kosulu
ekle, bu CI Name'ler icin nw_li gibi kural secme filtresi olsun").

Kural = CI adi oneki ('nw_li', 'nw_mbl', 'dc_' ...). Her CI EN UZUN eslesen oneke duser ('nw_li_cust_3g' tanimliysa 'nw_li'den
once gelir); hicbirine uymayan 'diger'. Envanter cizimi yalniz secili kurallardaki CI'lari cizer. Kural listesi ve her kuralin
varsayilan secimi genel ayardir (app_setting 'topoloji.ci_kurallari'); yalniz yonetici degistirir, herkes cizimde secimi
degistirebilir (kaydedilmez).
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSetting
from app.ortak import UygulamaHatasi, simdi

AYAR = "topoloji.ci_kurallari"
DIGER = "diger"
AZAMI_KURAL = 40
# 2026-11-24 envanter: aktif 95.961 CI'in onek dagilimindan (nw_li 36.9 bin, nw_mbl 22.6 bin, nw_cr 12.9 bin, nw_gw 9.5 bin, nw_ap 8.5 bin)
VARSAYILAN = (
    ("nw_li", "Hat / devre", True), ("nw_mbl", "Mobil yedek", True), ("nw_cr", "Kiralık devre / SDH", True),
    ("nw_gw", "CPE / gateway", True), ("nw_sdwan", "SD-WAN", True), ("nw_vg", "Ses gateway", True),
    ("nw_ap", "WiFi erişim noktası", True), ("nw_sw", "Switch", True), ("dbs_", "Yönetilen hizmet", True),
    ("dc_", "Veri merkezi", True), ("mss_", "Güvenlik", True), ("solcloud_", "Bulut yedekleme", True),
    ("df_", "Şehirlerarası güzergah", True),
)  # fmt: skip
_ONEK = re.compile(r"^[a-z0-9][a-z0-9_.\-]{1,39}$")


def onek_normal(onek: str) -> str:
    return "".join((onek or "").split()).lower()


def varsayilan() -> list[dict[str, Any]]:
    return [{"onek": o, "ad": a, "ciz": c} for o, a, c in VARSAYILAN]


def oku(db: Session) -> list[dict[str, Any]]:
    """[{'onek', 'ad', 'ciz'}] - kayit yoksa varsayilan."""
    k = db.get(AppSetting, AYAR)
    liste = (k.value or {}).get("kurallar") if k is not None and isinstance(k.value, dict) else None
    if not isinstance(liste, list):
        return varsayilan()
    return [{"onek": str(x.get("onek", "")), "ad": str(x.get("ad", "")), "ciz": bool(x.get("ciz", True))} for x in liste if isinstance(x, dict)]


def kaydet(db: Session, kurallar: list[dict[str, Any]], kullanici: str) -> list[dict[str, Any]]:
    """Kural setini dogrular ve yazar (commit cagiranda). Onek: kucuk harf, rakam, '_', '.', '-'; 2-40 karakter; tekrar yok."""
    temiz: list[dict[str, Any]] = []
    gorulen: set[str] = set()
    for x in kurallar[: AZAMI_KURAL + 1]:
        onek = onek_normal(str(x.get("onek", "")))
        ad = " ".join(str(x.get("ad", "")).split())[:40] or onek
        if not _ONEK.match(onek) or onek == DIGER:
            raise UygulamaHatasi(400, f"Geçersiz CI adı öneki: '{onek}' (harf, rakam, _ . -; 2-40 karakter).")
        if onek in gorulen:
            continue
        gorulen.add(onek)
        temiz.append({"onek": onek, "ad": ad, "ciz": bool(x.get("ciz", True))})
    if len(temiz) > AZAMI_KURAL:
        raise UygulamaHatasi(400, f"En fazla {AZAMI_KURAL} kural tanımlanabilir.")
    k = db.get(AppSetting, AYAR)
    if k is None:
        db.add(AppSetting(key=AYAR, value={"kurallar": temiz}, updated_by=kullanici[:120], updated_at=simdi()))
    else:
        k.value, k.updated_by, k.updated_at = {"kurallar": temiz}, kullanici[:120], simdi()
    return temiz


def sinifla(ci_adi: str, onekler: list[str]) -> str:
    """CI adinin dustugu kural oneki (en uzun eslesen) ya da 'diger'. onekler uzundan kisaya sirali verilmeli."""
    ad = onek_normal(ci_adi)
    return next((o for o in onekler if ad.startswith(o)), DIGER)


def secim_coz(secim: str | None, kurallar: list[dict[str, Any]]) -> set[str]:
    """Istekteki 'kural' parametresi: None/'' = varsayilan (ciz=True olanlar + diger), '-' = hicbiri, 'a,b' = liste."""
    if not secim:
        return {k["onek"] for k in kurallar if k["ciz"]} | {DIGER}
    if secim.strip() == "-":
        return set()
    return {onek_normal(p) for p in secim.split(",") if onek_normal(p)}
