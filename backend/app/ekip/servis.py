# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Ekip ozeti. Uretim karsiligi: kutucuklar/ekip/servis.py (_build_team_overview, _build_team_ai_summary, _build_team_stats,
_build_tam_personal_ai_summary). Ayri modul degil, Genel Bakis'ta bolum (2026-10-11 kullanici karari).

Her TAM icin: bugunku takvim durumu, portfoy (cati musteri), rapor uyumu (Ekim 2026 doneminden bugune; Aylik Rapor ile ayni rapor birimi kurali),
risk yuku (tum musterilerinin acik alarm + sikayet), acik talep, kapanan kayit, utilizasyon (puanlama disi personelde bos),
yilin toplantilari ve projeler. Uretimdeki 'acik gorev' (DailyTask) yeni panelde yok; yerine acik proje sayilir.
ICT/APN geliri kisi satirlarina girmez; modul ozet karolari ekip/moduller.py (2026-10-14).
Kapsam: admin ve TeamMngr tum ekibi, TeamMember yalniz kendini gorur. Ozet cumleleri kural tabanlidir (LLM yok).

Riskli utilizasyon (2026-10-14 kullanici istegi: "risk yukunu utilizasyonla birlestir, utilizasyona orantili formul"):
risk = olasilik x etki (ISO 31000 / NIST SP 800-30 risk matrisi, FMEA RPN ayni carpimsal yapidadir).
  1. Musteri riski   r_c = acik_c x etki_c ; acik_c = acik alarm + acik sikayet (olasilik: sorunun su an yasaniyor olmasi),
                       etki_c = utilizasyon skoru / 100 (musterinin agirligi); skorsuz musteride etki 1 (ihtiyatli: bilinmeyen etki dusuk sayilmaz).
  2. TAM risk puani  R = toplam r_c (cati + istirak).
  3. Risk orani      p = R / (R + E), E = YUKSEK_RISK (16): 0..1 arasi doygun oran, R = E iken %50; tek bir buyuk musteri orani 1'e tasimaz.
  4. Riskli utilizasyon = U x (1 + p), U = agirlik puani (0-100). Risk yoksa U'ya esit, en kotu durumda 2U; yani yuk utilizasyonla ORANTILI artar.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz import yonetici_mi
from app.db import mevcut_oturumlar
from app.dil import ingilizce, m
from app.ekip.moduller import modul_ozetleri
from app.kullanicilar import kullanici_kaydi, personel
from app.models import AppUser, CalendarDay, Customer, ProjectItem, Report, ScoringExclusion
from app.musteri.servis import rapor_bekleniyor_mu, rapor_birimi_mi
from app.ortak import rapor_uyum_aylari, tr_kucuk
from app.session import Principal
from app.skor.servis import tam_skor_ozeti
from app.takvim.kurum_takvimi import kurum_gunu
from app.takvim.servis import DURUMLAR

KRITIK_UYUM = 50  # % alti kritik (uretim)
ORTA_UYUM = 80
YUKSEK_RISK = 16  # acik alarm + sikayet (uretim)
ONEMLI_ONCELIK = ("yuksek", "kritik")
YEREL_SAAT = ZoneInfo("Europe/Istanbul")


def _bugun() -> date:
    """Takvim gunu yerel gundur (sunucu Turkiye saatinde); UTC kullanilirsa 00-03 arasi dunu gosterir."""
    return datetime.now(YEREL_SAAT).date()


def _uyeler(db: Session, user: Principal) -> list[AppUser]:
    if not yonetici_mi(user):
        return [kullanici_kaydi(db, user)]
    return personel(db)


def _takvim(uyeler: list[AppUser], bugun: date) -> dict[str, tuple[str | None, int, int]]:
    """Kullanici adi -> (bugunku durum, bu yil online, bu yil yuz yuze). Dosyasi olmayan kisi yok sayilir (okuma dosya olusturmaz)."""
    bas, son = date(bugun.year, 1, 1), date(bugun.year, 12, 31)
    sonuc: dict[str, tuple[str | None, int, int]] = {}
    for ad, k in mevcut_oturumlar([u.username for u in uyeler]):
        gunler = list(k.scalars(select(CalendarDay).where(CalendarDay.day >= bas, CalendarDay.day <= son)))
        durum = next((g.status for g in gunler if g.day == bugun), None) or (kurum_gunu(bugun) or (None,))[0]  # kayit yoksa kurum tatili
        sonuc[ad] = (durum, sum(g.online_count for g in gunler), sum(g.face_count for g in gunler))
    return sonuc


