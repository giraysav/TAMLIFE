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

import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dil import m
from app.models import AppSetting, Customer, CustomerCi, ReportCircuit, ReportCircuitData, ReportCmdb
from app.musteri.servis import MusteriHata, duzenleyebilir_mi, musteri_getir, musteri_yaz_getir
from app.ortak import simdi
from app.rapor import loe, loe_trafik
from app.session import Principal
from app.tampon.eslestirme import musteri_anahtarlari

EN_AZ_ARAMA = 3
EN_COK_ARAMA = 200
EN_COK_SONUC = 100
# Arama sonucunda CINAME yaninda gosterilecek sutunlar (adinda bu parcalar gecen, dolu olanlar)
_GOSTER = ("IMT", "DESC", "ACIKLAMA", "PORT", "ORG_ADI", "SERVICE", "HIZ", "SPEED", "BANDWIDTH", "EXCHOURS", "ADRES", "ADDRESS")


METRIKLER = ("erisim", "trafik", "kayip", "jitter", "gecikme")
# 2026-11-27 kullanici: "eslesen veri icin grafige availability, in/out trafik, ploss, delay, jitter hepsini yazsin"
VARSAYILAN_METRIKLER = list(METRIKLER)
ZAMAN_BICIMI = "%Y-%m-%dT%H:%M"
# Gosterilmeyen alanlar: IP adresi tasiyanlar (envanter kurali: IP gosterilmez/alinmaz; 'ADDRESS' parcasi IPADDRESS'i de yakaliyordu)
_IP_ALANI = re.compile(r"(^|_)IP(_|ADDR|$)", re.IGNORECASE)
_IP_DEGERI = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


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
        # 2026-11-27 kullanici: "time range ve donem sinirlamali olmamali" (onceden 2024 alt siniri, 366 gun ve gelecek tarih siniri)
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
        if ad in ("CINAME", "CUSTOMERNO") or v in (None, "") or _IP_ALANI.search(ad) or _IP_DEGERI.search(str(v)):
            continue
        if any(p in ad.upper() for p in _GOSTER):
            sonuc.append((ad, str(v)[:200]))
    return sonuc


def _kart_anahtarlari(db: Session, musteri: Customer) -> list[str]:
    """Kartin ve (cati ise) istiraklerinin Musteri No anahtarlari: IMT bir istirakin numarasinda olabilir."""
    numaralar = [musteri.customer_no, *db.scalars(select(Customer.customer_no).where(Customer.parent_id == musteri.id))]
    return sorted({k for n in numaralar for k in musteri_anahtarlari(n)})


def _imt_cileri(db: Session, anahtarlar: list[str], imt: str) -> list[CustomerCi]:
    """IMT'ye bagli ONENT envanter CI'lari (kartin musteri numaralari icinde; ayni IMT ana + yedek hatta olabilir)."""
    if not anahtarlar or not loe.IMT_BICIMI.match(imt):
        return []
    sorgu = select(CustomerCi).where(CustomerCi.customer_key.in_(anahtarlar), CustomerCi.attrs["imt"].as_string() == imt)
    gorulen: dict[str, CustomerCi] = {}
    for ci in db.scalars(sorgu.order_by(CustomerCi.ci_name)):
        if ci.ci_name and ci.ci_name not in gorulen:
            gorulen[ci.ci_name] = ci
    return list(gorulen.values())


def _envanter_etiketi(ci: CustomerCi, imt: str) -> list[tuple[str, str]]:
    return [(ad, v) for ad, v in (("IMT", imt), (m("Hizmet", "Service"), ci.service or ""), (m("Durum", "Status"), ci.status or "")) if v]


