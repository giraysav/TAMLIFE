"""Aylik raporun panelden SMTP ile gonderimi (2026-10-22: altyapi hazir, VARSAYILAN KAPALI).

RAPOR_GONDERIM_KIPI=eml (varsayilan): bugunku akis; .eml taslagi personele iner, Gonder'e Outlook'ta personel basar.
RAPOR_GONDERIM_KIPI=smtp: ileti sunucudan TEK kutudan gider (From = SMTP_USER, TAMLIFE@turkcell.com.tr); Reply-To raporu
hazirlayan personel, musteri yaniti TAM'a duser. Teslim edilemezse gonderim kaydi olusmaz (ay kilitlenmez).
Ayarlar backend/.env: SMTP_SERVER, SMTP_PORT (25), SMTP_USER, SMTP_STARTTLS (false), SMTP_TIMEOUT (20 sn), SMTP_AZAMI_MB (20),
SMTP_ARSIV (istege bagli gizli kopya kutusu). Kimlik dogrulama YOK (anonim ic relay; .env notu): parola anahtari eklenmez.
Isterler ve acik kararlar: docs/eposta-gonderimi.md.
"""

from __future__ import annotations

import os
import re
import smtplib
import socket
import ssl
from dataclasses import dataclass

from app.dil import m
from app.ortak import UygulamaHatasi

KIPLER = ("eml", "smtp")
ADRES = re.compile(r"[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+")


class EpostaHata(UygulamaHatasi):
    pass


def kip() -> str:
    deger = os.environ.get("RAPOR_GONDERIM_KIPI", "").strip().lower()
    return deger if deger in KIPLER else "eml"


def _tam_sayi(anahtar: str, varsayilan: int, alt: int, ust: int) -> int:
    try:
        return max(alt, min(int(os.environ.get(anahtar, "").strip() or varsayilan), ust))
    except ValueError:
        return varsayilan


@dataclass(frozen=True)
class Ayar:
    sunucu: str
    port: int
    gonderen: str
    starttls: bool
    zaman_asimi: int
    azami_bayt: int
    arsiv: str

    @classmethod
    def oku(cls) -> Ayar:
        return cls(
            sunucu=os.environ.get("SMTP_SERVER", "").strip(),
            port=_tam_sayi("SMTP_PORT", 25, 1, 65535),
            gonderen=os.environ.get("SMTP_USER", "").strip(),
            starttls=os.environ.get("SMTP_STARTTLS", "").strip().lower() == "true",
            zaman_asimi=_tam_sayi("SMTP_TIMEOUT", 20, 1, 120),
            azami_bayt=_tam_sayi("SMTP_AZAMI_MB", 20, 1, 150) * 1024 * 1024,
            arsiv=os.environ.get("SMTP_ARSIV", "").strip(),
        )

    def eksikler(self) -> list[str]:
        eksik = [ad for ad, deger in (("SMTP_SERVER", self.sunucu), ("SMTP_USER", self.gonderen)) if not deger]
        if self.gonderen and not ADRES.fullmatch(self.gonderen):
            eksik.append("SMTP_USER (geçerli adres değil)")
        if self.arsiv and not ADRES.fullmatch(self.arsiv):
            eksik.append("SMTP_ARSIV (geçerli adres değil)")
        return eksik


def durum() -> dict:
    """Yonetim karti: kip, hazir mi, eksik ayarlar. Adres ve sunucu adi yalniz admin ekranina gider."""
    a = Ayar.oku()
    eksik = a.eksikler()
    return {"kip": kip(), "hazir": not eksik, "eksik": eksik, "sunucu": a.sunucu, "port": a.port, "gonderen": a.gonderen,
            "starttls": a.starttls, "arsiv": bool(a.arsiv)}  # fmt: skip


def _baglan(a: Ayar) -> smtplib.SMTP:
    s = smtplib.SMTP(a.sunucu, a.port, timeout=a.zaman_asimi)
    s.ehlo()
    if a.starttls:
        s.starttls(context=ssl.create_default_context())  # sertifika dogrulanir
        s.ehlo()
    return s


