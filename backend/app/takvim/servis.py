"""Takvim servisi. Gun durumu kodlari uretimle ayni (kutucuklar/takvim/servis.py CALENDAR_STATUS_LABELS).

Izin gunu sayilanlar: yillik_izin, sirket_izni, raporlu. 'arife_tatili' yarim gundur (0,5). Hafta sonu ve bos gun kayitsizdir.
"""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.kullanicilar import giris_yapmislar, kullanici_kaydi
from app.models import AppUser, CalendarDay, Presentation
from app.ortak import UygulamaHatasi, iso, simdi
from app.session import Principal

DURUMLAR: dict[str, str] = {
    "calisiyor": "Çalışıyor",
    "yillik_izin": "Yıllık İzin",
    "sirket_izni": "Şirket İzni",
    "raporlu": "Raporlu",
    "arife_tatili": "Arife (Yarım Gün)",
    "resmi_tatil": "Resmi Tatil",
    "hafta_sonu": "Hafta Sonu",
}
IZIN_DURUMLARI = ("yillik_izin", "sirket_izni", "raporlu")
EN_COK_TOPLU_GUN = 62
EN_COK_TOPLANTI = 50
SUNUM_KAYNAK = "takvim"


class TakvimHata(UygulamaHatasi):
    """kod = HTTP durumu."""


def yonetici_mi(user: Principal) -> bool:
    return bool(user.is_admin or user.role in {"admin", "TeamMngr"})


# --- donem -----------------------------------------------------------------------------------------
def donem_araligi(yil: int, ceyrek: int) -> tuple[date, date]:
    """ceyrek 0 = tum yil; 1..4 = ceyrek. (baslangic, bitis dahil)"""
    if not 2000 <= yil <= 2100:
        raise TakvimHata(400, "Yıl 2000-2100 arasında olmalı.")
    if ceyrek not in (0, 1, 2, 3, 4):
        raise TakvimHata(400, "Çeyrek 0 (tüm yıl) ya da 1-4 olmalı.")
    if ceyrek == 0:
        return date(yil, 1, 1), date(yil, 12, 31)
    ilk_ay = 3 * (ceyrek - 1) + 1
    return date(yil, ilk_ay, 1), date(yil, ilk_ay + 2, monthrange(yil, ilk_ay + 2)[1])


def donem_adi(yil: int, ceyrek: int) -> str:
    return f"{yil}-Q{ceyrek}" if ceyrek else f"{yil}"


def bu_ceyrek() -> tuple[int, int]:
    an = simdi()
    return an.year, (an.month - 1) // 3 + 1


# --- kisinin kendi takvimi -----------------------------------------------------------------------------
def _tarih(deger: object, etiket: str = "Tarih") -> date:
    try:
        return datetime.strptime(str(deger or "")[:10], "%Y-%m-%d").date()  # noqa: DTZ007
    except ValueError:
        raise TakvimHata(400, f"{etiket} geçerli bir tarih olmalı (YYYY-AA-GG).") from None


def _sayi(deger: object, etiket: str) -> int:
    try:
        n = int(deger or 0)
    except (TypeError, ValueError):
        raise TakvimHata(400, f"{etiket} tam sayı olmalı.") from None
    if not 0 <= n <= EN_COK_TOPLANTI:
        raise TakvimHata(400, f"{etiket} 0-{EN_COK_TOPLANTI} arasında olmalı.")
    return n


def _durum(deger: object) -> str:
    d = str(deger or "calisiyor")
    if d not in DURUMLAR:
        raise TakvimHata(400, "Geçersiz gün durumu.")
    return d


def _gun(r: CalendarDay) -> dict:
    return {"tarih": r.day.isoformat(), "durum": r.status, "online": r.online_count, "yuzyuze": r.face_count}


def ay_oku(db: Session, user: Principal, yil: int, ay: int) -> dict:
    if not 1 <= ay <= 12:
        raise TakvimHata(400, "Ay 1-12 arasında olmalı.")
    bas, son = date(yil, ay, 1), date(yil, ay, monthrange(yil, ay)[1])
    uid = kullanici_kaydi(db, user).id
    gunler = db.scalars(select(CalendarDay).where(CalendarDay.user_id == uid, CalendarDay.day >= bas, CalendarDay.day <= son).order_by(CalendarDay.day)).all()
    return {"yil": yil, "ay": ay, "gunler": [_gun(g) for g in gunler], "ozet": _ozet_olustur(gunler), "durumlar": [{"kod": k, "ad": v} for k, v in DURUMLAR.items()]}


