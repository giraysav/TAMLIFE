"""Musteri Radar (uretim kutucuklar/radar/servis.py + reportdb_tampon.radar_adaylari). MANUEL GIRIS YOK.

Kural (uretimle ayni): ReportDB tamponunun son hazir partisinde kayit (alarm; aktif + kapanan, yil basindan) ureten ama panelde
karti OLMAYAN musteriler, kayit sayisina gore azalan ilk RADAR_ADET. Panelde sayilma: Musteri No bir kartin numaralarindan biriyse
YA DA unvan cekirdegi (yasal ek / noktalama / Turkce karakter farksiz) bir kartinkiyle ayniysa. Sikayet / talep: OneDesk bilet
semasi bu ReportDB hesabinda gorunmuyor -> yalniz alarm sayilir. Ayri sorgu yok: veri tampondan okunur (Oracle'a baglanilmaz).
"""

from __future__ import annotations

import heapq
import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, IngestBatch
from app.ortak import iso
from app.skor.urun_tutar import _cekirdek as unvan_cekirdegi
from app.tampon import depo, reportdb
from app.tampon.eslestirme import anahtar, musteri_anahtarlari

RADAR_ADET = 10
BOS = {"var": False, "taze": False, "veri_zamani": None, "satirlar": []}

# Hazir parti degismez (yeni veri yeni parti): satirlarin acilmis ve anahtarlanmis hali partiye gore onbellekte tutulur. Ekip Ozeti her
# acilista radar karosunu hesaplar; 8 bin satirda zlib + unvan cekirdegi istek basina ~250 ms (sunucuda 1 sn uzeri) CPU yakiyordu.
_ONBELLEK: tuple[tuple[int, str, int], tuple[Any, list[tuple[str, str, str, str, int, int]]]] | None = None
_KILIT = threading.Lock()


def _sayi(v: Any) -> int:
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def adaylar(db: Session, adet: int = RADAR_ADET) -> dict[str, Any]:
    """{'var': ReportDB verisi alindi mi, 'taze', 'veri_zamani', 'satirlar': [{sira, musteri_no, unvan, aktif, kapanan, toplam}]}."""
    parti = db.scalars(
        select(IngestBatch).where(IngestBatch.source_key == reportdb.KAYNAK, IngestBatch.status == "ready").order_by(IngestBatch.id.desc()).limit(1)
    ).first()
    if parti is None:
        return dict(BOS)
    sutun = {ad: i for i, ad in enumerate(parti.columns or [])}
    if any(ad not in sutun for ad in ("Musteri No", "Musteri Unvani", "Aktif Alarm", "Kapanan Alarm")):
        return dict(BOS)
    numaralar: set[str] = set()
    cekirdekler: set[str] = set()
    for no, ad in db.execute(select(Customer.customer_no, Customer.name)):
        numaralar.update(musteri_anahtarlari(no))
        if cek := unvan_cekirdegi(ad or ""):
            cekirdekler.add(cek)
    veri_zamani, satirlar_ = _parti_satirlari(db, parti, sutun)
    ilk = heapq.nsmallest(
        max(1, adet),
        (
            (no, unvan, aktif, kapanan)
            for no, unvan, no_anahtar, cekirdek, aktif, kapanan in satirlar_
            if no_anahtar not in numaralar and cekirdek not in cekirdekler
        ),
        key=lambda a: (-(a[2] + a[3]), a[1]),
    )
    satirlar = [
        {"sira": i, "musteri_no": no, "unvan": unvan, "aktif": aktif, "kapanan": kapanan, "toplam": aktif + kapanan}
        for i, (no, unvan, aktif, kapanan) in enumerate(ilk, 1)
    ]
    durum = reportdb.durum(db)
    return {"var": True, "taze": durum["taze"], "veri_zamani": veri_zamani or iso(parti.received_at), "satirlar": satirlar}


def _parti_satirlari(db: Session, parti: IngestBatch, sutun: dict[str, int]) -> tuple[Any, list[tuple[str, str, str, str, int, int]]]:
    """(veri zamani, [(no, unvan, no anahtari, unvan cekirdegi, aktif, kapanan)]); yalniz kaydi olan satirlar. Parti basina bir kez hesaplanir."""
    global _ONBELLEK
    iz = (parti.id, str(parti.received_at), parti.row_count)
    with _KILIT:
        if _ONBELLEK is not None and _ONBELLEK[0] == iz:
            return _ONBELLEK[1]
    veri_zamani = None
    satirlar: list[tuple[str, str, str, str, int, int]] = []
    for s in depo.satirlari_oku(db, parti.id):
        no, unvan = str(s[sutun["Musteri No"]] or ""), str(s[sutun["Musteri Unvani"]] or "")
        aktif, kapanan = _sayi(s[sutun["Aktif Alarm"]]), _sayi(s[sutun["Kapanan Alarm"]])
        if veri_zamani is None and "Veri Zamani" in sutun:
            veri_zamani = s[sutun["Veri Zamani"]] or None
        if aktif + kapanan > 0:
            satirlar.append((no, unvan, anahtar(no), unvan_cekirdegi(unvan), aktif, kapanan))
    sonuc = (veri_zamani, satirlar)
    with _KILIT:
        _ONBELLEK = (iz, sonuc)
    return sonuc
