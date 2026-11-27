"""DEMO ornegi icin SAHTE veri uretir (gercek panel verisine DOKUNMAZ, ondan KOPYALAMAZ).

Kullanim (demo.ps1 cagirir; elle de calisir):
  .venv\\Scripts\\python.exe -I kurulum\\demo_tohum.py
Cevre: TAMLIFE_DATABASE_URL = demo DB (sqlite), TAMLIFE_KULLANICI_DB_DIZINI = demo kullanici dizini, TAMLIFE_ENV_DOSYASI = bos/demo .env.
Guvenlik: DB yolu 'demo' icermiyorsa betik DURUR (gercek dev.db'yi ezmesin).
"""

from __future__ import annotations

import os
import random
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, r"E:\TAMLIFE\backend")

url = os.environ.get("TAMLIFE_DATABASE_URL", "")
if "demo" not in url.lower():
    sys.exit("DURDU: TAMLIFE_DATABASE_URL demo veritabanini gostermiyor (gercek veriyi korumak icin).")

from sqlalchemy import select  # noqa: E402

from app.db import kullanici_oturumu, oturum  # noqa: E402
from app.gelir_uretim.models import RevenueBenefit, RevenueBenefitPerson  # noqa: E402
from app.models import (  # noqa: E402
    AppUser, Customer, CustomerTeam, Demand, DemandLog, OnedeskRecord, ProjectAction, ProjectItem, Report, ReportDispatch,
    ReportRecipient, SmsRevenue, ApnRevenue, CalendarDay,
)

rnd = random.Random(2026)
UTC = timezone.utc
simdi = datetime.now(UTC)


def gun(n: int) -> datetime:
    return simdi - timedelta(days=n, hours=rnd.randint(0, 9))


