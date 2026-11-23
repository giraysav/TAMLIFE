"""Musteri eslesmesi (Veri Girisi > Musteri Eslesmesi, 2026-10-24 kullanici ilkesi: "DB'lerden aldigimiz her veri TAM personelindeki
atanmis musterilerle eslesmeli"). Yalniz okur; dis kaynaga baglanmaz.

Her kaynak icin: toplam kayit, karta eslesen, eslesen kartta TAM atanmis (kartin kendisi ya da catisi), kartsiz. Kartsiz TEMIP kayitlari
Radar'a duser (kart acilir ya da personele atanir); en cok kayit tasiyan kartsiz musteri numaralari ayrica listelenir.
Ozet agir (yuz binlerce kayit): bellekte ONBELLEK_SN ya da yeni kayit gelene kadar tutulur (CLAUDE.md: agir uc onbellek ister).
"""

from __future__ import annotations

import threading
import time
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app import musteri_alani
from app.gelir_uretim.models import RevenueBenefit
from app.models import Customer, OnedeskRecord, UrunTutarOzet
from app.ortak import eslestirme_anahtari, iso, simdi
from app.tampon import temip_kayit

ONBELLEK_SN = 120
KARTSIZ_ILK = 10
KAYNAK_ADI = {"temip": "TEMIP alarm kayıtları"}
_onbellek: dict[tuple, tuple[float, dict]] = {}
_kilit = threading.Lock()


def _oran(pay: int, payda: int) -> float | None:
    return round(100 * pay / payda, 1) if payda else None


def _satir(anahtar: str, ad: str, toplam: int, kartli: int, tamli: int, yer: str, not_: str = "") -> dict[str, Any]:
    return {"anahtar": anahtar, "ad": ad, "toplam": toplam, "karta_eslesen": kartli, "tam_atanmis": tamli, "kartsiz": toplam - kartli,
            "oran": _oran(tamli, toplam), "yer": yer, "not": not_}  # fmt: skip


def _tam_kosulu():
    """Kayit kartinin TAM'i: kartin kendi sorumlusu, yoksa catisinin (istirak catisindan devralir)."""
    cati = aliased(Customer)
    return cati, func.coalesce(Customer.owner_id, cati.owner_id).is_not(None)


