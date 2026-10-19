"""Musteri No eslesme raporu (2026-10-18 kullanici istegi: "ReportDB verilerini musteri kartlarina ata; hatali ya da atama olmayan
musteri no varsa raporla"). Yalniz okur: panel DB'sindeki TEMIP kayitlari (onedesk_record, source='temip') ve musteri kartlari.

    python -m araclar.musteri_no_raporu            -> backend/var/kesif/musteri-no-raporu-<zaman>.xlsx (git disi; musteri unvani icerir)

Sayfalar: Ozet, Eslesmeyen Musteri No (TEMIP'te var, kart yok; unvani benzeyen kart "aday"), Hatali kart numarasi (8 hane degil /
rakam disi), Numarasiz kartlar (TEMIP'te unvani tutan numara onerisiyle), Kaydi olmayan numarali kartlar, Belirsiz (numara birden
cok kartta), Sorumlusu TAM olmayan kartlar. Eslesme kurali iceri almayla ayni: yalniz numara (bastaki sifirlar yok sayilir).
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import func, select

from app.config import env_dosyasi_yukle

_AYRAC = re.compile(r"[,;/\n]+")


def _sorun(parca: str) -> str:
    """Kart numarasi parcasinin sorunu ('' = gecerli 8 hane)."""
    p = parca.strip()
    if not p:
        return ""
    if re.search(r"[^\d\s.]", p):
        return "rakam dışı karakter"
    rakam = re.sub(r"\D", "", p)
    if len(rakam) > 8:
        return f"{len(rakam)} hane (8 olmalı)"
    if len(rakam) < 8:
        return f"{len(rakam)} hane (8 olmalı; başında 0 eksik olabilir)" if len(rakam) == 7 else f"{len(rakam)} hane (8 olmalı)"
    return ""


def rapor(db) -> dict:
    from app.kullanicilar import musteri_personeli_mi
    from app.models import AppUser, Customer, OnedeskRecord
    from app.skor.urun_tutar import _cekirdek
    from app.tampon.eslestirme import anahtar, musteri_anahtarlari

    kisiler = {u.id: u for u in db.scalars(select(AppUser))}
    kartlar = list(db.scalars(select(Customer)))
    kart_ad = {c.id: c for c in kartlar}
    tam = lambda c: (kisiler[c.owner_id].display_name or kisiler[c.owner_id].username) if c.owner_id in kisiler else ""
    harita: dict[str, set[int]] = defaultdict(set)
    for c in kartlar:
        for k in musteri_anahtarlari(c.customer_no):
            harita[k].add(c.id)
    cekirdek: dict[str, list] = defaultdict(list)
    for c in kartlar:
        if ck := _cekirdek(c.name or ""):
            cekirdek[ck].append(c)

    # TEMIP kayitlari Musteri No bazinda
    temip: dict[str, dict] = {}
    for no, unvan, durum, kart, n, son in db.execute(
        select(
            OnedeskRecord.customer_no,
            func.max(OnedeskRecord.customer_label),
            OnedeskRecord.status,
            OnedeskRecord.customer_id,
            func.count(),
            func.max(OnedeskRecord.opened_at),
        )
        .where(OnedeskRecord.source == "temip")
        .group_by(OnedeskRecord.customer_no, OnedeskRecord.status, OnedeskRecord.customer_id)
    ):
        t = temip.setdefault(no or "", {"unvan": unvan or "", "acik": 0, "kapali": 0, "kart": set(), "son": None})
        t["acik" if durum == "open" else "kapali"] += n
        if kart:
            t["kart"].add(kart)
        t["son"] = max(filter(None, [t["son"], son]), default=None)

    eslesmeyen, belirsiz = [], []
    for no, t in temip.items():
        adaylar = harita.get(anahtar(no), set())
        if len(adaylar) > 1:
            belirsiz.append([no, t["unvan"], t["acik"], t["kapali"], ", ".join(kart_ad[i].name for i in sorted(adaylar))])
        elif not adaylar:
            aday = cekirdek.get(_cekirdek(t["unvan"]), [])
            eslesmeyen.append([no, t["unvan"], t["acik"], t["kapali"], t["acik"] + t["kapali"], t["son"],
                               ", ".join(c.name for c in aday), ", ".join(c.customer_no or "(numara yok)" for c in aday),
                               ", ".join(sorted({tam(c) for c in aday} - {""}))])  # fmt: skip
    eslesmeyen.sort(key=lambda r: (not r[6], -r[4]))  # once kart adayi olanlar, sonra kayit sayisi

    temip_anahtar = {anahtar(no) for no in temip}
    hatali, numarasiz, kayitsiz, personelsiz = [], [], [], []
    kayitli_kart = {i for t in temip.values() for i in t["kart"]}
    oneri_unvan: dict[str, list[str]] = defaultdict(list)
    for no, t in temip.items():
        oneri_unvan[_cekirdek(t["unvan"])].append(no)
    for c in sorted(kartlar, key=lambda c: c.name or ""):
        ham = (c.customer_no or "").strip()
        cati = kart_ad[c.parent_id].name if c.parent_id in kart_ad else ""
        if not ham:
            oneriler = oneri_unvan.get(_cekirdek(c.name or ""), [])
            numarasiz.append([c.id, c.name, cati, tam(c), ", ".join(sorted(oneriler)[:10])])
            continue
        for parca in _AYRAC.split(ham):
            if s := _sorun(parca):
                hatali.append([c.id, c.name, cati, tam(c), ham, parca.strip(), s])
        gecerli = [k for k in musteri_anahtarlari(ham)]
        if gecerli and not any(k in temip_anahtar for k in gecerli):
            kayitsiz.append([c.id, c.name, cati, tam(c), ham])
        if c.id in kayitli_kart and not musteri_personeli_mi(kisiler.get(c.owner_id)):
            personelsiz.append([c.id, c.name, cati, tam(c) or "(sorumlu yok)", ham])

    toplam_kayit = sum(t["acik"] + t["kapali"] for t in temip.values())
    eslesen_kayit = sum(t["acik"] + t["kapali"] for no, t in temip.items() if len(harita.get(anahtar(no), set())) == 1)
    ozet = [
        ["TEMIP kaydı (01.01.2026'dan)", toplam_kayit],
        ["Karta atanan kayıt", eslesen_kayit],
        ["Atanamayan kayıt (TAM Radar)", toplam_kayit - eslesen_kayit],
        ["TEMIP'teki farklı Müşteri No", len(temip)],
        ["  karta eşleşen", len(temip) - len(eslesmeyen) - len(belirsiz)],
        ["  eşleşmeyen (kartı yok)", len(eslesmeyen)],
        ["    bunlardan ünvanı bir kartla aynı (kart adayı)", sum(1 for r in eslesmeyen if r[6])],
        ["  belirsiz (birden çok kartta)", len(belirsiz)],
        ["Panel kartı", len(kartlar)],
        ["  kayıt alan kart", len(kayitli_kart)],
        ["  hatalı numara parçası olan kart", len({r[0] for r in hatali})],
        ["  Müşteri No'su boş kart", len(numarasiz)],
        ["  numaralı ama TEMIP kaydı olmayan kart", len(kayitsiz)],
        ["  kayıt alan ama sorumlusu TAM olmayan kart", len(personelsiz)],
    ]
    return {"ozet": ozet, "eslesmeyen": eslesmeyen, "belirsiz": belirsiz, "hatali": hatali, "numarasiz": numarasiz,
            "kayitsiz": kayitsiz, "personelsiz": personelsiz}  # fmt: skip


SAYFALAR = (
    ("Özet", "ozet", ["Kalem", "Değer"]),
    (
        "Eşleşmeyen Müşteri No",
        "eslesmeyen",
        [
            "Müşteri No (TEMIP)",
            "TEMIP ünvanı",
            "Açık",
            "Kapalı",
            "Toplam",
            "Son kayıt",
            "Kart adayı (ünvan aynı)",
            "Adayın Müşteri No'su",
            "Adayın TAM'i",
        ],
    ),
    ("Hatalı kart numarası", "hatali", ["Kart", "Kart ünvanı", "Çatı", "TAM", "Karttaki Müşteri No", "Hatalı parça", "Sorun"]),
    ("Numarasız kartlar", "numarasiz", ["Kart", "Kart ünvanı", "Çatı", "TAM", "TEMIP'te ünvanı tutan Müşteri No (öneri)"]),
    ("Kaydı olmayan numaralı kart", "kayitsiz", ["Kart", "Kart ünvanı", "Çatı", "TAM", "Karttaki Müşteri No"]),
    ("Belirsiz", "belirsiz", ["Müşteri No", "TEMIP ünvanı", "Açık", "Kapalı", "Kartlar"]),
    ("Sorumlusu TAM olmayan", "personelsiz", ["Kart", "Kart ünvanı", "Çatı", "Sorumlu", "Müşteri No"]),
)


def excel_yaz(r: dict, yol: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    kitap = Workbook()
    kitap.remove(kitap.active)
    for ad, anahtar_, basliklar in SAYFALAR:
        ws = kitap.create_sheet(ad[:31])
        ws.append(basliklar)
        for h in ws[1]:
            h.font, h.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="0A2A5E")
        for satir in r[anahtar_]:
            ws.append([v.replace(tzinfo=None) if isinstance(v, datetime) else v for v in satir])
        ws.freeze_panes = "A2"
        for i, b in enumerate(basliklar, 1):
            uzun = max([len(str(b)), *(len(str(s[i - 1] or "")) for s in r[anahtar_][:500])])
            ws.column_dimensions[ws.cell(1, i).column_letter].width = min(60, max(10, uzun + 2))
        if r[anahtar_]:
            ws.auto_filter.ref = ws.dimensions
    yol.parent.mkdir(parents=True, exist_ok=True)
    kitap.save(yol)


def main() -> int:
    env_dosyasi_yukle()
    from app.db import oturum

    with oturum() as db:
        r = rapor(db)
    yol = BACKEND / "var" / "kesif" / f"musteri-no-raporu-{datetime.now():%Y%m%d-%H%M}.xlsx"  # noqa: DTZ005 - dosya adi
    excel_yaz(r, yol)
    for kalem, deger in r["ozet"]:
        print(f"{kalem:<52} {deger}")
    print(f"Rapor: {yol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
