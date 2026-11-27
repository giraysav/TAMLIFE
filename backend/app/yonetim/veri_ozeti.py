# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Yonetim > Veri Ozeti (2026-11-21 kullanici: "ReportDB, OneDesk, ONENT DB'lerden gelen verileri konsolide edecegimiz sade, kullanimi
ve anlasilmasi kolay, yonetimi kolay bir gorunum").

Tek ekran: ust satirda uc kaynagin durumu (son basarili cekim, hata, hacim) + gunluk utilizasyon turunun son calismasi; altta musteri
basina birlesik satir (alarm / sikayet / talep = son 12 ayda KAPANAN; aktif CI / lokasyon; final skor ve son guncelleme). Yalniz admin
(Yonetim konsolu: kaynak adlari burada gorunebilir). "Simdi calistir" gunluk turu ayri surecte baslatir (06:00 gorevinin aynisi).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AppSetting, AppUser, Customer, OnedeskRecord, ScoreHistory
from app.ortak import UygulamaHatasi, iso, simdi
from app.skor import gunluk

CALISIYOR_DK = 20
BASLAT_ANAHTARI = "utilizasyon.gunluk_baslatildi"


def _son_temip(db: Session) -> dict[str, Any]:
    """TEMIP alarm kayit turu (30 dk'lik isci; reportdb.durum_yaz)."""
    from app.tampon import reportdb

    d = reportdb.durum_oku(db)
    acik = db.scalar(select(func.count()).select_from(OnedeskRecord).where(OnedeskRecord.source == "temip", OnedeskRecord.status == "open")) or 0
    surum = db.get(AppSetting, "temip.surum")  # temip_kayit.SURUM_AYARI: durum kaydi oncesi turlar icin
    son = d.get("son_basari") or (surum.value.get("an") if surum is not None and isinstance(surum.value, dict) else None)
    return {"son_basari": son, "son_hata": reportdb.son_hata(d), "acik_alarm": acik, "siklik": "30 dk"}


def _loe(db: Session) -> dict[str, Any]:
    """4. kart: aylik rapor LOE grafikleri (ReportDB devre CMDB kopyasi + secili devrelerin saatlik olcumleri; app.rapor.loe).
    ORA-00942 = tablo yetkisi henuz verilmedi: hata degil 'Yetki bekleniyor' gosterilir."""
    from app.models import ReportCircuit, ReportCircuitData, ReportCmdb
    from app.rapor import loe

    d = loe.durum_oku(db)
    cmdb, olcum = d.get("cmdb") or {}, d.get("olcum") or {}
    basarilar = [z for z in (cmdb.get("son_basari"), olcum.get("son_basari")) if z]
    hata = cmdb.get("hata") or olcum.get("hata") or ""
    yetki = "ORA-00942" in hata or "ORA-01031" in hata
    if yetki:
        hata = "Okuma yetkisi henüz verilmedi (" + hata.split(":")[0] + "). Yetki gelince ilk turda kendiliğinden dolar."

    def say(m: Any) -> int:
        return db.scalar(select(func.count()).select_from(m)) or 0

    return {"anahtar": "loe", "ad": "ReportDB", "icerik": "LOE grafikleri · erişilebilirlik, gecikme, jitter, kayıp",
            "siklik": "Liste günde bir · ölçüm 30 dk", "son_basari": max(basarilar) if basarilar else None,
            "hata": hata, "yetki_bekleniyor": yetki,
            "hacim": [["Devre listesi", say(ReportCmdb)], ["Grafiği seçili devre", say(ReportCircuit)],
                      ["Saklanan aylık veri", say(ReportCircuitData)]]}  # fmt: skip


def _onedesk_kayit(db: Session) -> dict[str, Any]:
    """OneDesk sikayet / talep kayit aktarimi (app.onedesk.canli; 30 dk'lik isci turu)."""
    from app.onedesk import canli

    d = canli.durum_oku(db)
    kaynak = OnedeskRecord.source == canli.KAYNAK_ADI
    acik = db.scalar(select(func.count()).select_from(OnedeskRecord).where(kaynak, OnedeskRecord.status == "open")) or 0
    toplam = db.scalar(select(func.count()).select_from(OnedeskRecord).where(kaynak)) or 0
    hata = d.get("hata", "") if d.get("son_deneme", "") >= d.get("son_basari", "") else ""
    return {"son_basari": d.get("son_basari"), "hata": hata, "acik": acik, "toplam": toplam}


