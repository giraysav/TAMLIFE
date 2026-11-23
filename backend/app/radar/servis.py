"""Musteri Radar (uretim kutucuklar/radar/servis.py + reportdb_tampon.radar_adaylari). MANUEL GIRIS YOK.

TAM Radar (2026-10-17 kullanici karari): TEMIP alarm kayitlarindan (tampon/temip_kayit, 01.01.2026'dan) Musteri No'su hicbir kartla
eslesmeyen kayitlar Radar'indir. Liste Musteri No'ya gore toplanir (acik / kapali / ticketli / son kayit), ayrinti kayit kayit
(ticket, CI, baslik, durum). Esleme yalniz numarayla; unvani bir kartla ayni olan musteri dislanmaz, 'kart_adayi' olarak isaretlenir
(kartina Musteri No eklenince kayitlari sonraki turda o karta gecer). TEMIP kaydi yoksa liste bostur (eski ReportDB ozet
yedegi 2026-11-23 kaldirildi).

Musteri Radar personel gibi (2026-10-25 kullanici istegi): liste yalniz Veri Girisi > Fark'ta Radar'a atanan kartsiz numaralardir
(tampon/temip_atama.RADAR_AYARI); atanmamis kartsiz numaralar Fark'ta bekler. Radar'da admin numarayi personele atar ya da Fark'a geri
gonderir.

"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app import musteri_alani
from app.models import Customer, OnedeskRecord
from app.ortak import UygulamaHatasi, iso, simdi
from app.skor.urun_tutar import _cekirdek as unvan_cekirdegi
from app.tampon import reportdb

RADAR_ADET = 10
EN_COK_ADET = 200
KAYIT_SAYFASI = 50
BOS = {"var": False, "taze": False, "veri_zamani": None, "kaynak": "", "satirlar": [], "toplam_musteri": 0, "toplam_kayit": 0, "sayfa": 1, "adet": RADAR_ADET}

_KILIT = threading.Lock()
_KAYIT_ONBELLEK: tuple[tuple, list[dict[str, Any]]] | None = None


class RadarHata(UygulamaHatasi):
    pass


def _temip():
    from app.tampon import temip_kayit  # gec import: temip_kayit oracle/onedesk zincirini yukler

    return temip_kayit


def _radar_kosulu():
    return (OnedeskRecord.source == _temip().KAYNAK_ADI) & OnedeskRecord.customer_id.is_(None)


def _radar_numaralari(db: Session) -> set[str]:
    from app.tampon import fark, temip_atama  # gec import: _temip ile ayni neden

    # 2026-10-25: yalniz Veri Girisi'nden (Fark) Radar'a atananlar; elle karta / personele atanan ya da silinen numara Radar'da gorunmez
    elle = {str(a.get("musteri_no")) for a in temip_atama.atamalar(db)}
    return temip_atama.radar_numaralari(db) - fark.silinen_numaralar(db) - elle


def bilet_surumu(db: Session) -> str:
    """Sikayet / talep kayitlarinin son basarili turu (onedesk.canli); Radar onbellek izine girer."""
    from app.onedesk import canli

    return str(canli.durum_oku(db).get("son_basari") or "")


def bilet_sayilari(db: Session, nolar: set[str]) -> dict[str, dict[str, int]]:
    """Musteri No -> {sikayet, talep, sikayet_acik, talep_acik}: Radar numarasinin kartsiz OneDesk kayitlari (onedesk.canli)."""
    from app.onedesk import canli

    sonuc: dict[str, dict[str, int]] = {}
    liste = sorted(nolar)
    for i in range(0, len(liste), 500):
        for no, tur, durum, n in db.execute(
            select(OnedeskRecord.customer_no, OnedeskRecord.kind, OnedeskRecord.status, func.count())
            .where(OnedeskRecord.source == canli.KAYNAK_ADI, OnedeskRecord.customer_id.is_(None), OnedeskRecord.customer_no.in_(liste[i : i + 500]))
            .group_by(OnedeskRecord.customer_no, OnedeskRecord.kind, OnedeskRecord.status)
        ):
            s = sonuc.setdefault(no, {"sikayet": 0, "talep": 0, "sikayet_acik": 0, "talep_acik": 0})
            s[tur] += n
            if durum == "open":
                s[f"{tur}_acik"] += n
    return sonuc


def _musteri_listesi(db: Session) -> list[dict[str, Any]]:
    """Radar'a atanan kartsiz TEMIP kayitlari Musteri No'ya gore (toplam azalan) + sikayet / talep sayilari. Her yazimda (Radar atamasi
    dahil) degisen surum + sikayet / talep turu + kart tablosu izine gore onbellekte."""
    global _KAYIT_ONBELLEK
    iz = (_temip().surum(db), bilet_surumu(db), *db.execute(select(func.count(), func.max(Customer.id))).one())
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
    radarda = _radar_numaralari(db)
    biletler = bilet_sayilari(db, radarda)
    bos = {"sikayet": 0, "talep": 0, "sikayet_acik": 0, "talep_acik": 0}
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
            **biletler.get(no, bos),
        }
        for no, unvan, a, n, t, son in satirlar
        if no in radarda
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
    return simdi() - zaman <= timedelta(minutes=reportdb.BAYAT_DK), iso(zaman)


@musteri_alani.tum_alanlarda
def adaylar(db: Session, adet: int = RADAR_ADET, sayfa: int = 1, arama: str = "") -> dict[str, Any]:
    """{'var', 'taze', 'veri_zamani', 'kaynak': kayit, 'satirlar': [{sira, musteri_no, unvan, aktif, kapanan, toplam, sikayet, talep, ...}],
    'toplam_musteri', 'toplam_kayit', 'sayfa', 'adet'}. TEMIP kayitlarindan (sayfali, aranabilir); kayit yoksa bos."""
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
    return {**BOS, "adet": adet}


@musteri_alani.tum_alanlarda
def kayitlar(db: Session, musteri_no: str, sayfa: int = 1) -> dict[str, Any]:
    """Radar musterisinin kayitlari (en yeni once, sayfali): ticket, CI, baslik, durum, acilis, kapanis."""
    if not musteri_no.isdigit() or len(musteri_no) > 20:
        raise RadarHata(400, "Müşteri No geçersiz.")
    sayfa = max(1, sayfa)
    if musteri_no not in _radar_numaralari(db):
        raise RadarHata(404, "Bu Müşteri No Müşteri Radar'a atanmamış.")
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
