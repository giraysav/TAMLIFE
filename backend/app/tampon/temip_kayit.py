"""ReportDB TEMIP kurumsal alarm kayitlari -> onedesk_record (2026-10-17 kullanici karari).

Kural:
- Kapsam: NOC DESTECH, 8 haneli Musteri No (INFORMATION1) ve unvani (INFORMATION2) dolu alarmlar; REPORTDB_KAYIT_BASLANGIC'tan
  (varsayilan 2026-01-01 00:00, Turkiye saati) itibaren ACILAN kayitlar. TEMIP yalniz ALARM verir: tur her zaman 'alarm';
  talep / sikayet OneDesk'ten gelir (bu ReportDB hesabinda OneDesk bilet tablosu yok, uydurma tur uretilmez).
- Kayit = TEMIP alarmi (external_key = IDENTIFIER, source = 'temip'); OneDesk ticket no, Musteri No, CI adi, baslik ve TEMIP durumu
  ayri alanlarda. Acik: TEMIP.ACTIVEALARMS_5DK (es ad; anlik). Kapali: TEMIP.VIEW_REPORT_ACTIVE (yalniz kapananlari tutar;
  EVENTTIME ile bolumlu -> her sorgu iki yonlu EVENTTIME sinirli).
- Atama: Musteri No tek bir karta duserse kayit o karta (sorumlu TAM'in kaydi) baglanir; kart yoksa customer_id bos kalir ve kayit
  TAM Radar'a duser (radar.servis). Kart numarasi degisince her turda yeniden baglanir.
- Kipler: 'tam' (baslangictan bugune ay ay; ilk yukleme, dakikalar surer), 'artimli' (her 30 dk: son 1 gunde kapananlar + acik
  goruntu + goruntuden dusen aciklarin kapanisi IDENTIFIER ile), 'mutabakat' (son N gun yeniden; gece).
- Kapali kayit yeniden acilmaz (anlik goruntu VIEW_REPORT_ACTIVE'den geri kalabilir). Kisisel veri alinmaz: kapatan kullanici
  yalniz atm / Auto-Clear / operator olarak yazilir.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import musteri_alani
from app.models import AppSetting, Customer, OnedeskRecord
from app.onedesk.sayac import TR_SAATI, sayaclari_yenile, tarih_oku
from app.ortak import simdi
from app.tampon import oracle, reportdb
from app.tampon.eslestirme import anahtar, musteri_anahtarlari

KAYNAK_ADI = "temip"  # onedesk_record.source
TUR = "alarm"
BASLANGIC_ANAHTARI = "REPORTDB_KAYIT_BASLANGIC"
VARSAYILAN_BASLANGIC = date(2026, 1, 1)
SURUM_AYARI = "temip.surum"  # her yazimda degisir: TAM Radar onbellegi buna bakar
PARCA = 1000
KAPANIS_PARCASI = 500
SORGU_SINIRI = 400_000  # tek sorgu (ay dilimi) en fazla bu kadar satir
ARTIMLI_GUN = 1
MUTABAKAT_GUN = 30
# Kurumsal alarm (2026-10-18 kullanici: "nw_li_cust ile kurumsal alarmlar geliyor; domain ACCESS ve NOC DESTECH; musteri numarasiyla
# iceri al"): NETWORK domaini, 8 haneli Musteri No (INFORMATION1; karta eslesme anahtari) ve CI'da (MANAGEDOBJECT / NODE1) nw_li_cust.
# 2026-10-19 kullanici: "NETWORK: ACCESS'i kaldir" -> yalniz NOC DESTECH (kurumsal).
DOMAINLER = ("NOC DESTECH",)
CI_ARAMA = "nw_li_cust"
_KOSUL = (
    "REPLACE(NETWORK, '\"', '') IN ('NOC DESTECH') AND REGEXP_LIKE(INFORMATION1, '^[0-9]{8}$') "
    "AND (INSTR(LOWER(MANAGEDOBJECT), 'nw_li_cust') > 0 OR INSTR(LOWER(NODE1), 'nw_li_cust') > 0)"
)
KIPLER = ("tam", "artimli", "mutabakat", "katalogdan")
_CI_ADI = re.compile(r"CIName:\s*(\S+)")
_TICKET = re.compile(r"^[0-9]+")
_KIMLIK = re.compile(r"^\d{1,20}$")


def baslangic() -> date:
    ham = os.environ.get(BASLANGIC_ANAHTARI, "").strip()
    if not ham:
        return VARSAYILAN_BASLANGIC
    try:
        return date.fromisoformat(ham)
    except ValueError:
        raise reportdb.ReportdbHata(f"{BASLANGIC_ANAHTARI} YYYY-AA-GG biçiminde olmalı.") from None


def _tarih(d: date | datetime) -> str:
    """Oracle tarih sabiti (yalniz koddan gelen tarih; kullanici girdisi sorguya girmez)."""
    return f"TO_DATE('{d:%Y-%m-%d %H:%M:%S}', 'YYYY-MM-DD HH24:MI:SS')" if isinstance(d, datetime) else f"DATE '{d:%Y-%m-%d}'"


def _kolonlar(acik: bool) -> str:
    durum = (
        "SUBSTR(STATE || '/' || PROBLEMSTATUS, 1, 80)"
        if acik
        else "'Closed/' || CASE WHEN CLOSEUSERIDENTIFIER IN ('atm', 'Auto-Clear') THEN CLOSEUSERIDENTIFIER "
        "WHEN CLOSEUSERIDENTIFIER IS NULL THEN '-' ELSE 'operator' END"
    )
    return ", ".join(
        (
            "TO_CHAR(IDENTIFIER) AS KIMLIK",
            "INFORMATION1 AS MNO",
            "SUBSTR(INFORMATION2, 1, 200) AS UNVAN",
            "REGEXP_SUBSTR(ALARMOBJECTOPERATORNO, '^[0-9]+') AS TICKET",
            "SUBSTR(NVL(REGEXP_SUBSTR(ADDITIONALTEXT, 'CIName:[[:space:]]*([^[:space:]]+)', 1, 1, NULL, 1), NODE1), 1, 200) AS CI",
            "SUBSTR(ALARMHEADER, 1, 200) AS BASLIK",
            "EVENTTIME AS ACILIS",
            "CLOSETIMESTAMP AS KAPANIS",
            f"{durum} AS DURUM",
        )
    )


def acik_sorgusu(bas: date) -> str:
    return f"SELECT {_kolonlar(True)} FROM TEMIP.ACTIVEALARMS_5DK WHERE EVENTTIME >= {_tarih(bas)} AND {_KOSUL}"


def kapali_sorgusu(alt: str, ust: str) -> str:
    """alt / ust: koddan uretilmis Oracle ifadesi (_tarih ya da SYSDATE aritmetigi). EVENTTIME iki yonlu sinirli (bolum budama)."""
    return f"SELECT {_kolonlar(False)} FROM TEMIP.VIEW_REPORT_ACTIVE WHERE EVENTTIME >= {alt} AND EVENTTIME < {ust} AND {_KOSUL}"


def kimlik_sorgusu(kimlikler: list[str], alt: datetime, ust: datetime) -> str:
    """Goruntuden dusen acik alarmlarin kapanisi: IDENTIFIER ile, bilinen acilis araligina sinirli (tum bolumler taranmaz)."""
    if not kimlikler or not all(_KIMLIK.match(k) for k in kimlikler):
        raise reportdb.ReportdbHata("Geçersiz TEMIP kimlik listesi.")
    return kapali_sorgusu(_tarih(alt), _tarih(ust)) + f" AND IDENTIFIER IN ({', '.join(kimlikler)})"


def _cek(sorgu: str) -> list[dict[str, Any]]:
    akis = oracle.ayar(reportdb.KAYNAK).akis(oracle.sorgu_temizle(sorgu), SORGU_SINIRI + 1)
    kolonlar = [str(k).upper() for k in next(akis)]
    satirlar = [dict(zip(kolonlar, s, strict=True)) for blok in akis for s in blok]
    if len(satirlar) > SORGU_SINIRI:
        raise reportdb.ReportdbHata("TEMIP sorgusu satır sınırını aştı; aralığı daraltın.")
    return satirlar


def _metin(v: Any, azami: int) -> str:
    return " ".join(str(v).split())[:azami] if v not in (None, "") else ""


@musteri_alani.tum_alanlarda
def harita(db: Session) -> dict[str, set[int]]:
    """Musteri No anahtari -> kart id'leri (eslesme reportdb / Onedesk aktarimiyla ayni: yalniz numara)."""
    sonuc: dict[str, set[int]] = {}
    for cid, no in db.execute(select(Customer.id, Customer.customer_no)):
        for k in musteri_anahtarlari(no):
            sonuc.setdefault(k, set()).add(cid)
    return sonuc