DURUM_EN = {
    "calisiyor": "working",
    "yillik_izin": "on annual leave",
    "sirket_izni": "on company leave",
    "raporlu": "on sick leave",
    "arife_tatili": "on half-day holiday",
    "resmi_tatil": "on public holiday",
    "hafta_sonu": "on weekend",
}


def risk_puani(musteriler: list[Customer]) -> float:
    """Utilizasyon agirlikli acik kayit (olasilik x etki); bkz. modul aciklamasi."""
    return round(sum(((c.alarm_count or 0) + (c.complaint_count or 0)) * ((c.score / 100) if c.score else 1.0) for c in musteriler), 1)


def risk_orani(puan: float) -> float:
    return round(puan / (puan + YUKSEK_RISK), 3) if puan > 0 else 0.0


def riskli_utilizasyon(agirlik: float | None, oran: float) -> float | None:
    return None if agirlik is None else round(agirlik * (1 + oran), 1)


def _uyum_kelimesi(yuzde: int) -> str:
    if yuzde < KRITIK_UYUM:
        return m("kritik seviyede", "critical")
    return m("orta seviyede", "moderate") if yuzde < ORTA_UYUM else m("sağlıklı seviyede", "healthy")


def _sayi(deger: object) -> str:
    """Ondalik ayrac dile gore: TR virgul, EN nokta."""
    return str(deger) if ingilizce() else str(deger).replace(".", ",")


def kisi_cumlesi(s: dict) -> str:
    """Uretim _build_tam_personal_ai_summary (kural tabanli tek paragraf). Dil: istegin dili (app.dil)."""
    if s["bugun"]:
        parcalar = [m(f"{s['ad']}, bugün {tr_kucuk(s['bugun_ad'])}.", f"{s['ad']} is {DURUM_EN.get(s['bugun'], s['bugun'])} today.")]
    else:
        parcalar = [m(f"{s['ad']}: bugün için takvim kaydı yok.", f"{s['ad']}: no calendar entry for today.")]
    if s["musteri"]:
        if s["rapor_beklenen"]:
            parcalar.append(
                m(
                    f"{s['musteri']} müşteri portföyünü yönetiyor; takip edilen rapor dönemlerinde {s['rapor_atilan']}/{s['rapor_beklenen']} "
                    f"rapor gönderdi (%{s['uyum']} uyum, {_uyum_kelimesi(s['uyum'])}).",
                    f"Manages a portfolio of {s['musteri']} customers; sent {s['rapor_atilan']}/{s['rapor_beklenen']} reports in the "
                    f"tracked report periods ({s['uyum']}% compliance, {_uyum_kelimesi(s['uyum'])}).",
                )
            )
        else:
            parcalar.append(m(f"{s['musteri']} müşteri portföyünü yönetiyor.", f"Manages a portfolio of {s['musteri']} customers."))
    else:
        parcalar.append(m("Henüz sorumlu olduğu bir müşteri portföyü yok.", "No customer portfolio assigned yet."))
    acik = s["alarm"] + s["sikayet"] + s["talep"]
    if acik or s["kapanan"]:
        parcalar.append(
            m(
                f"Portföyünde {s['alarm']} açık alarm, {s['sikayet']} açık şikayet ve {s['talep']} açık talep var (toplam {acik}); "
                f"yıl içinde {s['kapanan']} kayıt kapatıldı.",
                f"The portfolio has {s['alarm']} open alarms, {s['sikayet']} open complaints and {s['talep']} open requests "
                f"(total {acik}); {s['kapanan']} records were closed this year.",
            )
        )
    if s["final_skor"] is not None:
        parcalar.append(
            m(f"Ortalama TAM Utilizasyon skoru {_sayi(s['final_skor'])}.", f"Average TAM Utilization score is {_sayi(s['final_skor'])}.")
        )
    if s.get("riskli_utilizasyon") is not None and s.get("risk_orani"):
        yuzde = round(s["risk_orani"] * 100)
        parcalar.append(
            m(
                f"Risk ağırlıklı utilizasyonu {_sayi(s['riskli_utilizasyon'])} (risk oranı %{yuzde}).",
                f"Risk-weighted utilization is {_sayi(s['riskli_utilizasyon'])} (risk ratio {yuzde}%).",
            )
        )
    if s["online"] or s["yuzyuze"]:
        parcalar.append(
            m(
                f"Bu yıl {s['online']} online, {s['yuzyuze']} yüz yüze toplantı/etkinlik gerçekleştirdi.",
                f"Held {s['online']} online and {s['yuzyuze']} face-to-face meetings/events this year.",
            )
        )
    if s["proje_acik"] or s["proje_kapanan"]:
        parcalar.append(
            m(
                f"{s['proje_acik'] + s['proje_kapanan']} proje kaydı var ({s['proje_acik']} devam ediyor, {s['proje_kapanan']} kapandı).",
                f"{s['proje_acik'] + s['proje_kapanan']} project records ({s['proje_acik']} ongoing, {s['proje_kapanan']} closed).",
            )
        )
    if s["onemli_isler"]:
        n = len(s["onemli_isler"])
        parcalar.append(m(f"{n} yüksek/kritik öncelikli projeyi takip ediyor.", f"Tracks {n} high/critical priority projects."))
    return " ".join(parcalar)


