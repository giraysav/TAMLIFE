"""Ceyrek Sunum disa aktarma (2026-10-20 kullanici: "ceyrek sunumdaki her veriyi export edebilecegim bir buton: Excel / PDF").

Ceyregin gorunur alanlari (servis.donem: ekrandaki ile ayni ogeler, onayli ceyrekte onay kaydi) tek bicime cevrilir:
bolum = {baslik, durum, tablolar: [{baslik, sutunlar, satirlar}]}. Excel sunucuda (openpyxl: "Ozet" + alan basina bir sayfa),
PDF tarayicida ayni JSON'dan yazdirma penceresiyle uretilir (yeni bagimlilik yok). Metin cevirisi yapilmaz; Turkce basliklar.
"""

from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.sunum import servis

TAKVIM_SUTUNLARI = (("online", "Online toplantı"), ("yuzyuze", "Yüz yüze toplantı"), ("yillik_izin", "Yıllık izin"),
                    ("sirket_izni", "Şirket izni"), ("arife_tatili", "Yarım gün"), ("resmi_tatil", "Resmi tatil"), ("raporlu", "Raporlu"))  # fmt: skip
DURUM_ADI = {"canli": "Canlı (çeyrek sürüyor)", "kayitli": "Kayıtlı", "yok": "Veri yok", "hata": "Hesaplanamadı"}


def _kpi_tablosu(veri: dict) -> dict | None:
    kpi = veri.get("kpi") or []
    if not kpi:
        return None
    return {"baslik": "Göstergeler", "sutunlar": ["Gösterge", "Değer", "Birim", "Not"],
            "satirlar": [[k.get("ad", ""), k.get("deger"), k.get("birim", ""), k.get("alt", "")] for k in kpi]}  # fmt: skip


def _takvim_tablolari(veri: dict) -> list[dict]:
    def deger(o: dict, k: str) -> Any:
        return o.get(k) if k in ("online", "yuzyuze") else (o.get("durumlar") or {}).get(k, 0)

    g = veri.get("genel") or {}
    tablolar = [{"baslik": "Ekip (toplantılar kişi toplamı; günler dönemin takviminden)", "sutunlar": [ad for _, ad in TAKVIM_SUTUNLARI],
                 "satirlar": [[deger(g, k) for k, _ in TAKVIM_SUTUNLARI]]}]  # fmt: skip
    yil = veri.get("yil_toplami")
    if yil:
        tablolar.append({"baslik": "Yıl toplamı (toplantılar)", "sutunlar": ["Online toplantı", "Yüz yüze toplantı"], "satirlar": [[yil.get("online"), yil.get("yuzyuze")]]})
    uyeler = veri.get("uyeler") or []
    if uyeler:
        tablolar.append({"baslik": "Kişi bazında", "sutunlar": ["TAM", *(ad for _, ad in TAKVIM_SUTUNLARI)],
                         "satirlar": [[u.get("ad", ""), *(deger(u, k) for k, _ in TAKVIM_SUTUNLARI)] for u in uyeler]})  # fmt: skip
    return tablolar


def _tanitim_tablolari(veri: dict) -> list[dict]:
    tablolar = []
    if veri.get("ozet"):
        tablolar.append({"baslik": "Özet", "sutunlar": ["Metin"], "satirlar": [[veri["ozet"].get("tr", "")]]})
    if veri.get("alanlar"):
        tablolar.append({"baslik": "Kapsam", "sutunlar": ["İş alanı", "Modüller"],
                         "satirlar": [[a.get("ad", ""), ", ".join(m.get("ad", "") for m in a.get("moduller") or [])] for a in veri["alanlar"]]})  # fmt: skip
    if veri.get("canli"):
        tablolar.append({"baslik": "Rakamlarla", "sutunlar": ["Kalem", "Değer"], "satirlar": [[c.get("ad", ""), c.get("deger")] for c in veri["canli"]]})
    return tablolar