def _kart(h: dict[str, set[int]], musteri_no: str) -> int | None:
    adaylar = h.get(anahtar(musteri_no), set())
    return next(iter(adaylar)) if len(adaylar) == 1 else None


# --- Eslesme: Musteri No -> TEMIP unvani -> kart -> sorumlu personel -> acik kayit ---------------------------------------
def kart_bilgisi(db: Session) -> dict[int, dict[str, Any]]:
    """Kart id -> numara, panel unvani, cati, sorumlu personel (kart sahibi; bossa catinin sahibi) ve personelin TAM olup olmadigi."""
    from app.kullanicilar import musteri_personeli_mi  # gec import: isci tarafinda kullanici modulunu gereksiz yuklemez
    from app.models import AppUser

    kisiler = {u.id: u for u in db.scalars(select(AppUser))}
    kartlar = {c.id: c for c in db.scalars(select(Customer))}
    sonuc: dict[int, dict[str, Any]] = {}
    for cid, c in kartlar.items():
        cati = kartlar.get(c.parent_id) if c.parent_id else None
        kisi = kisiler.get(c.owner_id or (cati.owner_id if cati else None) or -1)
        sonuc[cid] = {
            "kart_no": c.customer_no or "",
            "panel_unvan": c.name or "",
            "cati": cati.name if cati else "",
            "personel": (kisi.display_name or kisi.username) if kisi else "",
            "personel_kullanici": kisi.username if kisi else "",
            "personel_tam": musteri_personeli_mi(kisi),
        }
    return sonuc