def ekip_cumlesi(satirlar: list[dict], risk_var: bool) -> str | None:
    """Uretim _build_team_ai_summary."""
    if not satirlar:
        return None
    kritik = sum(1 for s in satirlar if s["rapor_beklenen"] and s["uyum"] < KRITIK_UYUM)
    riskli = sum(1 for s in satirlar if risk_var and s["risk"] >= YUKSEK_RISK)
    parcalar = []
    if kritik:
        parcalar.append(
            m(
                f"{kritik} TAM'ın rapor uyumu kritik seviyede (%{KRITIK_UYUM} altı)",
                f"{kritik} TAMs have critical report compliance (below {KRITIK_UYUM}%)",
            )
        )
    if riskli:
        parcalar.append(m(f"{riskli} TAM yüksek risk yükü taşıyor", f"{riskli} TAMs carry a high risk load"))
    if parcalar:
        return " · ".join(parcalar) + "."
    if not risk_var:
        return m(
            "Ekip genelinde rapor uyumu sağlıklı seviyede; risk yükü için ReportDB verisi henüz alınmadı.",
            "Team-wide report compliance is healthy; ReportDB data for risk load has not been received yet.",
        )
    return m(
        "Ekip genelinde rapor uyumu ve risk göstergeleri şu an sağlıklı seviyede.",
        "Team-wide report compliance and risk indicators are currently healthy.",
    )


