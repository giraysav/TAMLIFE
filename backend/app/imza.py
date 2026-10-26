"""Kisinin e-posta imzasi (2026-10-26 kullanici: "profil kartindaki adres alanini kaldir, yerine Outlook'taki gibi resim ve yazi ile
freetext imza; bu imza aylik rapor mail govdesinde de olacak; imzadaki fotograf Teknocan, yanina yazi yazilabilsin").

Imza profilde (app_user.signature_html) zengin metin olarak saklanir. Tarayicidan gelen HTML burada IZIN LISTESIYLE temizlenir:
yalniz bicim etiketleri (paragraf, kalin, renk, tablo, baglanti, gorsel); betik, olay ozniteligi, dis kaynakli gorsel ve tehlikeli
stil (url(), expression) atilir. Gorseller yalniz govdeye gomulu (data:image/png|jpeg|gif;base64) kabul edilir; iletide CID parcasi
olur (Outlook dis resmi engeller). Yeni bagimlilik yok (html.parser).
"""

from __future__ import annotations

import base64
import binascii
import html
import re
from functools import cache
from html.parser import HTMLParser
from pathlib import Path

from app.ortak import UygulamaHatasi

AZAMI_HTML = 1_500_000  # karakter (gomulu gorseller dahil)
AZAMI_GORSEL = 600 * 1024  # tek gorsel (bayt)
EN_FAZLA_GORSEL = 8
TEKNOCAN = Path(__file__).resolve().parent / "rapor" / "sablon" / "teknocan.png"

ETIKETLER = {
    "p", "div", "span", "br", "b", "strong", "i", "em", "u", "s", "a", "img", "table", "tbody", "thead", "tr", "td", "th",
    "font", "ul", "ol", "li", "hr", "h1", "h2", "h3", "h4", "small", "sup", "sub", "blockquote",
}  # fmt: skip
BOS_ETIKETLER = {"br", "img", "hr"}
# etiket -> izinli oznitelikler (style ve align her etikette ayrica)
OZNITELIKLER = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
    "table": {"width", "cellpadding", "cellspacing", "border", "bgcolor"},
    "td": {"width", "valign", "colspan", "rowspan", "bgcolor"},
    "th": {"width", "valign", "colspan", "rowspan", "bgcolor"},
    "font": {"color", "size", "face"},
}
STILLER = {
    "color", "background-color", "font-size", "font-family", "font-weight", "font-style", "text-decoration", "text-align",
    "vertical-align", "line-height", "letter-spacing", "white-space", "width", "height", "max-width", "min-width",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "border", "border-top", "border-right", "border-bottom", "border-left", "border-color", "border-width", "border-style",
    "border-radius", "border-collapse", "display",
}  # fmt: skip
_TEHLIKELI_STIL = re.compile(r"url\s*\(|expression|javascript|vbscript|@import|[<>\\]|/\*", re.IGNORECASE)
_DISPLAY = {"block", "inline", "inline-block", "table", "table-cell", "table-row"}
_GORSEL = re.compile(r"^data:image/(png|jpeg|jpg|gif);base64,([A-Za-z0-9+/=\s]+)$", re.IGNORECASE)
_BAGLANTI = re.compile(r"^(https?://|mailto:|tel:)", re.IGNORECASE)
_SAYI = re.compile(r"^\d{1,4}%?$")
_RENK = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,20}|rgba?\([0-9.,\s%]+\))$")


class ImzaHata(UygulamaHatasi):
    pass


def _stil(deger: str) -> str:
    temiz = []
    for parca in deger.split(";"):
        ad, _, val = parca.partition(":")
        ad, val = ad.strip().lower(), val.strip()
        if not ad or not val or ad not in STILLER or _TEHLIKELI_STIL.search(val) or len(val) > 120:
            continue
        if ad == "display" and val.lower() not in _DISPLAY:
            continue
        temiz.append(f"{ad}:{val}")
    return ";".join(temiz)


