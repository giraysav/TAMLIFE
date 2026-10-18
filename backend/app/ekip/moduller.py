"""Genel Bakis > Ekip Ozeti modul kutucuklari (2026-10-14 kullanici istegi: "panelde her modulun ve icerdigi verinin ozeti olmali").

Kullanicinin menusundeki moduller icin tek kutu: bir ana sayi + kisa alt satir; tiklaninca modul acilir. Yonetim alanlari yok.
OZETTE_YOK modulleri karo acmaz (kullanici 2026-10-14 13:36Z cikardi: Izin&Takvim, ICT SMS, APN, Ceyrek Sunum, Baglantili Araclar, Toptan).
Kapsam modulun kendi kuralidir:
  - kisiye bagli veri (musteri, rapor, proje, Onedesk acik kayitlari, TAM Takvim toplantilari) Ekip Ozeti satirlarindan gelir:
    yonetici tum ekip, TeamMember yalniz kendisi;
  - ekip geneli moduller (Gelir Faydasi, Talepler, Radar): Gelir Faydasi sunumdaki ozetin bu yildaki ilk degerleridir
    (sunum/servis kaynak fonksiyonu; tek hesap, ayni sayi iki yerde farkli cikmaz).
Bir modulun ozeti hata verirse kutu "—" gosterir ve uygulama gunlugune yazilir; Genel Bakis acilmaya devam eder.
Sayilar uydurulmaz: veri yoksa deger None, arayuz "—" yazar.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import get as modul
from app.dil import m
from app.models import Customer, Demand
from app.navigation import PRESENTATION, navigation_for
from app.radar.servis import adaylar as radar_adaylari
from app.rolgorunum import etkin
from app.session import Principal

log = logging.getLogger(__name__)

KAPALI_TALEP = ("tamamlandi", "reddedildi")
OZETTE_YOK = frozenset({"takvim", "tamsms", "tamapn", "sunum", "baglantili", "toptan"})


def _kutu(anahtar: str, deger: object, alt: str = "", ton: str = "mavi") -> dict:
    k = modul(anahtar)
    return {
        "id": anahtar,
        "ad": m(k.title, k.title_en or k.title),
        "ikon": PRESENTATION.get(anahtar, ("", "", "", ""))[1],
        "deger": deger,
        "alt": alt,
        "ton": ton,
    }


def _toplam(satirlar: list[dict], alan: str) -> int:
    return sum(s[alan] or 0 for s in satirlar)


def _kpi_degeri(kaynak: dict, sira: int) -> object:
    kpi = kaynak.get("kpi") or []
    return kpi[sira]["deger"] if len(kpi) > sira else None


def _ekip_geneli(db: Session, yil: int) -> dict[str, Callable[[], dict]]:
    """Sunum kaynaklarindan tum yilin ozeti (gec import: sunum ekip modulunu bilmez, dongu yok)."""
    from app.sunum import servis as sunum

    ceyrek = 0
    donem = sunum.donem_adi(yil, ceyrek)

    def gelir_uretim() -> dict:
        v = sunum.KAYNAKLAR["gelir_uretim"].uret(db, yil, ceyrek)
        return {
            "deger": _kpi_degeri(v, 0),
            "alt": m(f"{donem} · {_kpi_degeri(v, 1)} tamamlandı", f"{donem} · {_kpi_degeri(v, 1)} completed"),
        }

    def radar() -> dict:
        v = radar_adaylari(db)
        if not v["var"]:
            return {"deger": None, "alt": m("ReportDB verisi yok", "No ReportDB data")}
        alarm = sum(s["toplam"] for s in v["satirlar"])
        return {"deger": len(v["satirlar"]), "alt": m(f"aday · {alarm} alarm", f"candidates · {alarm} alarms")}

    def talep() -> dict:
        durumlar = list(db.scalars(select(Demand.status)))
        acik = sum(1 for d in durumlar if d not in KAPALI_TALEP)
        return {"deger": acik, "alt": m(f"açık · toplam {len(durumlar)}", f"open · {len(durumlar)} in total")}

    return {"gelir_uretim": gelir_uretim, "radar": radar, "talep": talep}


def modul_ozetleri(db: Session, user: Principal, satirlar: list[dict], yil: int) -> list[dict]:
    """Kullanicinin menusundeki moduller sirasiyla (Yonetim, yalniz-admin ve OZETTE_YOK haric) birer kutu."""
    menude = [
        str(o["id"])
        for o in navigation_for(user, etkin(db, user).izinli)
        if o["id"] != "yonetim" and o["id"] not in OZETTE_YOK and not modul(str(o["id"])).admin_only
    ]
    cati = _toplam(satirlar, "musteri")
    istirak = None
    if "musteri" in menude:
        sahipler = {s["id"] for s in satirlar}
        istirak = sum(1 for (o,) in db.execute(select(Customer.owner_id).where(Customer.parent_id.is_not(None))) if o in sahipler)
    alarm, sikayet, talep_ = _toplam(satirlar, "alarm"), _toplam(satirlar, "sikayet"), _toplam(satirlar, "talep")
    atilan, beklenen = _toplam(satirlar, "rapor_atilan"), _toplam(satirlar, "rapor_beklenen")
    online, yuzyuze = _toplam(satirlar, "online"), _toplam(satirlar, "yuzyuze")
    acik_proje = _toplam(satirlar, "proje_acik")
    onemli = sum(len(s["onemli_isler"]) for s in satirlar)
    musteri_alt = m(f"çatı · {istirak} iştirak", f"parent · {istirak} affiliates")

    yerel: dict[str, Callable[[], dict]] = {
        "musteri": lambda: {"deger": cati, "alt": musteri_alt},
        "onedesk": lambda: {
            "deger": alarm + sikayet + talep_,
            "alt": m(
                f"açık: {alarm} alarm · {sikayet} şikayet · {talep_} talep",
                f"open: {alarm} alarms · {sikayet} complaints · {talep_} requests",
            ),
            "ton": "kirmizi" if alarm + sikayet else "mavi",
        },
        "rapor": lambda: {
            "deger": f"{atilan}/{beklenen}" if beklenen else None,
            "alt": m(
                f"{yil} raporları · %{round(100 * atilan / beklenen)} uyum", f"{yil} reports · {round(100 * atilan / beklenen)}% compliance"
            )
            if beklenen
            else m("rapor birimi yok", "no report units"),
        },
        "proje": lambda: {"deger": acik_proje, "alt": m(f"açık · {onemli} yüksek/kritik", f"open · {onemli} high/critical"), "ton": "sari"},
        "takvim_ozet": lambda: {
            "deger": online + yuzyuze,
            "alt": m(f"{yil} · {online} online · {yuzyuze} yüz yüze", f"{yil} · {online} online · {yuzyuze} in person"),
        },
    }
    hesap = {**_ekip_geneli(db, yil), **yerel}

    kutular = []
    for anahtar in menude:
        uret = hesap.get(anahtar)
        if uret is None:
            continue
        try:
            kutular.append(_kutu(anahtar, **uret()))
        except Exception:  # bir modulun ozeti Genel Bakis'i dusurmesin
            log.exception("ekip ozeti modul kutusu hesaplanamadi: %s", anahtar)
            kutular.append(_kutu(anahtar, None, m("özet alınamadı", "summary unavailable")))
    return kutular
