"""Veri Girisi partisinden Onedesk kaydi aktarimi (admin).

Kaynak: tampon.depo partisi (CSV ya da isci surecin ReportDB alarm kayit partisi). Sutunlar baslik adindan tanir (uretim ats_analizi
SUTUN_ADLARI mantigi); kayit numarasi (cagri no) varsa ayni numara + tur guncellenir, yoksa eklenir. Musteri: 'Musteri No' sutunu
varsa once numarayla (tek karta duserse; uretim kurali), yoksa / eslesmezse unvanla. Aktarimdan sonra etkilenen musterilerin
sayaclari (acik / yil boyu kapanan) kayitlardan yeniden hesaplanir (sayac_yenile=False: sayilar baska yoldan gelir).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Customer, IngestBatch, OnedeskRecord
from app.onedesk.servis import TURLER, OnedeskHata
from app.ortak import eslestirme_anahtari, normal, simdi
from app.tampon import depo, reportdb
from app.tampon.eslestirme import musteri_anahtarlari

EN_COK_SATIR = 200_000
PARCA = 500
# alan -> baslik adaylari (normal() sonrasi). Once birebir, sonra (>=4 harfli adaylar icin) icerme.
SUTUN_ADLARI: dict[str, tuple[str, ...]] = {
    "no": ("cagri no", "kayit no", "inc id", "ticket no", "ticket id", "no", "id"),
    "tur": ("kayit turu", "cagri turu", "tur", "type"),
    "durum": ("durum", "status", "state", "statu"),
    "musteri": ("musteri adi", "musteri", "customer", "firma"),
    "musteri_no": ("musteri no", "customer no", "musteri numarasi"),
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


TR_SAATI = timezone(timedelta(hours=3), "TR")  # Onedesk disa aktarimi ve Oracle saatleri yerel ve dilimsiz; Turkiye 2016'dan beri sabit +03


def tarih_oku(deger: object) -> datetime | None:
    """Dilimsiz deger Turkiye saati sayilir ve UTC'ye cevrilir (DB'de tum zamanlar UTC); dilimli deger oldugu gibi UTC'ye."""
    if isinstance(deger, datetime):
        return (deger if deger.tzinfo else deger.replace(tzinfo=TR_SAATI)).astimezone(UTC)
    m = _FRAKSIYON.sub("", str(deger or "").strip())
    if not m:
        return None
    for bicim in _BICIMLER:
        try:
            return datetime.strptime(m, bicim).replace(tzinfo=TR_SAATI).astimezone(UTC)
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


def aktarilabilir_mi(parti: IngestBatch) -> bool:
    """ReportDB musteri OZETI (satir = musteri, kayit degil) ve eski panelden alinan tampon Onedesk'e kayit olarak aktarilmaz:
    2026-10-14'te 8.441 satirlik ozet aktarilip kayit numarasiz 8.441 sahte kayit olusmustu (temizlik: python -m app.gecmis_temizle)."""
    return parti.source_key != reportdb.KAYNAK and parti.created_by != "eski_aktar"


def parti_aktar(db: Session, parti_id: int, varsayilan_tur: str | None = None, *, kaynak: str = "import", sayac_yenile: bool = True) -> dict:
    """Hazir partiyi Onedesk kaydi olarak aktarir. varsayilan_tur: kaynakta tur sutunu yoksa tum satirlarin turu; kaynak: kayit source."""
    parti = db.get(IngestBatch, parti_id)
    if parti is None:
        raise OnedeskHata(404, "Parti bulunamadı.")
    if parti.status != "ready":
        raise OnedeskHata(409, "Yalnız hazır (kabul edilmiş) parti aktarılabilir.")
    if not aktarilabilir_mi(parti):
        raise OnedeskHata(400, "Bu parti müşteri bazında alarm özeti ya da eski panel tamponu; Onedesk kaydı değildir.")
    if varsayilan_tur is not None and varsayilan_tur not in TURLER:
        raise OnedeskHata(400, "Tür alarm, talep ya da sikayet olmalı.")
    s = sutunlari_bul(parti.columns or [])
    if s["tur"] is None and varsayilan_tur is None:
        raise OnedeskHata(400, "Kayıt türü sütunu bulunamadı; kaynaktaki türü (alarm/talep/şikayet) seçin.")
    if any(s[a] is None for a in _ZORUNLU):
        raise OnedeskHata(400, "Müşteri sütunu bulunamadı.")
    if parti.row_count > EN_COK_SATIR:
        raise OnedeskHata(413, f"Parti en fazla {EN_COK_SATIR} satır aktarılabilir.")

    musteriler: dict[str, int] = {}
    no_dizini: dict[str, set[int]] = {}
    for m in db.scalars(select(Customer)):
        if m.name:
            musteriler[eslestirme_anahtari(m.name)] = m.id
        for k in musteri_anahtarlari(m.customer_no):
            no_dizini.setdefault(k, set()).add(m.id)
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
            adaylar = {i for k in musteri_anahtarlari(_hucre(satir, s["musteri_no"])) for i in no_dizini.get(k, ())}
            cid = next(iter(adaylar)) if len(adaylar) == 1 else musteriler.get(eslestirme_anahtari(ad))
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
                "source": kaynak[:20],
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
    if sayac_yenile:
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


def kaynak_yenile(db: Session, parti_id: int | None, kaynak: str, tur: str) -> dict:
    """Kaynagin (source) bu turdeki kayitlarini partiyle DEGISTIRIR (uretim reportdb_acik_kayit / ats_kaydet: her turda liste tamamen
    yenilenir, eski veri kalmaz). Tek islem, commit cagiranda. parti_id None: liste bosaltilir. Sayaclar yeniden hesaplanmaz."""
    silinen = db.execute(delete(OnedeskRecord).where(OnedeskRecord.source == kaynak, OnedeskRecord.kind == tur)).rowcount or 0
    sonuc = parti_aktar(db, parti_id, tur, kaynak=kaynak, sayac_yenile=False) if parti_id else {"eklenen": 0, "guncellenen": 0}
    return {**sonuc, "silinen": silinen}