class _Temizleyici(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parcalar: list[str] = []
        self.yigin: list[str] = []
        self.atla = 0  # script/style gibi icerigi tumden atilan etiketin derinligi
        self.gorsel = 0

    def _oznitelik(self, etiket: str, ad: str, deger: str | None) -> str | None:
        deger = (deger or "").strip()
        if ad == "style":
            return _stil(deger) or None
        if ad == "align":
            return deger.lower() if deger.lower() in {"left", "center", "right", "justify"} else None
        if ad not in OZNITELIKLER.get(etiket, set()):
            return None
        if ad == "href":
            return deger if _BAGLANTI.match(deger) and len(deger) <= 500 else None
        if ad == "src":
            esles = _GORSEL.match(deger)
            if not esles:
                return None
            try:
                bayt = base64.b64decode(re.sub(r"\s+", "", esles.group(2)), validate=True)
            except (binascii.Error, ValueError):
                return None
            if len(bayt) > AZAMI_GORSEL:
                raise ImzaHata(400, f"İmzadaki bir görsel {AZAMI_GORSEL // 1024} KB sınırını aşıyor; daha küçük görsel ekleyin.")
            self.gorsel += 1
            if self.gorsel > EN_FAZLA_GORSEL:
                raise ImzaHata(400, f"İmzada en fazla {EN_FAZLA_GORSEL} görsel olabilir.")
            return f"data:image/{esles.group(1).lower().replace('jpg', 'jpeg')};base64,{base64.b64encode(bayt).decode('ascii')}"
        if ad in {"width", "height", "cellpadding", "cellspacing", "border", "colspan", "rowspan", "size"}:
            return deger if _SAYI.match(deger) else None
        if ad in {"color", "bgcolor"}:
            return deger if _RENK.match(deger) else None
        if ad == "valign":
            return deger.lower() if deger.lower() in {"top", "middle", "bottom", "baseline"} else None
        return deger[:200]

    def handle_starttag(self, etiket: str, oznitelikler: list[tuple[str, str | None]]) -> None:
        if etiket in {"script", "style", "iframe", "object", "embed", "noscript", "template", "svg", "math", "head", "title"}:
            self.atla += 1
            return
        if self.atla or etiket not in ETIKETLER:
            return
        temiz = []
        for ad, deger in oznitelikler:
            ad = ad.lower()
            if ad.startswith("on"):
                continue
            sonuc = self._oznitelik(etiket, ad, deger)
            if sonuc is not None:
                temiz.append(f'{ad}="{html.escape(sonuc, quote=True)}"')
        if etiket == "img" and not any(t.startswith("src=") for t in temiz):
            return  # gomulu olmayan (dis kaynakli) gorsel atilir
        if etiket == "a":
            temiz.append('target="_blank"')
        self.parcalar.append(f"<{etiket}{''.join(' ' + t for t in temiz)}>")
        if etiket not in BOS_ETIKETLER:
            self.yigin.append(etiket)

    def handle_startendtag(self, etiket: str, oznitelikler: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(etiket, oznitelikler)
        if etiket not in BOS_ETIKETLER and self.yigin and self.yigin[-1] == etiket:
            self.handle_endtag(etiket)

    def handle_endtag(self, etiket: str) -> None:
        if etiket in {"script", "style", "iframe", "object", "embed", "noscript", "template", "svg", "math", "head", "title"}:
            self.atla = max(0, self.atla - 1)
            return
        if self.atla or etiket not in self.yigin:
            return
        while self.yigin:  # kapanmamis ic etiketler de kapanir (dengeli cikti)
            ust = self.yigin.pop()
            self.parcalar.append(f"</{ust}>")
            if ust == etiket:
                break

    def handle_data(self, veri: str) -> None:
        if not self.atla:
            self.parcalar.append(html.escape(veri, quote=False))

    def sonuc(self) -> str:
        return "".join(self.parcalar) + "".join(f"</{e}>" for e in reversed(self.yigin))


def temizle(ham: object) -> str:
    """Tarayicidan gelen imza HTML'i -> guvenli HTML (bos ya da yalniz bosluksa "")."""
    if ham is None:
        return ""
    if not isinstance(ham, str):
        raise ImzaHata(400, "İmza geçersiz.")
    if len(ham) > AZAMI_HTML:
        raise ImzaHata(400, "İmza çok büyük; görselleri küçültün.")
    t = _Temizleyici()
    t.feed(ham)
    t.close()
    cikti = t.sonuc().strip()
    return cikti if duz_metin(cikti).strip() or "<img" in cikti else ""


def duz_metin(guvenli_html: str) -> str:
    """HTML okumayan istemci icin: satir sonlari korunur, etiketler atilir."""
    metin = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-4])>", "\n", guvenli_html or "")
    metin = re.sub(r"(?i)</t[dh]>", " ", metin)
    metin = html.unescape(re.sub(r"<[^>]+>", "", metin))
    return "\n".join(s.strip() for s in metin.splitlines() if s.strip())


