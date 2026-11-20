"""Aylik rapor devre grafikleri (panel tarafi): devre arama, musterinin secili devreleri ve donemin olcumleri.

2026-11-20 kullanici: "grafigi aylik range'e gore olusturacagiz, sinirlama olmayacak; range secimi aylik rapor modulunde yapilacak;
description ya da port bilgisi yazildiginda gelen musteri bilgisi kullanici degistirmedikce grafik olusmaya devam edecek; grafigi
olusturan donem raporun atilacagi ay ne ise ona gore".

Veri ReportDB'den (LOE sorgusu, app.rapor.loe) ReportDB iscisiyle gelir; panel sureci Oracle'a BAGLANMAZ, yalniz panel DB'sini okur:
  report_cmdb          CMDB kopyasi (arama)            report_circuit       musterinin secili devreleri (kalici)
  report_circuit_data  devre x ay saatlik olcum + ozet
Cizim tarayicida, React paketinden AYRI kodla (ekran-react/dist/rapor-trafik.js + Apache ECharts 6.1.0); PNG'ler rapor
onizlemesindeki grafik listesine katilir, PDF akisi degismez.

GET .../rapor/trafik?donem=YYYY-MM sozlesmesi:
  {"yil", "ay", "duzenleyebilir": bool, "kaynak": {"cmdb": {...}, "olcum": {...}}, "bekliyor": bool,
   "devreler": [{"id", "ci", "baslik", "durum": "hazir" | "bekliyor" | "veri_yok", "cekildi", "exchours", "ozet",
                 "noktalar": [[epoch_ms, erisim 0-1, gecikme, jitter, kayip 0-1, pencere 0/1], ...]}]}
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dil import m
from app.models import ReportCircuit, ReportCircuitData, ReportCmdb
from app.musteri.servis import MusteriHata, duzenleyebilir_mi, musteri_getir, musteri_yaz_getir
from app.ortak import simdi
from app.rapor import loe
from app.session import Principal
from app.tampon.eslestirme import musteri_anahtarlari

EN_AZ_ARAMA = 3
EN_COK_ARAMA = 200
EN_COK_SONUC = 100
# Arama sonucunda CINAME yaninda gosterilecek sutunlar (adinda bu parcalar gecen, dolu olanlar)
_GOSTER = ("DESC", "ACIKLAMA", "PORT", "ORG_ADI", "SERVICE", "HIZ", "SPEED", "BANDWIDTH", "EXCHOURS", "ADRES", "ADDRESS")


def _iso(z: Any) -> str | None:
    return z.isoformat() if z is not None else None


def _kaynak_durumu(db: Session) -> dict[str, Any]:
    d = loe.durum_oku(db)
    return {b: {k: (d.get(b) or {}).get(k) for k in ("son_basari", "son_deneme", "hata", "satir")} for b in ("cmdb", "olcum")}


def _etiket(alanlar: dict[str, Any]) -> list[tuple[str, str]]:
    sonuc = []
    for ad, v in alanlar.items():
        if ad in ("CINAME", "CUSTOMERNO") or v in (None, ""):
            continue
        if any(p in ad.upper() for p in _GOSTER):
            sonuc.append((ad, str(v)[:200]))
    return sonuc


def _baslik(alanlar: dict[str, Any]) -> str:
    return " · ".join(v for _, v in _etiket(alanlar)[:2])[:300]


def ara(db: Session, user: Principal, musteri_id: int, metin: str) -> dict[str, Any]:
    """Musterinin (Musteri No) CMDB devrelerinde esnek arama: CI adi, aciklama, port ... herhangi bir sutunda parca eslesmesi."""
    musteri = musteri_getir(db, user, musteri_id)
    q = " ".join((metin or "").split())[:EN_COK_ARAMA].casefold()
    anahtarlar = musteri_anahtarlari(musteri.customer_no)
    sonuc: dict[str, Any] = {"metin": q, "musteri_no_var": bool(anahtarlar), "kaynak": _kaynak_durumu(db), "sonuclar": [], "toplam": 0}
    if len(q) < EN_AZ_ARAMA or not anahtarlar:
        return sonuc
    parcalar = q.split(" ")
    sorgu = select(ReportCmdb).where(ReportCmdb.customer_key.in_(anahtarlar))
    for p in parcalar:
        sorgu = sorgu.where(ReportCmdb.search_text.contains(p, autoescape=True))
    satirlar = db.scalars(sorgu.order_by(ReportCmdb.ciname)).all()
    secili = set(db.scalars(select(ReportCircuit.ciname).where(ReportCircuit.customer_id == musteri.id)))
    gorulen: set[str] = set()
    for s in satirlar:
        if s.ciname in gorulen:
            continue
        gorulen.add(s.ciname)
        if len(sonuc["sonuclar"]) < EN_COK_SONUC:
            sonuc["sonuclar"].append({"ci": s.ciname, "alanlar": _etiket(s.fields or {}), "secili": s.ciname in secili})
    sonuc["toplam"] = len(gorulen)
    return sonuc


def ekle(db: Session, user: Principal, musteri_id: int, ci: str) -> dict[str, Any]:
    musteri = musteri_yaz_getir(db, user, musteri_id)
    ci = (ci or "").strip()[:200]
    anahtarlar = musteri_anahtarlari(musteri.customer_no)
    satir = db.scalars(select(ReportCmdb).where(ReportCmdb.ciname == ci, ReportCmdb.customer_key.in_(anahtarlar)).limit(1)).first() if ci else None
    if satir is None:
        raise MusteriHata(404, m("Devre bu müşterinin CMDB kayıtlarında bulunamadı.", "Circuit not found in this customer's CMDB records."))
    var = db.scalars(select(ReportCircuit).where(ReportCircuit.customer_id == musteri.id, ReportCircuit.ciname == ci)).first()
    if var is None:
        var = ReportCircuit(customer_id=musteri.id, ciname=ci, label=_baslik(satir.fields or {}), added_by=user.username, added_at=simdi())
        db.add(var)
        db.flush()
    return {"id": var.id, "ci": var.ciname}


def kaldir(db: Session, user: Principal, musteri_id: int, devre_id: int) -> dict[str, Any]:
    musteri = musteri_yaz_getir(db, user, musteri_id)
    var = db.get(ReportCircuit, devre_id)
    if var is None or var.customer_id != musteri.id:
        raise MusteriHata(404, m("Devre bulunamadı.", "Circuit not found."))
    db.delete(var)
    return {"silindi": devre_id}


def getir(db: Session, user: Principal, musteri_id: int, donem_kodu: str | None = None) -> dict[str, Any]:
    from app.rapor.servis import donem

    musteri = musteri_getir(db, user, musteri_id)
    yil, ay = donem(donem_kodu)
    secili = db.scalars(select(ReportCircuit).where(ReportCircuit.customer_id == musteri.id).order_by(ReportCircuit.id)).all()
    veriler = {
        k.ciname: k
        for k in db.scalars(select(ReportCircuitData).where(
            ReportCircuitData.year == yil, ReportCircuitData.month == ay, ReportCircuitData.ciname.in_([s.ciname for s in secili])))
    } if secili else {}  # fmt: skip
    devreler = []
    for s in secili:
        v = veriler.get(s.ciname)
        durum = "bekliyor" if v is None else ("hazir" if v.points else "veri_yok")
        devreler.append({
            "id": s.id, "ci": s.ciname, "baslik": s.label, "durum": durum, "cekildi": _iso(v.fetched_at) if v else None,
            "exchours": v.exchours if v else "", "ozet": v.summary if v else {}, "noktalar": v.points if v else [],
        })  # fmt: skip
    return {
        "yil": yil,
        "ay": ay,
        "duzenleyebilir": duzenleyebilir_mi(db, user, musteri),
        "kaynak": _kaynak_durumu(db),
        "bekliyor": any(d["durum"] == "bekliyor" for d in devreler),
        "devreler": devreler,
    }
