"""Aylik rapor: taslak, alicilar, ayda tek ONAYLI gonderim, gonderim gecmisi ve geri alma.

Uretim karsiliklari: kutucuklar/rapor/aylik.py (taslak, gonderim, geri alma), rapor/servis.py (rapor birimi,
durum ozeti), blueprints/customer_bp.py (rapor_alicilari, aylik_rapor_taslak, send_customer_report_email,
aylik_rapor_geri_al). Iletiyi gonderen her zaman personeldir.
Gonderim, Outlook taslagini (.eml, rapor/eposta.py) da uretir; panel iletiyi gondermez, Gonder'e personel basar.
RAPOR_GONDERIM_KIPI=smtp ise (varsayilan kapali) ileti TAMLIFE@ kutusundan sunucudan gider (rapor/smtp_gonderim.py);
teslim edilemezse gonderim kaydi olusmaz.
Gonderim kaydi, kilit ve PDF arsivi vardir. Ay UTC'ye gore belirlenir.
Donem: bir ayda gonderilen rapor ONCEKI ayin raporudur (Ekim'de Eylul); ayda tek rapor kurali o doneme uygulanir.
Takip: gonderimde formdaki tum alanlar o donemin taslagina yazilir (rapor sonradan da okunur). Yeni donemde taslak yoksa
onceki donemin GONDERILMIS raporundaki 'Devam Eden Calismalar', 'Kritik Konular' ve imza tasinir; cozulmeyen konu personelce
guncellenir (kullanici karari 2026-10-11).
Ekler: panelin urettigi rapor PDF'i, o doneme yuklenen SLA Excel'i ve personelin ekledigi dosyalar (rapor/sla.py) iletiye
otomatik eklenir. SLA'nin tum verisinin analizi rapor/sla_analiz.py, personel metninin cevirisi rapor/ceviri.py.
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

from app import imza as imza_modulu
from app.authz import yonetici_mi
from app.dil import m, secili
from app.kullanicilar import kullanici_kaydi, personel
from app.models import AppUser, Customer, Report, ReportDispatch, ReportDraft, ReportRecipient
from app.musteri.servis import MusteriHata, musteri_getir, musteri_yaz_getir, rapor_birimi_mi
from app.onedesk import yz
from app.ortak import ay_adi, rapor_donemi, tr_kucuk
from app.rapor import ceviri, eposta, sla, sla_analiz, smtp_gonderim
from app.rapor import metin as rapor_metin
from app.session import Principal

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
    """Bu ay hazirlanan raporun donemi: onceki ay."""
    return rapor_donemi(simdi())


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
        raise RaporHata(400, m("Alıcı listesi geçersiz.", "Recipient list is invalid."))
    alicilar = [str(a).strip() for a in ham if str(a).strip()]
    if len(alicilar) > EN_FAZLA_ALICI:
        raise RaporHata(400, m(f"En fazla {EN_FAZLA_ALICI} alıcı girilebilir.", f"At most {EN_FAZLA_ALICI} recipients can be entered."))
    izinli = {a.strip().lower() for a in os.environ.get("RAPOR_MAIL_IZINLI_ALANLAR", "").split(",") if a.strip()}
    for adres in alicilar:
        eslesme = _EPOSTA.fullmatch(adres)  # fullmatch: sondaki satir sonu baslik enjeksiyonuna yol acmasin
        if not eslesme:
            raise RaporHata(400, m("Geçersiz e-posta adresi: ", "Invalid e-mail address: ") + adres[:80])
        if izinli and eslesme.group(1).lower() not in izinli:
            raise RaporHata(400, m("Bu alana rapor gönderimi izinli değil: ", "Sending reports to this domain is not allowed: ") + eslesme.group(1)[:80])
    return alicilar


def alicilar_getir(db: Session, musteri_id: int) -> dict:
    kayit = db.get(ReportRecipient, musteri_id)
    return {"kime": kayit.to_addrs if kayit else "", "bilgi": kayit.cc_addrs if kayit else ""}


def alicilar_kaydet(db: Session, user: Principal, musteri_id: int, govde: dict) -> dict:
    musteri = musteri_yaz_getir(db, user, musteri_id)
    try:
        kime = alicilari_ayikla(govde.get("kime"))
        bilgi = alicilari_ayikla(govde.get("bilgi"))
    except RaporHata as exc:
        raise RaporHata(exc.kod, m("Kime/Bilgi: ", "To/Cc: ") + exc.mesaj) from exc
    kayit = db.get(ReportRecipient, musteri.id) or ReportRecipient(customer_id=musteri.id)
    kayit.to_addrs, kayit.cc_addrs = "; ".join(kime), "; ".join(bilgi)
    db.add(kayit)
    db.flush()
    return {"kime": kayit.to_addrs, "bilgi": kayit.cc_addrs}


# --- rapor birimi ----------------------------------------------------------------------------------
def ayri_rapor_ayarla(db: Session, user: Principal, musteri_id: int, deger: object) -> dict:
    musteri = musteri_yaz_getir(db, user, musteri_id)
    if musteri.parent_id is None:
        raise RaporHata(400, m("Bu seçim yalnız iştirakler içindir.", "This option is only for subsidiaries."))
    if not isinstance(deger, bool):
        raise RaporHata(400, m("Seçim evet ya da hayır olmalı.", "The choice must be yes or no."))
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


def personel_adi(db: Session, user: Principal) -> str:
    """Imzadaki ad: profildeki gorunen ad (AD'den), yoksa kullanici adi. 2026-10-26 duzeltme: hazir imza kullanici adiyla
    ('tcgsav') yaziliyordu."""
    kayit = db.scalar(select(AppUser).where(AppUser.username == user.username))
    return ((kayit.display_name if kayit else "") or user.username).strip()


def hazir_metinler(musteri_adi: str, ay: int, yil: int, personel: str, dil: str) -> dict[str, str]:
    return {
        "konu": rapor_metin.mail_konusu(musteri_adi, ay, yil, dil),
        "govde": rapor_metin.mail_govdesi(ay, yil, dil),
        "imza": rapor_metin.imza(personel, dil),
        **rapor_metin.VARSAYILAN_METINLER[dil],
        **rapor_metin.BASLANGIC_METINLERI[dil],
    }


DEVREDEN_ALANLAR = ("devam", "kritik", "imza")


def _onceki_donem(yil: int, ay: int) -> tuple[int, int]:
    return (yil, ay - 1) if ay > 1 else (yil - 1, 12)


def _devreden(db: Session, user: Principal, musteri: Customer, yil: int, ay: int) -> tuple[dict, str | None]:
    """Onceki donem GONDERILMISSE o raporun takip alanlari (hazir metinden farkli olanlar) ve donem kodu."""
    oyil, oay = _onceki_donem(yil, ay)
    satir = db.get(ReportDraft, (musteri.id, oyil, oay))
    if satir is None or not isinstance(satir.fields, dict) or aktif_gonderim(db, musteri.id, oyil, oay) is None:
        return {}, None
    hazir = [hazir_metinler(musteri.name, oay, oyil, ad, d) for ad in {user.username, personel_adi(db, user)} for d in rapor_metin.DILLER]
    alanlar = {
        ad: str(satir.fields[ad])
        for ad in DEVREDEN_ALANLAR
        if str(satir.fields.get(ad) or "").strip() and all(satir.fields[ad] != h.get(ad) for h in hazir)
    }
    if alanlar and satir.fields.get("dil") in rapor_metin.DILLER:
        alanlar["dil"] = str(satir.fields["dil"])
    return alanlar, f"{oyil}-{oay:02d}" if alanlar else None


def _taslak_yaz(db: Session, user: Principal, musteri_id: int, yil: int, ay: int, temiz: dict) -> datetime:
    satir = db.get(ReportDraft, (musteri_id, yil, ay))
    zaman = simdi()
    if satir is None:
        db.add(ReportDraft(customer_id=musteri_id, year=yil, month=ay, fields=temiz, updated_by=user.username[:120], updated_at=zaman))
    else:
        satir.fields, satir.updated_by, satir.updated_at = temiz, user.username[:120], zaman
    db.flush()
    return zaman


def taslak_getir(db: Session, user: Principal, musteri_id: int) -> dict:
    """Donemin taslagi: kayitli alanlar uzerine hazir baslangic metinleri.

    Hazir metinler IKI dilde de doner (`varsayilanlar`): rapor dili degisince ekran, personelin degistirmedigi her alani
    o dilin karsiligiyla degistirir. Kayitli taslak yoksa rapor dili panelin dilidir."""
    musteri = musteri_getir(db, user, musteri_id)
    yil, ay = donem()
    satir = db.get(ReportDraft, (musteri.id, yil, ay))
    kayitli = satir.fields if satir and isinstance(satir.fields, dict) else {}
    devreden, devreden_donem = ({}, None) if satir is not None else _devreden(db, user, musteri, yil, ay)
    kayitli = kayitli or devreden
    dil: str = str(kayitli.get("dil")) if kayitli.get("dil") in rapor_metin.DILLER else ("en" if secili() == "en" else "tr")
    varsayilanlar = {d: hazir_metinler(musteri.name, ay, yil, personel_adi(db, user), d) for d in rapor_metin.DILLER}
    gonderim = aktif_gonderim(db, musteri.id, yil, ay)
    return {
        "yil": yil,
        "ay": ay,
        "birim": rapor_birimi_mi(musteri),
        "alanlar": {**varsayilanlar[dil], **kayitli, "dil": dil},
        "varsayilanlar": varsayilanlar,
        "sla": sla.ozet(sla.oku(musteri.id, yil, ay)),
        "kayitli": satir is not None,
        "devreden": {"donem": devreden_donem, "alanlar": [a for a in DEVREDEN_ALANLAR if a in devreden]} if devreden_donem else None,
        "guncelleyen": satir.updated_by if satir else None,
        "zaman": satir.updated_at.isoformat() if satir and satir.updated_at else None,
        "alicilar": alicilar_getir(db, musteri.id),
        "gonderim": gonderim_ozeti(gonderim) if gonderim else None,
        "gonderim_kipi": smtp_gonderim.kip(),
        # profil imzasi varsa ileti onu tasir; formdaki imza alani yalniz yedektir (arayuz bilgi gosterir)
        "profil_imza": bool(db.scalar(select(AppUser.signature_html).where(AppUser.username == user.username))),
    }


def taslak_kaydet(db: Session, user: Principal, musteri_id: int, alanlar: object) -> dict:
    musteri = musteri_yaz_getir(db, user, musteri_id)
    yil, ay = donem()
    onceki = aktif_gonderim(db, musteri.id, yil, ay)
    if onceki:
        raise RaporHata(409, m("Bu dönemin raporu gönderildi; taslak değiştirilemez.", "The report for this period was sent; the draft cannot be changed."), {"kilitli": True})
    if not isinstance(alanlar, dict):
        raise RaporHata(400, m("Kaydedilecek alan yok.", "There is nothing to save."))
    if alanlar.get("dil") not in (None, "") and alanlar.get("dil") not in rapor_metin.DILLER:
        raise RaporHata(400, m("Rapor dili tr ya da en olmalı.", "Report language must be tr or en."))
    zaman = _taslak_yaz(db, user, musteri.id, yil, ay, taslak_temizle(alanlar))
    return {"zaman": zaman.isoformat()}


# --- gonderim ------------------------------------------------------------------------------------
def _pdf_coz(ham: object) -> bytes | None:
    if not ham:
        return None
    metin = str(ham)
    try:
        veri = base64.b64decode(metin.split(",", 1)[1] if "," in metin else metin, validate=True)
    except (ValueError, IndexError) as exc:
        raise RaporHata(400, m("PDF verisi okunamadı.", "PDF data could not be read.")) from exc
    if not veri.startswith(b"%PDF"):
        raise RaporHata(400, m("PDF belgesi geçersiz (PDF imzası yok).", "Invalid PDF document (no PDF signature)."))
    if len(veri) > AZAMI_PDF:
        raise RaporHata(400, m("PDF çok büyük (en fazla 30 MB).", "PDF too large (max 30 MB)."))
    return veri


def _pdf_yaz(musteri_id: int, yil: int, ay: int, veri: bytes) -> tuple[str, int, str]:
    klasor = rapor_klasoru() / str(yil) / f"{ay:02d}"
    klasor.mkdir(parents=True, exist_ok=True)
    ad = f"musteri{musteri_id}_{simdi():%Y%m%d%H%M%S%f}.pdf"
    (klasor / ad).write_bytes(veri)
    return f"{yil}/{ay:02d}/{ad}", len(veri), hashlib.sha256(veri).hexdigest()


def gonder(db: Session, user: Principal, musteri_id: int, govde: dict) -> dict:
    """ONAYLI aylik rapor gonderimi: ayda TEK rapor. Onay zorunlu, bu ay gonderilmisse 409."""
    musteri = musteri_yaz_getir(db, user, musteri_id)
    if govde.get("onay") is not True:
        raise RaporHata(400, m("Rapor gönderimi için onay gerekli.", "Confirmation is required to send the report."))
    yil, ay = donem()
    onceki = aktif_gonderim(db, musteri.id, yil, ay)
    if onceki:
        raise RaporHata(
            409,
            m(
                f"Bu dönemin raporu {onceki.sender or '-'} tarafından gönderildi. Ayda yalnız bir rapor gönderilebilir.",
                f"The report for this period was sent by {onceki.sender or '-'}. Only one report can be sent per month.",
            ),
            {"kilitli": True, "gonderim": gonderim_ozeti(onceki)},
        )
    kayitli_alicilar = alicilar_getir(db, musteri.id) if "to" not in govde or "cc" not in govde else {}
    try:
        kime = alicilari_ayikla(govde.get("to") if "to" in govde else kayitli_alicilar["kime"])
        bilgi = alicilari_ayikla(govde.get("cc") if "cc" in govde else kayitli_alicilar["bilgi"])
    except RaporHata as exc:
        raise RaporHata(exc.kod, m("Alıcılar: ", "Recipients: ") + exc.mesaj) from exc
    dil = govde.get("lang") if govde.get("lang") in rapor_metin.DILLER else "tr"
    konu = " ".join(str(govde.get("subject") or rapor_metin.mail_konusu(musteri.name, ay, yil, dil)).split())[:200]
    pdf = _pdf_coz(govde.get("pdf_base64"))
    sla_ek = sla.excel_dosyasi(musteri.id, yil, ay)
    smtp = smtp_gonderim.kip() == "smtp"
    if smtp and not kime:
        raise RaporHata(400, m("Alıcılar: en az bir 'Kime' adresi gerekli.", "Recipients: at least one 'To' address is required."))
    ileti, ileti_adi, ek_adlari = _ileti(
        db, user, musteri, yil, ay, govde, konu, kime, bilgi, pdf, sla_ek, sla.ek_dosyalari(musteri.id, yil, ay), taslak=not smtp
    )
    teslim: dict = {}
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
            # Gonderilen raporun metinleri saklanir: sayfa sonradan da ayni raporu gosterir, sonraki ay takip alanlari tasinir.
            if isinstance(govde.get("alanlar"), dict):
                _taslak_yaz(db, user, musteri.id, yil, ay, taslak_temizle({**govde["alanlar"], "dil": dil}))
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
            # SMTP: kayit (ve ayda-tek kilidi) flush'ta dogrulandiktan SONRA teslim; hata islemi geri alir, kayit kalmaz.
            if smtp:
                try:
                    teslim = smtp_gonderim.gonder(ileti, kime + bilgi)
                except smtp_gonderim.EpostaHata:
                    if dosya is not None:
                        (rapor_klasoru() / dosya[0]).unlink(missing_ok=True)  # kayit geri alinir, arsiv PDF'i yetim kalmasin
                    raise
    except IntegrityError as exc:  # esZamanli ikinci gonderim kismi benzersiz indekse takilir
        raise RaporHata(409, m("Bu dönemin raporu az önce gönderildi. Ayda yalnız bir rapor gönderilebilir.", "The report for this period was just sent. Only one report can be sent per month."), {"kilitli": True}) from exc
    gonderim = aktif_gonderim(db, musteri.id, yil, ay)
    assert gonderim is not None
    sonuc = {"gonderim": gonderim_ozeti(gonderim), "kime": kime, "bilgi": bilgi, "ekler": ek_adlari, "kip": "smtp" if smtp else "eml"}
    if smtp:
        return {**sonuc, "reddedilen": teslim.get("reddedilen", [])}
    return {**sonuc, "eml_adi": ileti_adi, "eml_base64": base64.b64encode(ileti).decode("ascii")}


GONDERIM_ARIZASI = "TL-RAP-01"


def gonderim_hatasi_bildir(user: Principal, musteri_id: int, neden: str, exc: BaseException | None = None) -> str:
    """Admin bildirimi (2026-10-26 kullanici: "aylik rapor gonderiminde hata olunca admine bildirim"): fault_event TL-RAP-01; admin
    panelin ust cubugunda acik kayit sayisini gorur (GET /yonetim/bildirimler). Musteri adi ayri oturumla okunur (istek oturumu
    hatali olabilir). Kayit numarasini doner; ASLA istisna firlatmaz."""
    from app import ariza
    from app.db import oturum

    ad = ""
    try:
        with oturum() as db:
            ad = db.scalar(select(Customer.name).where(Customer.id == musteri_id)) or ""
    except Exception:  # noqa: BLE001, S110 - ad bildirimi engellemesin
        pass
    return ariza.kaydet(GONDERIM_ARIZASI, f"müşteri #{musteri_id} {ad}: {neden}".strip(), exc=exc, kaynak="rapor.gonder", kullanici=user.username, arka_plan=True)


def _ileti(
    db: Session,
    user: Principal,
    musteri: Customer,
    yil: int,
    ay: int,
    govde: dict,
    konu: str,
    kime: list[str],
    bilgi: list[str],
    pdf: bytes | None,
    sla_ek: tuple[bytes, str] | None = None,
    ek_dosyalar: list[tuple[bytes, str, str]] | None = None,
    taslak: bool = True,
) -> tuple[bytes, str, list[str]]:
    """Outlook taslagi (taslak=False: SMTP ile gidecek ileti, Reply-To personel). Metin istekten; yoksa bu ayin kayitli
    taslagindan; o da yoksa hazir metin (taslak_getir ile ayni).

    Rapor dili yalniz SABIT metinleri etkiler; personelin yazdigi govde oldugu gibi gider (uretim kurali)."""
    satir = db.get(ReportDraft, (musteri.id, yil, ay))
    kayitli = satir.fields if satir and isinstance(satir.fields, dict) else {}
    dil = govde.get("lang") or kayitli.get("dil")
    dil = dil if dil in rapor_metin.DILLER else "tr"
    metin = str(govde.get("body_text") or kayitli.get("govde") or rapor_metin.mail_govdesi(ay, yil, dil))[: rapor_metin.TASLAK_ALANLARI["govde"]]
    imza = govde["signature"] if govde.get("signature") is not None else kayitli.get("imza", rapor_metin.imza(personel_adi(db, user), dil))
    imza = str(imza or "")[: rapor_metin.TASLAK_ALANLARI["imza"]]
    kok = eposta.dosya_adi(musteri.name)
    ekler: list[tuple[bytes, str, str]] = []
    if pdf:
        ekler.append((pdf, f"{kok}.pdf", "application/pdf"))
    if sla_ek:
        ekler.append((sla_ek[0], sla_ek[1], eposta.XLSX))
    ekler.extend(ek_dosyalar or [])
    # Profil imzasi (2026-10-26) varsa iletinin imzasi odur: formdaki duz metin imza yerine (gorseller cid parcasi, Teknocan tek parca).
    profil_imzasi = db.scalar(select(AppUser.signature_html).where(AppUser.username == user.username)) or ""
    imza_html, satir_ici = imza_modulu.gomulu_gorselleri_ayir(profil_imzasi, {v: k for k, v in eposta.gorseller().items()}) if profil_imzasi else ("", [])
    if profil_imzasi:
        imza = imza_modulu.duz_metin(profil_imzasi)
    html_govde = eposta.mail_html(musteri_adi=musteri.name, donem=f"{ay_adi(ay, dil)} {yil}", govde=metin, imza=imza, dil=dil, imza_html=imza_html)
    try:
        veri = eposta.eml(
            konu=konu,
            govde_html=html_govde,
            govde_metin=eposta.duz_metin(metin, imza),
            kime=kime,
            bilgi=bilgi,
            gonderen_adres=eposta.gonderen(user.username),
            ekler=ekler,
            taslak=taslak,
            satir_ici=satir_ici,
            # 2026-10-26: Reply-To yazilmaz. kisi_adresi() oturum adindan UPN uretir (<ad>@AD_DOMAIN = turkcell.entp.tgc), bu bir
            # posta kutusu degil; musteri yaniti geri donerdi. Yanit From'a (TAMLIFE@) gider (docs/eposta-gonderimi.md alternatifi).
            yanit=None,
        )
    except ValueError as exc:  # baslikta CR/LF vb.
        raise RaporHata(400, m("İleti başlığında geçersiz karakter.", "Invalid character in the message header.")) from exc
    return veri, f"{kok}.eml", [ad for _, ad, _ in ekler]


# --- SLA Excel ve rapor grafikleri ----------------------------------------------------------------------
def _sla_kilidi(db: Session, musteri_id: int, yil: int, ay: int) -> None:
    if aktif_gonderim(db, musteri_id, yil, ay):
        raise RaporHata(409, m("Bu dönemin raporu gönderildi; ekler değiştirilemez.", "The report for this period was sent; attachments cannot be changed."), {"kilitli": True})


def sla_getir(db: Session, user: Principal, musteri_id: int) -> dict:
    """Donemin SLA analizi (grafikler) ve elle eklenen gorseller. Grafik sayisinda sinir yoktur."""
    musteri = musteri_getir(db, user, musteri_id)
    yil, ay = donem()
    kayit = sla.oku(musteri.id, yil, ay)
    return {
        "yil": yil,
        "ay": ay,
        "ozet": sla.ozet(kayit),
        "analiz": (kayit or {}).get("analiz"),
        "ekler": [{"no": e.get("no"), "baslik": e.get("baslik", ""), "gorsel": e.get("gorsel")} for e in (kayit or {}).get("ekler") or []],
        "dosyalar": [{"no": d.get("no"), "ad": d.get("ad", ""), "boyut": d.get("boyut", 0)} for d in (kayit or {}).get("dosyalar") or []],
        "araclar": {"ceviri": ceviri.durum(), "yz": bool(yz.durum()["hazir"])},
    }


def sla_yukle(db: Session, user: Principal, musteri_id: int, veri: bytes, dosya_adi: str) -> dict:
    musteri = musteri_yaz_getir(db, user, musteri_id)
    yil, ay = donem()
    _sla_kilidi(db, musteri.id, yil, ay)
    if not veri:
        raise RaporHata(400, m("Excel dosyası seçilmedi.", "No Excel file was selected."))
    # Dosya yalniz bu rapor biriminin olabilir: kartin ve (ayri raporu olmayan) istiraklerinin unvanlari (2026-10-26).
    istirakler = db.scalars(select(Customer.name).where(Customer.parent_id == musteri.id, Customer.separate_report.is_not(True))).all()
    sla.excel_yukle(musteri.id, yil, ay, veri, dosya_adi, user.username, unvanlar=[musteri.name or "", *istirakler])
    return sla_getir(db, user, musteri.id)


def sla_sil(db: Session, user: Principal, musteri_id: int) -> dict:
    musteri = musteri_yaz_getir(db, user, musteri_id)
    yil, ay = donem()
    _sla_kilidi(db, musteri.id, yil, ay)
    sla.excel_sil(musteri.id, yil, ay)
    return sla_getir(db, user, musteri.id)


def gorsel_ekle(db: Session, user: Principal, musteri_id: int, veri: bytes, baslik: str) -> dict:
    musteri = musteri_yaz_getir(db, user, musteri_id)
    yil, ay = donem()
    _sla_kilidi(db, musteri.id, yil, ay)
    sla.gorsel_ekle(musteri.id, yil, ay, veri, baslik, user.username)
    return sla_getir(db, user, musteri.id)


def gorsel_sil(db: Session, user: Principal, musteri_id: int, numara: int) -> dict:
    musteri = musteri_yaz_getir(db, user, musteri_id)
    yil, ay = donem()
    _sla_kilidi(db, musteri.id, yil, ay)
    sla.gorsel_sil(musteri.id, yil, ay, numara)
    return sla_getir(db, user, musteri.id)


def dosya_ekle(db: Session, user: Principal, musteri_id: int, veri: bytes, dosya_adi: str) -> dict:
    musteri = musteri_yaz_getir(db, user, musteri_id)
    yil, ay = donem()
    _sla_kilidi(db, musteri.id, yil, ay)
    sla.dosya_ekle(musteri.id, yil, ay, veri, dosya_adi, user.username)
    return sla_getir(db, user, musteri.id)


def dosya_sil(db: Session, user: Principal, musteri_id: int, numara: int) -> dict:
    musteri = musteri_yaz_getir(db, user, musteri_id)
    yil, ay = donem()
    _sla_kilidi(db, musteri.id, yil, ay)
    sla.dosya_sil(musteri.id, yil, ay, numara)
    return sla_getir(db, user, musteri.id)


def sla_analizi(db: Session, user: Principal, musteri_id: int, govde: dict) -> dict:
    """SLA Excel'inin tum verisinin analizi: yerlesik ozet (her zaman) + istenirse YZ yorumu. Rapor diline gore metin."""
    musteri = musteri_yaz_getir(db, user, musteri_id)
    yil, ay = donem()
    dosya = sla.excel_dosyasi(musteri.id, yil, ay)
    if dosya is None:
        raise RaporHata(404, m("Önce bu dönemin SLA Excel'ini yükleyin.", "Upload this period's SLA Excel first."))
    dil = "en" if govde.get("dil") == "en" else "tr"
    grafikler = ((sla.oku(musteri.id, yil, ay) or {}).get("analiz") or {}).get("grafikler")
    sonuc = sla_analiz.analiz(sla_analiz.dosyayi_oku(dosya[0]), f"{yil}-{ay:02d}", dil, grafikler)
    yz_durumu = yz.durum()
    yorum, neden = None, ""
    if govde.get("yz") is True:
        if yz_durumu["hazir"]:
            yorum = sla_analiz.yz_yorumu(sonuc, dil)
        else:
            neden = m("YZ kapalı: ", "AI is disabled: ") + ", ".join(str(e) for e in yz_durumu["eksik"])
    return {
        "analiz": sonuc,
        "ozet": sla_analiz.ozet_metni(sonuc, f"{ay_adi(ay, dil)} {yil}", dil),
        "yz": {"hazir": bool(yz_durumu["hazir"]), "yorum": yorum, "neden": neden},
    }


def metin_cevir(db: Session, user: Principal, musteri_id: int, govde: dict) -> dict:
    """Personelin yazdigi rapor alanlarini Ingilizceye cevirir (makine cevirisi; gondermeden once gozden gecirilir)."""
    musteri_yaz_getir(db, user, musteri_id)
    alanlar = govde.get("alanlar")
    if not isinstance(alanlar, dict):
        raise RaporHata(400, m("Çevrilecek alan yok.", "No fields to translate."))
    izinli = {ad: str(deger or "") for ad, deger in alanlar.items() if ad in rapor_metin.TASLAK_ALANLARI and ad != "dil"}
    return ceviri.sozlugu_cevir(izinli)


def geri_al(db: Session, user: Principal, gonderim_id: int) -> dict:
    """Yalniz admin: yanlis gonderilen ayin kilidini acar. Rapor kaydi silinir, sayac azalir; gonderim 'reverted' kalir."""
    if not (user.is_admin or user.role == "admin"):
        raise RaporHata(403, m("Yetki yok.", "Not authorized."))
    g = db.get(ReportDispatch, gonderim_id)
    if g is None or g.status != "sent":
        raise RaporHata(404, m("Geri alınacak gönderim bulunamadı.", "No dispatch to revert was found."))
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
    return [gonderim_ozeti(g, {c.id: c.name}) for g, c in sonuc]


def durum_ozeti(db: Session, user: Principal, ay: int, yil: int) -> dict:
    """TAM basina rapor birimi sayisi ve bu ayin atilan/bekleyen rapor sayisi (uretim _build_rapor_durumu).
    Catisina dahil bir istirak icin hazirlanan rapor CATININ raporu sayilir. Satirlar tek personel kumesidir (app.kullanicilar.personel):
    yonetici icin raporu olmayan personel de 0 satiridir; sahibi yonetici/admin ya da bos olan birimler tek '-' satirinda toplanir."""
    tum = {c.id: c for c in db.scalars(select(Customer))}  # 2026-10-20: herkes tum musterileri gorur
    musteriler = list(tum.values())
    atilanlar: set[int] = set()
    for kimlik in db.scalars(select(Report.customer_id).where(Report.report_month == ay, Report.report_year == yil).distinct()):
        c = tum.get(kimlik)
        if c is not None:
            atilanlar.add(c.id if rapor_birimi_mi(c) else (c.parent_id or c.id))
    kisiler = {u.id: (u.display_name or u.username) for u in personel(db)}
    satirlar: dict[int | None, dict] = {}
    if yonetici_mi(user):
        for kimlik, ad in kisiler.items():
            satirlar[kimlik] = {"id": kimlik, "ad": ad, "musteri": 0, "atilan": 0, "bekleyen": 0}
    for c in musteriler:
        if not rapor_birimi_mi(c):
            continue
        sahip = c.owner_id if c.owner_id in kisiler else None
        satir = satirlar.setdefault(sahip, {"id": sahip, "ad": kisiler[sahip] if sahip else "-", "musteri": 0, "atilan": 0, "bekleyen": 0})
        satir["musteri"] += 1
        satir["atilan" if c.id in atilanlar else "bekleyen"] += 1
    sirali = sorted(satirlar.values(), key=lambda s: (s["id"] is None, tr_kucuk(s["ad"])))  # "-" satiri hep sonda
    return {"yil": yil, "ay": ay, "satirlar": sirali, "toplam": {k: sum(s[k] for s in sirali) for k in ("musteri", "atilan", "bekleyen")}}
