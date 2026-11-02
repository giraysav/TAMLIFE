"""Musteri Yonetimi: liste, musteri karti ve kart duzenleme.

Uretim karsiliklari: kutucuklar/portfoy/servis.py, portfoy/kart/servis.py, portfoy/kart/duzenleme.py,
application/workspace.py (customer_page). Kapsam kurali uretimdeki gibidir: admin ve TeamMngr tum
musterileri, TeamMember yalniz kendi musterisini (ya da kendi catisinin istirakini) gorur.
Dogrulanmadi: izleme/kazima (internal_scraped_data) bu surumde yok, kart alani bos doner.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, Table, delete, func, or_, select, update
from sqlalchemy.orm import Session, aliased

from app import gorunurluk, musteri_alani
from app.authz import is_admin, yonetici_mi
from app.bildirim import servis as bildirim
from app.gelir.servis import tum_gelirler, unvan_tasi
from app.kullanicilar import kullanici_kaydi, modul_yoneticisi_mi, musteri_personeli, musteri_personeli_mi
from app.models import (
    ApnRevenue,
    AppUser,
    Base,
    Customer,
    CustomerTeam,
    MatrixConfig,
    Report,
    ScoreApprovalRequest,
    SmsRevenue,
    UserNotification,
)
from app.ortak import UygulamaHatasi, eslestirme_anahtari
from app.session import Principal

SEGMENTLER = ("SMB", "SA", "MA", "PA", "WHOLESALE", "CONNCAR")  # tum segmentler (ham yukleme, skor); ekranda alana gore: alan_segmentleri


def alan_segmentleri(alan: str | None = None) -> tuple[str, ...]:
    """2026-10-20 kullanici: "Toptan'da yalniz WHOLESALE, Musteri Yonetimi'nde WHOLESALE yok"; ayni gun "Baglantili Araclar'da yalniz CONNCAR". Kart acma / duzenleme bu listeyle
    dogrulanir; ham musteri yuklemesindeki WHOLESALE satir yine Toptan'a gider (musteri_alani._segment_alani)."""
    alan = alan or musteri_alani.secili()
    toptan = tuple(s for s, a in musteri_alani.SEGMENT_ALANI.items() if a == alan)
    return toptan or tuple(s for s in SEGMENTLER if s not in musteri_alani.SEGMENT_ALANI)
VARSAYILAN_TUTAR = "0,00 ₺"
MATRIS_ANAHTARLARI = ("destech", "ci", "raci")
RAPOR_ADEDI = 6
GELIR_ADEDI = 12
SAYFA_BASINA = 20
EN_FAZLA_SAYFA_BASINA = 100

# alan -> (etiket, azami uzunluk) (uretim ILETISIM_ALANLARI)
ILETISIM_ALANLARI = {
    "sales_manager": ("Satış Yöneticisi", 100),
    "presales_manager": ("Presales", 100),
    "tac_name": ("TAC adı", 100),
    "tac_gsm": ("TAC GSM", 50),
    "tac_email": ("TAC e-posta", 100),
    "sol_kmt_name": ("SOL KMT adı", 100),
    "sol_kmt_gsm": ("SOL KMT GSM", 50),
    "sol_kmt_email": ("SOL KMT e-posta", 100),
    "mobil_kmt_name": ("Mobil KMT adı", 100),
    "mobil_kmt_gsm": ("Mobil KMT GSM", 50),
    "mobil_kmt_email": ("Mobil KMT e-posta", 100),
    "mobil_kmt_detail": ("Mobil KMT notu", 2000),
}
_EPOSTA = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_GSM = re.compile(r"^[0-9+()\-\s]{3,50}$")


class MusteriHata(UygulamaHatasi):
    """kod = HTTP durumu."""


def simdi() -> datetime:
    return datetime.now(UTC)


# --- yetki ve kapsam -------------------------------------------------------------------------
def eylem_yetkisi(user: Principal, eylem: str) -> bool:
    """Uretim eylem_yetkisi: add/duzenle/sync/delete modul erisimiyle gelir (2026-10-19 kullanici karari: herkes KENDI verisinde
    duzenler ve siler; sahiplik musteri_getir / silinebilir_mi ile); final_skor_atama, talep_yonetimi yalniz yonetici."""
    if yonetici_mi(user):
        return True
    return eylem in {"add", "duzenle", "sync", "delete"}


# GORME (2026-10-26 kullanici karari, app.gorunurluk): admin ve TeamMngr alanin tum kartlarini, yonetimli modulde sahibi o modulun
# tum kartlarini, personel yalniz kendisine atanan kartlari (sorumlusu ya da catisinin sorumlusu) gorur. 2026-10-20'deki
# "herkes TUM kartlari gorur" karari Benim Yerim icin kalkti. Degistirme (2026-10-20, degismedi):
#   Musteri Yonetimi (alan musteri): admin ve TeamMngr her karti, personel yalniz kendisine atanan karti (sorumlusu ya da catisinin sorumlusu).
#   Toptan / Baglantili Araclar: yalniz admin ve o modulun sahibi (kullanicilar.modul_yoneticisi_mi); digerleri salt okunur.
def alan_yoneticisi_mi(db: Session, user: Principal, alan: str | None = None) -> bool:
    """Alanin tum kartlarinda yazma (devir, baskasi adina ekleme, her karti silme)."""
    alan = alan or musteri_alani.secili()
    if alan == musteri_alani.VARSAYILAN:
        return yonetici_mi(user)
    return modul_yoneticisi_mi(db, user, alan)