@musteri_alani.tum_alanlarda  # kart eslesmesi modulden bagimsiz (Toptan / Baglantili kartlari da sayilir)
def _hesapla(db: Session) -> dict[str, Any]:
    cati, tamli = _tam_kosulu()
    kaynaklar: list[dict[str, Any]] = []

    # 1. Onedesk / TEMIP kayitlari (kaynak turune gore)
    for kaynak, toplam, kartli, tam in db.execute(
        select(
            OnedeskRecord.source,
            func.count(),
            func.count(OnedeskRecord.customer_id),
            func.sum(case((tamli, 1), else_=0)),
        )
        .select_from(OnedeskRecord)
        .outerjoin(Customer, Customer.id == OnedeskRecord.customer_id)
        .outerjoin(cati, cati.id == Customer.parent_id)
        .group_by(OnedeskRecord.source)
    ):
        ad = KAYNAK_ADI.get(kaynak or "", f"Onedesk kayıtları ({kaynak or 'kaynaksız'})")
        kaynaklar.append(_satir(f"onedesk:{kaynak or ''}", ad, toplam, kartli, int(tam or 0), "yonetim/tampon?sekme=akis",
                                "Kartsız kayıtlar Radar'da: kart açın ya da personele atayın."))  # fmt: skip

    # 2. Urun-Tutar ozetleri: her ozet bir karta bagli; dosyadaki eslesmeyen gruplar ayrica sayilir
    ut_toplam, ut_eslesmeyen = 0, 0
    for (ozet,) in db.execute(select(UrunTutarOzet.summary)):
        ut_toplam += 1
        ut_eslesmeyen += len((ozet or {}).get("eslesmeyen_gruplar") or [])
    ut_tamli = db.scalar(
        select(func.count()).select_from(UrunTutarOzet).join(Customer, Customer.id == UrunTutarOzet.customer_id)
        .outerjoin(cati, cati.id == Customer.parent_id).where(tamli)
    ) or 0  # fmt: skip
    satir = _satir("urun_tutar", "Ürün-Tutar Excel", ut_toplam + ut_eslesmeyen, ut_toplam, ut_tamli, "yonetim/tampon?sekme=import",
                   f"{ut_eslesmeyen} grup dosyada vardı ama hiçbir karta eşlenmedi." if ut_eslesmeyen else "")  # fmt: skip
    kaynaklar.append(satir)

    # 3. Gelir Faydasi: musteri SERBEST METIN (karta bagli degil); kart adiyla eslesen oran gosterilir
    kartlar = {eslestirme_anahtari(ad): tam for ad, tam in db.execute(
        select(Customer.name, func.coalesce(Customer.owner_id, cati.owner_id)).outerjoin(cati, cati.id == Customer.parent_id)
    ) if ad}  # fmt: skip
    gf_toplam = gf_kartli = gf_tamli = 0
    for (metin,) in db.execute(select(RevenueBenefit.customers)):
        gf_toplam += 1
        adlar = [eslestirme_anahtari(p) for p in (metin or "").replace(";", ",").split(",") if p.strip()]
        eslesen = [a for a in adlar if a in kartlar]
        if eslesen:
            gf_kartli += 1
            gf_tamli += 1 if any(kartlar[a] is not None for a in eslesen) else 0
    kaynaklar.append(_satir("gelir_uretim", "Gelir Faydası kayıtları", gf_toplam, gf_kartli, gf_tamli, "yonetim/tampon?sekme=import",
                            "Müşteri serbest metin; karta bağlantı yok, kart adıyla eşleşme sayıldı."))  # fmt: skip

    # 4. Kartlar: TAM atanmamis kart (kendi ve catisi bos) eslesen veriyi de sahipsiz birakir
    kart_toplam, kart_tamli = db.execute(
        select(func.count(), func.sum(case((tamli, 1), else_=0))).select_from(Customer).outerjoin(cati, cati.id == Customer.parent_id)
    ).one()
    kart_tamli = int(kart_tamli or 0)

    kartsiz = [
        {"musteri_no": no or "", "ad": ad or "", "adet": adet}
        for no, ad, adet in db.execute(
            select(OnedeskRecord.customer_no, func.max(OnedeskRecord.customer_label), func.count().label("adet"))
            .where(OnedeskRecord.customer_id.is_(None), OnedeskRecord.source == temip_kayit.KAYNAK_ADI)  # sikayet / talep yalniz kart + Radar numarasi
            .group_by(OnedeskRecord.customer_no)
            .order_by(func.count().desc())
            .limit(KARTSIZ_ILK)
        )
    ]
    return {
        "kaynaklar": kaynaklar,
        "kartlar": {"toplam": kart_toplam, "tam_atanmis": kart_tamli, "tam_siz": kart_toplam - kart_tamli},
        "kartsiz_ilk": kartsiz,
        "zaman": iso(simdi()),
    }


def ozet(db: Session) -> dict[str, Any]:
    # Surum: elle atama / TAM secimi (Fark) yazar; yeni kayit ve kart sayisi da onbellegi bozar
    anahtar = (str(db.get_bind().url), db.scalar(select(func.max(OnedeskRecord.id))), db.scalar(select(func.count()).select_from(Customer)),
               temip_kayit.surum(db))  # fmt: skip
    with _kilit:
        kayit = _onbellek.get(anahtar)
    if kayit is not None and time.monotonic() - kayit[0] < ONBELLEK_SN:
        return kayit[1]
    sonuc = _hesapla(db)
    with _kilit:
        if len(_onbellek) > 16:
            _onbellek.clear()
        _onbellek[anahtar] = (time.monotonic(), sonuc)
    return sonuc
