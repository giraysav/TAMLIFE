"""Log yonetimi: kalici denetim olaylari (audit_event), arama, CSV disa aktarim, aktif oturumlar.

Eski yaklasim (uretim): kisi basina ayri tablo (u_<id>). Burada TEK tablo + indeksli filtre; kisi/olay/sonuc/zaman suzulur.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app import session as oturum
from app.models import AuditEvent
from app.ortak import iso, sayfa_bilgisi, simdi
from app.yonetim.kalici_yazici import yazici

CSV_AZAMI_SATIR = 5000


def kalici_yaz(satir: dict[str, str]) -> None:
    """audit_log.sink: olayi kuyruga alir (aninda doner); yazim arka planda (bkz. kalici_yazici)."""
    yazici(satir)


def _suz(*, aksiyon: str, sonuc: str, kullanici: str, modul: str, q: str, bas: datetime | None, bit: datetime | None):
    sorgu = select(AuditEvent)
    if aksiyon.strip():
        sorgu = sorgu.where(AuditEvent.action.startswith(aksiyon.strip(), autoescape=True))
    if sonuc in ("allow", "deny"):
        sorgu = sorgu.where(AuditEvent.outcome == sonuc)
    if kullanici.strip():
        sorgu = sorgu.where(func.lower(AuditEvent.actor) == kullanici.strip().lower())
    if modul.strip():
        sorgu = sorgu.where(AuditEvent.module_key == modul.strip())
    if q.strip():
        sorgu = sorgu.where(func.lower(AuditEvent.detail).contains(q.strip().lower(), autoescape=True))
    if bas is not None:
        sorgu = sorgu.where(AuditEvent.at >= bas)
    if bit is not None:
        sorgu = sorgu.where(AuditEvent.at < bit)
    return sorgu


def tarih_oku(metin: str, *, gun_sonu: bool = False) -> datetime | None:
    """'YYYY-MM-DD' (UTC) -> datetime; bos ya da gecersizse None. gun_sonu: ertesi gunun baslangici (bitis dahil)."""
    try:
        gun = datetime.strptime(metin.strip(), "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None
    return gun + timedelta(days=1) if gun_sonu else gun


def _satir(e: AuditEvent) -> dict[str, object]:
    return {
        "id": e.id,
        "zaman": iso(e.at),
        "kullanici": e.actor,
        "olay": e.action,
        "sonuc": e.outcome,
        "modul": e.module_key,
        "ayrinti": e.detail,
        "ip": e.ip or "",
    }


def kullanicilar(db: Session, *, sayfa: int = 1, adet: int = 50, **filtre) -> dict[str, object]:
    """Denetim olaylarinin kullaniciya gore agaci (2026-11-26 kullanici: 'kullanici adlarina gore tree, artiya basinca ne yaptigi').
    Ayni filtreler gecerli; kullanici basina olay / red sayisi, ilk-son olay ve son basarili girisin zamani + IP'si. Olaylarin kendisi
    acilan dugumde /gunlukler?kullanici=<ad> ile sayfali gelir. Siralama: en son islem yapan ustte."""
    yazici.bosalt(zorla=True)
    alt = _suz(**filtre).subquery()
    anahtar = func.lower(alt.c.actor)
    gruplu = (
        select(
            func.min(alt.c.actor).label("kullanici"),
            func.count().label("olay"),
            func.sum(case((alt.c.outcome == "deny", 1), else_=0)).label("red"),
            func.min(alt.c.at).label("ilk"),
            func.max(alt.c.at).label("son"),
        )
        .group_by(anahtar)
    )
    toplam = db.scalar(select(func.count()).select_from(gruplu.subquery())) or 0
    sayfa, atla, adet = sayfa_bilgisi(sayfa, adet, toplam)
    satirlar = db.execute(gruplu.order_by(func.max(alt.c.at).desc()).offset(atla).limit(adet)).all()
    adlar = [s.kullanici.lower() for s in satirlar]
    girisler: dict[str, AuditEvent] = {}
    if adlar:
        # son basarili giris (filtreden bagimsiz): kullanicinin panele en son hangi IP'den girdigi
        son_id = (
            select(func.max(AuditEvent.id))
            .where(AuditEvent.action == "login", AuditEvent.outcome == "allow", func.lower(AuditEvent.actor).in_(adlar))
            .group_by(func.lower(AuditEvent.actor))
        )
        for e in db.scalars(select(AuditEvent).where(AuditEvent.id.in_(son_id))):
            girisler[e.actor.lower()] = e
    sonuc = []
    for s in satirlar:
        g = girisler.get(s.kullanici.lower())
        sonuc.append({
            "kullanici": s.kullanici, "olay": int(s.olay or 0), "red": int(s.red or 0), "ilk": iso(s.ilk), "son": iso(s.son),
            "son_giris": iso(g.at) if g else None, "son_giris_ip": (g.ip or "") if g else "",
        })  # fmt: skip
    return {"toplam": toplam, "sayfa": sayfa, "adet": adet, "kullanicilar": sonuc}


def sorgula(db: Session, *, sayfa: int = 1, adet: int = 50, **filtre) -> dict[str, object]:
    yazici.bosalt(zorla=True)  # yonetici son olaylari gorsun
    sorgu = _suz(**filtre)
    toplam = db.scalar(select(func.count()).select_from(sorgu.subquery())) or 0
    sayfa, atla, adet = sayfa_bilgisi(sayfa, adet, toplam)
    satirlar = db.scalars(sorgu.order_by(AuditEvent.id.desc()).offset(atla).limit(adet)).all()
    return {"toplam": toplam, "sayfa": sayfa, "adet": adet, "satirlar": [_satir(e) for e in satirlar]}


def _hucre(deger: object) -> str:
    """CSV enjeksiyonu: Excel'in formul sayacagi baslangiclar kesme isaretiyle etkisizlestirilir."""
    metin = "" if deger is None else str(deger)
    return "'" + metin if metin[:1] in ("=", "+", "-", "@", "\t", "\r") else metin


def csv_uret(db: Session, **filtre) -> bytes:
    """Excel icin UTF-8 BOM'lu, ';' ayracli CSV (en yeni CSV_AZAMI_SATIR olay)."""
    yazici.bosalt(zorla=True)
    cikti = io.StringIO()
    csv_yazici = csv.writer(cikti, delimiter=";", lineterminator="\r\n")
    csv_yazici.writerow(["Zaman (UTC)", "Kullanıcı", "Olay", "Sonuç", "Modül", "Ayrıntı", "IP"])
    for e in db.scalars(_suz(**filtre).order_by(AuditEvent.id.desc()).limit(CSV_AZAMI_SATIR)):
        csv_yazici.writerow([_hucre(x) for x in (iso(e.at), e.actor, e.action, e.outcome, e.module_key, e.detail, e.ip)])
    return b"\xef\xbb\xbf" + cikti.getvalue().encode("utf-8")


def ozet(db: Session) -> dict[str, object]:
    yazici.bosalt()
    esik = simdi() - timedelta(hours=24)
    son24 = db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.at >= esik)) or 0
    red24 = db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.at >= esik, AuditEvent.outcome == "deny")) or 0
    toplam = db.scalar(select(func.count()).select_from(AuditEvent)) or 0
    return {"son_24s": son24, "red_24s": red24, "toplam": toplam}


def oturumlar() -> list[dict[str, object]]:
    return sorted(oturum.aktif_oturumlar(), key=lambda o: int(o["idle_s"]))  # type: ignore[call-overload]