def duzenleyebilir_mi(db: Session, user: Principal, musteri: Customer) -> bool:
    if alan_yoneticisi_mi(db, user, musteri.modul):
        return True
    if musteri.modul != musteri_alani.VARSAYILAN:
        return False  # yonetimli modul: yalniz sahibi ve admin
    uid = kullanici_id(db, user)
    if uid is None:
        return False
    if musteri.owner_id == uid:
        return True
    ust = db.get(Customer, musteri.parent_id) if musteri.parent_id else None
    return bool(ust and ust.owner_id == uid)


def silinebilir_mi(db: Session, user: Principal, musteri: Customer) -> bool:
    """Musteri kartini (istirakleriyle) YALNIZ admin siler (2026-10-31 kullanici). Digerleri silme talebi gonderir (silme_talebi)."""
    return is_admin(user)


def kullanici_id(db: Session, user: Principal) -> int | None:
    return db.scalar(select(AppUser.id).where(AppUser.username == user.username))


def musteri_getir(db: Session, user: Principal, musteri_id: int) -> Customer:
    """Okuma: alanda olmayan ya da kullanicinin goremedigi kart 404 (varligi sizdirilmaz; gorunurluk.kart_gorur_mu). Yazma musteri_yaz_getir."""
    musteri = db.get(Customer, musteri_id)
    if musteri is None or not gorunurluk.kart_gorur_mu(db, user, musteri):
        raise MusteriHata(404, "Müşteri bulunamadı.")
    return musteri


SALT_OKUNUR = "Bu kart size atanmamış: içeriği görebilirsiniz, değiştiremezsiniz."
SALT_OKUNUR_MODUL = "Bu modülde değişikliği yalnız modül sorumlusu ve admin yapabilir; içeriği görebilirsiniz."


def musteri_yaz_getir(db: Session, user: Principal, musteri_id: int) -> Customer:
    """Yazma: kart okunur ama kullaniciya atanmamissa 403 (aylik rapor, SLA, gorsel / dosya, kimlik, iletisim ...)."""
    musteri = musteri_getir(db, user, musteri_id)
    if not duzenleyebilir_mi(db, user, musteri):
        raise MusteriHata(403, SALT_OKUNUR if musteri.modul == musteri_alani.VARSAYILAN else SALT_OKUNUR_MODUL)
    return musteri


# --- liste ---------------------------------------------------------------------------------------
def liste(db: Session, user: Principal, arama: str = "", sayfa: int = 1, adet: int = SAYFA_BASINA) -> dict:
    sayfa = max(1, sayfa)
    adet = min(max(1, adet), EN_FAZLA_SAYFA_BASINA)
    ust = aliased(Customer)
    sorgu = select(Customer).outerjoin(ust, Customer.parent_id == ust.id)
    if (kosul := gorunurluk.kart_suzgeci(db, user, musteri_alani.secili())) is not None:
        sorgu = sorgu.where(kosul)  # 2026-10-26: personel yalniz kendi kartlari
    if arama.strip():
        ham = arama.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        kalip = f"%{ham}%"
        sorgu = sorgu.where(or_(Customer.name.ilike(kalip, escape="\\"), Customer.segment.ilike(kalip, escape="\\")))
    toplam = db.scalar(select(func.count()).select_from(sorgu.subquery())) or 0
    satirlar = db.scalars(sorgu.order_by(Customer.name, Customer.id).offset((sayfa - 1) * adet).limit(adet)).all()
    sahipler = {
        u.id: (u.display_name or u.username)
        for u in db.scalars(select(AppUser).where(AppUser.id.in_({c.owner_id for c in satirlar if c.owner_id})))
    }
    return {
        "items": [
            {
                "id": c.id,
                "name": c.name,
                "segment": c.segment or "",
                "owner": sahipler.get(c.owner_id) if c.owner_id else None,
                "score": (round(c.score, 1) if c.score is not None else None) if c.parent_id is None else None,
                "parent_id": c.parent_id,
            }
            for c in satirlar
        ],
        "total": toplam,
        "page": sayfa,
        "per_page": adet,
        "pages": math.ceil(toplam / adet) if toplam else 0,
    }


# --- portfoy (kart izgarasi) ---------------------------------------------------------------------------
PORTFOY_SAYFA = 24


def _kalip(arama: str) -> str:
    ham = arama.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{ham}%"


def secenekler(db: Session, user: Principal) -> dict:
    """Form ve filtre secenekleri: segmentler, TAM listesi (yalniz yonetici secer), iştirak icin cati musteriler."""
    uid = kullanici_id(db, user)
    yonetici = alan_yoneticisi_mi(db, user)
    kisiler = musteri_personeli(db)  # personel kumesi: TAM suzgeci
    if not gorunurluk.tumunu_gorur(db, user, musteri_alani.secili()):
        kisiler = [k for k in kisiler if k.id == uid]  # 2026-10-26: personel yalniz kendi kartlarini gorur
    catilar = select(Customer.id, Customer.name).where(Customer.parent_id.is_(None)).order_by(Customer.name)
    if not yonetici:  # istirak yalniz kendi catisina eklenir (yonetimli modulde sahibi olmayan hic ekleyemez)
        kendi = uid and musteri_alani.secili() == musteri_alani.VARSAYILAN
        catilar = catilar.where(Customer.owner_id == uid) if kendi else catilar.where(Customer.id == -1)
    return {
        "segmentler": list(alan_segmentleri()),
        "yonetici": yonetici,
        "ekleyebilir": yonetici or musteri_alani.secili() == musteri_alani.VARSAYILAN,
        "kendi_id": uid,
        "tam": [{"id": k.id, "ad": k.display_name or k.username} for k in kisiler],
        "catilar": [{"id": i, "ad": a} for i, a in db.execute(catilar)],
    }


