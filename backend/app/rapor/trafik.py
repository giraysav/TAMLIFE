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
PUT .../rapor/devre-ayar {"metrikler": [...], "bas_zaman": "YYYY-MM-DDTHH:MM" | null, "bit_zaman": ...}: grafik araligi (bos = raporun donemi).
"""

from __future__ import annotations

from datetime import datetime, timedelta
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
_GOSTER = ("IMT", "DESC", "ACIKLAMA", "PORT", "ORG_ADI", "SERVICE", "HIZ", "SPEED", "BANDWIDTH", "EXCHOURS", "ADRES", "ADDRESS")


METRIKLER = ("trafik", "kayip", "jitter", "gecikme")
VARSAYILAN_METRIKLER = ["kayip", "jitter", "gecikme"]
ZAMAN_BICIMI = "%Y-%m-%dT%H:%M"
EN_ERKEN = datetime(2024, 1, 1)
EN_UZUN_GUN = 366


def _ayar_anahtari(musteri_id: int) -> str:
    return f"rapor.devre_ayar.{musteri_id}"


def _zaman(v: Any) -> datetime | None:
    try:
        return datetime.strptime(str(v)[:16], ZAMAN_BICIMI) if v else None
    except ValueError:
        return None


def ayar_oku(db: Session, musteri_id: int) -> dict[str, Any]:
    """Grafik ayari: metrikler + istege bagli tarih araligi (Turkiye saati, dakika hassasiyeti). Aralik yoksa raporun donemi."""
    kayit = db.get(AppSetting, _ayar_anahtari(musteri_id))
    v = kayit.value if kayit is not None and isinstance(kayit.value, dict) else {}
    metrikler = [x for x in (v.get("metrikler") or []) if x in METRIKLER] if "metrikler" in v else list(VARSAYILAN_METRIKLER)
    ar = v.get("aralik") if isinstance(v.get("aralik"), dict) else None
    bas, bit = (_zaman(ar.get("bas")), _zaman(ar.get("bit"))) if ar else (None, None)
    aralik = {"bas": bas.strftime(ZAMAN_BICIMI), "bit": bit.strftime(ZAMAN_BICIMI)} if bas and bit and bit > bas else None
    return {"metrikler": metrikler, "aralik": aralik}


def ayar_yaz(db: Session, user: Principal, musteri_id: int, govde: dict[str, Any]) -> dict[str, Any]:
    """2026-11-21 kullanici: "raporda secili ay sartini kaldir; gun ay yil saat dakika secilebilsin, iki tarih araligi secimi".
    bas_zaman / bit_zaman bos ise aralik kalkar (raporun donemi kullanilir)."""
    musteri_yaz_getir(db, user, musteri_id)
    metrikler = [x for x in METRIKLER if x in set(govde.get("metrikler") or [])]
    bas, bit = _zaman(govde.get("bas_zaman")), _zaman(govde.get("bit_zaman"))
    aralik = None
    if govde.get("bas_zaman") or govde.get("bit_zaman"):
        if not bas or not bit or bit <= bas:
            raise MusteriHata(400, m("Bitiş, başlangıçtan sonra olmalı.", "End must be after start."))
        if bas < EN_ERKEN or bit > datetime.now() + timedelta(days=1):
            raise MusteriHata(400, m("Tarih aralığı geçersiz.", "Invalid date range."))
        if bit - bas > timedelta(days=EN_UZUN_GUN):
            raise MusteriHata(400, m(f"Aralık en fazla {EN_UZUN_GUN} gün olabilir.", f"The range can be at most {EN_UZUN_GUN} days."))
        aralik = {"bas": bas.strftime(ZAMAN_BICIMI), "bit": bit.strftime(ZAMAN_BICIMI)}
    deger = {"metrikler": metrikler, "aralik": aralik}
    kayit = db.get(AppSetting, _ayar_anahtari(musteri_id))
    if kayit is None:
        db.add(AppSetting(key=_ayar_anahtari(musteri_id), value=deger, updated_by=user.username, updated_at=simdi()))
    else:
        kayit.value, kayit.updated_by, kayit.updated_at = deger, user.username, simdi()
    return deger


def aylar(bas: datetime, bit: datetime) -> list[tuple[int, int]]:
    """Araligin kapsadigi aylar (yil, ay)."""
    sonuc, y, a = [], bas.year, bas.month
    while (y, a) <= (bit.year, bit.month):
        sonuc.append((y, a))
        y, a = (y + 1, 1) if a == 12 else (y, a + 1)
    return sonuc


def ozel_araliklar(db: Session) -> dict[int, tuple[datetime, datetime]]:
    """Isci icin: tarih araligi secilmis musteriler -> (bas, bit)."""
    sonuc = {}
    for k in db.scalars(select(AppSetting).where(AppSetting.key.like("rapor.devre_ayar.%"))):
        try:
            mid = int(k.key.rsplit(".", 1)[1])
        except ValueError:
            continue
        ar = (k.value or {}).get("aralik") if isinstance(k.value, dict) else None
        bas, bit = (_zaman(ar.get("bas")), _zaman(ar.get("bit"))) if isinstance(ar, dict) else (None, None)
        if bas and bit and bit > bas:
            sonuc[mid] = (bas, bit)
    return sonuc


def _ms(z: datetime) -> int:
    return int(z.replace(tzinfo=loe.TR).timestamp() * 1000)


def _aralik_ozeti(noktalar: list[list[Any]]) -> dict[str, Any]:
    """Secili araligin ozeti (saatlik toplam sure esit oldugundan LOE formulune denk ortalama): yalniz olcum penceresindeki saatler."""
    p = [n for n in noktalar if len(n) > 5 and n[5]]

    def ort(i: int) -> float | None:
        d = [n[i] for n in p if n[i] is not None]
        return sum(d) / len(d) if d else None

    return {"erisilebilirlik": ort(1), "gecikme": ort(2), "jitter": ort(3), "kayip": ort(4), "saat": len(noktalar), "pencere_saat": len(p)}


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
    ayar = ayar_oku(db, musteri.id)
    if ayar["aralik"]:
        bas, bit = _zaman(ayar["aralik"]["bas"]), _zaman(ayar["aralik"]["bit"])
    else:
        bas, son = loe.ay_araligi(yil, ay)
        bit = son - timedelta(minutes=1)
    bas_ms, bit_ms = _ms(bas), _ms(bit) + 59_999
    gereken = aylar(bas, bit)
    ilk, sonay = gereken[0][0] * 100 + gereken[0][1], gereken[-1][0] * 100 + gereken[-1][1]
    secili = db.scalars(select(ReportCircuit).where(ReportCircuit.customer_id == musteri.id).order_by(ReportCircuit.id)).all()
    veriler: dict[str, dict[tuple[int, int], ReportCircuitData]] = {}
    if secili:
        sorgu = select(ReportCircuitData).where(
            ReportCircuitData.ciname.in_([s.ciname for s in secili]),
            (ReportCircuitData.year * 100 + ReportCircuitData.month).between(ilk, sonay),
        )
        for k in db.scalars(sorgu):
            veriler.setdefault(k.ciname, {})[(k.year, k.month)] = k
    devreler = []
    for s in secili:
        aylik = veriler.get(s.ciname, {})
        eksik = [d for d in gereken if d not in aylik]
        noktalar = [n for d in gereken if d in aylik for n in (aylik[d].points or []) if bas_ms <= n[0] <= bit_ms]
        cekildi = max((v.fetched_at for v in aylik.values() if v.fetched_at), default=None)
        durum = "bekliyor" if eksik else ("hazir" if noktalar else "veri_yok")
        devreler.append({
            "id": s.id, "ci": s.ciname, "baslik": s.label, "durum": durum, "cekildi": _iso(cekildi),
            "exchours": next((v.exchours for v in aylik.values() if v.exchours), ""), "ozet": _aralik_ozeti(noktalar), "noktalar": noktalar,
        })  # fmt: skip
    return {
        "yil": yil,
        "ay": ay,
        "aralik": {"bas": bas.strftime(ZAMAN_BICIMI), "bit": bit.strftime(ZAMAN_BICIMI), "bas_ms": bas_ms, "bit_ms": bit_ms,
                   "ozel": bool(ayar["aralik"])},  # fmt: skip
        "duzenleyebilir": duzenleyebilir_mi(db, user, musteri),
        "trafik_var": loe.trafik_sutunlari() is not None,
        "ayar": ayar,
        "kaynak": _kaynak_durumu(db),
        "bekliyor": any(d["durum"] == "bekliyor" for d in devreler),
        "devreler": devreler,
    }
