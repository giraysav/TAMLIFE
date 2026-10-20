"""Takvim servisi. Gun durumu kodlari uretimle ayni (kutucuklar/takvim/servis.py CALENDAR_STATUS_LABELS).

Gunler kisinin kendi DB dosyasindadir (app.db.kullanici_oturumu); TAM Takvim her kisinin dosyasini okur.
Izin gunu sayilanlar: yillik_izin, sirket_izni, raporlu. 'arife_tatili' yarim gundur (0,5). Hafta sonu ve bos gun kayitsizdir.
Ekipte herkeste ayni olan resmi tatil / yarim gun / sirket tatili gunleri takvim.kurum_takvimi'ndedir: kisinin kaydi yoksa
o gun oradan gelir (dosyaya yazilmaz), kisinin kendi kaydi her zaman onceliklidir.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import kullanici_oturumu, mevcut_oturumlar, yazma_kilidi
from app.kullanicilar import personel, personel_mi
from app.models import AppUser, CalendarDay, Presentation
from app.ortak import UygulamaHatasi, iso, simdi
from app.takvim.kurum_takvimi import aralik as kurum_araligi
from app.takvim.kurum_takvimi import kurum_gunu, varsayilan_durum

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
EN_COK_TOPLANTI = 2_147_483_647  # 2026-10-20 kullanici: online / yuzyuze adet siniri kalkti (yalniz veritabani tamsayi tavani)
EN_COK_OZET = 4000  # toplanti ozeti ve yapilan isler karakter siniri
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


# --- kisinin takvimi ---------------------------------------------------------------------------------------
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
    if n < 0:
        raise TakvimHata(400, f"{etiket} negatif olamaz.")
    if n > EN_COK_TOPLANTI:
        raise TakvimHata(400, f"{etiket} çok büyük.")
    return n


def _ozet(deger: object, etiket: str = "Toplantı özeti") -> str:
    """Serbest metin (toplanti ozeti, yapilan isler): satir sonlari LF olur, satir sonu bosluklari ile bastaki/sondaki bos satirlar atilir."""
    if deger is not None and not isinstance(deger, str):
        raise TakvimHata(400, f"{etiket} metin olmalı.")
    metin = "\n".join(s.rstrip() for s in str(deger or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()
    if len(metin) > EN_COK_OZET:
        raise TakvimHata(400, f"{etiket} en fazla {EN_COK_OZET} karakter olabilir.")
    return metin


def _durum(deger: object) -> str:
    d = str(deger or "calisiyor")
    if d not in DURUMLAR:
        raise TakvimHata(400, "Geçersiz gün durumu.")
    return d


def _durum2(deger: object, durum: str) -> str | None:
    """Gunun ikinci yarisi (2026-10-15: arife + sirket tatili gibi yarim gunler; arayuzde Ctrl ile ikinci durum). Bos = bolunmemis gun."""
    if deger in (None, ""):
        return None
    d = _durum(deger)
    if d == durum:
        raise TakvimHata(400, "Günün iki yarısı farklı durumda olmalı.")
    return d


def _gun(r: CalendarDay, ozetli: bool = False) -> dict:
    """ozetli: toplanti ozeti ve yapilan isler de gider; kisinin kendi takvimi ve admin'in TAM Takvim'i icin (digerleri metni gormez)."""
    gun = {"tarih": r.day.isoformat(), "durum": r.status, "online": r.online_count, "yuzyuze": r.face_count}
    if r.status2:
        gun["durum2"] = r.status2
    kurum = kurum_gunu(r.day)
    if kurum is not None:
        gun["kurum"] = {"durum": kurum[0], "aciklama": kurum[1], "durum2": kurum[2]}  # "Varsayilana don" bu duruma doner
    if ozetli:
        gun["toplanti_ozeti"] = r.meeting_notes or ""
        gun["yapilan_isler"] = r.work_notes or ""
    return gun


def _gunler(kullanici: str, bas: date, son: date) -> list[CalendarDay]:
    """Kisinin dosyasindaki aralik (okuma dosya olusturmaz) + kaydi olmayan kurum gunleri (yazilmamis, kayitli_gun sayilmaz)."""
    satirlar: list[CalendarDay] = []
    for _, k in mevcut_oturumlar([kullanici]):
        satirlar = list(k.scalars(select(CalendarDay).where(CalendarDay.day >= bas, CalendarDay.day <= son)))
        k.expunge_all()
    kayitli = {r.day for r in satirlar}
    satirlar += [g for g in _kurum_gunleri(bas, son) if g.day not in kayitli]
    return sorted(satirlar, key=lambda r: r.day)


def _kurum_gunleri(bas: date, son: date) -> list[CalendarDay]:
    """Kurum takviminin (Turkcell'li Takvimi) donemdeki gunleri: kisinin dosyasina yazilmamis sanal satirlar."""
    gunler = []
    for gun, durum, _, durum2 in kurum_araligi(bas, son):
        sanal = CalendarDay(day=gun, status=durum, status2=durum2, online_count=0, face_count=0)
        sanal.kurum_sanal = True  # type: ignore[attr-defined]
        gunler.append(sanal)
    return gunler


def ay_oku(kullanici: str, yil: int, ay: int) -> dict:
    if not 1 <= ay <= 12:
        raise TakvimHata(400, "Ay 1-12 arasında olmalı.")
    gunler = _gunler(kullanici, date(yil, ay, 1), date(yil, ay, monthrange(yil, ay)[1]))
    return {
        "yil": yil,
        "ay": ay,
        "gunler": [_gun(g, True) for g in gunler],
        "ozet": _ozet_olustur(gunler),
        "yil_ozet": yil_ozeti(kullanici, yil),
        "durumlar": [{"kod": k, "ad": v} for k, v in DURUMLAR.items()],
    }


def yil_ozeti(kullanici: str, yil: int) -> dict:
    """Izin&Takvim ustundeki sayilar (2026-10-15 kullanici istegi: ayin degil kisinin YIL toplami). 'gorunen': her gunun ekranda
    gorunen durumu (kayitsiz is gunu Calisiyor, hafta sonu Hafta Sonu; bolunmus gun yarim yarim)."""
    bas, son = date(yil, 1, 1), date(yil, 12, 31)
    gunler = _gunler(kullanici, bas, son)
    o = _ozet_olustur(gunler)
    o["gorunen"] = _gorunen(gunler, bas, son)
    return o


def _gorunen(gunler, bas: date, son: date) -> dict:
    """Donemin her gununun ekranda gorunen durumu: kayitsiz is gunu Calisiyor, hafta sonu Hafta Sonu, bolunmus gun yarim yarim."""
    kayit = {g.day: g for g in gunler}
    gorunen: dict[str, float] = dict.fromkeys(DURUMLAR, 0)
    gun = bas
    while gun <= son:
        g = kayit.get(gun)
        for d, a in _yarilar(g) if g is not None else [("hafta_sonu" if gun.weekday() >= 5 else "calisiyor", 1.0)]:
            gorunen[d] = gorunen.get(d, 0) + a
        gun += timedelta(days=1)
    return {k: (int(v) if float(v).is_integer() else v) for k, v in gorunen.items()}


def _uye_ozeti(kullanici: str, bas: date, son: date) -> dict:
    """TAM Takvim satiri: durum sayilari kisinin kendi Izin&Takvim ekranindaki gibi donemin TUM gunlerinden (2026-10-15 kullanici
    istegi: "personellerin kendi ekranlarinda nasil gorunuyorsa burada da"); toplanti, izin, is gunu kayitlardan."""
    gunler = _gunler(kullanici, bas, son)
    o = _ozet_olustur(gunler)
    o["durumlar"] = _gorunen(gunler, bas, son)
    return o


def gun_kaydet(kullanici: str, govde: dict) -> dict:
    """Govdede toplanti_ozeti / yapilan_isler yoksa mevcut metin korunur (eski istemci yazmaz, silmez); '' gonderilirse temizlenir."""
    gun = _tarih(govde.get("tarih"))
    durum, online, yuzyuze = _durum(govde.get("durum")), _sayi(govde.get("online"), "Online toplantı"), _sayi(govde.get("yuzyuze"), "Yüz yüze toplantı")
    durum2 = _durum2(govde.get("durum2"), durum)
    ozet = _ozet(govde["toplanti_ozeti"]) if "toplanti_ozeti" in govde else None
    isler = _ozet(govde["yapilan_isler"], "Yapılan işler") if "yapilan_isler" in govde else None
    with kullanici_oturumu(kullanici) as k:
        yazma_kilidi(k)  # oku-sonra-ekle: ayni gune eszamanli ilk yazma UNIQUE(day) ile 500 veriyordu (tests/test_yuk_yaris.py)
        kayit = k.scalar(select(CalendarDay).where(CalendarDay.day == gun))
        if ozet is None:
            ozet = (kayit.meeting_notes if kayit is not None else None) or ""
        if isler is None:
            isler = (kayit.work_notes if kayit is not None else None) or ""
        if (durum, durum2) == varsayilan_durum(gun) and online == 0 and yuzyuze == 0 and not ozet and not isler:
            if kayit is not None:
                k.delete(kayit)  # varsayilan gun (calisiyor ya da kurum gunu) kayit tutmaz
                k.commit()
            return _gun(CalendarDay(day=gun, status=durum, status2=durum2, online_count=0, face_count=0, meeting_notes=None, work_notes=None), True)
        if kayit is None:
            kayit = CalendarDay(day=gun)
            k.add(kayit)
        kayit.status, kayit.status2, kayit.online_count, kayit.face_count = durum, durum2, online, yuzyuze
        kayit.meeting_notes, kayit.work_notes = ozet or None, isler or None
        k.commit()
        return _gun(kayit, True)


def toplu_kaydet(kullanici: str, govde: dict) -> dict:
    """Tarih araligina ayni durumu atar (hafta sonlari istege bagli, kurum tatilleri her zaman atlanir). Toplanti sayilari, ozetler ve yapilan isler korunur."""
    bas, son = _tarih(govde.get("baslangic"), "Başlangıç"), _tarih(govde.get("bitis"), "Bitiş")
    if son < bas:
        raise TakvimHata(400, "Bitiş başlangıçtan önce olamaz.")
    if (son - bas).days + 1 > EN_COK_TOPLU_GUN:
        raise TakvimHata(400, f"En fazla {EN_COK_TOPLU_GUN} gün atanabilir.")
    durum, atla = _durum(govde.get("durum")), bool(govde.get("hafta_sonu_atla", True))
    atanan = 0
    with kullanici_oturumu(kullanici) as k:
        yazma_kilidi(k)
        mevcut = {r.day: r for r in k.scalars(select(CalendarDay).where(CalendarDay.day >= bas, CalendarDay.day <= son))}
        gun = bas
        while gun <= son:
            if not (atla and gun.weekday() >= 5) and (kurum_gunu(gun) is None or (durum, None) == varsayilan_durum(gun)):  # izin tatili yemez
                kayit = mevcut.get(gun)
                if (durum, None) == varsayilan_durum(gun):
                    if kayit is not None and kayit.online_count == 0 and kayit.face_count == 0 and not kayit.meeting_notes and not kayit.work_notes:
                        k.delete(kayit)  # varsayilan gun kayit tutmaz
                    elif kayit is not None:
                        kayit.status, kayit.status2 = durum, None
                else:
                    if kayit is None:
                        kayit = CalendarDay(day=gun)
                        k.add(kayit)
                    kayit.status, kayit.status2 = durum, None
                atanan += 1
            gun += timedelta(days=1)
        k.commit()
    return {"atanan": atanan}


# --- ozet ----------------------------------------------------------------------------------------------
def _bos_ozet() -> dict:
    return {"durumlar": dict.fromkeys(DURUMLAR, 0), "online": 0, "yuzyuze": 0, "kayitli_gun": 0, "is_gunu": 0, "ozet_gunu": 0, "izin_gun": 0}


def _yarilar(g) -> list[tuple[str, float]]:
    """Gunun durumlari ve agirliklari: bolunmus gunde her yari 0,5."""
    return [(g.status, 0.5), (g.status2, 0.5)] if getattr(g, "status2", None) else [(g.status, 1.0)]


def _izin(g) -> float:
    """Izin gunu katkisi: izin durumlari agirligi kadar; tek basina arife 0,5 (yarisi izin), bolunmus gunde arife yarisi tatildir (0)."""
    yarilar = _yarilar(g)
    return sum(a for d, a in yarilar if d in IZIN_DURUMLARI) + (0.5 if yarilar == [("arife_tatili", 1.0)] else 0)


def _ozet_olustur(gunler) -> dict:
    o = _bos_ozet()
    for g in gunler:
        o["kayitli_gun"] += 0 if getattr(g, "kurum_sanal", False) else 1  # kurum gunu kisinin girdigi kayit degil
        for d, a in _yarilar(g):
            o["durumlar"][d] = o["durumlar"].get(d, 0) + a
        o["izin_gun"] += _izin(g)
        o["online"] += g.online_count
        o["yuzyuze"] += g.face_count
        o["is_gunu"] += 1 if g.work_notes else 0  # yapilan is girilen gun sayisi (metin TAM Takvim'e gitmez)
        o["ozet_gunu"] += 1 if g.meeting_notes else 0  # toplanti ozeti girilen gun sayisi (metin gitmez)
    return _bitir(o)


def _bitir(o: dict) -> dict:
    o["izin_gun"] = round(o["izin_gun"], 1)
    o["durumlar"] = {k: (int(v) if float(v).is_integer() else v) for k, v in o["durumlar"].items()}  # yarim gunler 0,5
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
    liste = [_uye(u, _uye_ozeti(u.username, bas, son)) for u in personel(db)]
    # 2026-10-20 kullanici: "yalniz online ve yuzyuze adetleri toplanir; sirket izni 14,5 gun ise personel sayisiyla carpilmaz, kac gun
    # ise o yazilir". Ekip satirinin gun kirilimlari (durumlar, izin gunu) donemin takviminden (kurum gunleri; kisiye ozel izin yok);
    # kisi satirlari degismez. Kayit sayilari (girilen gun, is / ozet girilen gun) kisi toplamidir.
    takvim = _ozet_olustur(kurum := _kurum_gunleri(bas, son))
    genel = _bos_ozet()
    genel["durumlar"], genel["izin_gun"] = _gorunen(kurum, bas, son), takvim["izin_gun"]
    for u in liste:
        genel["kayitli_gun"] += u["kayitli_gun"]
        genel["online"] += u["online"]
        genel["yuzyuze"] += u["yuzyuze"]
        genel["is_gunu"] += u["is_gunu"]
        genel["ozet_gunu"] += u["ozet_gunu"]
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


def uye_gunleri(db: Session, yil: int, ceyrek: int, uye_id: int, metinli: bool = False) -> dict:
    """Bir uyenin donemdeki kayitli gunleri (TAM Takvim'de satir acilinca). metinli: admin bakiyorsa toplanti ozeti ve yapilan
    isler de gider (2026-10-15 kullanici karari: "admin tarafindan herkesin girdigi kayitlarin gorulmesi lazim"); digerleri sayiyi gorur."""
    bas, son = donem_araligi(yil, ceyrek)
    uye = db.get(AppUser, uye_id)
    if not personel_mi(uye):
        raise TakvimHata(404, "Kişi bulunamadı.")
    gunler = _gunler(uye.username, bas, son)
    return {"uye": uye.display_name or uye.username, "gunler": [_gun(g, metinli) for g in gunler]}


# --- ceyrek sunum (app.sunum kaynagi) --------------------------------------------------------------
def sunum_ozeti(db: Session, yil: int, ceyrek: int) -> dict:
    """Donemin TAM Takvim goruntusu (Ceyrek Sunum 'takvim' kaynagi; grafik bu yukle cizilir)."""
    anlik = ekip(db, yil, ceyrek)
    return {
        "yil": yil,
        "ceyrek": ceyrek,
        "durumlar": anlik["durumlar"],
        "genel": anlik["genel"],
        # 2026-10-20: TAM Takvim varsayilan donemi tum yil; sunum ceyregi gosterir. Iki rakam karismasin diye yilin toplantilari da gider.
        "yil_toplami": {k: v for k, v in ekip(db, yil, 0)["genel"].items() if k in ("online", "yuzyuze", "toplanti")},
        "uyeler": [
            {k: u[k] for k in ("ad", "durumlar", "online", "yuzyuze", "izin_gun", "toplanti", "kayitli_gun")} for u in anlik["uyeler"]
        ],
    }