def kaynaklar(db: Session) -> list[dict[str, Any]]:
    from app.musteri import envanter

    d = gunluk.durum_oku(db)
    k = d.get("kaynaklar") or {}
    hacim, env = k.get("kayit") or {}, envanter.durum_oku(db)
    temip = _son_temip(db)
    kayit = _onedesk_kayit(db)
    return [
        {"anahtar": "reportdb", "ad": "ReportDB", "icerik": "Alarm kayıtları (TEMIP)", "siklik": temip["siklik"],
         "son_basari": temip["son_basari"], "hata": temip["son_hata"],
         "hacim": [["Kayıt hacmi: alarm (bu yıl kapanan + açık)", hacim.get("alarm")], ["Şu an açık alarm", temip["acik_alarm"]]]},
        {"anahtar": "onedesk", "ad": "OneDesk", "icerik": "Şikayet ve talep kayıtları", "siklik": "Kayıtlar 30 dk · skor 06:00",
         "son_basari": kayit["son_basari"], "hata": kayit["hata"],
         "hacim": [["Kayıt hacmi: şikayet (bu yıl kapanan + açık)", hacim.get("sikayet")], ["Kayıt hacmi: talep (bu yıl kapanan + açık)", hacim.get("talep")],
                   ["Panelde açık şikayet / talep", kayit["acik"]], ["Panelde kayıt (01.01'den)", kayit["toplam"]]]},
        {"anahtar": "onent", "ad": "ONENT", "icerik": "Müşteri envanteri (CMDB)", "siklik": "4 saatte bir",
         "son_basari": env.get("son_basari"), "hata": env.get("hata", ""),
         "hacim": [["Envanterdeki CI", env.get("satir")], ["Panel müşterilerinin aktif CI'ı", (k.get("onent") or {}).get("ci")]]},
        _loe(db),
    ]  # fmt: skip


def ozet(db: Session) -> dict[str, Any]:
    o = gunluk.ozetler(db)
    musteriler = list(db.scalars(select(Customer)))
    adlar = {u.id: u.display_name or u.username for u in db.scalars(select(AppUser))}
    catilar = {c.id: c for c in musteriler if c.parent_id is None}
    istirak: dict[int, list[Customer]] = {}
    for c in musteriler:
        if c.parent_id is not None:
            istirak.setdefault(c.parent_id, []).append(c)
    son = select(func.max(ScoreHistory.id)).group_by(ScoreHistory.customer_id)
    skor_zaman = {h.customer_id: (h.at, h.source) for h in db.scalars(select(ScoreHistory).where(ScoreHistory.id.in_(son)))}
    satirlar = []
    for c in sorted(catilar.values(), key=lambda x: (x.name or "").lower()):
        grup = istirak.get(c.id, [])
        z = skor_zaman.get(c.id)
        satirlar.append({
            "id": c.id, "ad": c.name, "tam": adlar.get(c.owner_id, "") if c.owner_id else "", "musteri_no": c.customer_no or "",
            "istirak": len(grup), "segment": c.segment or "",
            **{alan: gunluk.grup_toplami(o, c, grup, alan) for alan in ("alarm", "sikayet", "talep", "ci", "lokasyon")},
            "skor": round(c.score, 1) if c.score else None, "skor_zaman": iso(z[0]) if z else None, "skor_kaynak": z[1] if z else None,
        })  # fmt: skip
    d = gunluk.durum_oku(db)
    return {
        "tur": {**d, "calisiyor": calisiyor_mu(db)},
        "kaynaklar": kaynaklar(db),
        "musteriler": satirlar,
        "toplam": {alan: sum(s[alan] or 0 for s in satirlar) for alan in ("alarm", "sikayet", "talep", "ci", "lokasyon")},
    }


def calisiyor_mu(db: Session) -> bool:
    from app.models import AppSetting

    k = db.get(AppSetting, BASLAT_ANAHTARI)
    if k is None or not isinstance(k.value, dict):
        return False
    try:
        bas = datetime.fromisoformat(str(k.value.get("zaman")))
    except ValueError:
        return False
    son = gunluk.durum_oku(db).get("zaman")
    bitti = son is not None and datetime.fromisoformat(str(son)) >= bas
    return not bitti and simdi() - bas < timedelta(minutes=CALISIYOR_DK)


def baslat(db: Session, kisi: str) -> dict[str, Any]:
    from app.models import AppSetting
    from app.tampon import katalog

    if calisiyor_mu(db):
        raise UygulamaHatasi(409, "Günlük tur zaten çalışıyor.")
    an = simdi()
    k = db.get(AppSetting, BASLAT_ANAHTARI)
    deger = {"zaman": an.isoformat(), "kisi": kisi[:120]}
    if k is None:
        db.add(AppSetting(key=BASLAT_ANAHTARI, value=deger, updated_by=kisi[:120], updated_at=an))
    else:
        k.value, k.updated_by, k.updated_at = deger, kisi[:120], an
    db.commit()
    backend = Path(__file__).resolve().parents[2]
    gunluk_dizin = backend / "var" / "logs"
    gunluk_dizin.mkdir(parents=True, exist_ok=True)
    katalog._ayri_baslat([sys.executable, "-m", "app.isci", "utilizasyon"], backend, gunluk_dizin / "isci_utilizasyon.log")
    return {"baslatildi": iso(an)}