def portfoy_catilari(arama: str = "", tam_id: int | None = None, segment: str = "", kosul=None) -> select:
    """Portfoy filtresine (arama / TAM / segment) uyan cati kartlarinin sorgusu. kosul: gorunurluk.kart_suzgeci (None = hepsi)."""
    cati = select(Customer).where(Customer.parent_id.is_(None))
    if kosul is not None:
        cati = cati.where(kosul)
    if tam_id:
        cati = cati.where(Customer.owner_id == tam_id)
    if segment:
        cati = cati.where(Customer.segment == segment)
    if arama.strip():
        kalip = _kalip(arama)
        alt = select(Customer.parent_id).where(Customer.parent_id.is_not(None), Customer.name.ilike(kalip, escape="\\"))
        cati = cati.where(or_(Customer.name.ilike(kalip, escape="\\"), Customer.segment.ilike(kalip, escape="\\"), Customer.id.in_(alt)))
    return cati.order_by(Customer.name, Customer.id)


def portfoy(
    db: Session, user: Principal, arama: str = "", tam_id: int | None = None, segment: str = "", sayfa: int = 1, adet: int = PORTFOY_SAYFA
) -> dict:
    """Cati musterilerin kart listesi (uretim 'Musterilerim'): iştirakler cati kartinin icinde; arama iştirak adini da kapsar.

    2026-10-26: personel yalniz kendi kartlarini gorur (gorunurluk); kartin 'duzenlenebilir' bayragi kullaniciya atanmis mi.
    """
    adet = min(max(1, adet), EN_FAZLA_SAYFA_BASINA)
    hepsi = gorunurluk.tumunu_gorur(db, user, musteri_alani.secili())
    uid = None if hepsi else kullanici_id(db, user)
    tum = list(db.scalars(portfoy_catilari(arama, tam_id, segment, None if hepsi else gorunurluk.cati_kosulu(uid))))
    toplam = len(tum)
    sayfa = max(1, min(sayfa, max(1, math.ceil(toplam / adet))))
    parca = tum[(sayfa - 1) * adet : sayfa * adet]

    alt_sorgu = select(Customer).where(Customer.parent_id.in_([c.id for c in tum] or [-1]))
    if not hepsi:
        alt_sorgu = alt_sorgu.where(gorunurluk.kart_kosulu(uid))  # baskasinin catisinda yalniz kendi istirakleri
    cerceve = set() if hepsi else {c.id for c in tum if c.owner_id != uid}  # catisi baskasinin: sayilari / skoru gosterilmez
    altlar: dict[int, list[Customer]] = {}
    for a in db.scalars(alt_sorgu.order_by(Customer.name)):
        altlar.setdefault(a.parent_id, []).append(a)
    sahipler = {
        u.id: (u.display_name or u.username)
        for u in db.scalars(select(AppUser).where(AppUser.id.in_({c.owner_id for c in parca if c.owner_id} or {-1})))
    }
    kendi = [c for c in tum if c.id not in cerceve]
    skorlu = [c.score for c in kendi if c.score]

    def say(c: Customer, alan: str) -> int:
        return 0 if c.id in cerceve else (getattr(c, alan) or 0)

    return {
        "items": [
            {
                "id": c.id,
                "name": c.name,
                "segment": c.segment or "",
                "owner": sahipler.get(c.owner_id) if c.owner_id else None,
                "owner_id": c.owner_id,
                "score": round(c.score, 1) if c.score and c.id not in cerceve else None,
                "alarm": say(c, "alarm_count"),
                "sikayet": say(c, "complaint_count"),
                "talep": say(c, "request_count"),
                "alarm_kapanan": say(c, "alarm_closed_count"),  # Onedesk kayitlari kutusu: acik / yil ici kapanan
                "sikayet_kapanan": say(c, "complaint_closed_count"),
                "talep_kapanan": say(c, "request_closed_count"),
                "istirakler": [{"id": a.id, "name": a.name} for a in altlar.get(c.id, [])],
                "duzenlenebilir": duzenleyebilir_mi(db, user, c),
                "cerceve": c.id in cerceve,  # baskasinin catisi: yalniz kendi istiraklerinin cercevesi, kart acilmaz
            }
            for c in parca
        ],
        "ozet": {
            "cati": len(kendi),
            "istirak": sum(len(v) for v in altlar.values()),
            "alarm": sum(c.alarm_count or 0 for c in kendi),
            "sikayet": sum(c.complaint_count or 0 for c in kendi),
            "talep": sum(c.request_count or 0 for c in kendi),
            "ortalama_skor": round(sum(skorlu) / len(skorlu), 1) if skorlu else None,
            "skorlu": len(skorlu),
        },
        "total": toplam,
        "page": sayfa,
        "per_page": adet,
        "pages": math.ceil(toplam / adet) if toplam else 0,
    }


