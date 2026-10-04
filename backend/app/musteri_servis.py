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

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.authz import is_admin
from app.models import (
    AffiliateFinalFlag,
    ApnRevenue,
    AppUser,
    Customer,
    CustomerTeam,
    MatrixConfig,
    Report,
    ReportDispatch,
    ReportDraft,
    ReportRecipient,
    ScoreApprovalRequest,
    ScoreDetail,
    ScoreHistory,
    SmsRevenue,
)
from app.session import Principal
from app.trmetin import eslestirme_anahtari

SEGMENTLER = ("SMB", "SA", "MA", "PA", "WHOLESALE")
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


class MusteriHata(Exception):
    def __init__(self, kod: int, mesaj: str) -> None:
        super().__init__(mesaj)
        self.kod = kod
        self.mesaj = mesaj


def simdi() -> datetime:
    return datetime.now(UTC)


# --- yetki ve kapsam -------------------------------------------------------------------------
def yonetici_mi(user: Principal) -> bool:
    """Uretim yonetici_mi: admin ve TeamMngr tum portfoyu gorur ve silme/devir/final skor yetkisine sahiptir."""
    return bool(is_admin(user) or user.role == "TeamMngr")


def eylem_yetkisi(user: Principal, eylem: str) -> bool:
    """Uretim eylem_yetkisi: add/duzenle/sync modul erisimiyle gelir; delete, final_skor_atama, talep_yonetimi
    yalniz yonetici. (Moduli gorme kurali cagiranda: erisim kapisi.)"""
    if yonetici_mi(user):
        return True
    return eylem in {"add", "duzenle", "sync"}


def kullanici_id(db: Session, user: Principal) -> int | None:
    return db.scalar(select(AppUser.id).where(AppUser.username == user.username))


def gorunur_mu(db: Session, user: Principal, musteri: Customer) -> bool:
    if yonetici_mi(user):
        return True
    uid = kullanici_id(db, user)
    if uid is None:
        return False
    if musteri.owner_id == uid:
        return True
    ust = db.get(Customer, musteri.parent_id) if musteri.parent_id else None
    return bool(ust and ust.owner_id == uid)


def musteri_getir(db: Session, user: Principal, musteri_id: int) -> Customer:
    """Gorunmeyen musteri icin de 404 doner (varligi sizdirilmaz)."""
    musteri = db.get(Customer, musteri_id)
    if musteri is None or not gorunur_mu(db, user, musteri):
        raise MusteriHata(404, "Müşteri bulunamadı.")
    return musteri


# --- liste ---------------------------------------------------------------------------------------
def liste(db: Session, user: Principal, arama: str = "", sayfa: int = 1, adet: int = SAYFA_BASINA) -> dict:
    sayfa = max(1, sayfa)
    adet = min(max(1, adet), EN_FAZLA_SAYFA_BASINA)
    ust = aliased(Customer)
    sorgu = select(Customer).outerjoin(ust, Customer.parent_id == ust.id)
    if not yonetici_mi(user):
        uid = kullanici_id(db, user)
        if uid is None:
            return {"items": [], "total": 0, "page": sayfa, "per_page": adet, "pages": 0}
        sorgu = sorgu.where(or_(Customer.owner_id == uid, ust.owner_id == uid))
    if arama.strip():
        ham = arama.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        kalip = f"%{ham}%"
        sorgu = sorgu.where(or_(Customer.name.ilike(kalip, escape="\\"), Customer.segment.ilike(kalip, escape="\\")))
    toplam = db.scalar(select(func.count()).select_from(sorgu.subquery())) or 0
    satirlar = db.scalars(sorgu.order_by(Customer.name, Customer.id).offset((sayfa - 1) * adet).limit(adet)).all()
    sahipler = {u.id: (u.display_name or u.username) for u in db.scalars(select(AppUser).where(AppUser.id.in_({c.owner_id for c in satirlar if c.owner_id})))}
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


