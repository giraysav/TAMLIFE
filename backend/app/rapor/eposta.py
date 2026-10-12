"""Aylik rapor iletisi: HTML govde ve Outlook taslagi (.eml).

Uretim karsiliklari: blueprints/customer_bp.py (_rapor_mail_html, _rapor_eml_olustur, _gorunen_adli, _mail_gorselleri)
ve templates/mail/rapor_mail.html. Panel iletiyi GONDERMEZ: .eml kullanicinin bilgisayarina iner, X-Unsent sayesinde
Outlook onu gonderilmemis yeni ileti olarak acar; Gonder'e personel basar.

Tasarim burada degil: rapor/sablon/rapor_mail.html (+ rapor_mail_imza.html). Personel metni burada kacislanir,
sablona yalniz kacislanmis HTML gider (jinja2 yok; yeni bagimlilik eklenmedi).
"""

from __future__ import annotations

import html
import os
import re
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import cache
from pathlib import Path
from string import Template

from app.config import get_settings

SABLON = Path(__file__).resolve().parent / "sablon"
MAIL_YAZI = "font-family:'Segoe UI',Calibri,Arial,sans-serif;"
VARSAYILAN_GONDEREN = "tam.rapor@turkcell.com.tr"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Govdeye GOMULU gorseller: cid -> dosya. Outlook disaridan resim cekmeyi engeller. Kimlikler ALAN ADLI: Outlook'un
# .eml -> ileti donusturucusu duz 'cid:teknocan' basvurusunu cozemiyordu (uretim kullanici bildirimi 2026-09-20).
MAIL_GOVDE_CID = "govde@tamlife"
# Teknocan hem baslik bandinda hem imza bandinda (ayni cid, tek parca). Kullanilmayan gomulu gorsel Outlook'ta ek gibi
# gorundugu icin yalniz sablonda gecenler eklenir.
MAIL_GORSELLERI = {"teknocan@tamlife": "teknocan.png"}
SABIT_METINLER = {
    "tr": {"baslik": "TAM Aylık Rapor", "altbilgi": "Bu rapor TAM Life panelinden hazırlanmıştır."},
    "en": {"baslik": "TAM Monthly Report", "altbilgi": "This report was prepared with the TAM Life panel."},
}
_YORUM = re.compile(r"<!--.*?-->\s*", re.DOTALL)


@cache
def _sablon(ad: str) -> Template:
    """Tasarim dosyasi; bastaki aciklama yorumu iletiye girmez (yer tutucu adlari da icinde)."""
    return Template(_YORUM.sub("", (SABLON / ad).read_text(encoding="utf-8")))


def satirlar(metin: str) -> list[str]:
    return (metin or "").replace("\r\n", "\n").split("\n")


def paragraflar(metin: str) -> list[list[str]]:
    """Bos satirla ayrilmis paragraflar; her paragraf satir listesi."""
    return [satirlar(p) for p in (metin or "").replace("\r\n", "\n").split("\n\n") if p.strip()]


def mail_html(*, musteri_adi: str, donem: str, govde: str, imza: str, dil: str = "tr") -> str:
    """Aylik rapor iletisinin HTML govdesi. Personel metni kacislanir; HTML olarak yorumlanmaz."""
    dil = "en" if dil == "en" else "tr"
    k = html.escape
    govde_html = "".join('<p style="margin:0 0 14px 0;">' + "<br>".join(k(s) for s in p) + "</p>" for p in paragraflar(govde))
    imza_satirlari = [s for s in satirlar(imza) if s.strip()]
    imza_html = ""
    if imza_satirlari:
        imza_html = _sablon("rapor_mail_imza.html").substitute(
            yazi=MAIL_YAZI, ad=k(imza_satirlari[0]), satirlar="".join("<br>" + k(s) for s in imza_satirlari[1:])
        )
    return _sablon("rapor_mail.html").substitute(
        yazi=MAIL_YAZI,
        musteri_adi=k(musteri_adi or ""),
        donem=k(donem or ""),
        paragraflar=govde_html,
        imza=imza_html,
        **{ad: k(deger) for ad, deger in SABIT_METINLER[dil].items()},
    )


def duz_metin(govde: str, imza: str) -> str:
    """HTML okumayan istemci icin: imza govdenin sonunda kalir."""
    return f"{govde.rstrip()}\n\n{imza.strip()}" if imza.strip() else govde