# --- kart ----------------------------------------------------------------------------------------
def _matris_satirlari(db: Session, anahtar: str, adlar: set[str]) -> dict:
    """Matrisin 'Musteri' sutunu bu musteriye (ya da istirakine) uyan satirlari."""
    kayit = db.get(MatrixConfig, anahtar)
    basliklar = list(kayit.headers) if kayit and isinstance(kayit.headers, list) else []
    satirlar = list(kayit.rows) if kayit and isinstance(kayit.rows, list) else []
    sutun = _matris_musteri_sutunu(basliklar)
    if sutun is None:
        return {"basliklar": [], "satirlar": []}
    eslesen = [
        [str(h) if h is not None else "" for h in s]
        for s in satirlar
        if isinstance(s, list) and len(s) > sutun and eslestirme_anahtari(str(s[sutun])) in adlar
    ]
    return {"basliklar": [str(b) for b in basliklar], "satirlar": eslesen}


def _matris_musteri_sutunu(basliklar: list) -> int | None:
    return next((i for i, b in enumerate(basliklar) if any(k in eslestirme_anahtari(str(b)) for k in ("müşteri", "musteri"))), None)


def _sayilar(musteriler: list[Customer]) -> dict:
    return {
        "envanter": sum(c.inventory_count or 0 for c in musteriler),
        "alarm": sum(c.alarm_count or 0 for c in musteriler),
        "sikayet": sum(c.complaint_count or 0 for c in musteriler),
        "talep": sum(c.request_count or 0 for c in musteriler),
        "alarm_kapanan": sum(c.alarm_closed_count or 0 for c in musteriler),
        "sikayet_kapanan": sum(c.complaint_closed_count or 0 for c in musteriler),
        "talep_kapanan": sum(c.request_closed_count or 0 for c in musteriler),
    }


def iletisim_sozlugu(db: Session, musteri_id: int) -> dict:
    kayit = db.get(CustomerTeam, musteri_id)
    return {alan: (getattr(kayit, alan, None) or "") if kayit else "" for alan in ILETISIM_ALANLARI}


def _ad(kisi: AppUser | None) -> str | None:
    return (kisi.display_name or kisi.username) if kisi else None


def _tarih(an: datetime | None) -> str | None:
    return an.strftime("%d.%m.%Y %H:%M") if an else None


def ayri_rapor_mu(musteri: Customer) -> bool:
    return musteri.parent_id is not None and bool(musteri.separate_report)


def rapor_birimi_mi(musteri: Customer) -> bool:
    """Ayrica aylik rapor beklenen birim: cati musteri ya da 'ayri rapor' secilmis istirak."""
    return musteri.parent_id is None or ayri_rapor_mu(musteri)


def rapor_bekleniyor_mu(musteri: Customer) -> bool:
    """Bu ay raporu beklenen birim: rapor birimi ve kartinda 'raporu atilmamaktadir' isaretli degil (2026-10-31 kullanici).
    Raporun hangi birime sayilacagi rapor_birimi_mi ile kalir; muafiyet yalniz beklenen/bekleyen sayimini etkiler."""
    return rapor_birimi_mi(musteri) and not musteri.report_exempt