def ara(db: Session, user: Principal, musteri_id: int, metin: str) -> dict[str, Any]:
    """Musterinin devrelerinde arama. IMT yazilirsa (2026-11-27 kullanici: "kullanici yalniz IMT ile grafik olusturabilsin") once
    ONENT envanterinde IMT -> CI adi; bulunamazsa ve diger metinlerde CMDB kopyasinda esnek arama (CI adi, aciklama, port ...)."""
    musteri = musteri_getir(db, user, musteri_id)
    q = " ".join((metin or "").split())[:EN_COK_ARAMA].casefold()
    anahtarlar = musteri_anahtarlari(musteri.customer_no)
    sonuc: dict[str, Any] = {"metin": q, "musteri_no_var": bool(anahtarlar), "kaynak": _kaynak_durumu(db), "sonuclar": [], "toplam": 0, "imt": None}
    if len(q) < EN_AZ_ARAMA or not anahtarlar:
        return sonuc
    secili = set(db.scalars(select(ReportCircuit.ciname).where(ReportCircuit.customer_id == musteri.id)))
    if loe.IMT_BICIMI.match(q) and (cis := _imt_cileri(db, _kart_anahtarlari(db, musteri), q)):
        sonuc["imt"] = q
        sonuc["sonuclar"] = [{"ci": c.ci_name, "alanlar": _envanter_etiketi(c, q), "secili": c.ci_name in secili} for c in cis[:EN_COK_SONUC]]
        sonuc["toplam"] = len(cis)
        return sonuc
    parcalar = q.split(" ")
    sorgu = select(ReportCmdb).where(ReportCmdb.customer_key.in_(anahtarlar))
    for p in parcalar:
        sorgu = sorgu.where(ReportCmdb.search_text.contains(p, autoescape=True))
    satirlar = db.scalars(sorgu.order_by(ReportCmdb.ciname)).all()
    gorulen: set[str] = set()
    for s in satirlar:
        if s.ciname in gorulen:
            continue
        gorulen.add(s.ciname)
        if len(sonuc["sonuclar"]) < EN_COK_SONUC:
            sonuc["sonuclar"].append({"ci": s.ciname, "alanlar": _etiket(s.fields or {}), "secili": s.ciname in secili})
    sonuc["toplam"] = len(gorulen)
    return sonuc


def olcum_tetikle() -> None:
    """Devre eklenince / aralik degisince olcumu bir sonraki isci turunu beklemeden ceker: `app.isci rapor-devre` ayri surecte
    (panel Oracle'a baglanmaz; katalog._ayri_baslat). Calisan tur varsa isci kilit nedeniyle atlar, veri sonraki turda gelir.
    2026-11-26 kullanici: "IMT'yi yazinca cizmesi uzun surdu" (veri saatlik isci turunu bekliyordu)."""
    import logging
    import sys
    from pathlib import Path

    from app.tampon import katalog

    backend = Path(__file__).resolve().parents[2]
    gunluk = backend / "var" / "logs"
    try:
        gunluk.mkdir(parents=True, exist_ok=True)
        katalog._ayri_baslat([sys.executable, "-m", "app.isci", "rapor-devre"], backend, gunluk / "isci_rapor_devre.log")
    except Exception:  # noqa: BLE001 - tetik basarisizsa veri saatlik isci turunda gelir
        logging.getLogger("tamlife.trafik").warning("rapor-devre tetiklenemedi", exc_info=True)


GRAFIK_ADI_UZUNLUK = 120


def grafik_adi(ad: str | None) -> str:
    """2026-11-27 kullanici: "grafige kullanici kendisi isim versin; ONENT ya da CMDB'den aldigi detaylari yazmasin". Bos: baslik CI adi."""
    return " ".join((ad or "").split())[:GRAFIK_ADI_UZUNLUK]


def _devre_ekle(db: Session, user: Principal, musteri: Customer, ci: str, ad: str) -> ReportCircuit:
    var = db.scalars(select(ReportCircuit).where(ReportCircuit.customer_id == musteri.id, ReportCircuit.ciname == ci)).first()
    if var is None:
        var = ReportCircuit(customer_id=musteri.id, ciname=ci, label=ad, added_by=user.username, added_at=simdi())
        db.add(var)
        db.flush()
    elif ad:
        var.label = ad
    return var