with oturum() as db:
    if db.scalar(select(AppUser.id).limit(1)):
        sys.exit("Demo DB zaten dolu; once demo.db dosyasini silin.")

    # --- kullanicilar (kisi adi YOK: rol/gorev adlari) ---
    kisiler = [
        ("misafir", "Misafir (Demo)", "TeamMngr"),
        ("demo.yonetici", "Demo Yönetici", "TeamMngr"),
        ("demo.tam1", "Demo TAM 1", "TeamMember"),
        ("demo.tam2", "Demo TAM 2", "TeamMember"),
        ("demo.tam3", "Demo TAM 3", "TeamMember"),
        ("demo.tam4", "Demo TAM 4", "TeamMember"),
    ]
    U: dict[str, AppUser] = {}
    for kadi, ad, rol in kisiler:
        u = AppUser(username=kadi, display_name=ad, role=rol, is_admin=False, active=True, is_ad_user=False,
                    first_name=ad.split()[0], last_name=" ".join(ad.split()[1:]), title="TAM", department="Kurumsal Müşteriler",
                    email=f"{kadi}@ornek.invalid", last_login_at=gun(rnd.randint(0, 3)))
        db.add(u)
        U[kadi] = u
    db.flush()
    sahipler = [U["demo.tam1"], U["demo.tam2"], U["demo.tam3"], U["demo.tam4"], U["misafir"]]

    # --- musteriler: cati + istirakler ---
    segmentler = ["Kurumsal", "KOBİ", "Kamu", "Finans", "Sağlık", "Enerji"]
    sektorler = ["Bankacılık", "Perakende", "Üretim", "Telekom", "Sağlık", "Enerji", "Kamu"]
    musteriler: list[Customer] = []
    for n in range(1, 9):
        c = Customer(external_key=f"DEMO-{n:03d}", name=f"Örnek Müşteri {n} A.Ş.", segment=segmentler[n % len(segmentler)], status="aktif",
                     owner_id=sahipler[n % len(sahipler)].id, modul="musteri", score=round(rnd.uniform(55, 95), 1),
                     customer_no=f"9{n:05d}", ncst=f"NCST{n:04d}", sector=sektorler[n % len(sektorler)],
                     inventory_count=rnd.randint(10, 90), ft_volume=f"{rnd.randint(40, 900) * 1000:,} ₺".replace(",", "."),
                     tam_ft=f"{rnd.randint(5, 80) * 1000:,} ₺".replace(",", "."), report_count=rnd.randint(0, 6))
        db.add(c)
        musteriler.append(c)
    db.flush()
    for n, parent in enumerate(musteriler[:4], start=1):
        for k in (1, 2):
            c = Customer(external_key=f"DEMO-{n:03d}-I{k}", name=f"Örnek Müşteri {n} İştirak {k}", segment=parent.segment, status="aktif",
                         owner_id=parent.owner_id, parent_id=parent.id, modul="musteri", customer_no=f"8{n}{k:04d}", ncst=f"NCST{n}{k:03d}",
                         sector=parent.sector, inventory_count=rnd.randint(3, 25), ft_volume="0,00 ₺", tam_ft="0,00 ₺")
            db.add(c)
            musteriler.append(c)
    db.flush()
    for c in musteriler:
        db.add(CustomerTeam(customer_id=c.id, sales_manager="Satış Yöneticisi (örnek)", presales_manager="Ön Satış (örnek)",
                            tac_name="TAC Ekibi (örnek)", tac_email="tac@ornek.invalid", sol_kmt_name="Çözüm Mimarı (örnek)",
                            mobil_kmt_name="Mobil Mimar (örnek)"))
        db.add(ReportRecipient(customer_id=c.id, to_addrs="musteri@ornek.invalid", cc_addrs=""))

    # --- onedesk kayitlari ---
    kategoriler = ["Hat kesintisi", "Yavaşlık", "Konfigürasyon", "Donanım arızası", "Fatura sorusu", "Yeni servis talebi"]
    for _ in range(260):
        c = rnd.choice(musteriler)
        tur = rnd.choices(["alarm", "talep", "sikayet"], weights=[6, 3, 1])[0]
        ac = rnd.randint(2, 170)
        kapali = rnd.random() < 0.82
        db.add(OnedeskRecord(kind=tur, external_key=f"DEMO-OD-{rnd.randint(100000, 999999)}", customer_id=c.id, status="closed" if kapali else "open",
                             customer_label=c.name, location=f"Lokasyon {rnd.randint(1, 12)}", category=rnd.choice(kategoriler),
                             opened_at=gun(ac), closed_at=gun(max(ac - rnd.randint(0, 6), 0)) if kapali else None,
                             root_cause="Örnek kök neden açıklaması." if kapali and rnd.random() < 0.6 else "",
                             resolution="Örnek çözüm notu." if kapali else "", source="import", customer_no=c.customer_no or ""))

    # --- Erken Uyari senaryosu (2026-11-27, hackathon demosu): uc cati musteride bilinen oruntu; puan app.musteri.erken_uyari ile hesaplanir.
    def kayit(c: Customer, tur: str, gun_once: float, *, acik: bool = False, ci: str = "", kategori: str = "Hat kesintisi") -> None:
        an = simdi - timedelta(days=gun_once)
        db.add(OnedeskRecord(kind=tur, external_key=f"DEMO-EU-{rnd.randint(100000, 999999)}", customer_id=c.id, status="open" if acik else "closed",
                             customer_label=c.name, location=ci or f"Lokasyon {rnd.randint(1, 12)}", category=kategori, opened_at=an,
                             closed_at=None if acik else an + timedelta(hours=rnd.randint(1, 20)), source="import", customer_no=c.customer_no or ""))

    kritik, yuksek, izle = musteriler[0], musteriler[2], musteriler[4]
    for _ in range(18):  # onceki 8 hafta: sakin (14 gunde ~4-5 alarm)
        kayit(kritik, "alarm", rnd.uniform(16, 69))
    for _ in range(26):  # son 14 gun: ana hat surekli dusuyor
        kayit(kritik, "alarm", rnd.uniform(0.2, 13.5), ci="demo-ci-merkez-ana-hat")
    for _ in range(12):
        kayit(kritik, "alarm", rnd.uniform(0.2, 13.5))
    for _ in range(6):  # planli calisma: puana girmez
        kayit(kritik, "alarm", rnd.uniform(1, 10), kategori="PLANLI CALISMA ALARMI")
    for i in range(3):
        kayit(kritik, "sikayet", rnd.uniform(1, 12), acik=i == 0)
    kayit(kritik, "talep", 11, acik=True)
    for i in range(2):
        kayit(yuksek, "sikayet", rnd.uniform(2, 12), acik=i == 0)
    for _ in range(8):
        kayit(yuksek, "alarm", rnd.uniform(0.5, 13), ci="demo-ci-sube-yedek-hat")
    for _ in range(3):
        kayit(izle, "talep", rnd.uniform(9, 20), acik=True)
    db.flush()
    for c in musteriler:
        for tur, alan in (("alarm", "alarm_count"), ("talep", "request_count"), ("sikayet", "complaint_count")):
            kayitlar = db.scalars(select(OnedeskRecord).where(OnedeskRecord.customer_id == c.id, OnedeskRecord.kind == tur)).all()
            setattr(c, alan, len(kayitlar))
            setattr(c, alan.replace("_count", "_closed_count"), sum(1 for k in kayitlar if k.status == "closed"))

    # --- aylik rapor gonderimleri (son 3 ay) ---
    bugun = date.today()
    for ay_geri in (1, 2, 3):
        y, a = bugun.year, bugun.month - ay_geri
        while a <= 0:
            a += 12
            y -= 1
        for c in [m for m in musteriler if m.parent_id is None][: 8 - ay_geri]:
            r = Report(created_at=gun(ay_geri * 30), report_month=a, report_year=y, user_id=U["demo.tam1"].id, customer_id=c.id,
                       sun_success_text="Örnek başarı metni.", suggestions_text="Örnek öneri metni.", is_submitted=True)
            db.add(r)
            db.flush()
            db.add(ReportDispatch(customer_id=c.id, year=y, month=a, sender_id=U["demo.tam1"].id, sender="Demo TAM 1", at=gun(ay_geri * 30 - 2),
                                  subject=f"TAM Aylık Rapor - {c.name} - {a:02d}/{y}", report_id=r.id, status="sent", source="panel"))

    # --- projeler ---
    kat = ["proje", "calisma", "ddos", "dc_tasima", "topoloji"]
    for i in range(1, 9):
        p = ProjectItem(owner_id=sahipler[i % len(sahipler)].id, category=kat[i % 5], title=f"Örnek Proje {i}", description="Örnek açıklama.",
                        status=rnd.choice(["acik", "devam", "beklemede", "kapandi"]), priority=rnd.choice(["dusuk", "orta", "yuksek"]),
                        start_date=bugun - timedelta(days=rnd.randint(20, 120)), target_date=bugun + timedelta(days=rnd.randint(10, 90)),
                        created_by="Demo Yönetici", created_at=gun(60), updated_at=gun(5))
        db.add(p)
        db.flush()
        db.add(ProjectAction(item_id=p.id, text="Proje açıldı.", actor="Demo Yönetici", at=gun(60)))

    # --- gelistirme talepleri ---
    for i, (baslik, durum) in enumerate([("Rapor ekine yeni alan", "gelistiriliyor"), ("Takvim görünümü iyileştirme", "planlandi"),
                                          ("Alarm filtresi", "tamamlandi"), ("Müşteri arama hızlandırma", "yeni"), ("Dışa aktarım seçeneği", "yeni")], start=1):
        d = Demand(title=baslik, kind=rnd.choice(["ozellik", "iyilestirme"]), priority=rnd.choice(["dusuk", "orta", "yuksek"]), module="musteri",
                   current_state="Örnek mevcut durum.", expected_state="Örnek beklenen durum.", opened_by_id=U["demo.tam2"].id, opened_at=gun(40 - i * 5),
                   status=durum, assignee_id=U["demo.yonetici"].id, updated_at=gun(3))
        db.add(d)
        db.flush()
        db.add(DemandLog(demand_id=d.id, field="olusturma", old_value="", new_value=baslik, actor_id=U["demo.tam2"].id, at=gun(40 - i * 5)))

    # --- gelir faydasi ---
    for i, (baslik, tur, tutar) in enumerate([("Örnek iş A", "gelir", 480000), ("Örnek iş B", "tasarruf", 150000), ("Örnek iş C", "verimlilik", None)], start=1):
        r = RevenueBenefit(kind="proje", benefit_type=tur, title=baslik, status="devam", status_note="Örnek güncel durum.", description="Örnek açıklama.",
                           customers=musteriler[i].name, revenue_amount=tutar, revenue_period="yil", year_revenue=tutar,
                           hours_per_month=12 if tur == "verimlilik" else None, created_by="Demo Yönetici", created_at=gun(50),
                           updated_by="Demo Yönetici", updated_at=gun(4), approval="onayli")
        db.add(r)
        db.flush()
        db.add(RevenueBenefitPerson(item_id=r.id, user_id=U["demo.tam1"].id))
    db.commit()

