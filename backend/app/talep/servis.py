# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Gelistirme talebi / oneri kuyrugu. Uretim karsiligi: kutucuklar/talep/servis.py, blueprints/talep_bp.py.

Kurallar (uretimle ayni):
  - Talep acmak oturumu olan herkese acik. Baslik, mevcut durum ve beklenen durum AYRI AYRI zorunlu: tek kutuda
    "sunu duzeltin" yazan talepler sonradan yorum farkina donusuyordu.
  - Yonetmek (durum, atanan, hedef surum, yonetici notu): admin, TeamMngr ya da rolgorunum.TALEP_YETKISI.
    Yonetemeyen yalniz kendi taleplerini gorur.
  - Her degisiklik eski -> yeni olarak gecmise yazilir (yalniz deger gercekten degistiyse); acilis 'olusturma' satiridir.
  - Silme YALNIZ admin: talep gecmis tasir, silmek o gecmisi de yok eder. Kuyrugu yuruten 'tamamlandi'/'reddedildi' yapar.
  - Talep eden (2026-10-31): talep e-postayla da gelebilir; yoneten talebi acarken ya da sonradan talep edeni ve gelis yolunu
    (panel / eposta) secer. Bos ise talebi giren kisidir. Yonetemeyen, talep ettigi ya da girdigi talepleri gorur.
  - Durum, onem, hedef surum ya da yonetici notu degisince talep edene panel bildirimi gider (degistiren kendisi degilse).