@cache
def teknocan_veri_url() -> str:
    return "data:image/png;base64," + base64.b64encode(TEKNOCAN.read_bytes()).decode("ascii") if TEKNOCAN.is_file() else ""


def varsayilan(ad: str, unvan: str, sirket: str, telefon: str, web: str) -> str:
    """Ilk imza: solda Teknocan, sagda ad / unvan / sirket / iletisim (Outlook imzasi gibi duzenlenebilir)."""
    k = html.escape
    satirlar = [f'<span style="font-size:15px;font-weight:700;color:#002855">{k(ad)}</span>']
    satirlar += [k(s) for s in (unvan, sirket) if s]
    iletisim = " · ".join(p for p in (k(telefon) if telefon else "", f'<a href="{k(web)}">{k(web)}</a>' if web else "") if p)
    if iletisim:
        satirlar.append(iletisim)
    gorsel = teknocan_veri_url()
    sol = f'<td valign="middle" style="padding-right:16px"><img src="{gorsel}" alt="Teknocan" width="96" height="96"></td>' if gorsel else ""
    return (
        '<table cellpadding="0" cellspacing="0" border="0"><tbody><tr>'
        f"{sol}"
        f'<td valign="middle" style="font-family:Segoe UI,Calibri,Arial,sans-serif;font-size:13px;line-height:1.5;color:#334155">{"<br>".join(satirlar)}</td>'
        "</tr></tbody></table>"
    )


def gomulu_gorselleri_ayir(guvenli_html: str, bilinen: dict[bytes, str] | None = None) -> tuple[str, list[tuple[str, bytes, str]]]:
    """data:image gorselleri cid: basvurusuna cevirir. Donus: (html, [(cid, bayt, alt tur)]). Ayni gorsel tek parca olur; `bilinen`
    (bayt -> cid) iletide zaten olan gorseldir (Teknocan), yeni parca eklenmez."""
    parcalar: dict[bytes, tuple[str, str]] = {}
    bilinen = bilinen or {}

    def cevir(esles: re.Match) -> str:
        tur, veri = esles.group(1).lower().replace("jpg", "jpeg"), base64.b64decode(esles.group(2))
        if veri in bilinen:
            return f'src="cid:{bilinen[veri]}"'
        if veri not in parcalar:
            parcalar[veri] = (f"imza{len(parcalar) + 1}@tamlife", tur)
        return f'src="cid:{parcalar[veri][0]}"'

    yeni = re.sub(r'src="data:image/(png|jpeg|jpg|gif);base64,([A-Za-z0-9+/=]+)"', cevir, guvenli_html or "")
    return yeni, [(cid, veri, tur) for veri, (cid, tur) in parcalar.items()]
