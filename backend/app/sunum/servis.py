"""Ceyrek Bazli Sunum servisi. Kaynaklar tek kayitta (KAYNAKLAR: anahtar -> ad TR/EN -> ceyrek goruntusunu ureten fonksiyon).

Her panel modulu sunumda kendi alanina sahiptir (KAYNAKLAR'da modul basina en az bir kaynak; veri olmasa da alan cizilir).
Duzen (app_setting 'sunum.duzen' = {"sira": [...], "gizli": [...]}): alanlarin sirasi ve sunumdan cikarilanlar; Sunum sayfasindaki
'Sunum icerigi' penceresinden ve suruklenerek degistirilir. Varsayilan: hepsi gorunur, KAYNAKLAR sirasi (eski 'sunum.kaynaklar' secimi okunmaz).
Onay (app_setting 'sunum.onay.<donem>'): yetkili ceyregin sunumunu onaylayinca o anki ogeler ve sira kaydin icine yazilir; ceyrek bundan sonra
yalniz bu kayittan gosterilir, gonder/sabitle/kaldir reddedilir (409). Onayi kaldirmak sunumu yeniden duzenlenebilir yapar.

Gosterim kurali (donem, onaysiz):
  1. Kaynagin o ceyrege ait kaydi (presentation) varsa o gosterilir: elle gonderilmis/sabitlenmis ya da daha once dondurulmus.
  2. Kayit yoksa ve kaynak gorunurse:
     - icinde bulunulan ceyrek: her acilista CANLI hesaplanir, saklanmaz;
     - gecmis ceyrek: ilk goruntulemede hesaplanip DONDURULUR (sonra degismez; yetkili 'Guncelle' ile yeniler);
     - 'anlik' kaynak (donem filtresi yok, o anki durumu verir) yalniz bir onceki ceyrek icin dondurulur; daha eski ceyrege bugunku durum yazilmaz;
     - gelecek ceyrek hesaplanmaz (alan 'yok' durumuyla bos cizilir).
Goruntu ekip geneli kapsamla (yonetici gorunumu) tek kez hesaplanir, 'sunum' modulunu goren herkese aynidir.
Yonetim (gonder/sabitle/kaldir, duzen, onay) admin ya da rolgorunum.SUNUM_YETKISI ister; kontrol api katmanindadir.
Senkron (2026-10-15 kullanici bildirimi: "ceyrek sunuma akan veriler hatali"): karsilastir() her gorunur kaynagin kayitli (dondurulmus /
sabitlenmis / onayli) goruntusunu canli hesapla kiyaslar; senkronla() farkli ya da hic dondurulmemis olanlari canli veriyle yeniler (yetkili,
elle tetiklenir). Onayli ceyrek senkronlanmaz (409): once onay kaldirilir. 'Anlik' kaynagin eski ceyrekleri kapsam disidir (bugunku durum
gecmise yazilmaz).
Yuk bicimi: 'takvim' kendi grafigi icin (takvim.servis.sunum_ozeti); digerleri {"kpi": [...], "tablo": {...}}. Arayuz her kaynagi KISA
bir kartla cizer (KPI'lar + ilk satirlar; tablonun tamami 'Ayrinti' altinda). tablo.onizleme (opsiyonel) ilk satirlarin hangi sutunlardan
cizilecegini soyler. 'stil' alani ozel cizim ister: 'sayilar' (Sayilarla TAM Ekibi) ve 'tanitim' (TAMLIFE tanitim sayfasi).
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import ariza
from app.catalog import get as modul
from app.gelir.servis import PARA_BIRIMLERI, tum_gelirler
from app.gelir_uretim.servis import sunum_ozeti as gelir_uretim_ozeti
from app.kullanicilar import kullanici_kaydi, personel
from app.models import ApnRevenue, AppSetting, Customer, Demand, Presentation, ProjectItem, SmsRevenue
from app.musteri.servis import portfoy
from app.navigation import PRESENTATION as MENU
from app.onedesk.servis import top10
from app.ortak import UygulamaHatasi, ay_adi, iso, rapor_donemi, simdi, tr_kucuk
from app.radar.servis import adaylar as radar_adaylari
from app.rapor.servis import durum_ozeti
from app.session import Principal
from app.skor.servis import siralama
from app.sunum import tanitim
from app.takvim.servis import bu_ceyrek, donem_adi, donem_araligi, sunum_ozeti
from app.takvim.servis import ekip as takvim_ekibi

AYAR_ANAHTARI = "sunum.duzen"
ONAY_ONEKI = "sunum.onay."
ONAYLI = "Bu çeyreğin sunumu onaylandı ve sabitlendi; değiştirmek için önce onayı kaldırın."
EKIP = Principal("sunum", "TeamMngr", False)  # ekip geneli kapsam (yonetici gorunumu); kullanici kaydi acan fonksiyona verilmez


class SunumHata(UygulamaHatasi):
    """kod = HTTP durumu."""


# --- genel kart yuku -------------------------------------------------------------------------------
def _kpi(ad: str, ad_en: str, deger: float | None, birim: str = "", alt: str = "", alt_en: str = "", onceki: float | None = None, kod: str = "") -> dict:
    """alt/alt_en: degerin altindaki kisa not; onceki: bir onceki ceyregin degeri (arayuz farki gosterir); kod: ozel cizimde simge anahtari."""
    return {"ad": ad, "ad_en": ad_en, "deger": deger, "birim": birim, "alt": alt, "alt_en": alt_en or alt, "onceki": onceki, "kod": kod}


def _sutun(ad: str, ad_en: str, birim: str = "") -> dict:
    return {"ad": ad, "ad_en": ad_en, "birim": birim}


def _onizleme(adet: int, sira: int | None = None, etiket: int | None = None, deger: int | None = None, tavan: float | None = None) -> dict:
    """Kisa kartin ilk satirlari: gosterilecek satir sayisi ve tablo sutun numaralari (sira, etiket, deger); tavan: cubuk tam doluluk degeri (ornek skor 100)."""
    return {k: v for k, v in {"adet": adet, "sira": sira, "etiket": etiket, "deger": deger, "tavan": tavan}.items() if v is not None}


def _bir_onceki(yil: int, ceyrek: int) -> tuple[int, int]:
    return (yil, ceyrek - 1) if ceyrek > 1 else (yil - 1, 4)


# --- kaynaklar: (db, yil, ceyrek) -> goruntu -----------------------------------------------------------
def _takvim(db: Session, yil: int, ceyrek: int) -> dict:
    return sunum_ozeti(db, yil, ceyrek)


def _utilizasyon(db: Session, yil: int, ceyrek: int) -> dict:
    liste = siralama(db)
    skorlar = [r["avg_score"] for r in liste]
    return {
        "kpi": [
            _kpi("Sıralamadaki TAM", "TAMs ranked", len(liste)),
            _kpi("Ortalama skor", "Average score", round(sum(skorlar) / len(skorlar), 1) if skorlar else None),
            _kpi("En yüksek skor", "Highest score", max(skorlar, default=None)),
        ],
        "tablo": {
            "sutunlar": [_sutun("Sıra", "Rank"), _sutun("TAM", "TAM"), _sutun("Çatı müşteri", "Parent customers"), _sutun("Ortalama skor", "Average score")],
            "satirlar": [[r["rank"], r["full_name"], r["customer_count"], r["avg_score"]] for r in liste],
            "onizleme": _onizleme(3, sira=0, etiket=1, deger=3, tavan=100),
        },
    }


def _yuzde(parca: int, tam: int) -> str:
    return f" · %{round(100 * parca / tam)}" if tam else ""


def _rapor(db: Session, yil: int, ceyrek: int) -> dict:
    # Rapor donemi onceki aydir: bu ay hazirlanan rapor gecen ayin satirina yazilir, icinde bulunulan ay henuz beklenmez.
    son = rapor_donemi(simdi())
    aylar = [a for a in range(3 * ceyrek - 2, 3 * ceyrek + 1) if (yil, a) <= son]
    ozetler = [durum_ozeti(db, EKIP, ay, yil) for ay in aylar]
    tamlar: dict[int | None, list] = {}
    for i, o in enumerate(ozetler):
        for s in o["satirlar"]:
            satir = tamlar.setdefault(s["id"], [s["ad"], 0, *(["—"] * len(aylar))])
            satir[1] = s["musteri"]  # son ayin rapor birimi sayisi
            satir[2 + i] = f"{s['atilan']}/{s['musteri']}"
    return {
        "kpi": [_kpi(f"{ay_adi(a)} · atılan", f"{ay_adi(a, 'en')} · sent", o["toplam"]["atilan"], alt=f"/ {o['toplam']['musteri']}{_yuzde(o['toplam']['atilan'], o['toplam']['musteri'])}") for a, o in zip(aylar, ozetler, strict=True)],
        "tablo": {
            "sutunlar": [_sutun("TAM", "TAM"), _sutun("Rapor birimi", "Report units"), *(_sutun(f"{ay_adi(a)} atılan/birim", f"{ay_adi(a, 'en')} sent/units") for a in aylar)],
            "satirlar": list(tamlar.values()),
        },
    }


def _onedesk(db: Session, yil: int, ceyrek: int) -> dict:
    bas, son = donem_araligi(yil, ceyrek)
    v = top10(db, EKIP, yil, (datetime(bas.year, bas.month, bas.day, tzinfo=UTC), datetime(son.year, son.month, son.day, tzinfo=UTC) + timedelta(days=1)))
    t = v["toplam"]
    return {
        "kpi": [
            _kpi("Alarm", "Alarms", t["alarm"]),
            _kpi("Talep", "Requests", t["talep"]),
            _kpi("Şikayet", "Complaints", t["sikayet"]),
            _kpi("Kayıt oluşan müşteri", "Customers with records", v["musteri_sayisi"]),
        ],
        "tablo": {
            "sutunlar": [
                _sutun("Sıra", "Rank"),
                _sutun("Müşteri", "Customer"),
                _sutun("Alarm", "Alarms"),
                _sutun("Talep", "Requests"),
                _sutun("Şikayet", "Complaints"),
                _sutun("Toplam", "Total"),
                _sutun("En çok kayıt olan lokasyon", "Top location"),
            ],
            "satirlar": [[m["sira"], m["ad"], m["alarm"], m["talep"], m["sikayet"], m["toplam"], m["lokasyon"]] for m in v["musteriler"]],
            "onizleme": _onizleme(3, sira=0, etiket=1, deger=5),
        },
    }


def _sms(db: Session, yil: int, ceyrek: int) -> dict:
    aylar = range(3 * ceyrek - 2, 3 * ceyrek + 1)
    kayitlar = [r for r in tum_gelirler(db, SmsRevenue) if r.year == yil and r.month in aylar]
    toplam: dict[str, float] = defaultdict(float)
    tamlar: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in kayitlar:
        toplam[r.currency] += r.amount or 0
        tamlar[r.tam_name or "—"][r.currency] += r.amount or 0
    birimler = [b for b in PARA_BIRIMLERI if b in toplam]
    return {
        "kpi": [
            *(_kpi(f"Toplam {b}", f"Total {b}", round(toplam[b], 2), birim=b) for b in birimler),
            _kpi("Gelir kaydı", "Revenue records", len(kayitlar)),
            _kpi("Müşteri", "Customers", len({r.customer_name for r in kayitlar})),
        ],
        "tablo": {
            "sutunlar": [_sutun("TAM", "TAM"), *(_sutun(b, b, b) for b in birimler)],
            "satirlar": [[tam, *(round(v.get(b, 0), 2) for b in birimler)] for tam, v in sorted(tamlar.items(), key=lambda kv: tr_kucuk(kv[0]))],
        },
    }


def _apn(db: Session, yil: int, ceyrek: int) -> dict:
    bas, son = donem_araligi(yil, ceyrek)
    kayitlar = [r for r in tum_gelirler(db, ApnRevenue) if r.request_date and bas <= r.request_date <= son]
    tamlar: dict[str, list] = {}
    for r in kayitlar:
        s = tamlar.setdefault(r.tam_name or "—", [r.tam_name or "—", 0, 0, 0.0])
        s[1] += 1
        s[2] += 1 if r.delivery_date else 0
        s[3] = round(s[3] + (r.amount or 0), 2)
    teslim = sum(1 for r in kayitlar if r.delivery_date)
    return {
        "kpi": [
            _kpi("Kurulum talebi", "Installation requests", len(kayitlar)),
            _kpi("Teslim edilen", "Delivered", teslim),
            _kpi("Bekleyen", "Pending", len(kayitlar) - teslim),
            _kpi("Toplam tutar", "Total amount", round(sum(r.amount or 0 for r in kayitlar), 2), birim="TRY"),
        ],
        "tablo": {
            "sutunlar": [_sutun("TAM", "TAM"), _sutun("Kurulum", "Installations"), _sutun("Teslim", "Delivered"), _sutun("Tutar", "Amount", "TRY")],
            "satirlar": sorted(tamlar.values(), key=lambda s: tr_kucuk(s[0])),
        },
    }


def _portfoy(db: Session, yil: int, ceyrek: int) -> dict:
    o = portfoy(db, EKIP, adet=1)["ozet"]
    segmentler: dict[str, list] = {}
    for c in db.scalars(select(Customer).where(Customer.parent_id.is_(None))):
        s = segmentler.setdefault(c.segment or "—", [c.segment or "—", 0, 0, 0.0])
        s[1] += 1
        if c.score:
            s[2] += 1
            s[3] += c.score
    return {
        "kpi": [
            _kpi("Çatı müşteri", "Parent customers", o["cati"]),
            _kpi("İştirak", "Affiliates", o["istirak"]),
            _kpi("Skorlu müşteri", "Scored customers", o["skorlu"]),
            _kpi("Ortalama skor", "Average score", o["ortalama_skor"]),
        ],
        "tablo": {
            "sutunlar": [_sutun("Segment", "Segment"), _sutun("Çatı müşteri", "Parent customers"), _sutun("Skorlu", "Scored"), _sutun("Ortalama skor", "Average score")],
            "satirlar": [[a, n, k, round(t / k, 1) if k else None] for a, n, k, t in sorted(segmentler.values(), key=lambda s: -s[1])],
            "onizleme": _onizleme(6, etiket=0, deger=1),
        },
    }


def _proje(db: Session, yil: int, ceyrek: int) -> dict:
    bas, son = donem_araligi(yil, ceyrek)
    kalemler = list(db.scalars(select(ProjectItem)))
    acilan = [k for k in kalemler if k.created_at and bas <= k.created_at.date() <= son]
    kapanan = [k for k in kalemler if k.closed_date and bas <= k.closed_date <= son]
    suren = [k for k in kalemler if k.status != "kapandi"]
    adlar = {u.id: (u.display_name or u.username) for u in personel(db)}  # tek personel kumesi; yonetici/admin sahipli isler tek '—' satirinda
    tamlar: dict[int | None, list] = {}
    for k in kalemler:
        sahip = k.owner_id if k.owner_id in adlar else None
        s = tamlar.setdefault(sahip, [adlar.get(sahip, "—"), 0, 0, 0])
        s[1] += k in acilan
        s[2] += k in kapanan
        s[3] += k.status != "kapandi"
    return {
        "kpi": [
            _kpi("Çeyrekte açılan", "Opened in quarter", len(acilan)),
            _kpi("Çeyrekte kapanan", "Closed in quarter", len(kapanan)),
            _kpi("Süren proje", "Ongoing projects", len(suren)),
            _kpi("Beklemede", "On hold", sum(1 for k in suren if k.status == "beklemede")),
        ],
        "tablo": {
            "sutunlar": [_sutun("TAM", "TAM"), _sutun("Açılan", "Opened"), _sutun("Kapanan", "Closed"), _sutun("Süren", "Ongoing")],
            "satirlar": sorted((s for s in tamlar.values() if s[1] or s[2] or s[3]), key=lambda s: tr_kucuk(s[0])),
        },
    }


TALEP_DURUM = {
    "yeni": ("Yeni", "New"),
    "incelemede": ("İncelemede", "In review"),
    "planlandi": ("Planlandı", "Planned"),
    "yapiliyor": ("Yapılıyor", "In progress"),
    "tamamlandi": ("Tamamlandı", "Done"),
    "reddedildi": ("Reddedildi", "Rejected"),
}


def _talep(db: Session, yil: int, ceyrek: int) -> dict:
    bas, son = donem_araligi(yil, ceyrek)
    talepler = [t for t in db.scalars(select(Demand)) if t.opened_at and bas <= t.opened_at.date() <= son]
    sayim: dict[str, int] = defaultdict(int)
    for t in talepler:
        sayim[t.status] += 1
    return {
        "kpi": [
            _kpi("Açılan talep", "Requests opened", len(talepler)),
            _kpi("Tamamlanan", "Completed", sayim["tamamlandi"]),
            _kpi("Hata bildirimi", "Bug reports", sum(1 for t in talepler if t.kind == "hata")),
        ],
        "tablo": {
            "sutunlar": [_sutun(tr, en) for tr, en in TALEP_DURUM.values()],
            "satirlar": [[sayim[k] for k in TALEP_DURUM]] if talepler else [],
        },
    }


def _radar(db: Session, yil: int, ceyrek: int) -> dict:
    v = radar_adaylari(db)
    satirlar = v["satirlar"]
    return {
        "kpi": [
            _kpi("Radar adayı", "Radar candidates", len(satirlar)),
            _kpi("Toplam alarm", "Total alarms", sum(s["toplam"] for s in satirlar)),
        ],
        "tablo": {
            "sutunlar": [_sutun("Sıra", "Rank"), _sutun("Müşteri", "Customer"), _sutun("Aktif alarm", "Active alarms"), _sutun("Kapanan alarm", "Closed alarms")],
            "satirlar": [[s["sira"], s["unvan"], s["aktif"], s["kapanan"]] for s in satirlar],
            "onizleme": _onizleme(3, sira=0, etiket=1, deger=2),
        },
    }


# Sayilarla TAM Ekibi (ust yonetim sunumunun 3. slayti): proje kategorileri + toplantilar, onceki ceyrekle birlikte
SAYI_KATEGORILERI = (
    ("proje", "Proje", "Projects"),
    ("ddos", "DDoS optimizasyonu", "DDoS optimization"),
    ("topoloji", "Topoloji iyileştirme", "Topology improvement"),
    ("dc_tasima", "DC taşıma", "DC migration"),
    ("calisma", "Çalışma", "Work items"),
)


def _acilis(k: ProjectItem) -> date | None:
    return k.created_at.date() if k.created_at else None


def _kapanis(k: ProjectItem) -> date | None:
    """Kapanis tarihi; kapali ama tarihi girilmemis kalem son guncelleme gununde kapanmis sayilir."""
    if k.closed_date:
        return k.closed_date
    return k.updated_at.date() if k.status == "kapandi" and k.updated_at else None


def _ceyrekte_aktif(k: ProjectItem, bas: date, son: date) -> bool:
    """Ceyrekte yurutulen is: ceyrek sonundan once acilmis ve ceyrek basindan once kapanmamis."""
    acilis, kapanis = _acilis(k), _kapanis(k)
    return acilis is not None and acilis <= son and (kapanis is None or kapanis >= bas)


def _sayilar(db: Session, yil: int, ceyrek: int) -> dict:
    bas, son = donem_araligi(yil, ceyrek)
    onceki_bas, onceki_son = donem_araligi(*_bir_onceki(yil, ceyrek))
    kalemler = list(db.scalars(select(ProjectItem)))
    adlar = {u.id: (u.display_name or u.username) for u in personel(db)}  # tek personel kumesi; yonetici/admin sahipli isler tek '—' satirinda
    kpi: list[dict] = []
    tamlar: dict[int | None, list] = {}
    for i, (kod, ad, ad_en) in enumerate(SAYI_KATEGORILERI):
        kume = [k for k in kalemler if k.category == kod]
        aktif = [k for k in kume if _ceyrekte_aktif(k, bas, son)]
        acilan = sum(1 for k in aktif if (_acilis(k) or bas) >= bas)
        kapanan = sum(1 for k in aktif if (c := _kapanis(k)) is not None and c <= son)
        onceki = sum(1 for k in kume if _ceyrekte_aktif(k, onceki_bas, onceki_son))
        kpi.append(_kpi(ad, ad_en, len(aktif), alt=f"{acilan} açıldı · {kapanan} kapandı", alt_en=f"{acilan} opened · {kapanan} closed", onceki=onceki, kod=kod))
        for k in aktif:
            sahip = k.owner_id if k.owner_id in adlar else None
            satir = tamlar.setdefault(sahip, [adlar.get(sahip, "—"), *([0] * (len(SAYI_KATEGORILERI) + 1))])
            satir[1 + i] += 1
            satir[-1] += 1
    toplanti = takvim_ekibi(db, yil, ceyrek)["genel"]
    onceki_toplanti = takvim_ekibi(db, *_bir_onceki(yil, ceyrek))["genel"]
    kpi += [
        _kpi("Yüz yüze buluşma", "Face-to-face meetings", toplanti["yuzyuze"], onceki=onceki_toplanti["yuzyuze"], kod="yuz_yuze"),
        _kpi("Online toplantı", "Online meetings", toplanti["online"], onceki=onceki_toplanti["online"], kod="online"),
    ]
    return {
        "stil": "sayilar",
        "kpi": kpi,
        "tablo": {
            "sutunlar": [_sutun("TAM", "TAM"), *(_sutun(ad, ad_en) for _, ad, ad_en in SAYI_KATEGORILERI), _sutun("Toplam", "Total")],
            "satirlar": sorted(tamlar.values(), key=lambda s: (s[0] == "—", tr_kucuk(s[0]))),
        },
    }


def _izin(db: Session, yil: int, ceyrek: int) -> dict:
    """Izin&Takvim Yonetimi: ekibin ceyrekteki izin gunleri ve yapilan is / toplanti ozeti girilen gun sayilari (metinler sunuma gitmez)."""
    v = takvim_ekibi(db, yil, ceyrek)
    g = v["genel"]
    d = g["durumlar"]
    return {
        "kpi": [
            _kpi("İzin günü", "Leave days", g["izin_gun"]),
            _kpi("Yıllık izin", "Annual leave", d.get("yillik_izin", 0)),
            _kpi("Şirket izni", "Company leave", d.get("sirket_izni", 0)),
            _kpi("Raporlu", "Sick leave", d.get("raporlu", 0)),
            _kpi("Yapılan iş girilen gün", "Days with work notes", g["is_gunu"]),
            _kpi("Toplantı özeti girilen gün", "Days with meeting notes", g["ozet_gunu"]),
        ],
        "tablo": {
            "sutunlar": [
                _sutun("TAM", "TAM"), _sutun("İzin günü", "Leave days"), _sutun("Yıllık izin", "Annual leave"), _sutun("Şirket izni", "Company leave"),
                _sutun("Raporlu", "Sick leave"), _sutun("Yapılan iş girilen gün", "Days with work notes"), _sutun("Toplantı özeti girilen gün", "Days with meeting notes"),
            ],
            "satirlar": sorted(
                (
                    [u["ad"], u["izin_gun"], u["durumlar"].get("yillik_izin", 0), u["durumlar"].get("sirket_izni", 0), u["durumlar"].get("raporlu", 0), u["is_gunu"], u["ozet_gunu"]]
                    for u in v["uyeler"]
                ),
                key=lambda s: tr_kucuk(s[0]),
            ),
            "onizleme": _onizleme(3, etiket=0, deger=1),
        },
    }  # fmt: skip


def _bos_alan(db: Session, yil: int, ceyrek: int) -> dict:
    """Baglantili Araclar / Toptan: modul simdilik Musteri Yonetimi ekranini gosterir; kendi sunum
    ozeti modulun tasarimiyla gelecek. O zamana kadar alan bos durur (portfoy ozeti zaten kendi alaninda; uydurma veri yok)."""
    return {"kpi": [], "tablo": {"sutunlar": [], "satirlar": []}}


def _gelir_uretim(db: Session, yil: int, ceyrek: int) -> dict:
    """Gelir Faydasi Saglanan Isler: modulun kendi ozeti (iptaller haric, aylik tutarlar para birimi basina); kisa kartta ilk 3 is ve aylik tutari."""
    v = gelir_uretim_ozeti(db, yil, ceyrek)
    v["kpi"] = [_kpi(k["ad"], k["ad_en"], k["deger"], k["birim"], k["alt"]) for k in v["kpi"]]  # sunum KPI sozlesmesi (alt_en/onceki/kod)
    v["tablo"]["onizleme"] = _onizleme(3, etiket=0, deger=4)
    return v


def _tanitim(db: Session, yil: int, ceyrek: int) -> dict:
    v = tanitim.ozet(db)
    sayi = {s["kod"]: s for s in v["sayilar"]}
    kpi = [_kpi("Satır kod", "Lines of code", v["kod"]["satir"], kod="satir")] if v["kod"] else []
    kpi += [_kpi(sayi[k]["ad"], sayi[k]["ad_en"], sayi[k]["deger"], kod=k) for k in ("modul", "uc", "test") if k in sayi]
    return {"stil": "tanitim", "kpi": kpi, **v}


@dataclass(frozen=True)
class Kaynak:
    ad: str
    ad_en: str
    aciklama: str
    aciklama_en: str
    modul: str  # catalog modulu (verinin geldigi sayfa)
    uret: Callable[[Session, int, int], dict]
    anlik: bool = False  # donem filtresi yok: o anki durum (yalniz bir onceki ceyrek icin dondurulur)


# Varsayilan sira = sunumun akis sirasi (ust yonetim gundemi): once sayilar ve TAM Life, sonra isler, gelir, musteri, ekip, talepler.
# Her panel modulu (catalog, menude gorunen) en az bir kaynakla temsil edilir; test_her_modulun_sunumda_alani_var denetler.
KAYNAKLAR: dict[str, Kaynak] = {
    "sayilar": Kaynak(
        "Sayılarla TAM Ekibi", "TAM Team in Numbers",
        "Çeyrekte yürütülen proje, DDoS, topoloji, DC taşıma ve çalışma sayıları; yüz yüze ve online toplantılar (önceki çeyrekle).", "Projects, DDoS, topology, DC migration and work items run in the quarter, plus face-to-face and online meetings (vs. the previous quarter).",
        "proje", _sayilar,
    ),
    "tanitim": Kaynak(
        "TAM Life tanıtımı", "TAM Life introduction",
        "Panelin amacı, kapsamı ve faydası; kaç satır kod, hangi dil, kod ne yapıyor (ölçülür, elle yazılmaz; o anki durum).", "What the panel is for, covers and gives; lines of code, languages and what the code does (measured, not typed in; current state).",
        "sunum", _tanitim, anlik=True,
    ),
    "proje": Kaynak(
        "Takip edilen projeler özeti", "Tracked projects summary",
        "Çeyrekte açılan ve kapanan projeler, süren işler; TAM bazında.", "Projects opened and closed in the quarter and ongoing work, per TAM.",
        "proje", _proje,
    ),
    "gelir_uretim": Kaynak(
        "Gelir faydası sağlanan işler", "Work delivering revenue benefit",
        "Çeyrekte süren, gelir / tasarruf / verimlilik faydası sağlayan işler: tamamlananlar, aylık gelir ve efor kazancı.", "Work running in the quarter that delivers revenue, savings or efficiency benefit: completed items, monthly revenue and effort saved.",
        "gelir_uretim", _gelir_uretim,
    ),
    "sms": Kaynak(
        "ICT SMS gelir özeti", "ICT SMS revenue summary",
        "Çeyreğin aylarına girilen SMS gelirleri: para birimi ve TAM bazında toplam.", "SMS revenue entered for the quarter's months: totals per currency and TAM.",
        "tamsms", _sms,
    ),
    "apn": Kaynak(
        "APN kurulum özeti", "APN installation summary",
        "Talep tarihi çeyrekte olan APN kurulumları: teslim edilen, bekleyen ve tutar.", "APN installations requested in the quarter: delivered, pending and amount.",
        "tamapn", _apn,
    ),
    "onedesk": Kaynak(
        "Onedesk özeti", "Onedesk summary",
        "Çeyrekte açılan alarm, talep ve şikayet toplamları; en çok kayıt oluşan 10 müşteri.", "Alarms, requests and complaints opened in the quarter; top 10 customers by records.",
        "onedesk", _onedesk,
    ),
    "rapor": Kaynak(
        "Gönderilen aylık rapor durumu", "Sent monthly report status",
        "Çeyreğin her ayı için TAM bazında atılan / beklenen aylık rapor sayısı.", "Monthly reports sent / expected per TAM for each month of the quarter.",
        "rapor", _rapor,
    ),
    "portfoy": Kaynak(
        "Müşteri portföy özeti", "Customer portfolio summary",
        "Çatı / iştirak müşteri sayısı ve segment bazında ortalama skor (o anki durum).", "Parent / affiliate customer counts and average score per segment (current state).",
        "musteri", _portfoy, anlik=True,
    ),
    "utilizasyon": Kaynak(
        "TAM Utilizasyon sıralaması", "TAM Utilization ranking",
        "TAM'ların çatı müşterilerindeki ortalama final skora göre sıralaması (o anki skorlar).", "TAMs ranked by the average final score of their parent customers (current scores).",
        "utilizasyon", _utilizasyon, anlik=True,
    ),
    "takvim": Kaynak(
        "TAM Takvim özeti", "TAM Calendar summary",
        "Kişi bazında izin/gün durumu ve toplantılar (TAM Takvim grafiği).", "Leave/day status and meetings per person (TAM Calendar chart).",
        "takvim_ozet", _takvim,
    ),
    "izin": Kaynak(
        "İzin ve yapılan işler özeti", "Leave and work log summary",
        "Ekibin çeyrekteki izin günleri; yapılan iş ve toplantı özeti girilen gün sayıları (metinler sunuma gitmez).", "The team's leave days in the quarter; number of days with work and meeting notes (the texts are not shown).",
        "takvim", _izin,
    ),
    "talep": Kaynak(
        "Geliştirme talepleri özeti", "Development requests summary",
        "Çeyrekte açılan geliştirme talepleri ve durumları.", "Development requests opened in the quarter and their status.",
        "talep", _talep,
    ),
    "radar": Kaynak(
        "Müşteri radar özeti", "Customer radar summary",
        "Panelde kartı olmayan ama alarm kaydı oluşan ilk 10 müşteri (ReportDB verisi, o anki durum).", "Top 10 customers with alarm records but no card in the panel (ReportDB data, current state).",
        "radar", _radar, anlik=True,
    ),
    "baglantili": Kaynak(
        "Bağlantılı araçlar", "Connected tools",
        "Kurum içi bağlantılı araçlar (modül şimdilik Müşteri Yönetimi içeriğini gösterir; sunum özeti tasarımla gelecek).", "Internal connected tools (the module currently shows Customer Management; its summary comes with its design).",
        "baglantili", _bos_alan, anlik=True,
    ),
    "toptan": Kaynak(
        "Toptan", "Wholesale",
        "Toptan müşteriler (modül şimdilik Müşteri Yönetimi içeriğini gösterir; sunum özeti geliştirmeyle gelecek).", "Wholesale customers (the module currently shows Customer Management; its summary comes later).",
        "toptan", _bos_alan, anlik=True,
    ),
}  # fmt: skip


# --- sunum duzeni: alan sirasi ve gorunurluk ----------------------------------------------------------------
def duzen(db: Session) -> tuple[list[str], set[str]]:
    """(sira, gizli). Kayitta olmayan (yeni eklenen) kaynak sona eklenir ve gorunur."""
    kayit = db.get(AppSetting, AYAR_ANAHTARI)
    deger = kayit.value if kayit is not None and isinstance(kayit.value, dict) else {}
    sira = [k for k in dict.fromkeys(deger.get("sira") or []) if k in KAYNAKLAR]
    sira += [k for k in KAYNAKLAR if k not in sira]
    return sira, {k for k in deger.get("gizli") or [] if k in KAYNAKLAR}


def acik_kaynaklar(db: Session) -> list[str]:
    sira, gizli = duzen(db)
    return [k for k in sira if k not in gizli]


def kaynak_listesi(db: Session) -> list[dict]:
    sira, gizli = duzen(db)
    return [
        {
            "id": k,
            "ad": v.ad,
            "ad_en": v.ad_en,
            "aciklama": v.aciklama,
            "aciklama_en": v.aciklama_en,
            "modul": modul(v.modul).title,
            "modul_en": modul(v.modul).title_en,
            "anlik": v.anlik,
            "acik": k not in gizli,
            "grup": MENU.get(v.modul, ("",))[0] or "insights",  # work = Benim Yerim, insights = Raporlar, admin = Yonetim
        }
        for k in sira
        for v in (KAYNAKLAR[k],)
    ]


def kaynaklar_kaydet(db: Session, ham: object, actor: str, sira: object = None) -> list[str]:
    """ham: gorunur kaynaklar; sira (opsiyonel): alanlarin yeni sirasi (eksikler eski sirasiyla sona). Donus: gorunurler, sirasiyla."""
    def gecerli(x: object) -> bool:
        return isinstance(x, list) and all(isinstance(k, str) and k in KAYNAKLAR for k in x)

    if not gecerli(ham) or (sira is not None and not gecerli(sira)):
        raise SunumHata(400, "Kaynak listesi geçersiz.")
    eski, _ = duzen(db)
    yeni = list(dict.fromkeys([*(sira or []), *eski]))
    kayit = db.get(AppSetting, AYAR_ANAHTARI)
    if kayit is None:
        kayit = AppSetting(key=AYAR_ANAHTARI)
        db.add(kayit)
    kayit.value = {"sira": yeni, "gizli": [k for k in yeni if k not in ham]}
    kayit.updated_by, kayit.updated_at = actor[:120], simdi()
    db.flush()
    return acik_kaynaklar(db)


# --- onay: ceyregin sunumunu sabitleme ---------------------------------------------------------------------
def _onay_kaydi(db: Session, donem_: str) -> AppSetting | None:
    kayit = db.get(AppSetting, ONAY_ONEKI + donem_)
    return kayit if kayit is not None and isinstance(kayit.value, dict) else None


def _onay_ozeti(kayit: AppSetting) -> dict:
    return {"onaylayan": kayit.value.get("onaylayan", ""), "zaman": kayit.value.get("zaman")}


def onayla(db: Session, user: Principal, yil: int, ceyrek: int, onay: bool) -> dict:
    """onay=True: ceyregin o anki ogelerini (canli olanlar dahil) ve sirasini onay kaydina yazar; sunum bundan sonra yalniz oradan gosterilir.
    onay=False: kaydi siler; sunum yeniden duzenlenebilir ve canli/dondurulmus kurallarina doner."""
    _ceyrek_dogrula(yil, ceyrek)
    ad = donem_adi(yil, ceyrek)
    mevcut = _onay_kaydi(db, ad)
    if not onay:
        if mevcut is not None:
            db.delete(mevcut)
            db.flush()
        return {"donem": ad, "onay": None}
    if mevcut is not None:
        raise SunumHata(409, "Bu çeyreğin sunumu zaten onaylı.")
    if _zamani(yil, ceyrek) == "gelecek":
        raise SunumHata(400, "Henüz başlamamış çeyreğin sunumu onaylanamaz.")
    kisi = kullanici_kaydi(db, user).display_name or user.username
    an = iso(simdi())
    ogeler = [({**o, "durum": "kayitli", "gonderen": kisi, "zaman": an} if o["durum"] == "canli" else o) for o in donem(db, yil, ceyrek, user.username)["ogeler"]]
    db.add(AppSetting(key=ONAY_ONEKI + ad, value={"onaylayan": kisi, "zaman": an, "ogeler": ogeler}, updated_by=kisi[:120], updated_at=simdi()))
    db.flush()
    return {"donem": ad, "onay": {"onaylayan": kisi, "zaman": an}}


# --- ceyrek goruntusu -----------------------------------------------------------------------------------
def _ceyrek_dogrula(yil: int, ceyrek: int) -> None:
    if ceyrek not in (1, 2, 3, 4):
        raise SunumHata(400, "Çeyrek 1-4 olmalı.")
    donem_araligi(yil, ceyrek)  # yil denetimi


def _zamani(yil: int, ceyrek: int) -> str:
    simdiki = bu_ceyrek()
    return "guncel" if (yil, ceyrek) == simdiki else "gecmis" if (yil, ceyrek) < simdiki else "gelecek"


def _onceki_ceyrek() -> tuple[int, int]:
    return _bir_onceki(*bu_ceyrek())


def _oge(anahtar: str, durum: str, veri: dict | None = None, gonderen: str = "", zaman: str | None = None, kayit_no: str = "") -> dict:
    k = KAYNAKLAR.get(anahtar)
    return {
        "kaynak": anahtar,
        "ad": k.ad if k else anahtar,
        "ad_en": k.ad_en if k else anahtar,
        "anlik": bool(k and k.anlik),
        "durum": durum,  # canli | kayitli | yok | hata
        "gonderen": gonderen,  # bos = kendiliginden donduruldu
        "zaman": zaman,
        "veri": veri,
        "kayit_no": kayit_no[:8],
    }


def _sakla(db: Session, anahtar: str, donem: str, veri: dict, gonderen: str) -> Presentation:
    kayit = db.scalar(select(Presentation).where(Presentation.source == anahtar, Presentation.period == donem))
    if kayit is None:
        kayit = Presentation(source=anahtar, period=donem)
        db.add(kayit)
    kayit.title = f"{KAYNAKLAR[anahtar].ad} — {donem}"
    kayit.payload, kayit.sent_by, kayit.sent_at = veri, gonderen[:120], simdi()
    return kayit


def donem(db: Session, yil: int, ceyrek: int, kullanici: str) -> dict:
    """Ceyregin sunum ogeleri (kaynak sirasiyla). Gecmis ceyrekte ilk goruntulemede donduruleni yazar; commit cagiranda."""
    _ceyrek_dogrula(yil, ceyrek)
    ad, zamani = donem_adi(yil, ceyrek), _zamani(yil, ceyrek)
    onay = _onay_kaydi(db, ad)
    if onay is not None:
        return {"yil": yil, "ceyrek": ceyrek, "donem": ad, "zaman": zamani, "ogeler": onay.value.get("ogeler") or [], "onay": _onay_ozeti(onay)}
    kayitlar = {p.source: p for p in db.scalars(select(Presentation).where(Presentation.period == ad, Presentation.source != ""))}
    acik = acik_kaynaklar(db)
    ogeler: list[dict] = []
    dondurulen = False
    for anahtar in [*acik, *(k for k in kayitlar if k not in KAYNAKLAR)]:
        p = kayitlar.get(anahtar)
        if p is not None:
            ogeler.append(_oge(anahtar, "kayitli", p.payload, p.sent_by, iso(p.sent_at)))
            continue
        if zamani == "gelecek":
            ogeler.append(_oge(anahtar, "yok"))  # her modulun alani cizilir; veri ceyrek baslayinca gelir
            continue
        if zamani == "gecmis" and KAYNAKLAR[anahtar].anlik and (yil, ceyrek) != _onceki_ceyrek():
            ogeler.append(_oge(anahtar, "yok"))
            continue
        try:
            veri = KAYNAKLAR[anahtar].uret(db, yil, ceyrek)
        except Exception as exc:  # noqa: BLE001 - tek kaynagin hatasi sunumun geri kalanini dusurmez; ariza kaydi duser
            ogeler.append(_oge(anahtar, "hata", kayit_no=ariza.kaydet("TL-SRV-01", exc=exc, kaynak=f"sunum.{anahtar}", kullanici=kullanici)))
            continue
        if zamani == "guncel":
            ogeler.append(_oge(anahtar, "canli", veri, zaman=iso(simdi())))
        else:
            kayit = _sakla(db, anahtar, ad, veri, "")
            dondurulen = True
            ogeler.append(_oge(anahtar, "kayitli", veri, "", iso(kayit.sent_at)))
    if dondurulen:
        try:
            db.flush()
        except IntegrityError:  # ayni anda baska istek dondurdu: onun kaydi okunur
            db.rollback()
            return donem(db, yil, ceyrek, kullanici)
    return {"yil": yil, "ceyrek": ceyrek, "donem": ad, "zaman": zamani, "ogeler": ogeler, "onay": None}


def gonder(db: Session, user: Principal, kaynak: str, yil: int, ceyrek: int, gonder: bool) -> dict:
    """Kaynagin ceyrek goruntusunu sunuma sabitler (yeniden gonderim gunceller) ya da kaldirir. Ceyrek+kaynak basina tek kayit."""
    if kaynak not in KAYNAKLAR:
        raise SunumHata(404, "Sunum kaynağı bulunamadı.")
    _ceyrek_dogrula(yil, ceyrek)
    ad = donem_adi(yil, ceyrek)
    if _onay_kaydi(db, ad) is not None:
        raise SunumHata(409, ONAYLI)
    if not gonder:
        db.execute(delete(Presentation).where(Presentation.source == kaynak, Presentation.period == ad))
        return {"donem": ad, "kaynak": kaynak, "sunumda": None}
    kisi = kullanici_kaydi(db, user).display_name or user.username
    kayit = _sakla(db, kaynak, ad, KAYNAKLAR[kaynak].uret(db, yil, ceyrek), kisi)
    db.flush()
    return {"donem": ad, "kaynak": kaynak, "sunumda": {"gonderen": kayit.sent_by, "zaman": iso(kayit.sent_at)}}


# --- senkron: kayitli goruntu ile canli verinin karsilastirilmasi ---------------------------------------------------------
OYNAK_ANAHTARLAR = frozenset({"olcum"})  # her hesapta degisen zaman damgasi: karsilastirmaya girmez


def _sade(veri: object) -> object:
    if isinstance(veri, dict):
        return {k: _sade(v) for k, v in veri.items() if k not in OYNAK_ANAHTARLAR}
    if isinstance(veri, (list, tuple)):
        return [_sade(v) for v in veri]
    return veri


def _iz(veri: object) -> str:
    """Kalici (JSON) ve canli yuk ayni bicimde: anahtar sirasi, tuple/liste ve tarih farki yok sayilir."""
    return json.dumps(_sade(json.loads(json.dumps(veri, default=str))), sort_keys=True, ensure_ascii=False)


def _kpi_farklari(eski: object, yeni: object, en_cok: int = 6) -> list[dict]:
    """Ad bazinda degisen KPI degerleri (arayuz 'ne degisti' satiri icin)."""
    def harita(v: object) -> dict[str, object]:
        return {k.get("ad"): k.get("deger") for k in (v.get("kpi") or []) if isinstance(k, dict)} if isinstance(v, dict) else {}

    e, y = harita(eski), harita(yeni)
    return [{"ad": ad, "eski": e.get(ad), "yeni": y.get(ad)} for ad in dict.fromkeys([*y, *e]) if e.get(ad) != y.get(ad)][:en_cok]


def _kayitli_goruntuler(db: Session, ad: str) -> tuple[dict[str, dict], bool]:
    """(kaynak -> {veri, gonderen, zaman}, onayli_mi). Onayli ceyrekte onay kaydinin ogeleri, degilse presentation kayitlari."""
    onay = _onay_kaydi(db, ad)
    if onay is not None:
        return {o["kaynak"]: {"veri": o.get("veri"), "gonderen": o.get("gonderen", ""), "zaman": o.get("zaman")} for o in onay.value.get("ogeler") or [] if o.get("durum") == "kayitli"}, True
    kayitlar = db.scalars(select(Presentation).where(Presentation.period == ad, Presentation.source != ""))
    return {p.source: {"veri": p.payload, "gonderen": p.sent_by, "zaman": iso(p.sent_at)} for p in kayitlar}, False


def karsilastir(db: Session, yil: int, ceyrek: int, kullanici: str) -> dict:
    """Her gorunur kaynak icin durum: guncel (kayitli = canli) | farkli | eksik (gecmis ceyrek henuz dondurulmamis) | canli (icinde
    bulunulan ceyrek, kayit yok: zaten canli) | kapsam_disi (gelecek ceyrek ya da anlik kaynagin eski ceyregi) | hata. Hicbir sey yazmaz."""
    _ceyrek_dogrula(yil, ceyrek)
    ad, zamani = donem_adi(yil, ceyrek), _zamani(yil, ceyrek)
    kayitli, onayli = _kayitli_goruntuler(db, ad)
    satirlar: list[dict] = []
    for anahtar in acik_kaynaklar(db):
        k = KAYNAKLAR[anahtar]
        sakli = kayitli.get(anahtar)
        satir = {"kaynak": anahtar, "ad": k.ad, "ad_en": k.ad_en, "durum": "", "gonderen": (sakli or {}).get("gonderen", ""), "zaman": (sakli or {}).get("zaman"), "farklar": [], "kayit_no": ""}
        if zamani == "gelecek" or (zamani == "gecmis" and k.anlik and (yil, ceyrek) != _onceki_ceyrek()):
            satirlar.append({**satir, "durum": "kapsam_disi"})
            continue
        try:
            canli = k.uret(db, yil, ceyrek)
        except Exception as exc:  # noqa: BLE001 - tek kaynagin hatasi karsilastirmanin geri kalanini dusurmez
            satirlar.append({**satir, "durum": "hata", "kayit_no": ariza.kaydet("TL-SRV-01", exc=exc, kaynak=f"sunum.karsilastir.{anahtar}", kullanici=kullanici)[:8]})
            continue
        if sakli is None:
            satirlar.append({**satir, "durum": "canli" if zamani == "guncel" else "eksik"})
        elif _iz(sakli["veri"]) == _iz(canli):
            satirlar.append({**satir, "durum": "guncel"})
        else:
            satirlar.append({**satir, "durum": "farkli", "farklar": _kpi_farklari(sakli["veri"], canli)})
    sayilar = {d: sum(1 for s in satirlar if s["durum"] == d) for d in ("guncel", "farkli", "eksik", "canli", "kapsam_disi", "hata")}
    return {
        "yil": yil, "ceyrek": ceyrek, "donem": ad, "zaman": zamani, "onayli": onayli, "kontrol": iso(simdi()),
        "kaynaklar": satirlar, "sayilar": sayilar, "senkron_gerekli": bool(sayilar["farkli"] or sayilar["eksik"]),
    }  # fmt: skip


def senkronla(db: Session, user: Principal, yil: int, ceyrek: int) -> dict:
    """Farkli ve eksik kaynaklarin ceyrek goruntusunu canli veriyle yeniler (gonderen = tetikleyen). Onayli ceyrekte 409. Commit cagiranda."""
    _ceyrek_dogrula(yil, ceyrek)
    ad = donem_adi(yil, ceyrek)
    if _onay_kaydi(db, ad) is not None:
        raise SunumHata(409, "Bu çeyreğin sunumu onaylı; senkron için önce onayı kaldırın, senkrondan sonra yeniden onaylayın.")
    once = karsilastir(db, yil, ceyrek, user.username)
    kisi = kullanici_kaydi(db, user).display_name or user.username
    yenilenen = []
    for s in once["kaynaklar"]:
        if s["durum"] in ("farkli", "eksik"):
            _sakla(db, s["kaynak"], ad, KAYNAKLAR[s["kaynak"]].uret(db, yil, ceyrek), kisi)
            yenilenen.append(s["kaynak"])
    db.flush()
    return {"donem": ad, "yenilenen": yenilenen, "sonra": karsilastir(db, yil, ceyrek, user.username)}
