"""Aylik rapor: taslak, alicilar, ayda tek ONAYLI gonderim, gonderim gecmisi ve geri alma.

Uretim karsiliklari: kutucuklar/rapor/aylik.py (taslak, gonderim, geri alma), rapor/servis.py (rapor birimi,
durum ozeti), blueprints/customer_bp.py (rapor_alicilari, aylik_rapor_taslak, send_customer_report_email,
aylik_rapor_geri_al). Iletiyi gonderen her zaman personeldir.
Dogrulanmadi / sonra: Outlook taslagi (.eml) uretimi ve mail HTML sablonu bu surumde yok; gonderim kaydi,
kilit ve PDF arsivi vardir. Ay, uretimdeki gibi UTC'ye gore belirlenir.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AppUser, Customer, Report, ReportDispatch, ReportDraft, ReportRecipient
from app.musteri.servis import MusteriHata, musteri_getir, rapor_birimi_mi, yonetici_mi
from app.ortak import tr_kucuk
from app.rapor import metin as rapor_metin
from app.session import Principal
from app.skor.servis import kullanici_kaydi

AZAMI_PDF = 30 * 1024 * 1024
EN_FAZLA_ALICI = 20
_EPOSTA = re.compile(r"[^@\s]+@([^@\s]+\.[^@\s]+)")
_AYRAC = re.compile(r"[;,\s]+")


class RaporHata(MusteriHata):
    def __init__(self, kod: int, mesaj: str, ek: dict | None = None) -> None:
        super().__init__(kod, mesaj)
        self.ek = ek or {}


def simdi() -> datetime:
    return datetime.now(UTC)


def donem() -> tuple[int, int]:
    an = simdi()
    return an.year, an.month


def rapor_klasoru() -> Path:
    ayar = os.environ.get("TAMLIFE_REPORT_DIR", "").strip()
    return Path(ayar) if ayar else Path(__file__).resolve().parents[2] / "data" / "reports"


# --- alicilar ------------------------------------------------------------------------------------
def alicilari_ayikla(ham: object) -> list[str]:
    """Bos olabilir. Verildiyse dogrulanir; TAMLIFE disi alanlar icin RAPOR_MAIL_IZINLI_ALANLAR tanimliysa yalniz o alanlar."""
    if ham is None or ham == "":
        return []
    if isinstance(ham, str):
        ham = _AYRAC.split(ham)
    if not isinstance(ham, list):
        raise RaporHata(400, "Alıcı listesi geçersiz.")
    alicilar = [str(a).strip() for a in ham if str(a).strip()]
    if len(alicilar) > EN_FAZLA_ALICI:
        raise RaporHata(400, f"En fazla {EN_FAZLA_ALICI} alıcı girilebilir.")
    izinli = {a.strip().lower() for a in os.environ.get("RAPOR_MAIL_IZINLI_ALANLAR", "").split(",") if a.strip()}
    for adres in alicilar:
        eslesme = _EPOSTA.fullmatch(adres)  # fullmatch: sondaki satir sonu baslik enjeksiyonuna yol acmasin
        if not eslesme:
            raise RaporHata(400, f"Geçersiz e-posta adresi: {adres[:80]}")
        if izinli and eslesme.group(1).lower() not in izinli:
            raise RaporHata(400, f"Bu alana rapor gönderimi izinli değil: {eslesme.group(1)[:80]}")
    return alicilar


def alicilar_getir(db: Session, musteri_id: int) -> dict:
    kayit = db.get(ReportRecipient, musteri_id)
    return {"kime": kayit.to_addrs if kayit else "", "bilgi": kayit.cc_addrs if kayit else ""}


def alicilar_kaydet(db: Session, user: Principal, musteri_id: int, govde: dict) -> dict:
    musteri = musteri_getir(db, user, musteri_id)
    try:
        kime = alicilari_ayikla(govde.get("kime"))
        bilgi = alicilari_ayikla(govde.get("bilgi"))
    except RaporHata as exc:
        raise RaporHata(exc.kod, ("Kime/Bilgi: " + exc.mesaj)) from exc
    kayit = db.get(ReportRecipient, musteri.id) or ReportRecipient(customer_id=musteri.id)
    kayit.to_addrs, kayit.cc_addrs = "; ".join(kime), "; ".join(bilgi)
    db.add(kayit)
    db.flush()
    return {"kime": kayit.to_addrs, "bilgi": kayit.cc_addrs}


# --- rapor birimi ----------------------------------------------------------------------------------
def ayri_rapor_ayarla(db: Session, user: Principal, musteri_id: int, deger: object) -> dict:
    musteri = musteri_getir(db, user, musteri_id)
    if musteri.parent_id is None:
        raise RaporHata(400, "Bu seçim yalnız istirakler içindir.")
    if not isinstance(deger, bool):
        raise RaporHata(400, "Seçim evet ya da hayır olmalı.")
    musteri.separate_report = deger
    db.flush()
    return {"ayri_rapor": deger}


# --- taslak ----------------------------------------------------------------------------------------
def taslak_temizle(alanlar: object) -> dict:
    """Bilinmeyen alan atilir, metinler kisaltilir."""
    alanlar = alanlar if isinstance(alanlar, dict) else {}
    return {ad: str(alanlar.get(ad) or "")[:uzunluk] for ad, uzunluk in rapor_metin.TASLAK_ALANLARI.items() if alanlar.get(ad) not in (None, "")}


def aktif_gonderim(db: Session, musteri_id: int, yil: int, ay: int) -> ReportDispatch | None:
    return db.scalar(
        select(ReportDispatch).where(
            ReportDispatch.customer_id == musteri_id,
            ReportDispatch.year == yil,
            ReportDispatch.month == ay,
            ReportDispatch.status == "sent",
        )
    )


def gonderim_ozeti(g: ReportDispatch, musteri_adlari: dict[int, str] | None = None) -> dict:
    return {
        "id": g.id,
        "customer_id": g.customer_id,
        "musteri": (musteri_adlari or {}).get(g.customer_id, ""),
        "yil": g.year,
        "ay": g.month,
        "gonderen": g.sender,
        "zaman": g.at.isoformat() if g.at else "",
        "konu": g.subject,
        "durum": g.status,
        "pdf": bool(g.pdf_file),
        "geri_alan": g.reverted_by,
        "geri_alma_zamani": g.reverted_at.isoformat() if g.reverted_at else None,
    }


def taslak_getir(db: Session, user: Principal, musteri_id: int) -> dict:
    """Bu ayin taslagi: kayitli alanlar uzerine hazir baslangic metinleri."""
    musteri = musteri_getir(db, user, musteri_id)
    yil, ay = donem()
    satir = db.get(ReportDraft, (musteri.id, yil, ay))
    kayitli = satir.fields if satir and isinstance(satir.fields, dict) else {}
    dil: str = str(kayitli.get("dil")) if kayitli.get("dil") in rapor_metin.DILLER else "tr"
    varsayilan = {
        "dil": dil,
        "konu": rapor_metin.mail_konusu(musteri.name, ay, yil, dil),
        "govde": rapor_metin.mail_govdesi(ay, yil, dil),
        "imza": rapor_metin.imza(user.username, dil),
        **rapor_metin.VARSAYILAN_METINLER[dil],
        **rapor_metin.BASLANGIC_METINLERI[dil],
    }
    gonderim = aktif_gonderim(db, musteri.id, yil, ay)
    return {
        "yil": yil,
        "ay": ay,
        "birim": rapor_birimi_mi(musteri),
        "alanlar": {**varsayilan, **kayitli},
        "kayitli": satir is not None,
        "guncelleyen": satir.updated_by if satir else None,
        "zaman": satir.updated_at.isoformat() if satir and satir.updated_at else None,
        "alicilar": alicilar_getir(db, musteri.id),
        "gonderim": gonderim_ozeti(gonderim) if gonderim else None,
    }


def taslak_kaydet(db: Session, user: Principal, musteri_id: int, alanlar: object) -> dict:
    musteri = musteri_getir(db, user, musteri_id)
    yil, ay = donem()
    onceki = aktif_gonderim(db, musteri.id, yil, ay)
    if onceki:
        raise RaporHata(409, "Bu ayın raporu gönderildi; taslak değiştirilemez.", {"kilitli": True})
    if not isinstance(alanlar, dict):
        raise RaporHata(400, "Kaydedilecek alan yok.")
    if alanlar.get("dil") not in (None, "") and alanlar.get("dil") not in rapor_metin.DILLER:
        raise RaporHata(400, "Rapor dili tr ya da en olmalı.")
    temiz = taslak_temizle(alanlar)
    satir = db.get(ReportDraft, (musteri.id, yil, ay))
    zaman = simdi()
    if satir is None:
        db.add(ReportDraft(customer_id=musteri.id, year=yil, month=ay, fields=temiz, updated_by=user.username[:120], updated_at=zaman))
    else:
        satir.fields, satir.updated_by, satir.updated_at = temiz, user.username[:120], zaman
    db.flush()
    return {"zaman": zaman.isoformat()}


# --- gonderim ------------------------------------------------------------------------------------
def _pdf_coz(ham: object) -> bytes | None:
    if not ham:
        return None
    metin = str(ham)
    try:
        veri = base64.b64decode(metin.split(",", 1)[1] if "," in metin else metin, validate=True)
    except (ValueError, IndexError) as exc:
        raise RaporHata(400, "PDF verisi okunamadı.") from exc
    if not veri.startswith(b"%PDF"):
        raise RaporHata(400, "Ek PDF belgesi geçersiz (PDF imzası yok).")
    if len(veri) > AZAMI_PDF:
        raise RaporHata(400, "PDF çok büyük (en fazla 30 MB).")
    return veri


def _pdf_yaz(musteri_id: int, yil: int, ay: int, veri: bytes) -> tuple[str, int, str]:
    klasor = rapor_klasoru() / str(yil) / f"{ay:02d}"
    klasor.mkdir(parents=True, exist_ok=True)
    ad = f"musteri{musteri_id}_{simdi():%Y%m%d%H%M%S%f}.pdf"
    (klasor / ad).write_bytes(veri)
    return f"{yil}/{ay:02d}/{ad}", len(veri), hashlib.sha256(veri).hexdigest()


def gonder(db: Session, user: Principal, musteri_id: int, govde: dict) -> dict:
    """ONAYLI aylik rapor gonderimi: ayda TEK rapor. Onay zorunlu, bu ay gonderilmisse 409."""
    musteri = musteri_getir(db, user, musteri_id)
    if govde.get("onay") is not True:
        raise RaporHata(400, "Rapor gönderimi için onay gerekli.")
    yil, ay = donem()
    onceki = aktif_gonderim(db, musteri.id, yil, ay)
    if onceki:
        raise RaporHata(
            409,
            f"Bu ayın raporu {onceki.sender or '-'} tarafından gönderildi. Ayda yalnız bir rapor gönderilebilir.",
            {"kilitli": True, "gonderim": gonderim_ozeti(onceki)},
        )
    try:
        kime = alicilari_ayikla(govde.get("to") if "to" in govde else alicilar_getir(db, musteri.id)["kime"])
        bilgi = alicilari_ayikla(govde.get("cc") if "cc" in govde else alicilar_getir(db, musteri.id)["bilgi"])
    except RaporHata as exc:
        raise RaporHata(exc.kod, "Alıcılar: " + exc.mesaj) from exc
    konu = " ".join(str(govde.get("subject") or f"TAM Aylık Rapor - {musteri.name}").split())[:200]
    pdf = _pdf_coz(govde.get("pdf_base64"))
    kisi = kullanici_kaydi(db, user)
    zaman = simdi()
    dosya: tuple[str, int, str] | None = None
    try:
        with db.begin_nested():
            rapor = Report(
                customer_id=musteri.id,
                user_id=kisi.id,
                report_month=ay,
                report_year=yil,
                is_submitted=True,
                created_at=zaman,
                last_edited_by=user.username[:100],
                last_edited_at=zaman,
            )
            db.add(rapor)
            db.flush()
            if pdf is not None:
                dosya = _pdf_yaz(musteri.id, yil, ay, pdf)
            db.add(
                ReportDispatch(
                    customer_id=musteri.id,
                    year=yil,
                    month=ay,
                    sender_id=kisi.id,
                    sender=user.username[:120],
                    at=zaman,
                    subject=konu,
                    report_id=rapor.id,
                    pdf_file=dosya[0] if dosya else None,
                    pdf_size=dosya[1] if dosya else None,
                    pdf_sha256=dosya[2] if dosya else None,
                    status="sent",
                )
            )
            db.execute(update(Customer).where(Customer.id == musteri.id).values(report_count=func.coalesce(Customer.report_count, 0) + 1))
            db.flush()
    except IntegrityError as exc:  # esZamanli ikinci gonderim kismi benzersiz indekse takilir
        raise RaporHata(409, "Bu ayın raporu az önce gönderildi. Ayda yalnız bir rapor gönderilebilir.", {"kilitli": True}) from exc
    gonderim = aktif_gonderim(db, musteri.id, yil, ay)
    assert gonderim is not None
    return {"gonderim": gonderim_ozeti(gonderim), "kime": kime, "bilgi": bilgi}


def geri_al(db: Session, user: Principal, gonderim_id: int) -> dict:
    """Yalniz admin: yanlis gonderilen ayin kilidini acar. Rapor kaydi silinir, sayac azalir; gonderim 'reverted' kalir."""
    if not (user.is_admin or user.role == "admin"):
        raise RaporHata(403, "Yetki yok.")
    g = db.get(ReportDispatch, gonderim_id)
    if g is None or g.status != "sent":
        raise RaporHata(404, "Geri alınacak gönderim bulunamadı.")
    rapor_id = g.report_id
    g.status, g.reverted_by, g.reverted_at, g.report_id = "reverted", user.username[:120], simdi(), None
    db.flush()
    if rapor_id:
        rapor = db.get(Report, rapor_id)
        if rapor is not None:
            db.delete(rapor)
    db.execute(update(Customer).where(Customer.id == g.customer_id, Customer.report_count > 0).values(report_count=Customer.report_count - 1))
    db.flush()
    return gonderim_ozeti(g)


def gonderimler(db: Session, user: Principal, musteri_id: int | None = None, yil: int | None = None, ay: int | None = None, sinir: int = 500) -> list[dict]:
    """Gorebildigi musterilerin gonderim gecmisi (yeniden eskiye)."""
    sorgu = select(ReportDispatch, Customer).join(Customer, Customer.id == ReportDispatch.customer_id)
    if musteri_id is not None:
        musteri_getir(db, user, musteri_id)
        sorgu = sorgu.where(ReportDispatch.customer_id == musteri_id)
    if yil is not None:
        sorgu = sorgu.where(ReportDispatch.year == yil)
    if ay is not None:
        sorgu = sorgu.where(ReportDispatch.month == ay)
    sonuc = db.execute(sorgu.order_by(ReportDispatch.at.desc(), ReportDispatch.id.desc()).limit(min(sinir, 2000))).all()
    if not yonetici_mi(user) and musteri_id is None:
        from app.musteri.servis import gorunur_mu

        sonuc = [satir for satir in sonuc if gorunur_mu(db, user, satir[1])]
    return [gonderim_ozeti(g, {c.id: c.name}) for g, c in sonuc]


def durum_ozeti(db: Session, user: Principal, ay: int, yil: int) -> dict:
    """TAM basina rapor birimi sayisi ve bu ayin atilan/bekleyen rapor sayisi (uretim _build_rapor_durumu).
    Catisina dahil bir istirak icin hazirlanan rapor CATININ raporu sayilir."""
    from app.musteri.servis import gorunur_mu

    musteriler = [c for c in db.scalars(select(Customer)) if gorunur_mu(db, user, c)]
    tum = {c.id: c for c in db.scalars(select(Customer))}
    atilanlar: set[int] = set()
    for kimlik in db.scalars(select(Report.customer_id).where(Report.report_month == ay, Report.report_year == yil).distinct()):
        c = tum.get(kimlik)
        if c is not None:
            atilanlar.add(c.id if rapor_birimi_mi(c) else (c.parent_id or c.id))
    sahipler = {u.id: (u.display_name or u.username) for u in db.scalars(select(AppUser))}
    satirlar: dict[int | None, dict] = {}
    for c in musteriler:
        if not rapor_birimi_mi(c):
            continue
        satir = satirlar.setdefault(c.owner_id, {"id": c.owner_id, "ad": sahipler.get(c.owner_id, "-") if c.owner_id else "-", "musteri": 0, "atilan": 0, "bekleyen": 0})
        satir["musteri"] += 1
        satir["atilan" if c.id in atilanlar else "bekleyen"] += 1
    sirali = sorted(satirlar.values(), key=lambda s: tr_kucuk(s["ad"]))
    return {"yil": yil, "ay": ay, "satirlar": sirali, "toplam": {k: sum(s[k] for s in sirali) for k in ("musteri", "atilan", "bekleyen")}}