class Eslesme:
    """Kayitlari Musteri No'ya gore toplar ve kartlar / personel ile eslestirir (DB'ye yazmaz). Kural yazimla ayni: _kart()."""

    def __init__(self, h: dict[str, set[int]], kartlar: dict[int, dict[str, Any]]):
        self.h, self.kartlar = h, kartlar
        self.musteri: dict[str, dict[str, Any]] = {}

    def ekle(self, musteri_no: str, unvan: str, acik: bool, ticketli: bool, adet: int = 1) -> None:
        m = self.musteri.setdefault(
            anahtar(musteri_no), {"musteri_no": musteri_no, "temip_unvan": "", "acik": 0, "acik_ticketli": 0, "kapali": 0}
        )
        m["temip_unvan"] = m["temip_unvan"] or unvan
        if acik:
            m["acik"] += adet
            m["acik_ticketli"] += adet if ticketli else 0
        else:
            m["kapali"] += adet

    def sonuc(self) -> dict[str, Any]:
        musteriler, kisiler = [], {}
        for k, m in self.musteri.items():
            adaylar = self.h.get(k, set())
            cid = next(iter(adaylar)) if len(adaylar) == 1 else None
            kart = self.kartlar.get(cid, {}) if cid else {}
            durum = "kart" if cid else ("belirsiz" if adaylar else "radar")
            if cid and not kart.get("personel_tam"):
                durum = "kart_personelsiz"  # kayit karta baglanir ama hicbir TAM'in portfoyunde gorunmez
            satir = {**m, "durum": durum, "kart_id": cid or "", "toplam": m["acik"] + m["kapali"],
                     "aday_kartlar": ", ".join(self.kartlar.get(i, {}).get("panel_unvan", str(i)) for i in sorted(adaylar)) if len(adaylar) > 1 else "",
                     **{a: kart.get(a, "") for a in ("panel_unvan", "cati", "personel", "personel_kullanici")}}  # fmt: skip
            musteriler.append(satir)
            if cid:
                p = kisiler.setdefault(kart.get("personel_kullanici") or "-", {
                    "personel": kart.get("personel") or "-", "personel_kullanici": kart.get("personel_kullanici") or "",
                    "tam": bool(kart.get("personel_tam")), "kart": set(), "musteri_no": 0, "acik": 0, "acik_ticketli": 0, "kapali": 0})  # fmt: skip
                p["kart"].add(cid)
                p["musteri_no"] += 1
                for a in ("acik", "acik_ticketli", "kapali"):
                    p[a] += m[a]
        musteriler.sort(key=lambda r: (r["durum"] != "kart", -r["acik"], -r["toplam"], r["musteri_no"]))
        personel = sorted(({**p, "kart": len(p["kart"])} for p in kisiler.values()), key=lambda p: (-p["acik"], p["personel"]))
        ozet: dict[str, Any] = {d: {"musteri": 0, "acik": 0, "kapali": 0} for d in ("kart", "kart_personelsiz", "radar", "belirsiz")}
        for r in musteriler:
            o = ozet[r["durum"]]
            o["musteri"] += 1
            o["acik"] += r["acik"]
            o["kapali"] += r["kapali"]
        eslesen_kart = {r["kart_id"] for r in musteriler if r["kart_id"]}
        numarali = {cid for ks in self.h.values() for cid in ks}
        uyari = {
            "belirsiz_numara": [r["musteri_no"] for r in musteriler if r["durum"] == "belirsiz"],
            "personelsiz_kart": sorted({r["panel_unvan"] for r in musteriler if r["durum"] == "kart_personelsiz"}),
            # kart numarasi TEMIP bicimine (8 hane) uymuyor: bu numarayla hic kayit eslesmez
            "bicimsiz_kart_no": sorted(
                {self.kartlar[c]["panel_unvan"] for k, ks in self.h.items() if len(k) > 8 for c in ks if c in self.kartlar}
            ),
            "kayitsiz_numarali_kart": len(numarali - eslesen_kart),
        }
        return {"ozet": ozet, "musteriler": musteriler, "personel": personel, "uyari": uyari}