def karti(db: Session, user: Principal, musteri_id: int, izinli: frozenset[str] | None) -> dict:
    musteri = musteri_getir(db, user, musteri_id)
    istirakler = list(db.scalars(select(Customer).where(Customer.parent_id == musteri.id).order_by(func.lower(Customer.name))))
    tam = db.get(AppUser, musteri.owner_id) if musteri.owner_id else None
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
            "cati": {"id": ust.id, "unvan": ust.name} if ust else None,
            "istirakler": [{"id": c.id, "unvan": c.name, "ncst": c.ncst or "", "tam": _ad(db.get(AppUser, c.owner_id) if c.owner_id else None)} for c in istirakler],
        },
        "operasyon": {
            "ft_hacim": musteri.ft_volume or VARSAYILAN_TUTAR,
            "tam_ft": musteri.tam_ft or VARSAYILAN_TUTAR,
            "final_skor": round(musteri.score or 0, 1) if musteri.parent_id is None else None,
            "skor_talebi_bekliyor": (db.scalar(select(func.count()).select_from(ScoreApprovalRequest).where(ScoreApprovalRequest.customer_id == musteri.id, ScoreApprovalRequest.status == "pending")) or 0) > 0,
            "kendi": _sayilar([musteri]),
            "istirak_dahil": _sayilar([musteri, *istirakler]) if istirakler else None,
        },
        "ekip": _matris_satirlari(db, "destech", adlar),
        "iletisim": iletisim_sozlugu(db, musteri.id),
        "kritik_ci": _matris_satirlari(db, "ci", adlar),
        "izleme": {"cacti": [str(u) for u in (musteri.cacti_urls or []) if u], "son_kazima": None, "kazima_adedi": 0},
    }

    rapor_izni = erisim("rapor")
    if rapor_izni:
        sorgu = select(Report).where(Report.customer_id == musteri.id)
        raporlar = db.scalars(sorgu.order_by(Report.report_year.desc(), Report.report_month.desc(), Report.id.desc()).limit(RAPOR_ADEDI)).all()
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

    yonetici = yonetici_mi(user)
    kart["erisim"] = {
        "rapor": rapor_izni,
        "gelir": sms_izni or apn_izni,
        "aylik_rapor": True,  # Musteri Yonetimi'ni goren, gorebildigi musterinin aylik raporunu hazirlar
        "kimlik_duzenle": eylem_yetkisi(user, "duzenle"),
        "iletisim_duzenle": True,
        "istirak_ekle": eylem_yetkisi(user, "add"),
        "sil": eylem_yetkisi(user, "delete"),
        "tam_degistir": yonetici,
        "ayri_rapor_sec": musteri.parent_id is not None,
    }
    if yonetici:
        kart["tam_secenekleri"] = sorted(
            ({"id": u.id, "ad": u.display_name or u.username} for u in db.scalars(select(AppUser).where(AppUser.active.is_not(False)))),
            key=lambda u: (u["ad"] or "").lower(),
        )
    return kart