def gonder(veri: bytes, alicilar: list[str]) -> dict:
    """Hazir RFC 822 iletiyi gonderir. Zarf gondereni SMTP_USER; SMTP_ARSIV varsa gizli kopya (basliga yazilmaz).

    Tum alicilar reddedilirse ya da sunucuya ulasilamazsa EpostaHata (cagiran islem geri alinir). Kismi ret donulur:
    ileti digerlerine gitmistir, geri alinamaz."""
    a = Ayar.oku()
    if eksik := a.eksikler():
        raise EpostaHata(503, m("E-posta gönderim ayarı eksik: ", "E-mail sending settings are missing: ") + ", ".join(eksik))
    if not alicilar:
        raise EpostaHata(400, m("En az bir alıcı gerekli.", "At least one recipient is required."))
    if len(veri) > a.azami_bayt:
        mb = a.azami_bayt // (1024 * 1024)
        raise EpostaHata(413, m(f"İleti {mb} MB sınırını aşıyor; ekleri azaltın.", f"The message exceeds the {mb} MB limit; reduce the attachments."))
    zarf = list(dict.fromkeys([*alicilar, *([a.arsiv] if a.arsiv else [])]))
    try:
        with _baglan(a) as s:
            reddedilen = s.sendmail(a.gonderen, zarf, veri)
    except smtplib.SMTPRecipientsRefused as exc:
        raise EpostaHata(400, m("E-posta sunucusu tüm alıcıları reddetti: ", "The mail server refused all recipients: ") + ", ".join(exc.recipients)) from None
    except smtplib.SMTPSenderRefused as exc:
        raise EpostaHata(502, m(f"Gönderici adresi reddedildi ({exc.smtp_code}); relay / Send-As izni gerekir.", f"Sender address refused ({exc.smtp_code}); relay / Send-As permission is required.")) from None
    except smtplib.SMTPResponseException as exc:
        raise EpostaHata(502, m(f"E-posta sunucusu iletiyi kabul etmedi ({exc.smtp_code}).", f"The mail server did not accept the message ({exc.smtp_code}).")) from None
    except (smtplib.SMTPException, ssl.SSLError) as exc:
        raise EpostaHata(502, m("E-posta sunucusuyla oturum kurulamadı: ", "Could not establish a session with the mail server: ") + type(exc).__name__) from None
    except OSError as exc:
        raise EpostaHata(503, m(f"E-posta sunucusuna ulaşılamadı ({a.sunucu}:{a.port}); güvenlik duvarı izni gerekir.", f"The mail server is unreachable ({a.sunucu}:{a.port}); a firewall rule is required.") + f" [{type(exc).__name__}]") from None
    return {"reddedilen": sorted(reddedilen)}


def erisim_adimlari() -> list[dict[str, str]]:
    """PostgreSQL/Oracle testiyle ayni kalip: ayar -> DNS -> TCP -> EHLO (STARTTLS istenmisse o da). Ileti GONDERILMEZ."""
    a = Ayar.oku()
    adimlar: list[dict[str, str]] = []

    def ekle(adim: str, durum_: str, baslik: str, ayrinti: str = "") -> list[dict[str, str]]:
        adimlar.append({"adim": adim, "durum": durum_, "baslik": baslik, "ayrinti": ayrinti})
        return adimlar

    if eksik := a.eksikler():
        return ekle("ayar", "hata", "Ayar eksik", ", ".join(eksik))
    ekle("ayar", "ok", "Ayarlar tamam", f"kip {kip()} · port {a.port} · starttls {'açık' if a.starttls else 'kapalı'}")
    try:
        ipler = sorted({x[4][0] for x in socket.getaddrinfo(a.sunucu, a.port, proto=socket.IPPROTO_TCP)})
    except OSError as exc:
        return ekle("dns", "hata", "Sunucu adı çözülemedi", type(exc).__name__)
    ekle("dns", "ok", "Sunucu adı çözüldü", ", ".join(ipler))
    try:
        socket.create_connection((a.sunucu, a.port), timeout=min(a.zaman_asimi, 10)).close()
    except OSError as exc:
        return ekle("tcp", "hata", f"Porta ulaşılamadı ({a.port})", f"{type(exc).__name__} · güvenlik duvarı izni gerekir")
    ekle("tcp", "ok", f"Porta ulaşıldı ({a.port})")
    try:
        with _baglan(a) as s:
            boyut = s.esmtp_features.get("size", "").strip()
            tls = "starttls" in s.esmtp_features
        sinir = f"sunucu sınırı {int(boyut) // (1024 * 1024)} MB" if boyut.isdigit() else "sunucu sınırı bildirilmedi"
        ekle("ehlo", "ok", "SMTP oturumu (EHLO)", f"{sinir} · STARTTLS {'destekleniyor' if tls else 'yok'}")
    except (smtplib.SMTPException, OSError) as exc:
        ekle("ehlo", "hata", "SMTP oturumu (EHLO)", type(exc).__name__)
    return adimlar
