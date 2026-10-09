"""Gelistirme ortami ORNEK VERISI (uydurma): python -m app.ornek_veri [--temizle | --yenile]

Yeni ekranlari (Musteri, Onedesk, ICT SMS, APN, TAM Takvim) bos veritabaninda gorebilmek icindir.
- Yalniz TAMLIFE_ENV=dev iken calisir; uretim verisi kopyalanmaz, her sey tohumla (deterministik) uretilir.
- Takvim ve gelir satirlari ilgili ornek kisinin kendi DB dosyasina yazilir.
- Her satir isaretlidir: musteri external_key 'ORNEK-*', kullanici 'ornek.*', Onedesk source='ornek', gelir/calisma created_by='ornek'.
- --temizle yalniz bu isaretli satirlari siler; baska hicbir kayda dokunmaz.
"""

from __future__ import annotations

import os
import random
import sys
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import kullanici_oturumu, mevcut_oturumlar, oturum
from app.models import ApnRevenue, ApnWork, AppUser, CalendarDay, Customer, CustomerTeam, OnedeskRecord, Presentation, SmsRevenue
from app.onedesk.ice_al import sayaclari_yenile

TOHUM = 20261007
ISARET = "ornek"
KISILER = ("Elif Kaya", "Mert Demir", "Zeynep Arslan", "Can Öztürk", "Selin Aydın", "Burak Şahin")
MUSTERILER = (
    ("Anadolu Lojistik A.Ş.", "MA", "Lojistik"),
    ("Marmara Gıda Sanayi ve Ticaret A.Ş.", "PA", "Gıda"),
    ("Ege Tekstil Holding", "MA", "Tekstil"),
    ("Karadeniz Enerji Üretim A.Ş.", "PA", "Enerji"),
    ("Akdeniz Turizm İşletmeleri", "SA", "Turizm"),
    ("Başkent Sağlık Hizmetleri A.Ş.", "MA", "Sağlık"),
    ("Trakya Otomotiv Yan Sanayi", "SA", "Otomotiv"),
    ("İç Anadolu Madencilik A.Ş.", "PA", "Madencilik"),
    ("Güneydoğu Perakende Grubu", "WHOLESALE", "Perakende"),
    ("Boğaz Finansal Hizmetler A.Ş.", "PA", "Finans"),
)
ISTIRAKLER = (
    (0, "Anadolu Lojistik Depolama A.Ş."),
    (0, "Anadolu Lojistik Filo Hizmetleri"),
    (1, "Marmara Gıda Dağıtım Ltd."),
    (2, "Ege Tekstil Boyahane A.Ş."),
    (3, "Karadeniz Enerji Dağıtım A.Ş."),
)
LOKASYONLAR = (
    "İstanbul Gebze Depo", "Ankara OSB Tesis", "İzmir Liman Ofisi", "Bursa Fabrika", "Antalya Merkez Otel", "Kocaeli Rafineri Sahası",
    "Konya Dağıtım Merkezi", "Samsun Liman", "Adana Üretim Tesisi", "Eskişehir Şube", "Trabzon Bölge Müdürlüğü", "Gaziantep Depo",
)
KATEGORILER = ("Hat kesintisi", "Yüksek CPU", "Port hata sayacı", "Enerji kesintisi", "Paket kaybı", "Yazılım hatası", "Konfigürasyon değişikliği", "Sıcaklık alarmı", "Bant genişliği", "Yeni hat")
# (kok sebep sablonu, agirlik): ortak noktalar belirgin cikmasi icin birkac tekrar eden sebep
KOK_SEBEPLER = (
    ("Fiber kablo kesildi, saha ekibi ek noktasını değiştirdi (devre {n})", 9),
    ("Lokasyonda enerji kesintisi, UPS aküsü yetersiz kaldı (kabin {n})", 7),
    ("Port üzerinde CRC hataları, SFP modülü değiştirildi (port {n})", 6),
    ("Cihaz CPU kullanımı eşiği aştı, kapasite yetersiz (cihaz {n})", 5),
    ("Yanlış yönlendirme konfigürasyonu, değişiklik geri alındı (değişiklik {n})", 4),
    ("Cihaz yazılım sürümündeki hata nedeniyle yeniden başlama (sürüm 2.{n})", 4),
    ("Klima arızası nedeniyle kabin sıcaklığı yükseldi (oda {n})", 3),
    ("Müşteri tarafı kaynaklı kesinti, lokasyon yetkilisi bilgilendirildi", 3),
)
SMS_PROJELERI = ("Kampanya SMS Platformu", "OTP Doğrulama Hizmeti", "Toplu Bilgilendirme SMS", "Randevu Hatırlatma", "Filo Takip Bildirimleri", "Sipariş Durum Mesajları")
APN_ADLARI = ("lojistik.m2m", "filo.apn.kurum", "enerji.scada", "saha.terminal", "pos.guvenli", "kamera.altyapi")
TOPLANTI_KONULARI = ("APN yedekleme topolojisi", "Özel APN kapasite artırımı", "Saha cihazı geçiş planı", "Güvenlik duvarı kuralları", "Yeni lokasyon APN kurulumu", "Raporlama ihtiyaçları")


