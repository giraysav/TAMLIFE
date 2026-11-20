"""Gunluk utilizasyon turu (2026-11-21 kullanici): her sabah 06:00'da isci calisir, kapanmis kayitlarla skoru gunceller.

  "30 dk kodu cok yorar, utilizasyon skorunu dinamik hesaplamak icin sabaha karsi bir isci kur. Skor hesabi icin kapanmis kayitlari
   baz alacagimizdan anlik veri akisina gerek yok; durumu closed olmuslarla skor hesabi yapacagiz."

Tur (python -m app.isci utilizasyon; zamanlanmis gorev 06:00, kurulum\\canli_gorev_kur.ps1):
  Donem = SON 12 AY (bugunden geriye 365 gun; 2026-11-21 kullanici onayi, takvim yili Ocak'ta sifirlaniyordu).
  1) OneDesk  : donemde KAPANAN sikayet + talep, kart Musteri No'su basina (yalniz sayim, satir tasinmaz). Eski sistem
                elysion_customdata_fix.T_SOL_INCIDENT_TICKETS (TICKETTYPEID=1; TICKETSUBTYPEID 1=sikayet, 2=talep, 3=alarm -> alarm
                ALINMAZ: alarm ReportDB'den), STATUS='CLOSE', CLOSEDATE donemde. Yeni sistem elysion_soxdata_octopuscorp.
                T_OCT_CORPORATE_MAIN (TICKETTYPE_DESC Sikayet/Talep, STATUS Kapatildi; 2026-11-21 itibariyla tarih alanlari bos ->
                tarihsiz kapali kayit doneme sayilir).
  2) ReportDB : donemde kapanan alarm = panelde zaten olan TEMIP kayitlari (onedesk_record source=temip, 6 dk isci doldurur).
  3) ONENT    : aktif CI ve farkli kurumsal lokasyon sayisi = musteri envanteri (customer_ci, 4 saatte bir isci doldurur).
  4) util_source_summary bastan yazilir; cati musterilerin skoru yeniden hesaplanir ve DEGISENLERE yazilir (kaynak 'gunluk').
Skorda cati musterinin degeri = cati + istiraklerinin toplami. Bir kaynak okunamazsa o sutun bos (None) kalir; skor o kriter icin
kayitli secime (dokum) duser, mevcut deger korunur. Kaynak adlari yalniz Yonetim ekraninda gorunur.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, delete, func, insert, select
from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    Customer,
    CustomerCi,
    OnedeskRecord,
    UtilSourceSummary,
)
from app.ortak import iso, normal, simdi
from app.tampon import postgres
from app.tampon.eslestirme import musteri_anahtarlari

ONEDESK = "pg_onedesk"
DURUM_ANAHTARI = "utilizasyon.gunluk_durum"
TR = timezone(timedelta(hours=3))
DENEME = 3  # OneDesk salt okunur kopya: uzun sorgu "conflict with recovery" ile kesilebilir -> yeniden dene
SORGU_SN = 600
ISCI = "Günlük işçi"

_ESKI = (
    'SELECT LTRIM("CUSTOMERNO"::text, \'0\') AS k, "TICKETSUBTYPEID"::int AS t, COUNT(*) '
    'FROM elysion_customdata_fix."T_SOL_INCIDENT_TICKETS" '
    'WHERE "TICKETTYPEID" = 1 AND "TICKETSUBTYPEID" IN (1, 2) AND "STATUS" = \'CLOSE\' '
    'AND "CREATEDDATE" >= %(alt)s AND "CLOSEDATE" >= %(bas)s AND "CLOSEDATE" < %(bit)s '
    'AND LTRIM("CUSTOMERNO"::text, \'0\') = ANY(%(nolar)s) GROUP BY 1, 2'
)
_YENI = (
    'SELECT LTRIM("CUSTOMERNO"::text, \'0\') AS k, "TICKETTYPE_DESC" AS t, COUNT(*) '
    'FROM elysion_soxdata_octopuscorp."T_OCT_CORPORATE_MAIN" '
    'WHERE "STATUS" IN (\'Kapatıldı\', \'CLOSE\', \'Closed\') '
    'AND ("CLOSEDATE" IS NULL OR ("CLOSEDATE" >= %(bas)s AND "CLOSEDATE" < %(bit)s)) '
    'AND LTRIM("CUSTOMERNO"::text, \'0\') = ANY(%(nolar)s) GROUP BY 1, 2'
)
ESKI_TUR = {1: "sikayet", 2: "talep"}


GUN = 365  # 2026-11-21 kullanici onayi: takvim yili yerine SON 12 AY (Ocak'ta sayilar sifirlanmasin)


def donem_araligi(an: datetime | None = None) -> tuple[datetime, datetime]:
    """Turkiye saatiyle son 12 ay [bas, bit) (naive; OneDesk zamanlari yerel saat). bit = bugun 00:00 (tamamlanmis gunler)."""
    bugun = (an or datetime.now(TR)).astimezone(TR).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    return bugun - timedelta(days=GUN), bugun


# --- Durum ---------------------------------------------------------------------------------------------------------------------
def durum_oku(db: Session) -> dict[str, Any]:
    k = db.get(AppSetting, DURUM_ANAHTARI)
    return dict(k.value) if k is not None and isinstance(k.value, dict) else {}


def _durum_yaz(db: Session, deger: dict[str, Any]) -> None:
    k = db.get(AppSetting, DURUM_ANAHTARI)
    if k is None:
        db.add(AppSetting(key=DURUM_ANAHTARI, value=deger, updated_by="isci", updated_at=simdi()))
    else:
        k.value, k.updated_by, k.updated_at = deger, "isci", simdi()


# --- Kaynaklar -----------------------------------------------------------------------------------------------------------------
def _kart_anahtarlari(musteriler: list[Customer]) -> dict[int, list[str]]:
    return {c.id: musteri_anahtarlari(c.customer_no) for c in musteriler}


def onedesk_kapanan(nolar: list[str], bas: datetime, bit: datetime) -> dict[str, dict[str, int]]:
    """{musteri no anahtari: {'sikayet': n, 'talep': n}} - donemde kapanan (eski + yeni sistem)."""
    a = postgres.ayar(ONEDESK)
    parametre = {"alt": bas - timedelta(days=GUN), "bas": bas, "bit": bit, "nolar": nolar}
    sonuc: dict[str, dict[str, int]] = defaultdict(lambda: {"sikayet": 0, "talep": 0})
    for sorgu, eski in ((_ESKI, True), (_YENI, False)):
        for deneme in range(1, DENEME + 1):
            try:
                with a.baglan(SORGU_SN) as conn, conn.cursor() as cur:
                    cur.execute(sorgu, parametre)
                    satirlar = cur.fetchall()
                break
            except Exception as e:
                if deneme == DENEME:
                    raise postgres.PgHata(postgres.hata_metni(e, a.gizliler()), 502) from e
                time.sleep(5 * deneme)
        for k, t, n in satirlar:
            tur = ESKI_TUR.get(int(t)) if eski else ("sikayet" if normal(t).startswith("sikayet") else "talep" if normal(t).startswith("talep") else None)
            if tur and k:
                sonuc[str(k)][tur] += int(n)
    return dict(sonuc)


def alarm_kapanan(db: Session, bas: datetime, bit: datetime) -> dict[int, int]:
    """{customer_id: donemde kapanan alarm} - panelde olan ReportDB (TEMIP) kayitlari."""
    bas, bit = bas.replace(tzinfo=TR).astimezone(UTC), bit.replace(tzinfo=TR).astimezone(UTC)
    sorgu = (
        select(OnedeskRecord.customer_id, func.count())
        .where(OnedeskRecord.source == "temip", OnedeskRecord.status == "closed", OnedeskRecord.customer_id.is_not(None))
        .where(and_(OnedeskRecord.closed_at >= bas, OnedeskRecord.closed_at < bit))
        .group_by(OnedeskRecord.customer_id)
    )
    return {cid: int(n) for cid, n in db.execute(sorgu)}


def envanter_sayilari(db: Session) -> dict[str, tuple[int, int]]:
    """{musteri no anahtari: (aktif CI, farkli lokasyon)} - musteri envanterinden."""
    ci: dict[str, int] = defaultdict(int)
    lok: dict[str, set[str]] = defaultdict(set)
    for k, attrs in db.execute(select(CustomerCi.customer_key, CustomerCi.attrs).where(CustomerCi.status == "ACTIVE")):
        ci[k] += 1
        ad = normal((attrs or {}).get("lokasyon"))
        if ad:
            lok[k].add(ad)
    return {k: (n, len(lok[k])) for k, n in ci.items()}


# --- Tur -----------------------------------------------------------------------------------------------------------------------
def calistir(db: Session, skor_yaz: bool = True) -> dict[str, Any]:
    from app.skor import servis

    t0 = time.time()
    yil = datetime.now(TR).year
    bas, bit = donem_araligi()
    musteriler = list(db.scalars(select(Customer)))
    anahtarlar = _kart_anahtarlari(musteriler)
    nolar = sorted({k for v in anahtarlar.values() for k in v})
    kaynaklar: dict[str, dict[str, Any]] = {}

    od: dict[str, dict[str, int]] | None = None
    t = time.time()
    try:
        od = onedesk_kapanan(nolar, bas, bit) if postgres.ayar(ONEDESK).ENABLED else None
        kaynaklar["onedesk"] = {"durum": "ok" if od is not None else "kapali", "sure_sn": round(time.time() - t, 1),
                                "sikayet": sum(v["sikayet"] for v in (od or {}).values()), "talep": sum(v["talep"] for v in (od or {}).values())}  # fmt: skip
    except postgres.PgHata as e:
        kaynaklar["onedesk"] = {"durum": "hata", "hata": e.mesaj[:300], "sure_sn": round(time.time() - t, 1)}
    alarm = alarm_kapanan(db, bas, bit)
    kaynaklar["reportdb"] = {"durum": "ok", "alarm": sum(alarm.values())}
    env = envanter_sayilari(db)
    from app.musteri import envanter

    kaynaklar["onent"] = {"durum": "ok" if env else "bos", "ci": sum(v[0] for v in env.values()), "son": envanter.durum_oku(db).get("son_basari")}

    an = simdi()
    satirlar = []
    for c in musteriler:
        ks = anahtarlar[c.id]
        satirlar.append({
            "customer_id": c.id, "year": yil, "alarm": alarm.get(c.id, 0),
            "sikayet": sum(od.get(k, {}).get("sikayet", 0) for k in ks) if od is not None and ks else (0 if od is not None else None),
            "talep": sum(od.get(k, {}).get("talep", 0) for k in ks) if od is not None and ks else (0 if od is not None else None),
            "ci": sum(env.get(k, (0, 0))[0] for k in ks), "lokasyon": sum(env.get(k, (0, 0))[1] for k in ks), "refreshed_at": an,
        })  # fmt: skip
    if od is None:  # OneDesk okunamadi: onceki sayilar korunur (bos yazilmaz)
        onceki = {r.customer_id: r for r in db.scalars(select(UtilSourceSummary))}
        for s in satirlar:
            if (o := onceki.get(s["customer_id"])) is not None:
                s["sikayet"], s["talep"] = o.sikayet, o.talep
    db.execute(delete(UtilSourceSummary))
    if satirlar:
        db.execute(insert(UtilSourceSummary), satirlar)
    db.flush()

    uygulama = None
    if skor_yaz:
        sonuc = servis.uygula(db, servis.cati_musteriler(db), "gunluk", ISCI, None, yalniz_degisen=True)
        uygulama = {"uygulanan": len(sonuc["uygulanan"]), "atlanan": len(sonuc["atlanan"]), "degismeyen": sonuc["degismeyen"]}
    durum = {"zaman": iso(an), "yil": yil, "donem": [bas.date().isoformat(), (bit - timedelta(days=1)).date().isoformat()], "sure_sn": round(time.time() - t0, 1), "musteri": len(musteriler),
             "kaynaklar": kaynaklar, "skor": uygulama}  # fmt: skip
    _durum_yaz(db, durum)
    db.commit()
    return durum


# --- Okuma (skor kaynagi + Yonetim > Veri Ozeti) ---------------------------------------------------------------------------------
def ozetler(db: Session) -> dict[int, UtilSourceSummary]:
    return {r.customer_id: r for r in db.scalars(select(UtilSourceSummary))}


def grup_toplami(ozet: dict[int, UtilSourceSummary], cati: Customer, istirakler: list[Customer], alan: str) -> int | None:
    """Cati + istiraklerin toplami; hicbirinde deger yoksa None."""
    degerler = [getattr(ozet[c.id], alan) for c in [cati, *istirakler] if c.id in ozet and getattr(ozet[c.id], alan) is not None]
    return sum(degerler) if degerler else None
