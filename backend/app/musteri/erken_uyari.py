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
from datetime import datetime, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app import musteri_alani
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


def _sinyaller(db: Session, an: datetime | None = None) -> dict[int, _Sinyal]:
    """Bütün kartların sinyalleri, çatı müşterisine toplanmış olarak (iştirak -> çatı).

    an verilirse (geriye dönük doğrulama) yalnız o ana kadarki veri kullanılır: "açık" = o anda açılmış ve henüz kapanmamış;
    devre sinyali (ay sonu özeti) o anda bilinemeyeceği için atlanır. an yoksa şimdi ve kaydın güncel durumu.
    """
    simdi_ = an or simdi()
    son = simdi_ - timedelta(days=PENCERE_GUN)
    taban = son - timedelta(days=TABAN_GUN)
    bekleme = simdi_ - timedelta(days=BEKLEME_GUN)
    cati = {i: (p or i) for i, p in db.execute(select(Customer.id, Customer.parent_id))}
    s: dict[int, _Sinyal] = defaultdict(_Sinyal)
    R = OnedeskRecord
    planli_degil = R.category != PLANLI
    acik = (R.status == "open") if an is None else ((R.opened_at < simdi_) & (R.closed_at.is_(None) | (R.closed_at >= simdi_)))
    once = R.opened_at < simdi_

    alarm = R.kind == "alarm"
    for mid, son_, taban_ in db.execute(
        select(R.customer_id, func.sum(case((R.opened_at >= son, 1), else_=0)), func.sum(case((R.opened_at < son, 1), else_=0)))
        .where(alarm, planli_degil, R.customer_id.is_not(None), R.opened_at >= taban, once)
        .group_by(R.customer_id)
    ):
        x = s[cati.get(mid, YOK)]
        x.alarm_son += int(son_ or 0)
        x.alarm_taban += int(taban_ or 0)

    for mid, son_, acik_adet in db.execute(
        select(
            R.customer_id,
            func.sum(case((R.opened_at >= son, 1), else_=0)),
            func.sum(case((acik, 1), else_=0)),
        )
        .where(R.kind == "sikayet", R.customer_id.is_not(None), once, (R.opened_at >= son) | acik)
        .group_by(R.customer_id)
    ):
        x = s[cati.get(mid, YOK)]
        x.sikayet_son += int(son_ or 0)
        x.sikayet_acik += int(acik_adet or 0)

    for mid, tur, adet in db.execute(
        select(R.customer_id, R.kind, func.count())
        .where(acik, R.customer_id.is_not(None), R.opened_at < bekleme, planli_degil)
        .group_by(R.customer_id, R.kind)
    ):
        x = s[cati.get(mid, YOK)]
        if tur == "alarm":
            x.bekleyen_alarm += int(adet)
        else:
            x.bekleyen_is += int(adet)

    for mid, ci, adet in db.execute(
        select(R.customer_id, R.location, func.count())
        .where(alarm, planli_degil, R.customer_id.is_not(None), R.opened_at >= son, once, R.location != "")
        .group_by(R.customer_id, R.location)
        .having(func.count() >= TEKRAR_ESIGI)
    ):
        x = s[cati.get(mid, YOK)]
        x.tekrar[ci] = x.tekrar.get(ci, 0) + int(adet)

    yil, ay = simdi_.year, simdi_.month
    for mid, ci, ozet in [] if an is not None else db.execute(
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


def _hesapla(db: Session) -> dict[int, dict]:
    return {mid: p for mid, x in _sinyaller(db).items() if (p := _puanla(x))["puan"] > 0}


BILDIRIM_TURU = "erken_uyari"
BILDIRIM_ARALIK_GUN = 7  # ayni musteri icin sorumlu TAM'a en fazla haftada bir


@musteri_alani.tum_alanlarda
def bildir(db: Session) -> dict[str, int]:
    """Kritik seviyedeki cati musterinin sorumlu TAM'ina panel bildirimi (2026-11-27, yol haritasi "Simdi").

    Isci turu sonunda cagrilir (commit cagirana aittir). Tekrar siniri ayri durum tablosu tutmadan bildirimin kendisinden okunur:
    ayni kisiye ayni musteri icin son BILDIRIM_ARALIK_GUN gunde erken_uyari bildirimi varsa yenisi yazilmaz. Sahibi olmayan kart atlanir.
    Tum musteri alanlari (Musteri Yonetimi, Toptan, Baglantili Araclar) kapsanir."""
    from app.bildirim import servis as bildirim
    from app.models import UserNotification

    kritik = {mid: p for mid, p in _hesapla(db).items() if p["seviye"] == "kritik"}
    if not kritik:
        return {"kritik": 0, "gonderilen": 0, "atlanan": 0}
    esik = simdi() - timedelta(days=BILDIRIM_ARALIK_GUN)
    yakin = {
        (kisi, ref)
        for kisi, ref in db.execute(
            select(UserNotification.user_id, UserNotification.ref_id)
            .where(UserNotification.kind == BILDIRIM_TURU, UserNotification.created_at >= esik, UserNotification.ref_id.in_(list(kritik)))
        )
    }
    gonderilen = atlanan = 0
    for c in db.scalars(select(Customer).where(Customer.id.in_(list(kritik)))):
        p = kritik[c.id]
        if c.owner_id is None or (c.owner_id, c.id) in yakin:
            atlanan += 1
            continue
        neden = p["nedenler"][0]["metin"] if p["nedenler"] else ""
        mesaj = m(f"Erken Uyarı: {c.name} kritik seviyede (puan {p['puan']}). {neden}", f"Early Warning: {c.name} is critical (score {p['puan']}). {neden}")
        bildirim.ekle(db, c.owner_id, BILDIRIM_TURU, mesaj, f"#/{c.modul or musteri_alani.VARSAYILAN}?m={c.id}", c.id)
        gonderilen += 1
    return {"kritik": len(kritik), "gonderilen": gonderilen, "atlanan": atlanan}


OZET_GUN = 30


def geri_bildirim_ozeti(db: Session, kisi_id: int | None) -> dict[str, int]:
    """Son OZET_GUN gunde giden Erken Uyari bildirimleri ve TAM yanitlari (uyari dongusu: kacina bakildi, kaci gercekti).
    kisi_id None: tum ekip (alani tumuyle goren yonetici); degilse yalniz o kisinin bildirimleri."""
    from app.models import UserNotification as N

    sorgu = select(
        func.count(),
        func.sum(case((N.response == "ilgilendim", 1), else_=0)),
        func.sum(case((N.response == "gerekmedi", 1), else_=0)),
    ).where(N.kind == BILDIRIM_TURU, N.created_at >= simdi() - timedelta(days=OZET_GUN))
    if kisi_id is not None:
        sorgu = sorgu.where(N.user_id == kisi_id)
    toplam, ilgi, gerekmedi = db.execute(sorgu).one()
    toplam, ilgi, gerekmedi = int(toplam or 0), int(ilgi or 0), int(gerekmedi or 0)
    return {"gun": OZET_GUN, "bildirim": toplam, "ilgilendim": ilgi, "gerekmedi": gerekmedi, "yanitsiz": toplam - ilgi - gerekmedi}


def tumu(db: Session) -> dict[int, dict]:
    """Çatı müşteri kimliği -> {puan, seviye, nedenler}. Sinyali olmayan müşteri sözlükte yoktur (puan 0, normal)."""
    global _onbellek
    from app.tampon.temip_kayit import surum  # geç import: tampon zinciri yalnız gerekince

    # alan: Customer sorgulari istegin musteri alanina suzulur (Musteri Yonetimi / Toptan / Baglantili); her alanin sonucu ayri
    iz = (str(db.get_bind().url), db.scalar(select(func.max(OnedeskRecord.id))), surum(db), simdi().date(), secili(), musteri_alani.secili())
    with _kilit:
        if _onbellek is not None and _onbellek[0] == iz and time.monotonic() - _onbellek[1] < ONBELLEK_SN:
            return _onbellek[2]
    sonuc = _hesapla(db)
    with _kilit:
        _onbellek = (iz, time.monotonic(), sonuc)
    return sonuc


def dogrula(db: Session, *, hafta: int = 16) -> dict:
    """Geriye dönük doğrulama (2026-11-27, jüri sorusu "puan işe yarıyor mu?"): son `hafta` haftanın her pazartesisinde puan
    YALNIZ o güne kadarki veriyle hesaplanır; çatı müşterinin sonraki PENCERE_GUN günde yeni şikayet açıp açmadığına bakılır.
    "temiz" kümesi önceki 14 günde şikayeti olmayan müşterilerdir (şikayet sinyalinin kendini tekrar etmesini ayıklar)."""
    bugun = simdi().replace(hour=0, minute=0, second=0, microsecond=0)
    son_gun = bugun - timedelta(days=PENCERE_GUN + bugun.weekday())  # sonucu tamamen bilinen en yakın pazartesi
    gunler = [son_gun - timedelta(days=7 * k) for k in range(hafta)][::-1]
    cati = {i: (p or i) for i, p in db.execute(select(Customer.id, Customer.parent_id))}
    catilar = {i for i, p in cati.items() if p == i}
    tum: dict[str, list[int]] = {ad: [0, 0] for _, ad in SEVIYELER} | {"normal": [0, 0]}
    temiz: dict[str, list[int]] = {ad: [0, 0] for ad in tum}
    olay_toplam = olay_onceden = 0
    R = OnedeskRecord
    for an in gunler:
        s = _sinyaller(db, an)
        sonra = {
            cati.get(mid, YOK)
            for (mid,) in db.execute(
                select(R.customer_id).where(R.kind == "sikayet", R.customer_id.is_not(None), R.opened_at >= an, R.opened_at < an + timedelta(days=PENCERE_GUN)).distinct()
            )
        } & catilar
        for c in catilar:
            x = s.get(c)
            sev = _puanla(x)["seviye"] if x else "normal"
            olay = c in sonra
            tum[sev][0] += 1
            tum[sev][1] += olay
            if x is None or x.sikayet_son == 0:
                temiz[sev][0] += 1
                temiz[sev][1] += olay
            if olay:
                olay_toplam += 1
                olay_onceden += sev in ("kritik", "yuksek")
    oran = lambda t: {k: {"gozlem": g, "sikayet": o, "oran": round(o / g, 3) if g else None} for k, (g, o) in t.items()}  # noqa: E731
    return {
        "bas": gunler[0].date().isoformat(), "bit": gunler[-1].date().isoformat(), "hafta": hafta,
        "tum": oran(tum), "temiz": oran(temiz),
        "onceden_gorulen": round(olay_onceden / olay_toplam, 3) if olay_toplam else None, "sikayet_olayi": olay_toplam,
    }  # fmt: skip