def _gun_ekle(rng: random.Random, bas: date, bugun: date) -> date:
    return bas + timedelta(days=rng.randint(0, max((bugun - bas).days, 0)))


def tohumla(db: Session) -> dict[str, int]:
    rng = random.Random(TOHUM)
    simdi = datetime.now(UTC)
    bugun = simdi.date()
    yil_basi = date(bugun.year, 1, 1)

    kisiler = []
    for i, ad in enumerate(KISILER, start=1):
        k = AppUser(username=f"{ISARET}.tam{i}", display_name=ad, role="TeamMngr" if i == 1 else "TeamMember", is_admin=False, last_login_at=simdi - timedelta(days=rng.randint(0, 6)))
        db.add(k)
        kisiler.append(k)
    db.flush()

    catilar: list[Customer] = []
    for i, (ad, segment, sektor) in enumerate(MUSTERILER, start=1):
        c = Customer(
            external_key=f"ORNEK-{i:03d}", name=ad, segment=segment, status="active", owner_id=kisiler[(i - 1) % len(kisiler)].id, score=round(rng.uniform(58, 96), 1),
            customer_no=f"9{rng.randint(100000, 999999)}", sector=sektor, inventory_count=rng.randint(12, 240), separate_report=False,
        )
        db.add(c)
        catilar.append(c)
    db.flush()
    musteriler = list(catilar)
    for j, (ust, ad) in enumerate(ISTIRAKLER, start=1):
        c = Customer(external_key=f"ORNEK-I{j:02d}", name=ad, segment=catilar[ust].segment, status="active", owner_id=catilar[ust].owner_id, parent_id=catilar[ust].id, inventory_count=rng.randint(5, 60))
        db.add(c)
        musteriler.append(c)
    db.flush()
    for c in catilar[:6]:
        db.add(CustomerTeam(customer_id=c.id, sales_manager="Örnek Satış Yöneticisi", tac_name="Örnek TAC", tac_email="tac@ornek.invalid", tac_gsm="0 500 000 00 00"))

    # --- Onedesk kayitlari -------------------------------------------------------------------------
    agirlik = [max(1, 12 - 2 * i) for i in range(len(musteriler))]  # ilk musteriler cok kayit uretir (top10 belirgin)
    yerler = {c.id: rng.sample(LOKASYONLAR, k=rng.randint(3, 5)) for c in musteriler}
    sebep_havuzu = [s for s, a in KOK_SEBEPLER for _ in range(a)]
    kayit_adedi = 0
    for n in range(1, 481):
        c = rng.choices(musteriler, weights=agirlik)[0]
        tur = rng.choices(("alarm", "talep", "sikayet"), weights=(60, 25, 15))[0]
        acik = rng.random() < 0.2
        acilis = datetime.combine(_gun_ekle(rng, yil_basi if not acik else max(yil_basi, bugun - timedelta(days=75)), bugun), datetime.min.time(), tzinfo=UTC) + timedelta(hours=rng.randint(0, 23))
        kapanis = None if acik else min(simdi, acilis + timedelta(hours=rng.randint(1, 240)))
        kok = rng.choice(sebep_havuzu).format(n=rng.randint(1, 99)) if (not acik and tur != "talep") else ""
        db.add(
            OnedeskRecord(
                kind=tur, external_key=f"ORN-{n:05d}", customer_id=c.id, customer_label=c.name, status="open" if acik else "closed", location=rng.choice(yerler[c.id]),
                category=rng.choice(KATEGORILER), opened_at=min(acilis, simdi), closed_at=kapanis, root_cause=kok,
                resolution="Kalıcı çözüm için planlı çalışma yapıldı." if kok else "", source=ISARET,
            )
        )
        kayit_adedi += 1
    db.flush()
    sayaclari_yenile(db, {c.id for c in musteriler})

    # --- gelirler (TAM'in kendi dosyasina) ------------------------------------------------------------
    dosya: dict[str, list] = {k.username: [] for k in kisiler}
    for i in range(12):
        c = rng.choice(catilar)
        dosya[kisiler[i % len(kisiler)].username].append(
            SmsRevenue(
                tam_name=kisiler[i % len(kisiler)].display_name, customer_name=c.name, project=rng.choice(SMS_PROJELERI), amount=float(rng.randint(8, 250) * 1000), currency="TRY",
                year=bugun.year, month=rng.randint(1, bugun.month), created_by=ISARET, created_at=simdi,
            )
        )
    for i in range(10):
        c = rng.choice(catilar)
        talep = _gun_ekle(rng, bugun - timedelta(days=150), bugun - timedelta(days=10))
        teslim = talep + timedelta(days=rng.randint(7, 40)) if rng.random() < 0.7 else None
        teslim = teslim if teslim and teslim <= bugun else None
        dosya[kisiler[i % len(kisiler)].username].append(
            ApnRevenue(
                tam_name=kisiler[i % len(kisiler)].display_name, customer_name=c.name, amount=float(rng.randint(4, 90) * 1000), currency="TRY", apn_name=rng.choice(APN_ADLARI),
                request_date=talep, delivery_date=teslim, year=(teslim or talep).year, month=(teslim or talep).month, created_by=ISARET, created_at=simdi,
            )
        )
    for i in range(10):
        c = rng.choice(catilar)
        toplanti = _gun_ekle(rng, bugun - timedelta(days=60), bugun)
        dosya[kisiler[i % len(kisiler)].username].append(
            ApnWork(
                customer_name=c.name, meeting_subject=rng.choice(TOPLANTI_KONULARI), meeting_date=toplanti,
                planned_date=toplanti + timedelta(days=rng.randint(5, 45)) if rng.random() < 0.8 else None, apn_name=rng.choice(APN_ADLARI), created_by=ISARET, created_at=simdi,
            )
        )

    # --- takvim gunleri (gun kisi dosyasinda benzersiz: bellekte tutulur, oturum autoflush'a guvenilmez) ------------
    gun_adedi = 0
    for k in kisiler:
        gunler: dict[date, CalendarDay] = {}
        gun = yil_basi
        while gun <= bugun + timedelta(days=20):
            if gun.weekday() < 5 and rng.random() < 0.35:
                gunler[gun] = CalendarDay(day=gun, status="calisiyor", online_count=rng.randint(0, 3), face_count=rng.randint(0, 2))
            gun += timedelta(days=1)
        for durum, blok, adet in (("yillik_izin", 4, 2), ("sirket_izni", 1, 2), ("raporlu", 2, 1)):
            for _ in range(adet):
                bas = _gun_ekle(rng, yil_basi, bugun + timedelta(days=15))
                for d in range(blok):
                    g = bas + timedelta(days=d)
                    if g.weekday() >= 5:
                        continue
                    kayit = gunler.setdefault(g, CalendarDay(day=g))
                    kayit.status = durum
        dosya[k.username] += gunler.values()
        gun_adedi += len(gunler)
    db.commit()
    for ad, satirlar in dosya.items():
        with kullanici_oturumu(ad) as kd:
            kd.add_all(satirlar)
            kd.commit()
    return {"musteri": len(musteriler), "kisi": len(kisiler), "onedesk": kayit_adedi, "takvim_gunu": gun_adedi}