# --- kisiye ozel dosya: misafir (takvim, SMS, APN) ---
with kullanici_oturumu("misafir") as k:
    for n in range(1, 29):
        g = date.today() - timedelta(days=28 - n)
        if g.weekday() < 5:
            k.add(CalendarDay(day=g, status="calisiyor", online_count=rnd.randint(0, 4), face_count=rnd.randint(0, 2),
                              work_notes="Örnek çalışma notu." if rnd.random() < 0.4 else None))
    for ay_geri in range(0, 4):
        y, a = date.today().year, date.today().month - ay_geri
        if a <= 0:
            a, y = a + 12, y - 1
        for c in (1, 2, 3):
            k.add(SmsRevenue(tam_name="Misafir (Demo)", customer_name=f"Örnek Müşteri {c} A.Ş.", amount=rnd.randint(8, 40) * 1000, project="Örnek proje",
                             year=y, month=a, created_by="misafir", created_at=simdi))
            k.add(ApnRevenue(tam_name="Misafir (Demo)", customer_name=f"Örnek Müşteri {c} A.Ş.", amount=rnd.randint(5, 25) * 1000, installation_pct=rnd.choice([0, 50, 100]),
                             apn_name=f"ornek-apn-{c}", year=y, month=a, created_by="misafir", created_at=simdi))
    k.commit()
print("Demo verisi hazir.")
