"""Müşteri Erken Uyarı (2026-11-27): müşteri aramadan önce sorunlu müşteriyi gösteren risk puanı (0-100).

Panelde zaten akan verilerden hesaplanır; ayrı tablo, elle aktarma ya da işçi yoktur. Dört kayıt sinyali ve bir devre sinyali vardır:

* Alarm ivmesi: son 14 gündeki alarm sayısı, önceki 56 günün 14 günlük ortalamasına göre artış oranı.
* Şikayet: son 14 günde açılan şikayetler ve şu an açık olanlar.
* Bekleyen kayıt: 7 günden uzun süredir açık talep, şikayet ve alarm.
* Tekrarlayan arıza: son 14 günde aynı CI'da 3 ya da daha fazla alarm.
* Devre performansı: rapor devresinin bu ayki erişilebilirliği %99,5'in altında ya da paket kaybı %1'in üstünde.

Planlı çalışma alarmları hiçbir sinyale girmez. İştiraklerin kayıtları çatı müşterisine toplanır; puan çatı kartında gösterilir.
Sonuç bütün müşteriler için tek geçişte hesaplanır ve kısa süre önbellekte tutulur (kayıtlar 6 dakikada bir gelir).
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.dil import m, secili
from app.models import Customer, OnedeskRecord, ReportCircuit, ReportCircuitData
from app.ortak import simdi

PENCERE_GUN = 14  # "son dönem"
TABAN_GUN = 56  # karşılaştırma dönemi (son dönemden hemen önceki 8 hafta)
BEKLEME_GUN = 7  # bu süreden uzun açık kalan kayıt "bekleyen" sayılır
TEKRAR_ESIGI = 3  # aynı CI'da bu kadar alarm "tekrarlayan arıza"
PLANLI = "PLANLI CALISMA ALARMI"
ERISIM_ESIGI = 0.995
KAYIP_ESIGI = 0.01

# puan tavanları (toplam 100'ü aşarsa 100'e kırpılır)
TAVAN = {"alarm": 30, "sikayet": 30, "bekleyen": 20, "tekrar": 20, "devre": 15}
BOS = {"puan": 0, "seviye": "normal", "nedenler": []}  # sinyali olmayan musteri
SEVIYELER = ((60, "kritik"), (35, "yuksek"), (15, "izle"))  # altı: normal

ONBELLEK_SN = 300
YOK = -1  # artik olmayan kart
_kilit = threading.Lock()
_onbellek: tuple[tuple, float, dict[int, dict]] | None = None


@dataclass
class _Sinyal:
    alarm_son: int = 0
    alarm_taban: int = 0
    sikayet_son: int = 0
    sikayet_acik: int = 0
    bekleyen_is: int = 0  # talep + şikayet
    bekleyen_alarm: int = 0
    tekrar: dict[str, int] = field(default_factory=dict)  # CI adı -> alarm sayısı
    devre: list[tuple[str, float | None, float | None]] = field(default_factory=list)  # (CI, erişim, kayıp)


def seviye(puan: int) -> str:
    return next((ad for esik, ad in SEVIYELER if puan >= esik), "normal")


def _sayi(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def _yuzde(oran: float) -> str:
    return f"%{oran * 100:.2f}".replace(".", ",")


def _cumle(parcalar: list[str]) -> str:
    metin = ", ".join(parcalar)
    return metin[:1].upper() + metin[1:]


def _puanla(s: _Sinyal) -> dict:
    """Sinyallerden puan ve "neden" satırları. Her neden kendi katkısıyla birlikte döner; en büyük katkı önce."""
    nedenler: list[tuple[int, str, str]] = []  # (puan, tür, metin)

    taban = s.alarm_taban * PENCERE_GUN / TABAN_GUN
    if s.alarm_son >= 5:
        oran = s.alarm_son / max(taban, 1.0)
        if oran >= 1.5:
            p = min(TAVAN["alarm"], round((oran - 1) * 10))
            kat = f"{oran:.1f}".replace(".", ",")
            nedenler.append((p, "alarm", m(
                f"Son {PENCERE_GUN} günde {_sayi(s.alarm_son)} alarm (önceki ortalama {_sayi(taban)}, ×{kat})",
                f"{_sayi(s.alarm_son)} alarms in the last {PENCERE_GUN} days (previous average {_sayi(taban)}, ×{kat})",
            )))
    if s.sikayet_son or s.sikayet_acik:
        p = min(20, s.sikayet_son * 7) + min(10, s.sikayet_acik * 5)
        parcalar = [m(f"son {PENCERE_GUN} günde {s.sikayet_son} yeni şikayet", f"{s.sikayet_son} new complaints in {PENCERE_GUN} days")] * bool(s.sikayet_son)
        parcalar += [m(f"{s.sikayet_acik} şikayet hâlâ açık", f"{s.sikayet_acik} complaints still open")] * bool(s.sikayet_acik)
        nedenler.append((min(TAVAN["sikayet"], p), "sikayet", _cumle(parcalar)))
    if s.bekleyen_is or s.bekleyen_alarm:
        p = min(TAVAN["bekleyen"], s.bekleyen_is * 4 + min(8, s.bekleyen_alarm))
        parcalar = [m(f"{s.bekleyen_is} talep/şikayet", f"{s.bekleyen_is} requests/complaints")] * bool(s.bekleyen_is)
        parcalar += [m(f"{_sayi(s.bekleyen_alarm)} alarm", f"{_sayi(s.bekleyen_alarm)} alarms")] * bool(s.bekleyen_alarm)
        nedenler.append((p, "bekleyen", m(f"{BEKLEME_GUN} günden uzun açık: ", f"Open for over {BEKLEME_GUN} days: ") + ", ".join(parcalar)))
    if s.tekrar:
        # puan en kötü CI'ya göre (müşterinin büyüklüğünden bağımsız): aynı hat ne kadar sık düşüyor
        ci, adet = max(s.tekrar.items(), key=lambda x: x[1])
        p = TAVAN["tekrar"] if adet >= 20 else 14 if adet >= 6 else 7
        nedenler.append((p, "tekrar", m(
            f"Aynı CI'da tekrarlayan alarm: {ci} son {PENCERE_GUN} günde {_sayi(adet)} kez"
            + (f" (+{len(s.tekrar) - 1} CI daha)" if len(s.tekrar) > 1 else ""),
            f"Repeating alarms on one CI: {ci}, {_sayi(adet)} times in {PENCERE_GUN} days"
            + (f" (+{len(s.tekrar) - 1} more CIs)" if len(s.tekrar) > 1 else ""),
        )))
    for ci, erisim, kayip in s.devre:
        parcalar = []
        if erisim is not None and erisim < ERISIM_ESIGI:
            parcalar.append(m(f"erişilebilirlik {_yuzde(erisim)}", f"availability {_yuzde(erisim)}"))
        if kayip is not None and kayip > KAYIP_ESIGI:
            parcalar.append(m(f"paket kaybı {_yuzde(kayip)}", f"packet loss {_yuzde(kayip)}"))
        if parcalar:
            nedenler.append((TAVAN["devre"], "devre", m("Rapor devresi bu ay: ", "Report circuit this month: ") + ", ".join(parcalar) + f" ({ci})"))
            break  # bir devre yeter; puan tavanı tek

    nedenler.sort(key=lambda n: -n[0])
    puan = min(100, sum(n[0] for n in nedenler))
    return {
        "puan": puan,
        "seviye": seviye(puan),
        "nedenler": [{"tur": t, "puan": p, "metin": metin} for p, t, metin in nedenler if p > 0],
    }


def _sinyaller(db: Session) -> dict[int, _Sinyal]:
    """Bütün kartların sinyalleri, çatı müşterisine toplanmış olarak (iştirak -> çatı)."""
    simdi_ = simdi()
    son = simdi_ - timedelta(days=PENCERE_GUN)
    taban = son - timedelta(days=TABAN_GUN)
    bekleme = simdi_ - timedelta(days=BEKLEME_GUN)
    cati = {i: (p or i) for i, p in db.execute(select(Customer.id, Customer.parent_id))}
    s: dict[int, _Sinyal] = defaultdict(_Sinyal)
    R = OnedeskRecord
    planli_degil = R.category != PLANLI

    alarm = R.kind == "alarm"
    for mid, son_, taban_ in db.execute(
        select(R.customer_id, func.sum(case((R.opened_at >= son, 1), else_=0)), func.sum(case((R.opened_at < son, 1), else_=0)))
        .where(alarm, planli_degil, R.customer_id.is_not(None), R.opened_at >= taban)
        .group_by(R.customer_id)
    ):
        x = s[cati.get(mid, YOK)]
        x.alarm_son += int(son_ or 0)
        x.alarm_taban += int(taban_ or 0)

    for mid, son_, acik in db.execute(
        select(
            R.customer_id,
            func.sum(case((R.opened_at >= son, 1), else_=0)),
            func.sum(case((R.status == "open", 1), else_=0)),
        )
        .where(R.kind == "sikayet", R.customer_id.is_not(None), (R.opened_at >= son) | (R.status == "open"))
        .group_by(R.customer_id)
    ):
        x = s[cati.get(mid, YOK)]
        x.sikayet_son += int(son_ or 0)
        x.sikayet_acik += int(acik or 0)

    for mid, tur, adet in db.execute(
        select(R.customer_id, R.kind, func.count())
        .where(R.status == "open", R.customer_id.is_not(None), R.opened_at < bekleme, planli_degil)
        .group_by(R.customer_id, R.kind)
    ):
        x = s[cati.get(mid, YOK)]
        if tur == "alarm":
            x.bekleyen_alarm += int(adet)
        else:
            x.bekleyen_is += int(adet)

    for mid, ci, adet in db.execute(
        select(R.customer_id, R.location, func.count())
        .where(alarm, planli_degil, R.customer_id.is_not(None), R.opened_at >= son, R.location != "")
        .group_by(R.customer_id, R.location)
        .having(func.count() >= TEKRAR_ESIGI)
    ):
        x = s[cati.get(mid, YOK)]
        x.tekrar[ci] = x.tekrar.get(ci, 0) + int(adet)

    yil, ay = simdi_.year, simdi_.month
    for mid, ci, ozet in db.execute(
        select(ReportCircuit.customer_id, ReportCircuit.ciname, ReportCircuitData.summary)
        .join(ReportCircuitData, and_(ReportCircuitData.ciname == ReportCircuit.ciname, ReportCircuitData.year == yil, ReportCircuitData.month == ay))
    ):
        ozet = ozet if isinstance(ozet, dict) else {}
        def sayi(k: str) -> float | None:
            v = ozet.get(k)
            return float(v) if isinstance(v, int | float) and math.isfinite(v) else None
        s[cati.get(mid, YOK)].devre.append((ci, sayi("erisilebilirlik"), sayi("kayip")))
    s.pop(YOK, None)  # silinmis karta bagli kalmis kayitlar
    return s


def tumu(db: Session) -> dict[int, dict]:
    """Çatı müşteri kimliği -> {puan, seviye, nedenler}. Sinyali olmayan müşteri sözlükte yoktur (puan 0, normal)."""
    global _onbellek
    from app.tampon.temip_kayit import surum  # geç import: tampon zinciri yalnız gerekince

    iz = (str(db.get_bind().url), db.scalar(select(func.max(OnedeskRecord.id))), surum(db), simdi().date(), secili())
    with _kilit:
        if _onbellek is not None and _onbellek[0] == iz and time.monotonic() - _onbellek[1] < ONBELLEK_SN:
            return _onbellek[2]
    sonuc = {mid: p for mid, x in _sinyaller(db).items() if (p := _puanla(x))["puan"] > 0}
    with _kilit:
        _onbellek = (iz, time.monotonic(), sonuc)
    return sonuc
