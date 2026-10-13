"""Takvim servisi. Gun durumu kodlari uretimle ayni (kutucuklar/takvim/servis.py CALENDAR_STATUS_LABELS).

Gunler kisinin kendi DB dosyasindadir (app.db.kullanici_oturumu); TAM Takvim her kisinin dosyasini okur.
Izin gunu sayilanlar: yillik_izin, sirket_izni, raporlu. 'arife_tatili' yarim gundur (0,5). Hafta sonu ve bos gun kayitsizdir.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import kullanici_oturumu, mevcut_oturumlar
from app.kullanicilar import personel, personel_mi
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
EN_COK_OZET = 4000  # toplanti ozeti karakter siniri
SUNUM_KAYNAK = "takvim"


class TakvimHata(UygulamaHatasi):
    """kod = HTTP durumu."""


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
        return datetime.strptime(str(deger or "")[:10], "%Y-%m-%d").date()
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


def _ozet(deger: object) -> str:
    """Toplanti ozeti: satir sonlari LF olur, satir sonu bosluklari ile bastaki/sondaki bos satirlar atilir."""
    if deger is not None and not isinstance(deger, str):
        raise TakvimHata(400, "Toplantı özeti metin olmalı.")
    metin = "\n".join(s.rstrip() for s in str(deger or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()
    if len(metin) > EN_COK_OZET:
        raise TakvimHata(400, f"Toplantı özeti en fazla {EN_COK_OZET} karakter olabilir.")
    return metin


def _durum(deger: object) -> str:
    d = str(deger or "calisiyor")
    if d not in DURUMLAR:
        raise TakvimHata(400, "Geçersiz gün durumu.")
    return d


def _gun(r: CalendarDay, ozetli: bool = False) -> dict:
    """ozetli: toplanti ozeti de gider; yalniz kisinin kendi takvimi icin (TAM Takvim baskasinin ozetini gostermez)."""
    gun = {"tarih": r.day.isoformat(), "durum": r.status, "online": r.online_count, "yuzyuze": r.face_count}
    if ozetli:
        gun["toplanti_ozeti"] = r.meeting_notes or ""
    return gun


def _gunler(kullanici: str, bas: date, son: date) -> list[CalendarDay]:
    """Kisinin dosyasindaki aralik (dosya yoksa bos; okuma dosya olusturmaz)."""
    for _, k in mevcut_oturumlar([kullanici]):
        satirlar = list(k.scalars(select(CalendarDay).where(CalendarDay.day >= bas, CalendarDay.day <= son).order_by(CalendarDay.day)))
        k.expunge_all()
        return satirlar
    return []


def ay_oku(user: Principal, yil: int, ay: int) -> dict:
    if not 1 <= ay <= 12:
        raise TakvimHata(400, "Ay 1-12 arasında olmalı.")
    gunler = _gunler(user.username, date(yil, ay, 1), date(yil, ay, monthrange(yil, ay)[1]))
    return {"yil": yil, "ay": ay, "gunler": [_gun(g, True) for g in gunler], "ozet": _ozet_olustur(gunler), "durumlar": [{"kod": k, "ad": v} for k, v in DURUMLAR.items()]}


def gun_kaydet(user: Principal, govde: dict) -> dict:
    """Govdede toplanti_ozeti yoksa mevcut ozet korunur (eski istemci yazmaz, silmez); '' gonderilirse temizlenir."""
    gun = _tarih(govde.get("tarih"))
    durum, online, yuzyuze = _durum(govde.get("durum")), _sayi(govde.get("online"), "Online toplantı"), _sayi(govde.get("yuzyuze"), "Yüz yüze toplantı")
    ozet = _ozet(govde["toplanti_ozeti"]) if "toplanti_ozeti" in govde else None
    with kullanici_oturumu(user.username) as k:
        kayit = k.scalar(select(CalendarDay).where(CalendarDay.day == gun))
        if ozet is None:
            ozet = (kayit.meeting_notes if kayit is not None else None) or ""
        if durum == "calisiyor" and online == 0 and yuzyuze == 0 and not ozet:
            if kayit is not None:
                k.delete(kayit)  # varsayilan gun kayit tutmaz
                k.commit()
            return {"tarih": gun.isoformat(), "durum": "calisiyor", "online": 0, "yuzyuze": 0, "toplanti_ozeti": ""}
        if kayit is None:
            kayit = CalendarDay(day=gun)
            k.add(kayit)
        kayit.status, kayit.online_count, kayit.face_count, kayit.meeting_notes = durum, online, yuzyuze, ozet or None
        k.commit()
        return _gun(kayit, True)


def toplu_kaydet(user: Principal, govde: dict) -> dict:
    """Tarih araligina ayni durumu atar (hafta sonlari istege bagli atlanir). Toplanti sayilari ve ozetleri korunur."""
    bas, son = _tarih(govde.get("baslangic"), "Başlangıç"), _tarih(govde.get("bitis"), "Bitiş")
    if son < bas:
        raise TakvimHata(400, "Bitiş başlangıçtan önce olamaz.")
    if (son - bas).days + 1 > EN_COK_TOPLU_GUN:
        raise TakvimHata(400, f"En fazla {EN_COK_TOPLU_GUN} gün atanabilir.")
    durum, atla = _durum(govde.get("durum")), bool(govde.get("hafta_sonu_atla", True))
    atanan = 0
    with kullanici_oturumu(user.username) as k:
        mevcut = {r.day: r for r in k.scalars(select(CalendarDay).where(CalendarDay.day >= bas, CalendarDay.day <= son))}
        gun = bas
        while gun <= son:
            if not (atla and gun.weekday() >= 5):
                kayit = mevcut.get(gun)
                if durum == "calisiyor":
                    if kayit is not None and kayit.online_count == 0 and kayit.face_count == 0 and not kayit.meeting_notes:
                        k.delete(kayit)  # varsayilan gun kayit tutmaz
                    elif kayit is not None:
                        kayit.status = durum
                else:
                    if kayit is None:
                        kayit = CalendarDay(day=gun)
                        k.add(kayit)
                    kayit.status = durum
                atanan += 1
            gun += timedelta(days=1)
        k.commit()
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


def ekip(db: Session, yil: int, ceyrek: int) -> dict:
    """Etkin TAM personelinin tamami (TeamMember; hic giris yapmamis olsa da, bos takvimiyle); her kisi icin izin/gun durumu ve toplanti toplamlari (TAM Takvim)."""
    bas, son = donem_araligi(yil, ceyrek)
    liste = [_uye(u, _ozet_olustur(_gunler(u.username, bas, son))) for u in personel(db)]
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
    if not personel_mi(uye):
        raise TakvimHata(404, "Kişi bulunamadı.")
    gunler = _gunler(uye.username, bas, son)
    return {"uye": uye.display_name or uye.username, "gunler": [_gun(g) for g in gunler]}


# --- ceyrek bazli sunum (app.sunum kaynagi) --------------------------------------------------------------
def sunum_ozeti(db: Session, yil: int, ceyrek: int) -> dict:
    """Donemin TAM Takvim goruntusu (Ceyrek Bazli Sunum 'takvim' kaynagi; grafik bu yukle cizilir)."""
    anlik = ekip(db, yil, ceyrek)
    return {
        "yil": yil,
        "ceyrek": ceyrek,
        "durumlar": anlik["durumlar"],
        "genel": anlik["genel"],
        "uyeler": [
            {k: u[k] for k in ("ad", "durumlar", "online", "yuzyuze", "izin_gun", "toplanti", "kayitli_gun")} for u in anlik["uyeler"]
        ],
    }