_GRUP_ONBELLEK: tuple[str, tuple[list, list]] | None = None  # (surum, (durum gruplari, kart gruplari)): yazim turu degisince yenilenir
_GRUP_KILIT = threading.Lock()


def _gruplar(db: Session) -> tuple[list, list]:
    """Kayitlarin Musteri No / durum / ticket ve Musteri No / kart gruplari. Panelde her yazim surumu degistirir: surum ayniysa onbellek."""
    global _GRUP_ONBELLEK
    iz = surum(db)
    with _GRUP_KILIT:
        if iz and _GRUP_ONBELLEK is not None and _GRUP_ONBELLEK[0] == iz:
            return _GRUP_ONBELLEK[1]
    ticketli = OnedeskRecord.ticket_no != ""
    durumlar = db.execute(
        select(OnedeskRecord.customer_no, func.max(OnedeskRecord.customer_label), OnedeskRecord.status, ticketli, func.count())
        .where(OnedeskRecord.source == KAYNAK_ADI)
        .group_by(OnedeskRecord.customer_no, OnedeskRecord.status, ticketli)
    ).all()
    kartlar = db.execute(
        select(OnedeskRecord.customer_no, OnedeskRecord.customer_id, func.count())
        .where(OnedeskRecord.source == KAYNAK_ADI)
        .group_by(OnedeskRecord.customer_no, OnedeskRecord.customer_id)
    ).all()
    sonuc = ([tuple(r) for r in durumlar], [tuple(r) for r in kartlar])
    if iz:
        with _GRUP_KILIT:
            _GRUP_ONBELLEK = (iz, sonuc)
    return sonuc


@musteri_alani.tum_alanlarda
def eslesme_raporu(db: Session) -> dict[str, Any]:
    """Paneldeki TEMIP kayitlarinin eslesmesi, SU ANKI kart numaralarina gore (sonraki turun baglayacagi hal). Kart ve personel her
    cagrida tazedir; kayit gruplari yazim surumune gore onbellekte (on binlerce kayitta gruplama istek basina tekrarlanmaz)."""
    e = Eslesme(harita(db), kart_bilgisi(db))
    durumlar, kartlar = _gruplar(db)
    for no, unvan, durum, ticketli, adet in durumlar:
        e.ekle(no or "", unvan or "", durum == "open", bool(ticketli), int(adet))
    rapor = e.sonuc()
    h = e.h
    bekleyen = sum(int(adet) for no, cid, adet in kartlar if _kart(h, no or "") != cid)
    rapor["bagli_olmayan"] = bekleyen  # kart numarasi degismis, sonraki turda yeniden baglanacak kayit
    return rapor