def karti(db: Session, user: Principal, musteri_id: int, izinli: frozenset[str] | None) -> dict:
    musteri = musteri_getir(db, user, musteri_id)
    istirakler = list(db.scalars(select(Customer).where(Customer.parent_id == musteri.id).order_by(func.lower(Customer.name))))
    sahipler = {
        u.id: u for u in db.scalars(select(AppUser).where(AppUser.id.in_({c.owner_id for c in [musteri, *istirakler] if c.owner_id})))
    }
    tam = sahipler.get(musteri.owner_id)
    ust = db.get(Customer, musteri.parent_id) if musteri.parent_id else None
    adlar = {eslestirme_anahtari(c.name) for c in [musteri, *istirakler] if c.name}

    def erisim(modul: str) -> bool:
        return is_admin(user) or (izinli is not None and modul in izinli)

    kart: dict = {
        "kimlik": {
            "id": musteri.id,
            "unvan": musteri.name,
            "musteri_no": musteri.customer_no,
            "ncst": musteri.ncst or "",
            "segment": musteri.segment or "",
            "sektor": musteri.sector,
            "envanter": musteri.inventory_count or 0,
            "tam": _ad(tam),
            "tam_id": musteri.owner_id,
            "ayri_rapor": ayri_rapor_mu(musteri) if musteri.parent_id else None,
            "rapor_muaf": bool(musteri.report_exempt),
            "cati": {"id": ust.id, "unvan": ust.name} if ust else None,
            "istirakler": [{"id": c.id, "unvan": c.name, "ncst": c.ncst or "", "tam": _ad(sahipler.get(c.owner_id))} for c in istirakler],
        },
        "operasyon": {
            "ft_hacim": musteri.ft_volume or VARSAYILAN_TUTAR,
            "tam_ft": musteri.tam_ft or VARSAYILAN_TUTAR,
            "final_skor": round(musteri.score or 0, 1) if musteri.parent_id is None else None,
            "skor_talebi_bekliyor": (
                db.scalar(
                    select(func.count())
                    .select_from(ScoreApprovalRequest)
                    .where(ScoreApprovalRequest.customer_id == musteri.id, ScoreApprovalRequest.status == "pending")
                )
                or 0
            )
            > 0,
            "kendi": _sayilar([musteri]),
            "istirak_dahil": _sayilar([musteri, *istirakler]) if istirakler else None,
        },
        "ekip": _matris_satirlari(db, "destech", adlar),
        "iletisim": iletisim_sozlugu(db, musteri.id),
        "kritik_ci": _matris_satirlari(db, "ci", adlar),
    }

    rapor_izni = erisim("rapor")
    if rapor_izni:
        sorgu = select(Report).where(Report.customer_id == musteri.id)
        raporlar = db.scalars(
            sorgu.order_by(Report.report_year.desc(), Report.report_month.desc(), Report.id.desc()).limit(RAPOR_ADEDI)
        ).all()
        kart["raporlar"] = {
            "toplam": db.scalar(select(func.count()).select_from(Report).where(Report.customer_id == musteri.id)) or 0,
            "son": [
                {
                    "donem": f"{r.report_month:02d}.{r.report_year}",
                    "gonderildi": bool(r.is_submitted),
                    "duzenleyen": r.last_edited_by,
                    "tarih": _tarih(r.last_edited_at or r.created_at),
                    "bayrak": r.flag_count or 0,
                }
                for r in raporlar
            ],
        }

    sms_izni, apn_izni = erisim("tamsms"), erisim("tamapn")
    if sms_izni or apn_izni:
        kart["gelirler"] = {}
        if sms_izni:
            kart["gelirler"]["ict"] = _gelirler(db, SmsRevenue, adlar)
        if apn_izni:
            kart["gelirler"]["apn"] = _gelirler(db, ApnRevenue, adlar, ek=("installation_pct",))

    # Gorme musteri_getir'de (2026-10-26 gorunurluk); yazma kullaniciya atanmis kartta (duzenleyebilir_mi), yonetimli modulde sahibinde
    yazma = duzenleyebilir_mi(db, user, musteri)
    yonetici = alan_yoneticisi_mi(db, user, musteri.modul)
    kart["segmentler"] = list(alan_segmentleri(musteri.modul))  # kart duzenleme secenekleri (alana gore)
    kart["erisim"] = {
        "rapor": rapor_izni,
        "gelir": sms_izni or apn_izni,
        "aylik_rapor": yazma,  # aylik raporu yalniz karti kendisine atanan (ya da yonetici) hazirlar / gonderir
        "kimlik_duzenle": yazma and eylem_yetkisi(user, "duzenle"),
        "iletisim_duzenle": yazma,
        "istirak_ekle": yazma and eylem_yetkisi(user, "add"),
        "sil": silinebilir_mi(db, user, musteri),
        "sil_talebi": not is_admin(user),  # 2026-10-31: dugme herkese gorunur; admin olmayan silme onayina gonderir
        "tam_degistir": yonetici,  # sorumlu devri yalniz yonetici (tam_degistir)
        "rapor_geri_al": yazma,  # 2026-11-02: gonderimi geri alma raporu yazabilen herkese (onceden yalniz admin)
        "ayri_rapor_sec": yazma and musteri.parent_id is not None,
        "rapor_muaf_sec": yazma and rapor_birimi_mi(musteri),
    }
    if yazma:
        kart["cati_secenekleri"] = [
            {"id": c.id, "ad": c.name}
            for c in db.scalars(
                select(Customer)
                .where(Customer.parent_id.is_(None), Customer.id != musteri.id, *([] if yonetici else [Customer.owner_id == kullanici_id(db, user)]))
                .order_by(Customer.name, Customer.id)
            )  # personel istirakini yalniz kendi catisina baglar
        ]
        secenek = {u.id: u for u in musteri_personeli(db)}
        if musteri.owner_id and musteri.owner_id not in secenek:  # eski kayit: personel olmayan sahip secili gorunsun
            eski = db.get(AppUser, musteri.owner_id)
            if eski is not None:
                secenek[eski.id] = eski
        kart["tam_secenekleri"] = sorted(
            ({"id": u.id, "ad": u.display_name or u.username} for u in secenek.values()),
            key=lambda u: (u["ad"] or "").lower(),
        )
    if not yonetici:
        kart.pop("tam_secenekleri", None)  # sorumlu devri yalniz yonetici
    return kart


def _gelirler(db: Session, model: Any, adlar: set[str], ek: tuple[str, ...] = ()) -> dict:
    tumu: list[Any] = sorted(tum_gelirler(db, model), key=lambda k: (k.year, k.month), reverse=True)
    kayitlar = [k for k in tumu if eslestirme_anahtari(k.customer_name) in adlar]
    toplam: dict[str, float] = {}
    for k in kayitlar:
        para = k.currency or "TRY"
        toplam[para] = toplam.get(para, 0) + (k.amount or 0)
    return {
        "toplam": {p: round(t, 2) for p, t in toplam.items()},
        "son": [
            {
                "donem": f"{k.month:02d}.{k.year}",
                "tutar": k.amount,
                "para": k.currency,
                "musteri": k.customer_name,
                **{a: getattr(k, a) for a in ek},
            }
            for k in kayitlar[:GELIR_ADEDI]
        ],
    }


# --- girdi dogrulama -----------------------------------------------------------------------------
def _metin(govde: dict, alan: str, etiket: str, azami: int, zorunlu: bool = False) -> str | None:
    deger = govde.get(alan)
    if deger is None or (isinstance(deger, str) and not deger.strip()):
        if zorunlu:
            raise MusteriHata(400, f"{etiket} zorunludur.")
        return None
    if not isinstance(deger, str):
        raise MusteriHata(400, f"{etiket} metin olmalı.")
    temiz = deger.strip()
    if len(temiz) > azami:
        raise MusteriHata(400, f"{etiket} en fazla {azami} karakter olabilir.")
    return temiz