def ozet(db: Session, user: Principal) -> dict:
    bugun = _bugun()
    # Yalniz tamamlanmis rapor donemleri beklenir; Ekim 2026 oncesi sayilmaz (ortak.RAPOR_UYUM_BASLANGICI, 2026-11-03).
    rapor_aylari = rapor_uyum_aylari(bugun)
    uyeler = _uyeler(db, user)
    kimlikler = {u.id for u in uyeler}
    musteriler = list(db.scalars(select(Customer)))
    # Alarm/sikayet sayisi hic yoksa 0 'saglikli' degil, veri yoktur (uretim _risk_verisi_var).
    risk_var = any(c.alarm_count or c.complaint_count or c.request_count for c in musteriler)
    tum = {c.id: c for c in musteriler}
    atilan: set[tuple[int, int]] = set()
    raporlar = select(Report.customer_id, Report.report_month).where(
        Report.report_year == bugun.year,
        Report.report_month.in_(rapor_aylari),
    )
    for kimlik, ay in db.execute(raporlar).unique():
        c = tum.get(kimlik)
        if c is not None:
            atilan.add((c.id if rapor_birimi_mi(c) else (c.parent_id or c.id), ay))
    sahip: dict[int, list[Customer]] = {}
    for c in musteriler:
        if c.owner_id in kimlikler:
            sahip.setdefault(c.owner_id, []).append(c)
    disi = set(db.scalars(select(ScoringExclusion.user_id)))
    projeler: dict[int, list[ProjectItem]] = {}
    for p in db.scalars(select(ProjectItem).where(ProjectItem.owner_id.in_(kimlikler))):
        projeler.setdefault(p.owner_id, []).append(p)
    takvim = _takvim(uyeler, bugun)

    satirlar = []
    for u in uyeler:
        hepsi = sahip.get(u.id, [])
        catilar = [c for c in hepsi if c.parent_id is None]
        birimler = [c.id for c in hepsi if rapor_bekleniyor_mu(c)]
        gonderilen = sum(1 for b in birimler for ay in rapor_aylari if (b, ay) in atilan)
        beklenen = len(birimler) * len(rapor_aylari)
        skor = tam_skor_ozeti([] if u.id in disi else catilar)
        durum, online, yuzyuze = takvim.get(u.username, (None, 0, 0))
        pler = projeler.get(u.id, [])
        acik_p = [p for p in pler if p.status != "kapandi"]
        alarm = sum(c.alarm_count or 0 for c in hepsi)
        sikayet = sum(c.complaint_count or 0 for c in hepsi)
        s = {
            "id": u.id,
            "ad": u.display_name or u.username,
            "rol": u.role,
            "bugun": durum,
            "bugun_ad": DURUMLAR.get(durum, durum) if durum else "",
            "musteri": len(catilar),
            "rapor_atilan": gonderilen,
            "rapor_beklenen": beklenen,
            "uyum": round(gonderilen * 100 / beklenen) if beklenen else 0,
            "alarm": alarm,
            "sikayet": sikayet,
            "talep": sum(c.request_count or 0 for c in hepsi),
            "kapanan": sum((c.alarm_closed_count or 0) + (c.complaint_closed_count or 0) + (c.request_closed_count or 0) for c in hepsi),
            "risk": alarm + sikayet,
            "risk_puani": risk_puani(hepsi),
            "puanlama_disi": u.id in disi,
            "final_skor": skor["final_skor"],
            "toplam_puan": skor["toplam_puan"],
            "agirlik_puani": skor["agirlik_puani"],
            "online": online,
            "yuzyuze": yuzyuze,
            "proje_acik": len(acik_p),
            "proje_kapanan": len(pler) - len(acik_p),
            "onemli_isler": [
                {"id": p.id, "baslik": p.title, "oncelik": p.priority, "hedef": p.target_date.isoformat() if p.target_date else None}
                for p in sorted(acik_p, key=lambda p: (p.priority != "kritik", p.target_date or date.max))
                if p.priority in ONEMLI_ONCELIK
            ],
        }
        s["risk_orani"] = risk_orani(s["risk_puani"]) if risk_var else 0.0
        s["riskli_utilizasyon"] = riskli_utilizasyon(s["agirlik_puani"], s["risk_orani"])
        s["cumle"] = kisi_cumlesi(s)
        satirlar.append(s)
    # Uretim: agirlik puanina gore buyukten kucuge (Veri Yonlendirici > Personel Agirlik ile ayni deger); skoru olmayan en altta.
    satirlar.sort(key=lambda s: tr_kucuk(s["ad"]))
    satirlar.sort(key=lambda s: s["agirlik_puani"] if s["agirlik_puani"] is not None else -1, reverse=True)
    return {
        "tarih": bugun.isoformat(),
        "kapsam": "ekip" if yonetici_mi(user) else "kendi",
        "risk_var": risk_var,
        "cumle": ekip_cumlesi(satirlar, risk_var),
        "sayilar": {
            "kisi": len(satirlar),
            "kritik_uyum": sum(1 for s in satirlar if s["rapor_beklenen"] and s["uyum"] < KRITIK_UYUM),
            "yuksek_risk": sum(1 for s in satirlar if risk_var and s["risk"] >= YUKSEK_RISK),
            "acik_proje": sum(s["proje_acik"] for s in satirlar),
        },
        "satirlar": satirlar,
        # menudeki her modulun yillik ozet kutusu (ekip/moduller.py)
        "moduller": modul_ozetleri(db, user, satirlar, bugun.year, rapor_aylari),
        "esikler": {"kritik_uyum": KRITIK_UYUM, "yuksek_risk": YUKSEK_RISK},  # yuksek_risk ayni zamanda risk oraninin yari doygunluk sabiti (E)
    }