def gorunen_adli(adres: str) -> str:
    """Kurum alanindaki adresi "GIRAY SAV <giray.sav@...>" bicimine cevirir (Outlook adsiz adresi ham gosterir).

    Ad yalniz AD_DOMAIN alanindaki adreslerden uretilir (ad.soyad duzeni bilinir); musteri adresinde ad uydurulmaz."""
    alan = get_settings().ad_domain.strip().lower().lstrip("@")
    if not alan or "@" not in adres or adres.rsplit("@", 1)[1].lower() != alan:
        return adres
    ad = " ".join(p for p in re.split(r"[._\-]+", adres.rsplit("@", 1)[0]) if p).upper()
    return f"{ad} <{adres}>" if ad else adres


def gonderen(kullanici: str) -> str:
    """Uretimle ayni sira: SMTP_USER > kullanici adi (alan yoksa @AD_DOMAIN eklenir) > varsayilan kutu."""
    smtp = os.environ.get("SMTP_USER", "").strip()
    if smtp:
        return smtp
    kullanici = (kullanici or "").strip()
    alan = get_settings().ad_domain.strip().lstrip("@")
    if kullanici and "@" not in kullanici and alan:
        return f"{kullanici}@{alan}"
    return kullanici if "@" in kullanici else VARSAYILAN_GONDEREN


@cache
def gorseller() -> dict[str, bytes]:
    """{cid: png}. Dosya yoksa o gorsel atlanir: eksik logo yuzunden ileti hic uretilemesin istenmez."""
    return {cid: (SABLON / ad).read_bytes() for cid, ad in MAIL_GORSELLERI.items() if (SABLON / ad).is_file()}


def eml(
    *,
    konu: str,
    govde_html: str,
    govde_metin: str,
    kime: list[str],
    bilgi: list[str],
    gonderen_adres: str,
    ekler: list[tuple[bytes, str, str]] | None = None,
) -> bytes:
    """RFC 822 baytlari. Basliklar email paketiyle kurulur (CR/LF enjeksiyonu istisna atar); alicilar zaten dogrulanmistir.

    `ekler`: (bayt, dosya adi, MIME turu) - rapor PDF'i, SLA Excel'i ve personelin ekledigi dosyalar."""
    msg = MIMEMultipart("mixed")
    msg["X-Unsent"] = "1"
    msg["From"] = gonderen_adres
    if kime:
        msg["To"] = ", ".join(gorunen_adli(a) for a in kime)
    if bilgi:
        msg["Cc"] = ", ".join(gorunen_adli(a) for a in bilgi)
    msg["Subject"] = konu
    alternatif = MIMEMultipart("alternative")
    alternatif.attach(MIMEText(govde_metin, "plain", "utf-8"))
    # 'related' + type/start: kok parcanin HTML oldugunu acikca soyler; Outlook aksi halde gorselleri govdeye baglamiyor.
    ilgili = MIMEMultipart("related", type="text/html", start=f"<{MAIL_GOVDE_CID}>")
    govde_parca = MIMEText(govde_html, "html", "utf-8")
    govde_parca.add_header("Content-ID", f"<{MAIL_GOVDE_CID}>")
    ilgili.attach(govde_parca)
    for cid, png in gorseller().items():
        parca = MIMEImage(png, _subtype="png")
        parca.add_header("Content-ID", f"<{cid}>")
        parca.add_header("Content-Disposition", "inline", filename=f"{cid.split('@')[0]}.png")
        ilgili.attach(parca)
    alternatif.attach(ilgili)
    msg.attach(alternatif)
    for veri, ad, tur in ekler or []:
        if not veri:
            continue
        ana, _, alt = (tur if "/" in tur else "application/octet-stream").partition("/")
        ek = MIMEBase(ana, alt)
        ek.set_payload(veri)
        encoders.encode_base64(ek)
        ek.add_header("Content-Disposition", "attachment", filename=ad)
        msg.attach(ek)
    return msg.as_bytes()


def dosya_adi(musteri_adi: str) -> str:
    """'TAM_Aylik_Rapor_<unvan>' (uzantisiz); PDF eki ve .eml ayni kok adi tasir."""
    temiz = re.sub(r"[^\w\s-]", "", musteri_adi or "musteri").strip().replace(" ", "_") or "musteri"
    return f"TAM_Aylik_Rapor_{temiz[:80]}"
