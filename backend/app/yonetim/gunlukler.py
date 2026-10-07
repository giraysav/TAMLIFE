"""Log yonetimi: kalici denetim olaylari (audit_event), arama, CSV disa aktarim, aktif oturumlar.

Eski yaklasim (uretim): kisi basina ayri tablo (u_<id>). Burada TEK tablo + indeksli filtre; kisi/olay/sonuc/zaman suzulur.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
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
    }


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
    csv_yazici.writerow(["Zaman (UTC)", "Kullanıcı", "Olay", "Sonuç", "Modül", "Ayrıntı"])
    for e in db.scalars(_suz(**filtre).order_by(AuditEvent.id.desc()).limit(CSV_AZAMI_SATIR)):
        csv_yazici.writerow([_hucre(x) for x in (iso(e.at), e.actor, e.action, e.outcome, e.module_key, e.detail)])
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