def onizle(db: Session, kip: str = "artimli", gun: int = MUTABAKAT_GUN) -> dict[str, Any]:
    """Kuru deneme: calistir() ile ayni sorgular, HICBIR SEY YAZILMAZ. Satirlar akarken eslesmeye eklenir (tam kipte bellek sabit)."""
    if kip not in ("tam", "artimli", "mutabakat"):
        raise reportdb.ReportdbHata("Kip tam, artimli ya da mutabakat olmalı.")
    bas = baslangic()
    h = harita(db)
    e = Eslesme(h, kart_bilgisi(db))
    kapali_kimlik: set[str] = set()
    ozet: dict[str, Any] = {"kip": kip, "baslangic": bas.isoformat(), "kapali_satir": 0, "acik_satir": 0, "aylar": []}

    def kapali(satirlar: list[dict[str, Any]]) -> None:
        for s in satirlar:
            if (a := alanlar(s, False, h)) is not None and a["external_key"] not in kapali_kimlik:
                kapali_kimlik.add(a["external_key"])
                e.ekle(a["customer_no"], a["customer_label"], False, bool(a["ticket_no"]))
        ozet["kapali_satir"] += len(satirlar)

    if kip == "tam":
        for alt, ust in _aylar(bas, simdi().astimezone(TR_SAATI).date()):
            satirlar = _cek(kapali_sorgusu(_tarih(alt), f"LEAST({_tarih(ust)}, SYSDATE + 1)"))
            kapali(satirlar)
            ozet["aylar"].append({"ay": f"{alt:%Y-%m}", "satir": len(satirlar)})
    else:
        geri = ARTIMLI_GUN if kip == "artimli" else max(1, int(gun))
        kapali(_cek(kapali_sorgusu(f"GREATEST(SYSDATE - {geri}, {_tarih(bas)})", "SYSDATE + 1")))
    for s in _cek(acik_sorgusu(bas)):
        if (a := alanlar(s, True, h)) is not None and a["external_key"] not in kapali_kimlik:
            e.ekle(a["customer_no"], a["customer_label"], True, bool(a["ticket_no"]))
            ozet["acik_satir"] += 1
    db.rollback()
    return {**ozet, **e.sonuc()}


def alanlar(satir: dict[str, Any], acik: bool, h: dict[str, set[int]]) -> dict[str, Any] | None:
    """TEMIP satiri -> onedesk_record alanlari. Kimliksiz satir None."""
    kimlik = _metin(satir.get("KIMLIK"), 80)
    if not _KIMLIK.match(kimlik):
        return None
    mno = _metin(satir.get("MNO"), 20)
    acilis = tarih_oku(satir.get("ACILIS")) or simdi()
    kapanis = None if acik else (tarih_oku(satir.get("KAPANIS")) or acilis)
    return {
        "kind": TUR,
        "source": KAYNAK_ADI,
        "external_key": kimlik,
        "customer_no": mno,
        "customer_id": _kart(h, mno),
        "customer_label": _metin(satir.get("UNVAN"), 200),
        "ticket_no": _metin(satir.get("TICKET"), 40),
        "location": _metin(satir.get("CI"), 200),
        "category": _metin(satir.get("BASLIK"), 200),
        "status": "open" if acik else "closed",
        "opened_at": acilis,
        "closed_at": kapanis,
        "detail": _metin(satir.get("DURUM"), 80),
    }


def yaz(db: Session, kayitlar: Iterable[dict[str, Any]], etkilenen: set[int], *, parca_commit: bool = False) -> dict[str, int]:
    """(source, IDENTIFIER) ile ekler / gunceller. Kapali kayit acik satirla yeniden acilmaz. etkilenen: sayaci yenilenecek kartlar."""
    sayac = {"eklenen": 0, "guncellenen": 0, "atlanan": 0}
    tekil: dict[str, dict[str, Any]] = {}
    for k in kayitlar:
        onceki = tekil.get(k["external_key"])
        if onceki is None or k["status"] == "closed":  # ayni turda iki kez gelirse kapali olan kazanir
            tekil[k["external_key"]] = k
    liste = list(tekil.values())
    for i in range(0, len(liste), PARCA):
        parca = liste[i : i + PARCA]
        mevcut = {
            r.external_key: r
            for r in db.scalars(
                select(OnedeskRecord).where(
                    OnedeskRecord.source == KAYNAK_ADI, OnedeskRecord.external_key.in_([k["external_key"] for k in parca])
                )
            )
        }
        for k in parca:
            r = mevcut.get(k["external_key"])
            if r is None:
                db.add(OnedeskRecord(**k, root_cause="", resolution=""))
                sayac["eklenen"] += 1
            elif r.status == "closed" and k["status"] == "open":
                sayac["atlanan"] += 1
                continue
            else:
                if r.customer_id:
                    etkilenen.add(r.customer_id)
                for alan, deger in k.items():
                    setattr(r, alan, deger)
                sayac["guncellenen"] += 1
            if k["customer_id"]:
                etkilenen.add(k["customer_id"])
        db.flush()
        if parca_commit:
            db.commit()
            db.expunge_all()
    return sayac