def _gelirler(db: Session, model: Any, adlar: set[str], ek: tuple[str, ...] = ()) -> dict:
    tumu: list[Any] = list(db.scalars(select(model).order_by(model.year.desc(), model.month.desc())))
    kayitlar = [k for k in tumu if eslestirme_anahtari(k.customer_name) in adlar]
    toplam: dict[str, float] = {}
    for k in kayitlar:
        para = k.currency or "TRY"
        toplam[para] = toplam.get(para, 0) + (k.amount or 0)
    return {
        "toplam": {p: round(t, 2) for p, t in toplam.items()},
        "son": [
            {"donem": f"{k.month:02d}.{k.year}", "tutar": k.amount, "para": k.currency, "musteri": k.customer_name, **{a: getattr(k, a) for a in ek}}
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
    for s in SEGMENTLER:
        if deger.upper() == s:
            return s
    if mevcut and deger == str(mevcut).strip():
        return mevcut  # eski deger yalniz musterinin mevcut degeriyse korunur
    raise MusteriHata(400, "Segment şunlardan biri olmalı: " + ", ".join(SEGMENTLER) + ".")


# --- yazma ---------------------------------------------------------------------------------------
def kimlik_guncelle(db: Session, user: Principal, musteri_id: int, govde: dict) -> dict:
    """Gelen alanlari gunceller (gelmeyen alana dokunulmaz). Sorumlu TAM'i degistirmez (tam_degistir)."""
    if not eylem_yetkisi(user, "duzenle"):
        raise MusteriHata(403, "Yetki yok.")
    musteri = musteri_getir(db, user, musteri_id)
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
        musteri.customer_no = _metin(govde, "customer_no", "Müşteri No", 50)
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
    db.flush()
    return {"unvan": musteri.name}


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
    gelir_modelleri: tuple[Any, ...] = (SmsRevenue, ApnRevenue)
    for model in gelir_modelleri:
        gelirler: list[Any] = list(db.scalars(select(model)))
        for gelir in gelirler:
            if eslestirme_anahtari(gelir.customer_name or "") == eski_anahtar:
                gelir.customer_name = yeni_ad
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
    musteri = musteri_getir(db, user, musteri_id)
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
    uid = kullanici_id(db, user)
    if not yonetici_mi(user):
        if istenen_tam and istenen_tam != uid:
            raise MusteriHata(403, "Başka bir personel adına müşteri ekleyemezsiniz.")
        if ust is not None and not gorunur_mu(db, user, ust):
            raise MusteriHata(403, "Bu müşteri başka bir TAM temsilcisine ait.")
    tam_id = istenen_tam or (ust.owner_id if ust else uid)
    if istenen_tam:
        tam = db.get(AppUser, istenen_tam)
        if tam is None or tam.active is False:
            raise MusteriHata(404, "Personel bulunamadı veya pasif.")
    anahtar = eslestirme_anahtari(ad)
    if any(eslestirme_anahtari(c.name or "") == anahtar for c in db.scalars(select(Customer))):
        raise MusteriHata(409, "Bu ünvanla kayıtlı başka bir müşteri var.")
    yeni = Customer(
        name=ad, segment=segment, owner_id=tam_id, parent_id=ust.id if ust else None, external_key=f"panel-{anahtar}"[:80], status=""
    )
    db.add(yeni)
    db.flush()
    return {"id": yeni.id, "owner_id": yeni.owner_id}


def tam_degistir(db: Session, user: Principal, musteri_id: int, yeni_tam_id: object) -> dict:
    """Sorumlu TAM devri: yalniz yonetici. Istirakler cati ile birlikte tasinmaz."""
    if not yonetici_mi(user):
        raise MusteriHata(403, "Yetki yok.")
    musteri = musteri_getir(db, user, musteri_id)
    if isinstance(yeni_tam_id, bool) or not isinstance(yeni_tam_id, int):
        raise MusteriHata(400, "Personel geçersiz.")
    tam = db.get(AppUser, yeni_tam_id)
    if tam is None or tam.active is False:
        raise MusteriHata(404, "Personel bulunamadı veya pasif.")
    musteri.owner_id = tam.id
    db.flush()
    return {"owner_id": tam.id, "full_name": tam.display_name or tam.username}


def sil(db: Session, user: Principal, musteri_id: int) -> dict:
    """Musteriyi ve istiraklerini (bagli rapor, taslak, gonderim, skor kayitlariyla) siler. Yalniz yonetici."""
    if not eylem_yetkisi(user, "delete"):
        raise MusteriHata(403, "Yetki yok.")
    musteri = musteri_getir(db, user, musteri_id)
    kimlikler = [musteri.id]
    kuyruk = [musteri.id]
    while kuyruk:
        cocuklar = list(db.scalars(select(Customer.id).where(Customer.parent_id.in_(kuyruk))))
        kimlikler += cocuklar
        kuyruk = cocuklar
    # Once gonderimler (rapora bagli), sonra raporlar ve digerleri; en son musteriler (altlar ustten once).
    for tablo in (ReportDispatch, ReportDraft, ReportRecipient, Report, CustomerTeam, ScoreHistory, ScoreDetail, ScoreApprovalRequest, AffiliateFinalFlag):
        db.execute(delete(tablo).where(tablo.customer_id.in_(kimlikler)))
    for kimlik in reversed(kimlikler):
        db.execute(delete(Customer).where(Customer.id == kimlik))
    db.flush()
    return {"silinen": len(kimlikler)}