def _tum_metrikler(db: Session, user: Principal, musteri_id: int, aralik_sifirla: bool = False) -> None:
    """IMT ile olusturulan grafikte butun veriler (erisim, trafik, kayip, jitter, gecikme) cizilir. aralik_sifirla: 2026-11-27
    kullanici "IMT girilince o ayi kapsayan donem icin grafigi cizsin" - ozel tarih araligi kalkar, raporun donemi kullanilir."""
    ayar = ayar_oku(db, musteri_id)
    ar = None if aralik_sifirla else (ayar["aralik"] or {})
    if set(ayar["metrikler"]) != set(METRIKLER) or (aralik_sifirla and ayar["aralik"]):
        ayar_yaz(db, user, musteri_id, {"metrikler": list(METRIKLER), "bas_zaman": (ar or {}).get("bas"), "bit_zaman": (ar or {}).get("bit")})


def ekle(db: Session, user: Principal, musteri_id: int, ci: str | None = None, imt: str | None = None, ad: str | None = None) -> dict[str, Any]:
    """Devre ekleme: CI adi (CMDB kopyasindan ya da ONENT envanterinden) ya da IMT (IMT'ye bagli tum envanter CI'lari). ad: grafigin
    kullanicinin verdigi adi (bos olabilir)."""
    musteri = musteri_yaz_getir(db, user, musteri_id)
    imt = (imt or "").strip()
    ad = grafik_adi(ad)
    if imt:
        cis = _imt_cileri(db, _kart_anahtarlari(db, musteri), imt)
        if not cis:
            raise MusteriHata(404, m("Bu IMT müşterinin envanterinde bulunamadı.", "This IMT was not found in the customer's inventory."))
        eklenen = [_devre_ekle(db, user, musteri, c.ci_name, ad) for c in cis]
        _tum_metrikler(db, user, musteri.id, aralik_sifirla=True)
        return {"imt": imt, "eklenen": [{"id": v.id, "ci": v.ciname} for v in eklenen]}
    ci = (ci or "").strip()[:200]
    if not ci:
        raise MusteriHata(400, m("CI adı ya da IMT gerekli.", "A CI name or IMT is required."))
    anahtarlar = musteri_anahtarlari(musteri.customer_no)
    satir = db.scalars(select(ReportCmdb).where(ReportCmdb.ciname == ci, ReportCmdb.customer_key.in_(anahtarlar)).limit(1)).first()
    if satir is not None:
        var = _devre_ekle(db, user, musteri, ci, ad)
        return {"id": var.id, "ci": var.ciname}
    envanter = db.scalars(select(CustomerCi).where(CustomerCi.ci_name == ci, CustomerCi.customer_key.in_(_kart_anahtarlari(db, musteri))).limit(1)).first()
    if envanter is None:
        raise MusteriHata(404, m("Devre bu müşterinin CMDB kayıtlarında bulunamadı.", "Circuit not found in this customer's CMDB records."))
    var = _devre_ekle(db, user, musteri, ci, ad)
    return {"id": var.id, "ci": var.ciname}


def adlandir(db: Session, user: Principal, musteri_id: int, devre_id: int, ad: str | None) -> dict[str, Any]:
    """Secili devrenin grafik adini degistirir (bos: baslik CI adi)."""
    musteri = musteri_yaz_getir(db, user, musteri_id)
    var = db.get(ReportCircuit, devre_id)
    if var is None or var.customer_id != musteri.id:
        raise MusteriHata(404, m("Devre bulunamadı.", "Circuit not found."))
    var.label = grafik_adi(ad)
    return {"id": var.id, "ci": var.ciname, "ad": var.label}


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
            "trafik_eslesme": next(((v.summary or {}).get("trafik_eslesme") for v in aylik.values() if (v.summary or {}).get("trafik_eslesme")), ""),
        })  # fmt: skip
    return {
        "yil": yil,
        "ay": ay,
        "aralik": {"bas": bas.strftime(ZAMAN_BICIMI), "bit": bit.strftime(ZAMAN_BICIMI), "bas_ms": bas_ms, "bit_ms": bit_ms,
                   "ozel": bool(ayar["aralik"])},  # fmt: skip
        "duzenleyebilir": duzenleyebilir_mi(db, user, musteri),
        "trafik_var": loe_trafik.acik(),  # 2026-11-27: MSSQL LOE trafik kaynagi (app.rapor.loe_trafik)
        "ayar": ayar,
        "kaynak": _kaynak_durumu(db),
        "bekliyor": any(d["durum"] == "bekliyor" for d in devreler),
        "devreler": devreler,
    }