def _tr(an: datetime) -> datetime:
    """UTC (DB) -> Turkiye yerel saati, dilimsiz (Oracle DATE)."""
    return (an if an.tzinfo else an.replace(tzinfo=UTC)).astimezone(TR_SAATI).replace(tzinfo=None)


def dusen_acik_kayitlar(db: Session, acik_kimlikler: set[str]) -> list[tuple[str, datetime]]:
    """Panelde acik ama anlik goruntude artik olmayan TEMIP kayitlari: (IDENTIFIER, acilis)."""
    return [
        (k, a)
        for k, a in db.execute(
            select(OnedeskRecord.external_key, OnedeskRecord.opened_at).where(
                OnedeskRecord.source == KAYNAK_ADI, OnedeskRecord.status == "open"
            )
        )
        if k not in acik_kimlikler and a is not None
    ]


def kapanislari_cek(dusenler: list[tuple[str, datetime]], h: dict[str, set[int]]) -> list[dict[str, Any]]:
    """Dusen aciklarin kapali satirlarini VIEW_REPORT_ACTIVE'den IDENTIFIER ile ceker (acilis araligi +- 1 gun)."""
    sonuc: list[dict[str, Any]] = []
    dusenler = sorted(dusenler, key=lambda x: x[1])
    for i in range(0, len(dusenler), KAPANIS_PARCASI):
        parca = dusenler[i : i + KAPANIS_PARCASI]
        alt, ust = _tr(parca[0][1]) - timedelta(days=1), _tr(parca[-1][1]) + timedelta(days=1)
        for s in _cek(kimlik_sorgusu([k for k, _ in parca], alt, ust)):
            if (a := alanlar(s, False, h)) is not None:
                sonuc.append(a)
    return sonuc


@musteri_alani.tum_alanlarda
def yeniden_bagla(db: Session, h: dict[str, set[int]], etkilenen: set[int]) -> int:
    """Musteri No'ya gore kart baglantisini tazeler (kart eklendi / numara degisti): kartsizdan karta ya da tersi."""
    degisen = 0
    for no, cid in db.execute(
        select(OnedeskRecord.customer_no, OnedeskRecord.customer_id)
        .where(OnedeskRecord.source == KAYNAK_ADI)
        .group_by(OnedeskRecord.customer_no, OnedeskRecord.customer_id)
    ).all():
        beklenen = _kart(h, no or "")
        if beklenen == cid:
            continue
        kosul = OnedeskRecord.customer_id.is_(None) if cid is None else OnedeskRecord.customer_id == cid
        degisen += (
            db.execute(
                update(OnedeskRecord)
                .where(OnedeskRecord.source == KAYNAK_ADI, OnedeskRecord.customer_no == (no or ""), kosul)
                .values(customer_id=beklenen)
            ).rowcount
            or 0
        )
        etkilenen.update(i for i in (cid, beklenen) if i)
    return degisen


def surum(db: Session) -> str:
    ayar = db.get(AppSetting, SURUM_AYARI)
    return str((ayar.value or {}).get("an", "")) if ayar is not None and isinstance(ayar.value, dict) else ""


MUTABAKAT_SAATI = 2  # Turkiye saati: bu saatten sonraki ilk otomatik tur gunun mutabakatini yapar


def otomatik_kip(db: Session) -> str:
    """Zamanlanmis tur icin: gunde bir kez (MUTABAKAT_SAATI'nden sonra) 'mutabakat', digerleri 'artimli'."""
    yerel = simdi().astimezone(TR_SAATI)
    ayar = db.get(AppSetting, SURUM_AYARI)
    son = (ayar.value or {}).get("mutabakat_gunu", "") if ayar is not None and isinstance(ayar.value, dict) else ""
    return "mutabakat" if yerel.hour >= MUTABAKAT_SAATI and son != yerel.date().isoformat() else "artimli"