Yetki kontrolu api katmanindadir; buradaki fonksiyonlar karar verilmis kisiyle cagrilir.
"""

from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.bildirim import servis as bildirim
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
KANALLAR = ("panel", "eposta")
ALANLAR = ("durum", "oncelik", "atanan_id", "hedef_surum", "admin_notu", "talep_eden_id", "kanal")
# api adi -> model sutunu
_SUTUN = {
    "durum": "status",
    "oncelik": "priority",
    "atanan_id": "assignee_id",
    "hedef_surum": "target_version",
    "admin_notu": "admin_note",
    "talep_eden_id": "requester_id",
    "kanal": "channel",
}
_KISI_ALANLARI = frozenset({"atanan_id", "talep_eden_id"})  # gecmise kimlik yerine ad yazilir
# Talep edeni ilgilendiren degisiklikler bildirim uretir; atama ve talep eden/kanal duzeltmesi uretmez.
BILDIRIM_ALANLARI = ("durum", "oncelik", "hedef_surum", "admin_notu")
DURUM_ADLARI = {"yeni": "Yeni", "incelemede": "İncelemede", "planlandi": "Planlandı", "yapiliyor": "Yapılıyor", "tamamlandi": "Tamamlandı", "reddedildi": "Reddedildi"}
ONCELIK_ADLARI = {"dusuk": "Düşük", "orta": "Orta", "yuksek": "Yüksek", "kritik": "Kritik"}
GECMIS_SINIRI = 200  # gecmiste tutulan eski/yeni deger uzunlugu


class TalepHata(UygulamaHatasi):
    """kod = HTTP durumu."""


def _ad(kisi: AppUser | None) -> str:
    return (kisi.display_name or kisi.username) if kisi else ""


def _kisa(deger: object) -> str:
    return "" if deger is None else str(deger)[:GECMIS_SINIRI]


def _gecmise_yaz(db: Session, talep_id: int, alan: str, eski: object, yeni: object, yapan_id: int | None) -> None:
    db.add(DemandLog(demand_id=talep_id, field=alan, old_value=_kisa(eski), new_value=_kisa(yeni), actor_id=yapan_id, at=simdi()))


def _etkin_kisi(db: Session, kimlik: int, mesaj: str) -> AppUser:
    kisi = db.get(AppUser, kimlik)
    if kisi is None or not kisi.active:
        raise TalepHata(400, mesaj)
    return kisi


def olustur(db: Session, user: Principal, veri: dict, yonetebilir: bool = False) -> int:
    """veri: baslik, mevcut_durum, beklenen_durum, kabul_olcutu, tur, oncelik, modul (uzunluklar api'de dogrulanir);
    yonetebilen icin talep_eden_id ve kanal (e-postayla gelen talebi baskasi adina girme)."""
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
    kanal = veri.get("kanal") or "panel"
    talep_eden_id = veri.get("talep_eden_id")
    if not yonetebilir and (talep_eden_id is not None or kanal != "panel"):
        raise TalepHata(403, "Başkası adına talep girmek için talepleri yönetme yetkisi gerekir.")
    if kanal not in KANALLAR:
        raise TalepHata(400, "Geçersiz geliş yolu.")
    if talep_eden_id is not None:
        _etkin_kisi(db, talep_eden_id, "Talep eden kişi bulunamadı.")
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
        requester_id=talep_eden_id or kisi.id,
        channel=kanal,
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
        _etkin_kisi(db, degisiklik["atanan_id"], "Atanan kişi bulunamadı.")
    if "talep_eden_id" in degisiklik:
        if degisiklik["talep_eden_id"] is None:
            raise TalepHata(400, "Talep eden boş bırakılamaz.")
        _etkin_kisi(db, degisiklik["talep_eden_id"], "Talep eden kişi bulunamadı.")
    if "kanal" in degisiklik and degisiklik["kanal"] not in KANALLAR:
        raise TalepHata(400, "Geçersiz geliş yolu.")
    yapan = kullanici_kaydi(db, user)
    degisen: list[str] = []
    onceki: dict[str, object] = {}
    for alan in ALANLAR:
        if alan not in degisiklik:
            continue
        yeni = degisiklik[alan]
        if isinstance(yeni, str):
            yeni = yeni.strip()
        eski = getattr(talep, _SUTUN[alan])
        if eski == yeni:
            continue
        if alan in _KISI_ALANLARI:
            _gecmise_yaz(db, talep.id, alan, _ad(db.get(AppUser, eski)) if eski else "", _ad(db.get(AppUser, yeni)) if yeni else "", yapan.id)
        else:
            _gecmise_yaz(db, talep.id, alan, eski, yeni, yapan.id)
        setattr(talep, _SUTUN[alan], yeni)
        onceki[alan] = eski
        degisen.append(alan)
    if degisen:
        talep.updated_at = simdi()
        _talep_edene_bildir(db, talep, onceki, yapan.id)
    return degisen


def _talep_edene_bildir(db: Session, talep: Demand, onceki: dict[str, object], yapan_id: int) -> None:
    """Talep edeni ilgilendiren degisiklikleri tek bildirimde toplar; degistiren talep edenin kendisiyse bildirim yok."""
    sahip = talep.requester_id or talep.opened_by_id
    parcalar = []
    if "durum" in onceki:
        parcalar.append(f"durum {DURUM_ADLARI.get(str(onceki['durum']), onceki['durum'])} → {DURUM_ADLARI.get(talep.status, talep.status)}")
    if "oncelik" in onceki:
        parcalar.append(f"önem {ONCELIK_ADLARI.get(talep.priority, talep.priority)}")
    if "hedef_surum" in onceki:
        parcalar.append(f"hedef sürüm {talep.target_version or '—'}")
    if "admin_notu" in onceki:
        parcalar.append("yönetici notu güncellendi")
    if sahip == yapan_id or not parcalar:
        return
    bildirim.ekle(db, sahip, "talep", f"Talebiniz #{talep.id} “{talep.title}”: {', '.join(parcalar)}", "#/talep", talep.id)


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
        ben = kullanici_kaydi(db, user).id
        sorgu = sorgu.where(or_(Demand.requester_id == ben, Demand.opened_by_id == ben))
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
    kimlikler = {t.opened_by_id for t in talepler} | {t.assignee_id for t in talepler if t.assignee_id} | {t.requester_id for t in talepler if t.requester_id}
    kimlikler |= {k.actor_id for kayitlar in gecmis.values() for k in kayitlar if k.actor_id}
    kisiler = _kisiler(db, kimlikler)
    sonuc: dict = {"yonetebilir": yonetebilir, "talepler": [_satir(t, gecmis.get(t.id, []), kisiler, yonetebilir) for t in talepler]}
    if yonetebilir:
        sonuc["acik_sayisi"] = db.scalar(select(func.count()).select_from(Demand).where(Demand.status.not_in(KAPALI))) or 0
        sonuc["kisiler"] = [
            {"id": k.id, "ad": _ad(k), "kullanici": k.username}
            for k in db.scalars(select(AppUser).where(AppUser.active.is_(True)).order_by(AppUser.display_name, AppUser.username))
        ]
    return sonuc


def _satir(t: Demand, gecmis: list[DemandLog], kisiler: dict[int, AppUser], yonetebilir: bool) -> dict:
    talep_eden_id = t.requester_id or t.opened_by_id
    talep_eden = kisiler.get(talep_eden_id)
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
        "talep_eden_id": talep_eden_id,
        "talep_eden": _ad(talep_eden),
        "talep_eden_kullanici": talep_eden.username if talep_eden else "",
        "giren": _ad(kisiler.get(t.opened_by_id)) if t.opened_by_id != talep_eden_id else "",  # baskasi adina girildiyse
        "kanal": t.channel or "panel",
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
