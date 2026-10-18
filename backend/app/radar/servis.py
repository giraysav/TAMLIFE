"""Musteri Radar (uretim kutucuklar/radar/servis.py + reportdb_tampon.radar_adaylari). MANUEL GIRIS YOK.

TAM Radar (2026-10-17 kullanici karari): TEMIP alarm kayitlarindan (tampon/temip_kayit, 01.01.2026'dan) Musteri No'su hicbir kartla
eslesmeyen kayitlar Radar'indir. Liste Musteri No'ya gore toplanir (acik / kapali / ticketli / son kayit), ayrinti kayit kayit
(ticket, CI, baslik, durum). Esleme yalniz numarayla; unvani bir kartla ayni olan musteri dislanmaz, 'kart_adayi' olarak isaretlenir
(kartina Musteri No eklenince kayitlari sonraki turda o karta gecer). TEMIP kaydi yoksa asagidaki eski ozet kurali calisir.

Eski kural (TEMIP kaydi yokken):

Kural (uretimle ayni): ReportDB tamponunun son hazir partisinde kayit (alarm; aktif + kapanan, yil basindan) ureten ama panelde
karti OLMAYAN musteriler, kayit sayisina gore azalan ilk RADAR_ADET. Panelde sayilma: Musteri No bir kartin numaralarindan biriyse
YA DA unvan cekirdegi (yasal ek / noktalama / Turkce karakter farksiz) bir kartinkiyle ayniysa. Sikayet / talep: OneDesk bilet
semasi bu ReportDB hesabinda gorunmuyor -> yalniz alarm sayilir. Ayri sorgu yok: veri tampondan okunur (Oracle'a baglanilmaz).
"""

from __future__ import annotations

import heapq
import threading
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Customer, IngestBatch, OnedeskRecord
from app.ortak import UygulamaHatasi, iso, simdi
from app.skor.urun_tutar import _cekirdek as unvan_cekirdegi
from app.tampon import depo, reportdb
from app.tampon.eslestirme import anahtar, musteri_anahtarlari

RADAR_ADET = 10
EN_COK_ADET = 200
KAYIT_SAYFASI = 50
BOS = {"var": False, "taze": False, "veri_zamani": None, "kaynak": "", "satirlar": [], "toplam_musteri": 0, "toplam_kayit": 0, "sayfa": 1, "adet": RADAR_ADET}

# Hazir parti degismez (yeni veri yeni parti): satirlarin acilmis ve anahtarlanmis hali partiye gore onbellekte tutulur. Ekip Ozeti her
# acilista radar karosunu hesaplar; 8 bin satirda zlib + unvan cekirdegi istek basina ~250 ms (sunucuda 1 sn uzeri) CPU yakiyordu.
_ONBELLEK: tuple[tuple[int, str, int], tuple[Any, list[tuple[str, str, str, str, int, int]]]] | None = None
_KILIT = threading.Lock()
_KAYIT_ONBELLEK: tuple[tuple, list[dict[str, Any]]] | None = None


class RadarHata(UygulamaHatasi):
    pass


def _sayi(v: Any) -> int:
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def _temip():
    from app.tampon import temip_kayit  # gec import: temip_kayit oracle/onedesk zincirini yukler

    return temip_kayit


def _radar_kosulu():
    return (OnedeskRecord.source == _temip().KAYNAK_ADI) & OnedeskRecord.customer_id.is_(None)


def _musteri_listesi(db: Session) -> list[dict[str, Any]]:
    """Kartsiz TEMIP kayitlari Musteri No'ya gore (toplam azalan). Her yazimda degisen surum + kart tablosu izine gore onbellekte."""
    global _KAYIT_ONBELLEK
    iz = (_temip().surum(db), *db.execute(select(func.count(), func.max(Customer.id))).one())
    with _KILIT:
        if _KAYIT_ONBELLEK is not None and _KAYIT_ONBELLEK[0] == iz:
            return _KAYIT_ONBELLEK[1]
    cekirdekler: dict[str, dict[str, Any]] = {}
    for cid, ad in db.execute(select(Customer.id, Customer.name)):
        if cek := unvan_cekirdegi(ad or ""):
            cekirdekler.setdefault(cek, {"id": cid, "ad": ad})
    acik = func.sum(case((OnedeskRecord.status == "open", 1), else_=0))
    ticketli = func.sum(case((OnedeskRecord.ticket_no != "", 1), else_=0))
    satirlar = db.execute(
        select(OnedeskRecord.customer_no, func.max(OnedeskRecord.customer_label), acik, func.count(), ticketli, func.max(OnedeskRecord.opened_at))
        .where(_radar_kosulu())
        .group_by(OnedeskRecord.customer_no)
    ).all()
    liste = [
        {
            "musteri_no": no,
            "unvan": unvan or no,
            "aktif": int(a or 0),
            "kapanan": int(n) - int(a or 0),
            "toplam": int(n),
            "ticketli": int(t or 0),
            "son_kayit": iso(son),
            "kart_adayi": cekirdekler.get(unvan_cekirdegi(unvan or "")),
        }
        for no, unvan, a, n, t, son in satirlar
    ]
    liste.sort(key=lambda r: (-r["toplam"], r["unvan"]))
    for i, r in enumerate(liste, 1):
        r["sira"] = i
    with _KILIT:
        _KAYIT_ONBELLEK = (iz, liste)
    return liste