def gun_kaydet(db: Session, user: Principal, govde: dict) -> dict:
    gun = _tarih(govde.get("tarih"))
    durum, online, yuzyuze = _durum(govde.get("durum")), _sayi(govde.get("online"), "Online toplantı"), _sayi(govde.get("yuzyuze"), "Yüz yüze toplantı")
    uid = kullanici_kaydi(db, user).id
    kayit = db.scalar(select(CalendarDay).where(CalendarDay.user_id == uid, CalendarDay.day == gun))
    if durum == "calisiyor" and online == 0 and yuzyuze == 0:
        if kayit is not None:
            db.delete(kayit)  # varsayilan gun kayit tutmaz
        return {"tarih": gun.isoformat(), "durum": "calisiyor", "online": 0, "yuzyuze": 0}
    if kayit is None:
        kayit = CalendarDay(user_id=uid, day=gun)
        db.add(kayit)
    kayit.status, kayit.online_count, kayit.face_count = durum, online, yuzyuze
    db.flush()
    return _gun(kayit)


def toplu_kaydet(db: Session, user: Principal, govde: dict) -> dict:
    """Tarih araligina ayni durumu atar (hafta sonlari istege bagli atlanir). Toplanti sayilari korunur."""
    bas, son = _tarih(govde.get("baslangic"), "Başlangıç"), _tarih(govde.get("bitis"), "Bitiş")
    if son < bas:
        raise TakvimHata(400, "Bitiş başlangıçtan önce olamaz.")
    if (son - bas).days + 1 > EN_COK_TOPLU_GUN:
        raise TakvimHata(400, f"En fazla {EN_COK_TOPLU_GUN} gün atanabilir.")
    durum, atla = _durum(govde.get("durum")), bool(govde.get("hafta_sonu_atla", True))
    uid = kullanici_kaydi(db, user).id
    mevcut = {r.day: r for r in db.scalars(select(CalendarDay).where(CalendarDay.user_id == uid, CalendarDay.day >= bas, CalendarDay.day <= son))}
    atanan = 0
    gun = bas
    while gun <= son:
        if not (atla and gun.weekday() >= 5):
            kayit = mevcut.get(gun)
            if durum == "calisiyor":
                if kayit is not None and kayit.online_count == 0 and kayit.face_count == 0:
                    db.delete(kayit)  # varsayilan gun kayit tutmaz
                elif kayit is not None:
                    kayit.status = durum
            else:
                if kayit is None:
                    kayit = CalendarDay(user_id=uid, day=gun)
                    db.add(kayit)
                kayit.status = durum
            atanan += 1
        gun += timedelta(days=1)
    db.flush()
    return {"atanan": atanan}


# --- ozet ----------------------------------------------------------------------------------------------
def _bos_ozet() -> dict:
    return {"durumlar": dict.fromkeys(DURUMLAR, 0), "online": 0, "yuzyuze": 0, "kayitli_gun": 0}


def _ozet_olustur(gunler) -> dict:
    o = _bos_ozet()
    for g in gunler:
        o["kayitli_gun"] += 1
        o["durumlar"][g.status] = o["durumlar"].get(g.status, 0) + 1
        o["online"] += g.online_count
        o["yuzyuze"] += g.face_count
    return _bitir(o)


def _bitir(o: dict) -> dict:
    d = o["durumlar"]
    o["izin_gun"] = round(sum(d.get(k, 0) for k in IZIN_DURUMLARI) + 0.5 * d.get("arife_tatili", 0), 1)
    o["toplanti"] = o["online"] + o["yuzyuze"]
    return o


def _uye(u: AppUser, o: dict) -> dict:
    return {
        "id": u.id,
        "ad": u.display_name or u.username,
        "kullanici": u.username,
        "rol": u.role,
        "son_giris": iso(u.last_login_at),
        **o,
    }