def segment_oku(govde: dict, mevcut: str | None = None) -> str | None:
    deger = (_metin(govde, "segment", "Segment", 100) or "").strip()
    if not deger:
        return None
    gecerli = alan_segmentleri()
    for s in gecerli:
        if deger.upper() == s:
            return s
    if mevcut and deger == str(mevcut).strip():
        return mevcut  # eski deger yalniz musterinin mevcut degeriyse korunur
    raise MusteriHata(400, "Segment bu modülde şunlardan biri olmalı: " + ", ".join(gecerli) + ".")


# --- yazma ---------------------------------------------------------------------------------------
def kimlik_guncelle(db: Session, user: Principal, musteri_id: int, govde: dict) -> dict:
    """Gelen alanlari gunceller (gelmeyen alana dokunulmaz). Sorumlu TAM'i degistirmez (tam_degistir)."""
    if not eylem_yetkisi(user, "duzenle"):
        raise MusteriHata(403, "Yetki yok.")
    musteri = musteri_yaz_getir(db, user, musteri_id)
    if "parent_id" in govde:
        yeni_cati = govde["parent_id"]
        if yeni_cati is not None:
            if isinstance(yeni_cati, bool) or not isinstance(yeni_cati, int) or not 1 <= yeni_cati <= 2_147_483_647:
                raise MusteriHata(400, "Çatı müşteri seçimi geçersiz.")
            if yeni_cati == musteri.id:
                raise MusteriHata(400, "Müşteri kendisinin çatısı olamaz.")
            # Kilit sirasi sabit: eszamanli A->B ve B->A degisiklikleri dongu olusturmasin.
            kilitli = {
                c.id: c
                for c in db.scalars(
                    select(Customer)
                    .where(Customer.id.in_([musteri.id, yeni_cati]))
                    .order_by(Customer.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            }
            ust = kilitli.get(yeni_cati)
            if ust is None or not (alan_yoneticisi_mi(db, user, musteri.modul) or ust.owner_id == kullanici_id(db, user)):
                raise MusteriHata(404, "Çatı müşteri bulunamadı.")  # personel yalniz kendi catisini secer; baskasininki sizdirilmaz
            if ust.parent_id is not None:
                raise MusteriHata(400, "Bir iştirak çatı müşteri olarak seçilemez.")
            if (
                yeni_cati != musteri.parent_id
                and db.scalar(select(Customer.id).where(Customer.parent_id == musteri.id).limit(1)) is not None
            ):
                raise MusteriHata(409, "Bu müşterinin iştiraklerini önce başka bir çatıya taşıyın.")
    if "name" in govde:
        yeni_ad = _metin(govde, "name", "Müşteri Ünvanı", 150, zorunlu=True)
        assert yeni_ad is not None
        yeni_anahtar = eslestirme_anahtari(yeni_ad)
        eski_anahtar = eslestirme_anahtari(musteri.name or "")
        if yeni_anahtar != eski_anahtar:
            for c in db.scalars(select(Customer).where(Customer.id != musteri.id)):
                if eslestirme_anahtari(c.name or "") == yeni_anahtar:
                    raise MusteriHata(409, "Bu ünvanla kayıtlı başka bir müşteri var.")
            _unvan_baglantilarini_tasi(db, eski_anahtar, yeni_ad, user.username)
        musteri.name = yeni_ad
    if "ncst" in govde:
        musteri.ncst = _metin(govde, "ncst", "Müşteri NCST", 50) or ""
    if "customer_no" in govde:
        musteri.customer_no = _metin(govde, "customer_no", "Müşteri No", 200)
    if "segment" in govde:
        musteri.segment = segment_oku(govde, mevcut=musteri.segment) or ""
    if "sector" in govde:
        musteri.sector = _metin(govde, "sector", "Sektör", 100)
    if "ft_volume" in govde:
        musteri.ft_volume = _metin(govde, "ft_volume", "FT Hacim", 100) or VARSAYILAN_TUTAR
    if "tam_ft" in govde:
        musteri.tam_ft = _metin(govde, "tam_ft", "TAM FT", 100) or VARSAYILAN_TUTAR
    if "inventory" in govde:
        musteri.inventory_count = _tamsayi(govde["inventory"], "Envanter", 0, 1_000_000_000)
    if "parent_id" in govde:
        musteri.parent_id = govde["parent_id"]
    db.flush()
    return {"unvan": musteri.name, "modul": musteri.modul}  # WHOLESALE cati Toptan'a gecer (musteri_alani._segment_alani)


def _tamsayi(deger: object, etiket: str, en_az: int, en_cok: int) -> int:
    if isinstance(deger, bool) or not isinstance(deger, int | str):
        raise MusteriHata(400, f"{etiket} tam sayı olmalı.")
    try:
        sayi = int(deger)
    except ValueError as exc:
        raise MusteriHata(400, f"{etiket} tam sayı olmalı.") from exc
    if not en_az <= sayi <= en_cok:
        raise MusteriHata(400, f"{etiket} {en_az} ile {en_cok} arasında olmalı.")
    return sayi


def _unvan_baglantilarini_tasi(db: Session, eski_anahtar: str, yeni_ad: str, kim: str) -> None:
    """Gelirler ve Destech/CI/RACI matrisleri musteriye UNVAN METNIYLE baglidir; yeniden adlandirmada tasinir."""
    if not eski_anahtar:
        return
    unvan_tasi(db, eski_anahtar, yeni_ad)
    for anahtar in MATRIS_ANAHTARLARI:
        matris = db.get(MatrixConfig, anahtar)
        if not matris or not isinstance(matris.headers, list) or not isinstance(matris.rows, list):
            continue
        sutun = _matris_musteri_sutunu(matris.headers)
        if sutun is None:
            continue
        yeni_satirlar = [list(s) for s in matris.rows]
        degisti = False
        for satir in yeni_satirlar:
            if isinstance(satir, list) and len(satir) > sutun and eslestirme_anahtari(str(satir[sutun])) == eski_anahtar:
                satir[sutun] = yeni_ad
                degisti = True
        if degisti:
            matris.rows = yeni_satirlar  # JSON alani yeniden atanir ki degisiklik izlensin
            matris.updated_by, matris.updated_at = kim[:100], simdi()


def iletisim_kaydet(db: Session, user: Principal, musteri_id: int, govde: dict) -> dict:
    musteri = musteri_yaz_getir(db, user, musteri_id)
    degerler: dict[str, str | None] = {}
    for alan, (etiket, azami) in ILETISIM_ALANLARI.items():
        if alan not in govde:
            continue
        deger = _metin(govde, alan, etiket, azami) or ""
        if deger and alan.endswith("_email") and not _EPOSTA.match(deger):
            raise MusteriHata(400, f"{etiket}: geçerli bir e-posta adresi olmalı.")
        if deger and alan.endswith("_gsm") and not _GSM.match(deger):
            raise MusteriHata(400, f"{etiket}: yalnızca rakam, +, boşluk, - ve parantez içerebilir.")
        degerler[alan] = deger or None
    kayit = db.get(CustomerTeam, musteri.id)
    if kayit is None:
        if not any(degerler.values()):
            return iletisim_sozlugu(db, musteri.id)
        kayit = CustomerTeam(customer_id=musteri.id)
        db.add(kayit)
    for alan, yeni_deger in degerler.items():
        setattr(kayit, alan, yeni_deger)
    db.flush()
    return iletisim_sozlugu(db, musteri.id)


def _dis_anahtar(anahtar: str) -> str:
    """external_key tum alanlarda tekil: ayni unvan Musteri Yonetimi'nde ve Toptan'da ayri kart olabilir."""
    alan = musteri_alani.secili()
    return (f"panel-{anahtar}" if alan == musteri_alani.VARSAYILAN else f"{alan}-{anahtar}")[:80]


def musteri_ekle(db: Session, user: Principal, govde: dict) -> dict:
    """Uretim add_customer. Yonetici disi baskasi adina ya da baskasinin catisi altina ekleyemez."""
    if not eylem_yetkisi(user, "add"):
        raise MusteriHata(403, "Yetki yok.")
    ad = _metin(govde, "name", "Müşteri Ünvanı", 150, zorunlu=True)
    assert ad is not None
    segment = segment_oku(govde)
    ust_id = govde.get("parent_id")
    istenen_tam = govde.get("owner_id")
    ust = db.get(Customer, ust_id) if ust_id else None
    if ust_id and ust is None:
        raise MusteriHata(404, "Üst müşteri bulunamadı.")
    if segment is None and ust is not None and ust.segment in SEGMENTLER:
        segment = ust.segment  # istirak segment gondermezse catinin segmentini alir
    if segment is None and len(alan_segmentleri()) == 1:
        segment = alan_segmentleri()[0]  # Toptan: segment hep WHOLESALE
    ben = kullanici_kaydi(db, user)  # yazan kisinin app_user satiri yoksa olusturulur (yerel/dev oturumu)
    uid = ben.id
    if not alan_yoneticisi_mi(db, user):
        if musteri_alani.secili() != musteri_alani.VARSAYILAN:
            raise MusteriHata(403, SALT_OKUNUR_MODUL)
        if istenen_tam and istenen_tam != uid:
            raise MusteriHata(403, "Başka bir personel adına müşteri ekleyemezsiniz.")
        if ust is not None and not duzenleyebilir_mi(db, user, ust):
            raise MusteriHata(403, "Bu müşteri başka bir TAM temsilcisine ait.")
    tam_id = istenen_tam or (
        ust.owner_id if ust else (uid if musteri_personeli_mi(ben) else None)
    )  # yonetici/admin/modul sahibi kendi adina musteri sahibi olmaz
    if istenen_tam:
        tam = db.get(AppUser, istenen_tam)
        if not musteri_personeli_mi(tam):
            raise MusteriHata(404, "Personel bulunamadı veya pasif.")
    anahtar = eslestirme_anahtari(ad)
    if any(eslestirme_anahtari(c.name or "") == anahtar for c in db.scalars(select(Customer))):
        raise MusteriHata(409, "Bu ünvanla kayıtlı başka bir müşteri var.")
    yeni = Customer(
        name=ad, segment=segment, owner_id=tam_id, parent_id=ust.id if ust else None, external_key=_dis_anahtar(anahtar), status=""
    )
    db.add(yeni)
    db.flush()
    return {"id": yeni.id, "owner_id": yeni.owner_id, "modul": yeni.modul}


def tam_degistir(db: Session, user: Principal, musteri_id: int, yeni_tam_id: object) -> dict:
    """Sorumlu TAM devri: yalniz alan yoneticisi (Musteri Yonetimi: admin / TeamMngr; Toptan, Baglantili: admin / modul sahibi)."""
    if not alan_yoneticisi_mi(db, user):
        raise MusteriHata(403, "Yetki yok.")
    musteri = musteri_yaz_getir(db, user, musteri_id)
    if isinstance(yeni_tam_id, bool) or not isinstance(yeni_tam_id, int):
        raise MusteriHata(400, "Personel geçersiz.")
    tam = db.get(AppUser, yeni_tam_id)
    if not musteri_personeli_mi(tam):
        raise MusteriHata(404, "Personel bulunamadı veya pasif.")
    musteri.owner_id = tam.id
    db.flush()
    return {"owner_id": tam.id, "full_name": tam.display_name or tam.username}


def musteriye_bagli_tablolar() -> list[tuple[Table, Column]]:
    """customer.id'ye yabanci anahtarla bagli tum tablolar (yeni model eklenince silme kendiliginden kapsar), cocuklar once:
    rapora bagli gonderim, raporun kendisinden once silinir."""
    bagli = []
    for tablo in reversed(Base.metadata.sorted_tables):
        if tablo.name == "customer":
            continue
        bagli += [(tablo, fk.parent) for fk in tablo.foreign_keys if fk.column.table.name == "customer"]
    return bagli


def _parcalar(kimlikler: list[int], boyut: int = 500):
    """IN listesi sinirini (SQLite/PostgreSQL parametre siniri) asmamak icin."""
    for i in range(0, len(kimlikler), boyut):
        yield kimlikler[i : i + boyut]


def agaci_sil(db: Session, kokler: list[int]) -> int:
    """Verilen musterileri ve butun istiraklerini siler; silinen musteri adedini doner. Yetki ve gorunurluk CAGIRANDA denetlenir.
    Bagli kayitlar: zorunlu baglar (rapor, taslak, gonderim, skor, dagitim gunlugu ...) silinir, istege bagli baglar (Onedesk kaydi,
    sunum ogesi) kopar (musteri_id bosalir, kayit kalir). Alt musteriler ustlerinden once silinir."""
    tum = list(dict.fromkeys(kokler))
    gorulen = set(tum)
    kuyruk = list(tum)
    while kuyruk:
        yeni: list[int] = []
        for parca in _parcalar(kuyruk):
            for k in db.scalars(select(Customer.id).where(Customer.parent_id.in_(parca))):
                if k not in gorulen:
                    gorulen.add(k)
                    yeni.append(k)
        tum += yeni
        kuyruk = yeni
    ust: dict[int, int | None] = {}
    for parca in _parcalar(tum):
        ust.update({k: p for k, p in db.execute(select(Customer.id, Customer.parent_id).where(Customer.id.in_(parca))).all()})
    tum = [k for k in tum if k in ust]  # veritabaninda olmayan kimlik sayilmaz

    def derinlik(k: int) -> int:
        n, ata = 0, ust.get(k)
        while ata in ust and n <= len(ust):
            ata = ust[ata]
            n += 1
        return n

    for tablo, sutun in musteriye_bagli_tablolar():
        for parca in _parcalar(tum):
            if sutun.nullable:
                db.execute(update(tablo).where(sutun.in_(parca)).values({sutun.name: None}))
            else:
                db.execute(delete(tablo).where(sutun.in_(parca)))
    for parca in _parcalar(sorted(tum, key=derinlik, reverse=True)):  # en derin istirak once: yabanci anahtar sirasi
        db.execute(delete(Customer).where(Customer.id.in_(parca)))
    db.flush()
    return len(tum)


def sil(db: Session, user: Principal, musteri_id: int) -> dict:
    """Musteriyi ve istiraklerini (bagli rapor, taslak, gonderim, skor kayitlariyla) siler. Yalniz admin (silinebilir_mi)."""
    musteri = musteri_getir(db, user, musteri_id)
    if not silinebilir_mi(db, user, musteri):
        raise MusteriHata(403, "Müşteriyi yalnız admin silebilir; silme onayına gönderin.")
    return {"silinen": agaci_sil(db, [musteri.id])}


SILME_TALEBI = "musteri_silme"


def silme_talebi(db: Session, user: Principal, musteri_id: int) -> dict:
    """Admin olmayan, gorebildigi kart icin silme onayi ister (2026-10-31 kullanici): her etkin admin'e kisisel panel bildirimi
    (ust cubuk zili, karta baglanti). Ayni kart icin okunmamis talep varsa yenisi yazilmaz (`zaten`)."""
    musteri = musteri_getir(db, user, musteri_id)
    if is_admin(user):
        raise MusteriHata(400, "Admin kartı doğrudan silebilir.")
    adminler = [k.id for k in db.scalars(select(AppUser).where(AppUser.active.is_(True), or_(AppUser.is_admin.is_(True), AppUser.role == "admin")))]
    bekleyen = db.scalar(
        select(UserNotification.id).where(UserNotification.kind == SILME_TALEBI, UserNotification.ref_id == musteri.id, UserNotification.read_at.is_(None)).limit(1)
    )
    if bekleyen is not None:
        return {"zaten": True, "bildirilen": 0}
    isteyen = kullanici_kaydi(db, user)
    istirak = db.scalar(select(func.count()).select_from(Customer).where(Customer.parent_id == musteri.id)) or 0
    ek = f" ({istirak} iştirakiyle)" if istirak else ""
    mesaj = f"{isteyen.display_name or isteyen.username}, “{musteri.name}”{ek} müşteri kartının silinmesini istiyor."
    for kimlik in adminler:
        bildirim.ekle(db, kimlik, SILME_TALEBI, mesaj, f"#/{musteri.modul or musteri_alani.VARSAYILAN}?m={musteri.id}", musteri.id)
    return {"zaten": False, "bildirilen": len(adminler)}
