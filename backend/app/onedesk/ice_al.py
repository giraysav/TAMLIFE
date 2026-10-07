"""Veri Girisi partisinden Onedesk kaydi aktarimi (admin).

Kaynak: tampon.depo partisi (CSV ya da ileride canli Onedesk DB cekimi). Sutunlar baslik adindan tanir (uretim ats_analizi
SUTUN_ADLARI mantigi); kayit numarasi (cagri no) varsa ayni numara + tur guncellenir, yoksa eklenir. Aktarimdan sonra
etkilenen musterilerin sayaclari (acik / yil boyu kapanan) kayitlardan yeniden hesaplanir.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Customer, IngestBatch, OnedeskRecord
from app.onedesk.servis import TURLER, OnedeskHata
from app.ortak import eslestirme_anahtari, normal, simdi
from app.tampon import depo

EN_COK_SATIR = 200_000
PARCA = 500
# alan -> baslik adaylari (normal() sonrasi). Once birebir, sonra (>=4 harfli adaylar icin) icerme.
SUTUN_ADLARI: dict[str, tuple[str, ...]] = {
    "no": ("cagri no", "kayit no", "inc id", "ticket no", "ticket id", "no", "id"),
    "tur": ("kayit turu", "cagri turu", "tur", "type"),
    "durum": ("durum", "status", "state", "statu"),
    "musteri": ("musteri adi", "musteri", "customer", "firma"),
    "lokasyon": ("lokasyon", "ci adi", "ci name", "location", "site", "konfigurasyon ogesi", "ci"),
    "kategori": ("kategori", "alarm adi", "category", "ozet", "summary"),
    "acilis": ("acilis tarihi", "acilis", "open date", "olusturma tarihi", "created"),
    "kapanis": ("kapanis tarihi", "kapanis", "closed date", "close date", "resolved"),
    "kok": ("kok sebep", "kok neden", "root cause", "rca"),
    "cozum": ("cozum aciklamasi", "cozum", "resolution", "yapilan islem", "kapanis notu"),
}
_ZORUNLU = ("musteri",)
_KAPALI = ("kapal", "closed", "cozul", "resolved", "tamam", "done")
_BICIMLER = ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y")
_FRAKSIYON = re.compile(r"\.\d+$")


def sutunlari_bul(basliklar: Iterable[object]) -> dict[str, int | None]:
    adlar = [normal(b) for b in basliklar]
    sonuc: dict[str, int | None] = {}
    for alan, adaylar in SUTUN_ADLARI.items():
        bulunan = next((adlar.index(a) for a in adaylar if a in adlar), None)
        if bulunan is None:
            for aday in adaylar:
                if len(aday) < 4:
                    continue
                bulunan = next((i for i, a in enumerate(adlar) if aday in a), None)
                if bulunan is not None:
                    break
        sonuc[alan] = bulunan
    return sonuc


def tur_tani(deger: object, varsayilan: str | None) -> str | None:
    m = normal(deger)
    if not m:
        return varsayilan
    if "alarm" in m:
        return "alarm"
    if "sikayet" in m or "complaint" in m:
        return "sikayet"
    if "talep" in m or "request" in m:
        return "talep"
    return varsayilan


def tarih_oku(deger: object) -> datetime | None:
    if isinstance(deger, datetime):
        return deger if deger.tzinfo else deger.replace(tzinfo=UTC)
    m = _FRAKSIYON.sub("", str(deger or "").strip())
    if not m:
        return None
    for bicim in _BICIMLER:
        try:
            return datetime.strptime(m, bicim).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _hucre(satir: list, indeks: int | None) -> str:
    return "" if indeks is None or indeks >= len(satir) or satir[indeks] is None else str(satir[indeks]).strip()


def sayaclari_yenile(db: Session, musteri_idleri: set[int]) -> None:
    """Musteri kartindaki sayaclar kayitlardan: acik (tur basina) ve bu yil kapanan."""
    if not musteri_idleri:
        return
    yil = simdi().year
    bas, son = datetime(yil, 1, 1, tzinfo=UTC), datetime(yil + 1, 1, 1, tzinfo=UTC)
    acik: dict[tuple[int, str], int] = {}
    for cid, tur, adet in db.execute(
        select(OnedeskRecord.customer_id, OnedeskRecord.kind, func.count())
        .where(OnedeskRecord.customer_id.in_(musteri_idleri), OnedeskRecord.status == "open")
        .group_by(OnedeskRecord.customer_id, OnedeskRecord.kind)
    ):
        acik[(cid, tur)] = adet
    kapali: dict[tuple[int, str], int] = {}
    for cid, tur, adet in db.execute(
        select(OnedeskRecord.customer_id, OnedeskRecord.kind, func.count())
        .where(OnedeskRecord.customer_id.in_(musteri_idleri), OnedeskRecord.status == "closed", OnedeskRecord.closed_at >= bas, OnedeskRecord.closed_at < son)
        .group_by(OnedeskRecord.customer_id, OnedeskRecord.kind)
    ):
        kapali[(cid, tur)] = adet
    for m in db.scalars(select(Customer).where(Customer.id.in_(musteri_idleri))):
        m.alarm_count, m.request_count, m.complaint_count = acik.get((m.id, "alarm"), 0), acik.get((m.id, "talep"), 0), acik.get((m.id, "sikayet"), 0)
        m.alarm_closed_count, m.request_closed_count, m.complaint_closed_count = (
            kapali.get((m.id, "alarm"), 0),
            kapali.get((m.id, "talep"), 0),
            kapali.get((m.id, "sikayet"), 0),
        )


def parti_aktar(db: Session, parti_id: int, varsayilan_tur: str | None = None) -> dict:
    """Hazir partiyi Onedesk kaydi olarak aktarir. varsayilan_tur: kaynakta tur sutunu yoksa tum satirlarin turu."""
    parti = db.get(IngestBatch, parti_id)
    if parti is None:
        raise OnedeskHata(404, "Parti bulunamadı.")
    if parti.status != "ready":
        raise OnedeskHata(409, "Yalnız hazır (kabul edilmiş) parti aktarılabilir.")
    if varsayilan_tur is not None and varsayilan_tur not in TURLER:
        raise OnedeskHata(400, "Tür alarm, talep ya da sikayet olmalı.")
    s = sutunlari_bul(parti.columns or [])
    if s["tur"] is None and varsayilan_tur is None:
        raise OnedeskHata(400, "Kayıt türü sütunu bulunamadı; kaynaktaki türü (alarm/talep/şikayet) seçin.")
    if any(s[a] is None for a in _ZORUNLU):
        raise OnedeskHata(400, "Müşteri sütunu bulunamadı.")
    if parti.row_count > EN_COK_SATIR:
        raise OnedeskHata(413, f"Parti en fazla {EN_COK_SATIR} satır aktarılabilir.")

    musteriler = {eslestirme_anahtari(m.name): m.id for m in db.scalars(select(Customer)) if m.name}
    eklenen = guncellenen = atlanan = eslesmeyen = 0
    etkilenen: set[int] = set()
    parca: list[list] = []

    def isle(satirlar: list[list]) -> None:
        nonlocal eklenen, guncellenen, atlanan, eslesmeyen
        anahtarlar = {(tur_tani(_hucre(s_, s["tur"]), varsayilan_tur), _hucre(s_, s["no"])) for s_ in satirlar}
        mevcut: dict[tuple[str, str], OnedeskRecord] = {}
        numaralar = [n for _, n in anahtarlar if n]
        if numaralar:
            for r in db.scalars(select(OnedeskRecord).where(OnedeskRecord.external_key.in_(numaralar))):
                mevcut[(r.kind, r.external_key)] = r
        for satir in satirlar:
            tur = tur_tani(_hucre(satir, s["tur"]), varsayilan_tur)
            ad = _hucre(satir, s["musteri"])
            if tur is None or not ad:
                atlanan += 1
                continue
            numara = _hucre(satir, s["no"])[:80]
            acilis, kapanis = tarih_oku(_hucre(satir, s["acilis"])), tarih_oku(_hucre(satir, s["kapanis"]))
            durum_metni = normal(_hucre(satir, s["durum"]))
            kapali = kapanis is not None if s["durum"] is None else any(k in durum_metni for k in _KAPALI)
            cid = musteriler.get(eslestirme_anahtari(ad))
            if cid is None:
                eslesmeyen += 1
            else:
                etkilenen.add(cid)
            alanlar = {
                "customer_id": cid,
                "customer_label": ad[:200],
                "location": _hucre(satir, s["lokasyon"])[:200],
                "category": _hucre(satir, s["kategori"])[:200],
                "status": "closed" if kapali else "open",
                "opened_at": acilis or kapanis or simdi(),
                "closed_at": (kapanis or simdi()) if kapali else None,
                "root_cause": _hucre(satir, s["kok"]),
                "resolution": _hucre(satir, s["cozum"]),
                "source": "import",
            }
            kayit = mevcut.get((tur, numara)) if numara else None
            if kayit is None:
                kayit = OnedeskRecord(kind=tur, external_key=numara, **alanlar)
                db.add(kayit)
                if numara:
                    mevcut[(tur, numara)] = kayit
                eklenen += 1
            else:
                if kayit.customer_id:
                    etkilenen.add(kayit.customer_id)
                for k, v in alanlar.items():
                    setattr(kayit, k, v)
                guncellenen += 1

    for satir in depo.satirlari_oku(db, parti_id):
        parca.append(satir)
        if len(parca) >= PARCA:
            isle(parca)
            parca = []
    if parca:
        isle(parca)
    db.flush()
    sayaclari_yenile(db, etkilenen)
    return {
        "parti": parti_id,
        "eklenen": eklenen,
        "guncellenen": guncellenen,
        "atlanan": atlanan,
        "musteri_eslesmeyen": eslesmeyen,
        "etkilenen_musteri": len(etkilenen),
        "sutunlar": {alan: (parti.columns[i] if i is not None and i < len(parti.columns) else None) for alan, i in s.items()},
    }
