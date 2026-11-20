"""Aylik rapor devre grafikleri (panel tarafi): devre arama, musterinin secili devreleri ve donemin olcumleri.

2026-11-20 kullanici: "grafigi aylik range'e gore olusturacagiz, sinirlama olmayacak; range secimi aylik rapor modulunde yapilacak;
description ya da port bilgisi yazildiginda gelen musteri bilgisi kullanici degistirmedikce grafik olusmaya devam edecek; grafigi
olusturan donem raporun atilacagi ay ne ise ona gore".

Veri ReportDB'den (LOE sorgusu, app.rapor.loe) ReportDB iscisiyle gelir; panel sureci Oracle'a BAGLANMAZ, yalniz panel DB'sini okur:
  report_cmdb          CMDB kopyasi (arama)            report_circuit       musterinin secili devreleri (kalici)
  report_circuit_data  devre x ay saatlik olcum + ozet
Cizim tarayicida, React paketinden AYRI kodla (ekran-react/dist/rapor-trafik.js + Apache ECharts 6.1.0); PNG'ler rapor
onizlemesindeki grafik listesine katilir, PDF akisi degismez.

2026-11-20 (2): "aciklama metnini kaldir; trafik, ploss, jitter, delay checkbox koy; tiklandiginda o veriyi db'den alip tek grafik
uzerinde olustursun; grafigi olustururken saat secimi olsun". Grafik ayari (metrikler + saat araligi) musteri basina kalicidir
(app_setting 'rapor.devre_ayar.<musteri_id>'); her devre icin secili metrikler TEK grafikte cizilir.

GET .../rapor/trafik?donem=YYYY-MM sozlesmesi:
  {"yil", "ay", "duzenleyebilir": bool, "trafik_var": bool, "ayar": {"metrikler": [...], "saat": [bas, bit]}, "kaynak": {"cmdb": {...}, "olcum": {...}}, "bekliyor": bool,
   "devreler": [{"id", "ci", "baslik", "durum": "hazir" | "bekliyor" | "veri_yok", "cekildi", "exchours", "ozet",
                 "noktalar": [[epoch_ms, erisim 0-1, gecikme ms, jitter ms, kayip 0-1, pencere 0/1, giris bps, cikis bps], ...]}]}
PUT .../rapor/devre-ayar {"metrikler": [...], "bas": 0-23, "bit": 0-23}: saat araligi bas:00 - bit:59 (bas > bit: gece yarisini asar).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dil import m
from app.models import AppSetting, ReportCircuit, ReportCircuitData, ReportCmdb
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


METRIKLER = ("trafik", "kayip", "jitter", "gecikme")
VARSAYILAN_AYAR = {"metrikler": ["kayip", "jitter", "gecikme"], "saat": [0, 23]}


def _ayar_anahtari(musteri_id: int) -> str:
    return f"rapor.devre_ayar.{musteri_id}"


def ayar_oku(db: Session, musteri_id: int) -> dict[str, Any]:
    kayit = db.get(AppSetting, _ayar_anahtari(musteri_id))
    v = kayit.value if kayit is not None and isinstance(kayit.value, dict) else {}
    metrikler = [x for x in (v.get("metrikler") or []) if x in METRIKLER] if "metrikler" in v else list(VARSAYILAN_AYAR["metrikler"])
    saat = v.get("saat") if isinstance(v.get("saat"), list) and len(v["saat"]) == 2 else VARSAYILAN_AYAR["saat"]
    return {"metrikler": metrikler, "saat": [int(saat[0]) % 24, int(saat[1]) % 24]}


def ayar_yaz(db: Session, user: Principal, musteri_id: int, govde: dict[str, Any]) -> dict[str, Any]:
    musteri_yaz_getir(db, user, musteri_id)
    metrikler = [x for x in METRIKLER if x in set(govde.get("metrikler") or [])]
    try:
        bas, bit = int(govde.get("bas", 0)), int(govde.get("bit", 23))
    except (TypeError, ValueError):
        raise MusteriHata(400, m("Saat aralığı geçersiz.", "Invalid hour range.")) from None
    if not (0 <= bas <= 23 and 0 <= bit <= 23):
        raise MusteriHata(400, m("Saat aralığı geçersiz.", "Invalid hour range."))
    deger = {"metrikler": metrikler, "saat": [bas, bit]}
    kayit = db.get(AppSetting, _ayar_anahtari(musteri_id))
    if kayit is None:
        db.add(AppSetting(key=_ayar_anahtari(musteri_id), value=deger, updated_by=user.username, updated_at=simdi()))
    else:
        kayit.value, kayit.updated_by, kayit.updated_at = deger, user.username, simdi()
    return deger


def _iso(z: Any) -> str | None:
    return z.isoformat() if z is not None else None


def _kaynak_durumu(db: Session) -> dict[str, Any]:
    """Ekran icin yalniz zaman ve hata VAR/YOK: kullaniciya kaynak adi ya da ham veritabani hatasi gitmez (2026-11-20 kullanici:
    "panelde kullanicilara acilan her noktada veriyi aldigimiz kaynagin adini yazdirma"). Ayrinti isci gunlugunde ve yonetimde."""
    d = loe.durum_oku(db)
    return {
        b: {"son_basari": (d.get(b) or {}).get("son_basari"), "son_deneme": (d.get(b) or {}).get("son_deneme"), "hata": bool((d.get(b) or {}).get("hata"))}
        for b in ("cmdb", "olcum")
    }


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
        "trafik_var": loe.trafik_sutunlari() is not None,
        "ayar": ayar_oku(db, musteri.id),
        "kaynak": _kaynak_durumu(db),
        "bekliyor": any(d["durum"] == "bekliyor" for d in devreler),
        "devreler": devreler,
    }