def _surum_yaz(db: Session, ozet: dict[str, Any]) -> None:
    an = simdi()
    ayar = db.get(AppSetting, SURUM_AYARI)
    onceki = ayar.value if ayar is not None and isinstance(ayar.value, dict) else {}
    gun = an.astimezone(TR_SAATI).date().isoformat() if ozet["kip"] in ("mutabakat", "tam") else onceki.get("mutabakat_gunu", "")
    deger = {
        "an": an.isoformat(),
        "kip": ozet["kip"],
        "eklenen": ozet["eklenen"],
        "guncellenen": ozet["guncellenen"],
        "mutabakat_gunu": gun,
    }
    if ayar is None:
        db.add(AppSetting(key=SURUM_AYARI, value=deger, updated_by=reportdb.ISCI, updated_at=an))
    else:
        ayar.value, ayar.updated_by, ayar.updated_at = deger, reportdb.ISCI, an


def _aylar(bas: date, bugun: date) -> list[tuple[date, date]]:
    dilimler = []
    alt = bas
    while alt <= bugun:
        ust = date(alt.year + (alt.month == 12), alt.month % 12 + 1, 1)
        dilimler.append((alt, ust))
        alt = ust
    return dilimler


def katalog_kapalilari(db: Session, bas: date, parca: int = 5_000) -> Iterator[list[dict[str, Any]]]:
    """Son hazir katalogun ham dosyasindaki VIEW_REPORT_ACTIVE satirlari -> TEMIP sorgu satiri bicimi (KIMLIK, MNO, ...), parca parca.
    Kosul _KOSUL ile ayni (domain, 8 haneli Musteri No, CI'da nw_li_cust); acilis `bas` ve sonrasi."""
    import sqlite3

    from app.tampon import katalog
    from app.tampon.models import SourceCatalog, SourceCatalogObject

    k = db.scalars(
        select(SourceCatalog)
        .where(SourceCatalog.source_key == katalog.KAYNAK, SourceCatalog.status == "ready")
        .order_by(SourceCatalog.id.desc())
        .limit(1)
    ).first()
    n = k and db.scalars(
        select(SourceCatalogObject).where(SourceCatalogObject.catalog_id == k.id, SourceCatalogObject.owner == "TEMIP", SourceCatalogObject.name == "VIEW_REPORT_ACTIVE")
    ).first()  # fmt: skip
    tablo = (((n.details or {}).get("arama") or {}).get("ham_tablo") if n else "") or ""
    yol = katalog.HAM_DIZIN / f"katalog_{k.id}.db" if k else None
    if not tablo or yol is None or not yol.is_file():
        raise reportdb.ReportdbHata("Ham katalog dosyası yok: önce Veri Girişi › ReportDB kataloğunu 01.01'den tarayın.")
    sutunlar = ("IDENTIFIER", "INFORMATION1", "INFORMATION2", "ALARMOBJECTOPERATORNO", "ADDITIONALTEXT", "NODE1", "ALARMHEADER",
                "EVENTTIME", "CLOSETIMESTAMP", "CLOSEUSERIDENTIFIER")  # fmt: skip
    q = chr(34)
    secim = ", ".join(f"{q}{c}{q}" for c in sutunlar)
    domain = ", ".join("?" * len(DOMAINLER))
    sql = (f"SELECT {secim} FROM {q}{tablo}{q} WHERE {q}__D{q} IN ({domain}) AND INFORMATION1 GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' "
           f"AND (INSTR(LOWER(MANAGEDOBJECT), ?) > 0 OR INSTR(LOWER(NODE1), ?) > 0) AND EVENTTIME >= ?")  # fmt: skip
    bag = sqlite3.connect(f"{yol.as_uri()}?mode=ro", uri=True)
    try:
        imlec = bag.execute(sql, [*DOMAINLER, CI_ARAMA, CI_ARAMA, f"{bas:%Y-%m-%d}"])
        while blok := imlec.fetchmany(parca):
            cikti = []
            for kimlik, mno, unvan, opno, metin, node1, baslik, acilis, kapanis, kapatan in blok:
                ci = _CI_ADI.search(metin or "")
                tk = _TICKET.match(str(opno or ""))
                kapatan = str(kapatan or "")
                durum = "Closed/" + (kapatan if kapatan in ("atm", "Auto-Clear") else ("-" if not kapatan else "operator"))
                cikti.append({"KIMLIK": str(kimlik), "MNO": mno, "UNVAN": (unvan or "")[:200], "TICKET": tk.group(0) if tk else "",
                              "CI": (ci.group(1) if ci else (node1 or ""))[:200], "BASLIK": (baslik or "")[:200], "ACILIS": acilis,
                              "KAPANIS": kapanis, "DURUM": durum})  # fmt: skip
            yield cikti
    finally:
        bag.close()