def _kayit_tazeligi(db: Session) -> tuple[bool, str | None]:
    an = _temip().surum(db)
    if not an:
        return False, None
    try:
        zaman = datetime.fromisoformat(an)
    except ValueError:
        return False, None
    return simdi() - zaman <= timedelta(minutes=reportdb.TAZELIK_DAKIKA), iso(zaman)


def adaylar(db: Session, adet: int = RADAR_ADET, sayfa: int = 1, arama: str = "") -> dict[str, Any]:
    """{'var', 'taze', 'veri_zamani', 'kaynak': kayit|ozet, 'satirlar': [{sira, musteri_no, unvan, aktif, kapanan, toplam, ...}],
    'toplam_musteri', 'toplam_kayit', 'sayfa', 'adet'}. TEMIP kaydi varsa ondan (sayfali, aranabilir), yoksa eski ozet kuralindan."""
    adet, sayfa = min(max(1, adet), EN_COK_ADET), max(1, sayfa)
    if db.scalar(select(OnedeskRecord.id).where(OnedeskRecord.source == _temip().KAYNAK_ADI).limit(1)) is not None:
        liste = _musteri_listesi(db)
        if arama.strip():
            q = arama.strip().casefold()
            liste = [r for r in liste if q in r["unvan"].casefold() or q in r["musteri_no"]]
        taze, zaman = _kayit_tazeligi(db)
        return {
            "var": True,
            "taze": taze,
            "veri_zamani": zaman,
            "kaynak": "kayit",
            "satirlar": liste[(sayfa - 1) * adet : sayfa * adet],
            "toplam_musteri": len(liste),
            "toplam_kayit": sum(r["toplam"] for r in liste),
            "sayfa": sayfa,
            "adet": adet,
        }
    return _ozet_adaylari(db, adet)


def kayitlar(db: Session, musteri_no: str, sayfa: int = 1) -> dict[str, Any]:
    """Radar musterisinin kayitlari (en yeni once, sayfali): ticket, CI, baslik, durum, acilis, kapanis."""
    if not musteri_no.isdigit() or len(musteri_no) > 20:
        raise RadarHata(400, "Müşteri No geçersiz.")
    sayfa = max(1, sayfa)
    kosul = _radar_kosulu() & (OnedeskRecord.customer_no == musteri_no)
    toplam = db.scalar(select(func.count()).select_from(OnedeskRecord).where(kosul)) or 0
    if not toplam:
        raise RadarHata(404, "Bu Müşteri No için Radar kaydı yok.")
    satirlar = db.scalars(
        select(OnedeskRecord)
        .where(kosul)
        .order_by(OnedeskRecord.opened_at.desc(), OnedeskRecord.id.desc())
        .offset((sayfa - 1) * KAYIT_SAYFASI)
        .limit(KAYIT_SAYFASI)
    ).all()
    return {
        "musteri_no": musteri_no,
        "unvan": satirlar[0].customer_label if satirlar else "",
        "toplam": toplam,
        "sayfa": sayfa,
        "adet": KAYIT_SAYFASI,
        "kayitlar": [
            {
                "kimlik": r.external_key,
                "ticket": r.ticket_no,
                "ci": r.location,
                "baslik": r.category,
                "durum": r.status,
                "ayrinti": r.detail,
                "acilis": iso(r.opened_at),
                "kapanis": iso(r.closed_at),
            }
            for r in satirlar
        ],
    }


def _ozet_adaylari(db: Session, adet: int = RADAR_ADET) -> dict[str, Any]:
    """Eski kural: ReportDB ozet partisinden karti olmayan ilk `adet` musteri (TEMIP kaydi yokken)."""
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
    return {
        "var": True,
        "taze": durum["taze"],
        "veri_zamani": veri_zamani or iso(parti.received_at),
        "kaynak": "ozet",
        "satirlar": satirlar,
        "toplam_musteri": len(satirlar),
        "toplam_kayit": sum(r["toplam"] for r in satirlar),
        "sayfa": 1,
        "adet": adet,
    }


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
