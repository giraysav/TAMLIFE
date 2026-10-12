"""Ceyrek Bazli Sunum servisi. Kaynaklar tek kayitta (KAYNAKLAR: anahtar -> ad TR/EN -> ceyrek goruntusunu ureten fonksiyon).

Gosterim kurali (donem):
  1. Kaynagin o ceyrege ait kaydi (presentation) varsa o gosterilir: elle gonderilmis/sabitlenmis ya da daha once dondurulmus.
  2. Kayit yoksa ve kaynak 'sunuma akan' olarak isaretliyse (app_setting 'sunum.kaynaklar'):
     - icinde bulunulan ceyrek: her acilista CANLI hesaplanir, saklanmaz;
     - gecmis ceyrek: ilk goruntulemede hesaplanip DONDURULUR (sonra degismez; yetkili 'Guncelle' ile yeniler);
     - 'anlik' kaynak (donem filtresi yok, o anki durumu verir) yalniz bir onceki ceyrek icin dondurulur; daha eski ceyrege bugunku durum yazilmaz;
     - gelecek ceyrek hesaplanmaz.
Goruntu ekip geneli kapsamla (yonetici gorunumu) tek kez hesaplanir, 'sunum' modulunu goren herkese aynidir.
Yonetim (gonder/sabitle/kaldir, kaynak secimi) admin ya da rolgorunum.SUNUM_YETKISI ister; kontrol api katmanindadir.
Yuk bicimi: 'takvim' kendi grafigi icin (takvim.servis.sunum_ozeti); digerleri {"kpi": [...], "tablo": {...}} (arayuz tek genel kartla cizer).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import ariza
from app.catalog import get as modul
from app.gelir.servis import PARA_BIRIMLERI, tum_gelirler
from app.kullanicilar import kullanici_kaydi
from app.models import ApnRevenue, AppSetting, AppUser, Customer, Demand, Presentation, ProjectItem, SmsRevenue
from app.musteri.servis import portfoy
from app.navigation import PRESENTATION as MENU
from app.onedesk.servis import top10
from app.ortak import UygulamaHatasi, ay_adi, iso, rapor_donemi, simdi, tr_kucuk
from app.radar.servis import adaylar as radar_adaylari
from app.rapor.servis import durum_ozeti
from app.session import Principal
from app.skor.servis import siralama
from app.takvim.servis import bu_ceyrek, donem_adi, donem_araligi, sunum_ozeti

AYAR_ANAHTARI = "sunum.kaynaklar"
EKIP = Principal("sunum", "TeamMngr", False)  # ekip geneli kapsam (yonetici gorunumu); kullanici kaydi acan fonksiyona verilmez


class SunumHata(UygulamaHatasi):
    """kod = HTTP durumu."""


# --- genel kart yuku -------------------------------------------------------------------------------
def _kpi(ad: str, ad_en: str, deger: float | None, birim: str = "", alt: str = "") -> dict:
    return {"ad": ad, "ad_en": ad_en, "deger": deger, "birim": birim, "alt": alt}


def _sutun(ad: str, ad_en: str, birim: str = "") -> dict:
    return {"ad": ad, "ad_en": ad_en, "birim": birim}


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
        },
    }


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
        "kpi": [_kpi(f"{ay_adi(a)} · atılan", f"{ay_adi(a, 'en')} · sent", o["toplam"]["atilan"], alt=f"/ {o['toplam']['musteri']}") for a, o in zip(aylar, ozetler, strict=True)],
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
            _kpi("Gelir kaydı", "Revenue records", len(kayitlar)),
            _kpi("Müşteri", "Customers", len({r.customer_name for r in kayitlar})),
            *(_kpi(f"Toplam {b}", f"Total {b}", round(toplam[b], 2), birim=b) for b in birimler),
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
        },
    }


def _proje(db: Session, yil: int, ceyrek: int) -> dict:
    bas, son = donem_araligi(yil, ceyrek)
    kalemler = list(db.scalars(select(ProjectItem)))
    acilan = [k for k in kalemler if k.created_at and bas <= k.created_at.date() <= son]
    kapanan = [k for k in kalemler if k.closed_date and bas <= k.closed_date <= son]
    suren = [k for k in kalemler if k.status != "kapandi"]
    adlar = {u.id: (u.display_name or u.username) for u in db.scalars(select(AppUser))}
    tamlar: dict[int, list] = {}
    for k in kalemler:
        s = tamlar.setdefault(k.owner_id, [adlar.get(k.owner_id, "—"), 0, 0, 0])
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
        },
    }


@dataclass(frozen=True)
class Kaynak:
    ad: str
    ad_en: str
    aciklama: str
    aciklama_en: str
    modul: str  # catalog modulu (verinin geldigi sayfa)
    uret: Callable[[Session, int, int], dict]
    anlik: bool = False  # donem filtresi yok: o anki durum (yalniz bir onceki ceyrek icin dondurulur)


KAYNAKLAR: dict[str, Kaynak] = {
    "takvim": Kaynak(
        "TAM Takvim özeti", "TAM Calendar summary",
        "Kişi bazında izin/gün durumu ve toplantılar (TAM Takvim grafiği).", "Leave/day status and meetings per person (TAM Calendar chart).",
        "takvim_ozet", _takvim,
    ),
    "utilizasyon": Kaynak(
        "TAM Utilizasyon sıralaması", "TAM Utilization ranking",
        "TAM'ların çatı müşterilerindeki ortalama final skora göre sıralaması (o anki skorlar).", "TAMs ranked by the average final score of their parent customers (current scores).",
        "utilizasyon", _utilizasyon, anlik=True,
    ),
    "rapor": Kaynak(
        "Gönderilen aylık rapor durumu", "Sent monthly report status",
        "Çeyreğin her ayı için TAM bazında atılan / beklenen aylık rapor sayısı.", "Monthly reports sent / expected per TAM for each month of the quarter.",
        "rapor", _rapor,
    ),
    "onedesk": Kaynak(
        "Onedesk özeti", "Onedesk summary",
        "Çeyrekte açılan alarm, talep ve şikayet toplamları; en çok kayıt oluşan 10 müşteri.", "Alarms, requests and complaints opened in the quarter; top 10 customers by records.",
        "onedesk", _onedesk,
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
    "portfoy": Kaynak(
        "Müşteri portföy özeti", "Customer portfolio summary",
        "Çatı / iştirak müşteri sayısı ve segment bazında ortalama skor (o anki durum).", "Parent / affiliate customer counts and average score per segment (current state).",
        "musteri", _portfoy, anlik=True,
    ),
    "proje": Kaynak(
        "Takip edilen projeler özeti", "Tracked projects summary",
        "Çeyrekte açılan ve kapanan projeler, süren işler; TAM bazında.", "Projects opened and closed in the quarter and ongoing work, per TAM.",
        "proje", _proje,
    ),
    "radar": Kaynak(
        "Müşteri radar özeti", "Customer radar summary",
        "Panelde kartı olmayan ama alarm kaydı oluşan ilk 10 müşteri (ReportDB verisi, o anki durum).", "Top 10 customers with alarm records but no card in the panel (ReportDB data, current state).",
        "radar", _radar, anlik=True,
    ),
    "talep": Kaynak(
        "Geliştirme talepleri özeti", "Development requests summary",
        "Çeyrekte açılan geliştirme talepleri ve durumları.", "Development requests opened in the quarter and their status.",
        "talep", _talep,
    ),
}  # fmt: skip


# --- sunuma akan kaynak ayari ---------------------------------------------------------------------------
def acik_kaynaklar(db: Session) -> list[str]:
    kayit = db.get(AppSetting, AYAR_ANAHTARI)
    deger = kayit.value if kayit is not None and isinstance(kayit.value, list) else []
    return [k for k in KAYNAKLAR if k in deger]


def kaynak_listesi(db: Session) -> list[dict]:
    acik = set(acik_kaynaklar(db))
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
            "acik": k in acik,
            "grup": MENU.get(v.modul, ("",))[0] or "insights",  # work = Benim Yerim, insights = Raporlar, admin = Yonetim
        }
        for k, v in KAYNAKLAR.items()
    ]


def kaynaklar_kaydet(db: Session, ham: object, actor: str) -> list[str]:
    if not isinstance(ham, list) or not all(isinstance(k, str) and k in KAYNAKLAR for k in ham):
        raise SunumHata(400, "Kaynak listesi geçersiz.")
    kayit = db.get(AppSetting, AYAR_ANAHTARI)
    if kayit is None:
        kayit = AppSetting(key=AYAR_ANAHTARI)
        db.add(kayit)
    kayit.value, kayit.updated_by, kayit.updated_at = [k for k in KAYNAKLAR if k in ham], actor[:120], simdi()
    db.flush()
    return list(kayit.value)


# --- ceyrek goruntusu -----------------------------------------------------------------------------------
def _ceyrek_dogrula(yil: int, ceyrek: int) -> None:
    if ceyrek not in (1, 2, 3, 4):
        raise SunumHata(400, "Çeyrek 1-4 olmalı.")
    donem_araligi(yil, ceyrek)  # yil denetimi


def _zamani(yil: int, ceyrek: int) -> str:
    simdiki = bu_ceyrek()
    return "guncel" if (yil, ceyrek) == simdiki else "gecmis" if (yil, ceyrek) < simdiki else "gelecek"


def _onceki_ceyrek() -> tuple[int, int]:
    yil, ceyrek = bu_ceyrek()
    return (yil, ceyrek - 1) if ceyrek > 1 else (yil - 1, 4)


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
    kayitlar = {p.source: p for p in db.scalars(select(Presentation).where(Presentation.period == ad, Presentation.source != ""))}
    acik = acik_kaynaklar(db)
    ogeler: list[dict] = []
    dondurulen = False
    for anahtar in [*KAYNAKLAR, *(k for k in kayitlar if k not in KAYNAKLAR)]:
        p = kayitlar.get(anahtar)
        if p is not None:
            ogeler.append(_oge(anahtar, "kayitli", p.payload, p.sent_by, iso(p.sent_at)))
            continue
        if anahtar not in acik or zamani == "gelecek":
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
    return {"yil": yil, "ceyrek": ceyrek, "donem": ad, "zaman": zamani, "ogeler": ogeler}


def gonder(db: Session, user: Principal, kaynak: str, yil: int, ceyrek: int, gonder: bool) -> dict:
    """Kaynagin ceyrek goruntusunu sunuma sabitler (yeniden gonderim gunceller) ya da kaldirir. Ceyrek+kaynak basina tek kayit."""
    if kaynak not in KAYNAKLAR:
        raise SunumHata(404, "Sunum kaynağı bulunamadı.")
    _ceyrek_dogrula(yil, ceyrek)
    ad = donem_adi(yil, ceyrek)
    if not gonder:
        db.execute(delete(Presentation).where(Presentation.source == kaynak, Presentation.period == ad))
        return {"donem": ad, "kaynak": kaynak, "sunumda": None}
    kisi = kullanici_kaydi(db, user).display_name or user.username
    kayit = _sakla(db, kaynak, ad, KAYNAKLAR[kaynak].uret(db, yil, ceyrek), kisi)
    db.flush()
    return {"donem": ad, "kaynak": kaynak, "sunumda": {"gonderen": kayit.sent_by, "zaman": iso(kayit.sent_at)}}