def bolumler(db: Session, yil: int, ceyrek: int, kullanici: str) -> dict[str, Any]:
    """Ceyregin ekrandaki ogeleri, disa aktarma bicimiyle (ekranla ayni veri; onayli ceyrekte onay kaydi)."""
    d = servis.donem(db, yil, ceyrek, kullanici)
    sonuc = []
    for o in d["ogeler"]:
        veri = o.get("veri") or {}
        tablolar: list[dict] = []
        if o["kaynak"] == "takvim":
            tablolar = _takvim_tablolari(veri)
        else:
            if (t := _kpi_tablosu(veri)) is not None:
                tablolar.append(t)
            if veri.get("stil") == "tanitim":
                tablolar += _tanitim_tablolari(veri)
            tablo = veri.get("tablo") or {}
            if tablo.get("satirlar"):
                tablolar.append({"baslik": "Ayrıntı", "sutunlar": [s.get("ad", "") for s in tablo.get("sutunlar") or []], "satirlar": tablo["satirlar"]})
        sonuc.append({"kaynak": o["kaynak"], "baslik": o["ad"], "durum": DURUM_ADI.get(o["durum"], o["durum"]), "zaman": o.get("zaman"), "tablolar": tablolar})
    return {"yil": yil, "ceyrek": ceyrek, "donem": d["donem"], "onay": d.get("onay"), "bolumler": sonuc}


def _sayfa_adi(ad: str, kullanilan: set[str]) -> str:
    temiz = "".join(c for c in ad if c not in "[]:*?/\\")[:28].strip() or "Alan"
    aday, n = temiz, 2
    while aday in kullanilan:
        aday, n = f"{temiz[:25]} {n}", n + 1
    kullanilan.add(aday)
    return aday


def excel(veri: dict[str, Any]) -> bytes:
    baslik_dolgu, baslik_yazi = PatternFill("solid", fgColor="002855"), Font(bold=True, color="FFFFFF")
    wb = Workbook()
    ozet = wb.active
    ozet.title = "Özet"
    ozet.append([f"TAMLIFE Çeyrek Sunum · {veri['donem']}" + (f" · onaylayan {veri['onay']['onaylayan']}" if veri.get("onay") else "")])
    ozet["A1"].font = Font(bold=True, size=14, color="002855")
    ozet.append([])
    ozet.append(["Alan", "Durum", "İlk göstergeler"])
    for h in ozet[3]:
        h.fill, h.font = baslik_dolgu, baslik_yazi
    kullanilan = {"Özet"}
    for b in veri["bolumler"]:
        ilk = next((t for t in b["tablolar"]), None)
        ozet.append([b["baslik"], b["durum"], " · ".join(f"{s[0]}: {s[1]}" for s in (ilk["satirlar"][:4] if ilk and ilk["baslik"] == "Göstergeler" else []))])
        ws = wb.create_sheet(_sayfa_adi(b["baslik"], kullanilan))
        ws.append([b["baslik"]])
        ws["A1"].font = Font(bold=True, size=13, color="002855")
        ws.append([f"{veri['donem']} · {b['durum']}"])
        if not b["tablolar"]:
            ws.append(["Bu çeyrekte veri yok."])
        for t in b["tablolar"]:
            ws.append([])
            ws.append([t["baslik"]])
            ws.cell(ws.max_row, 1).font = Font(bold=True, color="0055A5")
            ws.append(list(t["sutunlar"]))
            for h in ws[ws.max_row]:
                h.fill, h.font = baslik_dolgu, baslik_yazi
            for s in t["satirlar"]:
                ws.append([h if isinstance(h, (int, float)) or h is None else str(h) for h in s])
        for i in range(1, ws.max_column + 1):
            ws.column_dimensions[get_column_letter(i)].width = 18 if i > 1 else 34
    ozet.column_dimensions["A"].width, ozet.column_dimensions["B"].width, ozet.column_dimensions["C"].width = 36, 22, 90
    for satir in ozet.iter_rows(min_row=4):
        satir[2].alignment = Alignment(wrap_text=True, vertical="top")
    cikti = io.BytesIO()
    wb.save(cikti)
    return cikti.getvalue()
