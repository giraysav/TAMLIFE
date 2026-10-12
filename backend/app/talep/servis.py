"""Gelistirme talebi / oneri kuyrugu. Uretim karsiligi: kutucuklar/talep/servis.py, blueprints/talep_bp.py.

Kurallar (uretimle ayni):
  - Talep acmak oturumu olan herkese acik. Baslik, mevcut durum ve beklenen durum AYRI AYRI zorunlu: tek kutuda
    "sunu duzeltin" yazan talepler sonradan yorum farkina donusuyordu.
  - Yonetmek (durum, atanan, hedef surum, yonetici notu): admin, TeamMngr ya da rolgorunum.TALEP_YETKISI.
    Yonetemeyen yalniz kendi taleplerini gorur.
  - Her degisiklik eski -> yeni olarak gecmise yazilir (yalniz deger gercekten degistiyse); acilis 'olusturma' satiridir.
  - Silme YALNIZ admin: talep gecmis tasir, silmek o gecmisi de yok eder. Kuyrugu yuruten 'tamamlandi'/'reddedildi' yapar.
Yetki kontrolu api katmanindadir; buradaki fonksiyonlar karar verilmis kisiyle cagrilir.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.kullanicilar import kullanici_kaydi
from app.models import AppUser, Demand, DemandLog
from app.ortak import UygulamaHatasi, iso, simdi
from app.session import Principal

TURLER = ("ozellik", "iyilestirme", "hata")
ONCELIKLER = ("dusuk", "orta", "yuksek", "kritik")
DURUMLAR = ("yeni", "incelemede", "planlandi", "yapiliyor", "tamamlandi", "reddedildi")
KAPALI = frozenset({"tamamlandi", "reddedildi"})
# Uretimdeki "Ilgili ekran" secenekleri (bos = secilmedi).
EKRANLAR = ("musteri", "utilizasyon", "takvim", "onedesk", "roller", "dashboard", "diger")
ALANLAR = ("durum", "oncelik", "atanan_id", "hedef_surum", "admin_notu")
# api adi -> model sutunu
_SUTUN = {"durum": "status", "oncelik": "priority", "atanan_id": "assignee_id", "hedef_surum": "target_version", "admin_notu": "admin_note"}
GECMIS_SINIRI = 200  # gecmiste tutulan eski/yeni deger uzunlugu


class TalepHata(UygulamaHatasi):
    """kod = HTTP durumu."""


def _ad(kisi: AppUser | None) -> str:
    return (kisi.display_name or kisi.username) if kisi else ""


def _kisa(deger: object) -> str:
    return "" if deger is None else str(deger)[:GECMIS_SINIRI]


def _gecmise_yaz(db: Session, talep_id: int, alan: str, eski: object, yeni: object, yapan_id: int | None) -> None:
    db.add(DemandLog(demand_id=talep_id, field=alan, old_value=_kisa(eski), new_value=_kisa(yeni), actor_id=yapan_id, at=simdi()))


def olustur(db: Session, user: Principal, veri: dict) -> int:
    """veri: baslik, mevcut_durum, beklenen_durum, kabul_olcutu, tur, oncelik, modul (uzunluklar api'de dogrulanir)."""
    baslik = (veri.get("baslik") or "").strip()
    mevcut = (veri.get("mevcut_durum") or "").strip()
    beklenen = (veri.get("beklenen_durum") or "").strip()
    if not baslik:
        raise TalepHata(400, "Başlık zorunlu.")
    if not mevcut or not beklenen:
        raise TalepHata(400, "“Şu an ne oluyor?” ve “Ne olmasını istiyorsunuz?” alanlarının ikisi de zorunlu.")
    tur = veri.get("tur") or "ozellik"
    oncelik = veri.get("oncelik") or "orta"
    modul = (veri.get("modul") or "").strip()
    if tur not in TURLER or oncelik not in ONCELIKLER or (modul and modul not in EKRANLAR):
        raise TalepHata(400, "Geçersiz tür, önem ya da ekran.")
    kisi = kullanici_kaydi(db, user)
    talep = Demand(
        title=baslik,
        kind=tur,
        priority=oncelik,
        module=modul,
        current_state=mevcut,
        expected_state=beklenen,
        acceptance=(veri.get("kabul_olcutu") or "").strip(),
        opened_by_id=kisi.id,
        opened_at=simdi(),
        status="yeni",
        target_version="",
        admin_note="",
    )
    db.add(talep)
    db.flush()
    _gecmise_yaz(db, talep.id, "olusturma", "", "", kisi.id)
    return talep.id


def _talep(db: Session, talep_id: int) -> Demand:
    talep = db.get(Demand, talep_id)
    if talep is None:
        raise TalepHata(404, "Talep bulunamadı.")
    return talep


def guncelle(db: Session, user: Principal, talep_id: int, degisiklik: dict) -> list[str]:
    """Yalniz verilen alanlar; gercekten degisenler gecmise yazilir. Donus: degisen alan adlari."""
    talep = _talep(db, talep_id)
    if "durum" in degisiklik and degisiklik["durum"] not in DURUMLAR:
        raise TalepHata(400, "Geçersiz durum.")
    if "oncelik" in degisiklik and degisiklik["oncelik"] not in ONCELIKLER:
        raise TalepHata(400, "Geçersiz önem.")
    if degisiklik.get("atanan_id") is not None:
        atanan = db.get(AppUser, degisiklik["atanan_id"])
        if atanan is None or not atanan.active:
            raise TalepHata(400, "Atanan kişi bulunamadı.")
    yapan = kullanici_kaydi(db, user)
    degisen: list[str] = []
    for alan in ALANLAR:
        if alan not in degisiklik:
            continue
        yeni = degisiklik[alan]
        if isinstance(yeni, str):
            yeni = yeni.strip()
        eski = getattr(talep, _SUTUN[alan])
        if eski == yeni:
            continue
        if alan == "atanan_id":
            _gecmise_yaz(db, talep.id, alan, _ad(db.get(AppUser, eski)) if eski else "", _ad(db.get(AppUser, yeni)) if yeni else "", yapan.id)
        else:
            _gecmise_yaz(db, talep.id, alan, eski, yeni, yapan.id)
        setattr(talep, _SUTUN[alan], yeni)
        degisen.append(alan)
    if degisen:
        talep.updated_at = simdi()
    return degisen


def sil(db: Session, talep_id: int) -> None:
    talep = _talep(db, talep_id)
    db.execute(delete(DemandLog).where(DemandLog.demand_id == talep.id))
    db.delete(talep)


def _kisiler(db: Session, kimlikler: set[int]) -> dict[int, AppUser]:
    if not kimlikler:
        return {}
    return {k.id: k for k in db.scalars(select(AppUser).where(AppUser.id.in_(kimlikler)))}


def liste(db: Session, user: Principal, yonetebilir: bool, durum: str = "acik") -> dict:
    """durum: 'acik' (kapanmamislar, varsayilan), '' (hepsi) ya da DURUMLAR'dan biri.
    Yonetemeyen yalniz kendi taleplerini gorur; acik sayisi yalniz yonetene doner."""
    sorgu = select(Demand).order_by(Demand.opened_at.desc(), Demand.id.desc())
    if not yonetebilir:
        sorgu = sorgu.where(Demand.opened_by_id == kullanici_kaydi(db, user).id)
    if durum == "acik":
        sorgu = sorgu.where(Demand.status.not_in(KAPALI))
    elif durum:
        if durum not in DURUMLAR:
            raise TalepHata(400, "Geçersiz durum süzgeci.")
        sorgu = sorgu.where(Demand.status == durum)
    talepler = list(db.scalars(sorgu))
    gecmis: dict[int, list[DemandLog]] = {}
    if talepler:
        for kayit in db.scalars(select(DemandLog).where(DemandLog.demand_id.in_([t.id for t in talepler])).order_by(DemandLog.at, DemandLog.id)):
            gecmis.setdefault(kayit.demand_id, []).append(kayit)
    kimlikler = {t.opened_by_id for t in talepler} | {t.assignee_id for t in talepler if t.assignee_id}
    kimlikler |= {k.actor_id for kayitlar in gecmis.values() for k in kayitlar if k.actor_id}
    kisiler = _kisiler(db, kimlikler)
    sonuc: dict = {"yonetebilir": yonetebilir, "talepler": [_satir(t, gecmis.get(t.id, []), kisiler, yonetebilir) for t in talepler]}
    if yonetebilir:
        sonuc["acik_sayisi"] = db.scalar(select(func.count()).select_from(Demand).where(Demand.status.not_in(KAPALI))) or 0
        sonuc["kisiler"] = [
            {"id": k.id, "ad": _ad(k)}
            for k in db.scalars(select(AppUser).where(AppUser.active.is_(True)).order_by(AppUser.display_name, AppUser.username))
        ]
    return sonuc


def _satir(t: Demand, gecmis: list[DemandLog], kisiler: dict[int, AppUser], yonetebilir: bool) -> dict:
    satir = {
        "id": t.id,
        "baslik": t.title,
        "tur": t.kind,
        "oncelik": t.priority,
        "modul": t.module,
        "mevcut_durum": t.current_state,
        "beklenen_durum": t.expected_state,
        "kabul_olcutu": t.acceptance,
        "durum": t.status,
        "acik": t.status not in KAPALI,
        "talep_eden": _ad(kisiler.get(t.opened_by_id)),
        "olusturuldu": iso(t.opened_at),
        "guncellendi": iso(t.updated_at),
        "hedef_surum": t.target_version,
        "admin_notu": t.admin_note,
        "atanan_id": t.assignee_id,
        "atanan": _ad(kisiler.get(t.assignee_id)) if t.assignee_id else "",
    }
    if yonetebilir:  # gecmis is listesinin parcasi; talep eden kendi talebinin durumunu ve notunu zaten gorur
        satir["gecmis"] = [
            {"zaman": iso(k.at), "yapan": _ad(kisiler.get(k.actor_id)) if k.actor_id else "", "alan": k.field, "eski": k.old_value, "yeni": k.new_value}
            for k in gecmis
        ]
    return satir