@musteri_alani.tum_alanlarda
def calistir(db: Session, kip: str = "artimli", gun: int = MUTABAKAT_GUN) -> dict[str, Any]:
    """TEMIP kayitlarini panele yazar. Siralama: kapananlar -> acik goruntu (kapaliyi acmaz) -> goruntuden dusenlerin kapanisi ->
    kart baglantilari -> kart sayaclari. Her adim commit eder; hata olursa yazilan kalir, sonraki tur tamamlar (yazim idempotent)."""
    if kip not in KIPLER:
        raise reportdb.ReportdbHata("Kip tam, artimli, mutabakat ya da katalogdan olmalı.")
    bas = baslangic()
    h = harita(db)
    etkilenen: set[int] = set()
    ozet: dict[str, Any] = {"kip": kip, "baslangic": bas.isoformat(), "eklenen": 0, "guncellenen": 0, "atlanan": 0, "kapanan_sorgu": 0}

    def topla(s: dict[str, int]) -> None:
        for k in ("eklenen", "guncellenen", "atlanan"):
            ozet[k] += s[k]

    alt_sinir = _tarih(bas)
    if kip == "katalogdan":
        # Ilk yukleme: kapananlar Oracle'i yeniden taramadan son hazir katalogun ham dosyasindan; sonra son 1 gun Oracle'dan
        n = 0
        for parca in katalog_kapalilari(db, bas):
            topla(yaz(db, (a for x in parca if (a := alanlar(x, False, h))), etkilenen, parca_commit=True))
            n += len(parca)
        ozet["katalog_satir"] = n
        satirlar = _cek(kapali_sorgusu(f"GREATEST(SYSDATE - {ARTIMLI_GUN}, {alt_sinir})", "SYSDATE + 1"))
        topla(yaz(db, (a for x in satirlar if (a := alanlar(x, False, h))), etkilenen, parca_commit=True))
        ozet["kapali_satir"] = len(satirlar)
    elif kip == "tam":
        for alt, ust in _aylar(bas, simdi().astimezone(TR_SAATI).date()):
            satirlar = _cek(kapali_sorgusu(_tarih(alt), f"LEAST({_tarih(ust)}, SYSDATE + 1)"))
            topla(yaz(db, (a for s in satirlar if (a := alanlar(s, False, h))), etkilenen, parca_commit=True))
            ozet.setdefault("aylar", []).append({"ay": f"{alt:%Y-%m}", "satir": len(satirlar)})
    else:
        geri = ARTIMLI_GUN if kip == "artimli" else max(1, int(gun))
        satirlar = _cek(kapali_sorgusu(f"GREATEST(SYSDATE - {geri}, {alt_sinir})", "SYSDATE + 1"))
        topla(yaz(db, (a for s in satirlar if (a := alanlar(s, False, h))), etkilenen, parca_commit=True))
        ozet["kapali_satir"] = len(satirlar)
    acik = [a for s in _cek(acik_sorgusu(bas)) if (a := alanlar(s, True, h))]
    topla(yaz(db, acik, etkilenen, parca_commit=True))
    ozet["acik_satir"] = len(acik)
    dusenler = dusen_acik_kayitlar(db, {a["external_key"] for a in acik})
    if dusenler:
        kapananlar = kapanislari_cek(dusenler, h)
        ozet["kapanan_sorgu"] = len(kapananlar)
        topla(yaz(db, kapananlar, etkilenen, parca_commit=True))
    ozet["dusen_acik"] = len(dusenler)
    ozet["yeniden_baglanan"] = yeniden_bagla(db, h, etkilenen)
    sayaclari_yenile(db, etkilenen)
    ozet["etkilenen_kart"] = len(etkilenen)
    _surum_yaz(db, ozet)
    db.commit()
    return ozet