def temizle(db: Session) -> dict[str, int]:
    """Yalniz isaretli ornek satirlari siler."""
    sonuc: dict[str, int] = {}
    kisi_idleri = list(db.scalars(select(AppUser.id).where(AppUser.username.like(f"{ISARET}.%"))))
    musteri_idleri = list(db.scalars(select(Customer.id).where(Customer.external_key.like("ORNEK-%"))))
    sonuc["takvim_gunu"] = 0
    for _, kd in mevcut_oturumlar(list(db.scalars(select(AppUser.username).where(AppUser.id.in_(kisi_idleri or [-1]))))):
        sonuc["takvim_gunu"] += kd.execute(delete(CalendarDay)).rowcount
        for model in (SmsRevenue, ApnRevenue, ApnWork):
            kd.execute(delete(model).where(model.created_by == ISARET))
        kd.commit()
    sonuc["onedesk"] = db.execute(delete(OnedeskRecord).where(OnedeskRecord.source == ISARET)).rowcount
    db.execute(delete(Presentation).where(Presentation.sent_by.in_(KISILER)))
    db.execute(delete(CustomerTeam).where(CustomerTeam.customer_id.in_(musteri_idleri or [-1])))
    istirak = db.execute(delete(Customer).where(Customer.parent_id.in_(musteri_idleri or [-1]), Customer.external_key.like("ORNEK-%"))).rowcount  # once istirakler
    sonuc["musteri"] = istirak + db.execute(delete(Customer).where(Customer.external_key.like("ORNEK-%"))).rowcount
    sonuc["kisi"] = db.execute(delete(AppUser).where(AppUser.id.in_(kisi_idleri or [-1]))).rowcount
    db.commit()
    return sonuc


def var_mi(db: Session) -> bool:
    return db.scalar(select(Customer.id).where(Customer.external_key.like("ORNEK-%")).limit(1)) is not None


def main(argv: list[str]) -> int:
    if os.environ.get("TAMLIFE_ENV", "") != "dev":
        print("Reddedildi: ornek veri yalniz TAMLIFE_ENV=dev ile yuklenir.")
        return 2
    with oturum() as db:
        if "--temizle" in argv:
            print("Temizlendi:", temizle(db))
            return 0
        if var_mi(db):
            if "--yenile" not in argv:
                print("Ornek veri zaten var. Yenilemek icin --yenile, silmek icin --temizle.")
                return 1
            temizle(db)
        print("Yuklendi:", tohumla(db))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