def ekip(db: Session, user: Principal, yil: int, ceyrek: int) -> dict:
    """Panele giris yapmis herkes; her kisi icin izin/gun durumu ve toplanti toplamlari (TAM Takvim)."""
    bas, son = donem_araligi(yil, ceyrek)
    uyeler = giris_yapmislar(db)
    ozetler: dict[int, dict] = defaultdict(_bos_ozet)
    kimlikler = [u.id for u in uyeler]
    if kimlikler:
        for r in db.scalars(select(CalendarDay).where(CalendarDay.user_id.in_(kimlikler), CalendarDay.day >= bas, CalendarDay.day <= son)):
            o = ozetler[r.user_id]
            o["kayitli_gun"] += 1
            o["durumlar"][r.status] = o["durumlar"].get(r.status, 0) + 1
            o["online"] += r.online_count
            o["yuzyuze"] += r.face_count
    liste = [_uye(u, _bitir(ozetler[u.id] if u.id in ozetler else _bos_ozet())) for u in uyeler]
    genel = _bos_ozet()
    for u in liste:
        genel["kayitli_gun"] += u["kayitli_gun"]
        genel["online"] += u["online"]
        genel["yuzyuze"] += u["yuzyuze"]
        for k, v in u["durumlar"].items():
            genel["durumlar"][k] = genel["durumlar"].get(k, 0) + v
    gonderilen = db.scalar(select(Presentation).where(Presentation.source == SUNUM_KAYNAK, Presentation.period == donem_adi(yil, ceyrek)))
    return {
        "yil": yil,
        "ceyrek": ceyrek,
        "donem": donem_adi(yil, ceyrek),
        "uyeler": liste,
        "genel": _bitir(genel),
        "durumlar": [{"kod": k, "ad": v} for k, v in DURUMLAR.items()],
        "sunumda": None if gonderilen is None else {"gonderen": gonderilen.sent_by, "zaman": iso(gonderilen.sent_at)},
    }


def uye_gunleri(db: Session, yil: int, ceyrek: int, uye_id: int) -> dict:
    """Bir uyenin donemdeki kayitli gunleri (TAM Takvim'de satir acilinca)."""
    bas, son = donem_araligi(yil, ceyrek)
    uye = db.get(AppUser, uye_id)
    if uye is None or uye.last_login_at is None:
        raise TakvimHata(404, "Kişi bulunamadı.")
    gunler = db.scalars(select(CalendarDay).where(CalendarDay.user_id == uye_id, CalendarDay.day >= bas, CalendarDay.day <= son).order_by(CalendarDay.day)).all()
    return {"uye": uye.display_name or uye.username, "gunler": [_gun(g) for g in gunler]}


# --- sunuma gonder -----------------------------------------------------------------------------------
def sunuma_gonder(db: Session, user: Principal, yil: int, ceyrek: int, gonder: bool) -> dict:
    """Donemin TAM Takvim goruntusunu ceyrek bazli sunuma ekler (ya da kaldirir). Donem basina tek kayit; yeniden gonderim gunceller."""
    donem = donem_adi(yil, ceyrek)
    if not gonder:
        db.execute(delete(Presentation).where(Presentation.source == SUNUM_KAYNAK, Presentation.period == donem))
        return {"donem": donem, "sunumda": None}
    anlik = ekip(db, user, yil, ceyrek)
    yuk = {
        "yil": yil,
        "ceyrek": ceyrek,
        "durumlar": anlik["durumlar"],
        "genel": anlik["genel"],
        "uyeler": [
            {k: u[k] for k in ("ad", "durumlar", "online", "yuzyuze", "izin_gun", "toplanti", "kayitli_gun")} for u in anlik["uyeler"]
        ],
    }
    kayit = db.scalar(select(Presentation).where(Presentation.source == SUNUM_KAYNAK, Presentation.period == donem))
    ad = kullanici_kaydi(db, user).display_name or user.username
    if kayit is None:
        kayit = Presentation(source=SUNUM_KAYNAK, period=donem)
        db.add(kayit)
    kayit.title = f"TAM Takvim — {donem}"
    kayit.payload, kayit.sent_by, kayit.sent_at = yuk, ad[:120], simdi()
    db.flush()
    return {"donem": donem, "sunumda": {"gonderen": kayit.sent_by, "zaman": iso(kayit.sent_at)}}


def sunum_ogeleri(db: Session, yil: int | None = None) -> list[dict]:
    """Ceyrek bazli sunum modulu icin gonderilmis ogeler (yeniden eskiye)."""
    sorgu = select(Presentation).where(Presentation.source != "")
    if yil:
        sorgu = sorgu.where(Presentation.period.like(f"{yil}%"))
    return [
        {"id": p.id, "kaynak": p.source, "donem": p.period, "baslik": p.title, "gonderen": p.sent_by, "zaman": iso(p.sent_at), "veri": p.payload}
        for p in db.scalars(sorgu.order_by(Presentation.period.desc(), Presentation.id.desc()).limit(100))
    ]
