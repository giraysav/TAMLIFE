"""Eski panelden ve elle aktarimdan kalan gecmis veriyi panelden kaldirir (2026-10-15 kullanici istegi: "hicbir eski veri, gecmisten
gelen ya da tamponda bekleyen veri panelde olmasin").

  python -m app.gecmis_temizle             kuru deneme: ne silinecegini sayilarla yazar, hicbir sey yazmaz
  python -m app.gecmis_temizle --uygula    once panel DB yedegi (var/yedek/), sonra siler; panel yeniden baslatilmali

Silinenler:
  * Eski panel tamponu: `eski_aktar` ile alinan tampon partileri (Musteri Radar'i ve Onedesk "Aktarilabilir partiler"i besliyordu).
  * Kayit numarasiz elle aktarilmis Onedesk kayitlari (source='import', bos external_key): musteri bazli ReportDB OZETI partisi
    Onedesk'e kayit diye aktarildiginda olusur (8.441 satirlik ozet = 8.441 sahte "alarm"). Numarali gercek aktarimlara dokunulmaz.
  * Musteri kartindaki alarm / sikayet / talep sayaclari eski panelden kopyalanmisti: kalan gercek Onedesk kayitlarindan yeniden
    hesaplanir (ReportDB isci sureci acik ise sonraki turda kendi degerini yeniden yazar).
Kalanlar: kullanicilar, musteri kartlari, ekip-iletisim (ana veri), denetim kaydi, ReportDB iscisinin kendi partileri.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import env_dosyasi_yukle
from app.db import oturum
from app.models import AuditEvent, Customer, IngestBatch, OnedeskRecord
from app.onedesk.ice_al import sayaclari_yenile
from app.ortak import simdi
from app.tampon import depo

ESKI_AKTARAN = "eski_aktar"  # eski_aktar.tamponu_aktar partinin created_by degeri
SAYACLAR = ("alarm_count", "complaint_count", "request_count", "alarm_closed_count", "complaint_closed_count", "request_closed_count")


def _numarasiz_aktarim():
    return (OnedeskRecord.source == "import") & (func.coalesce(OnedeskRecord.external_key, "") == "")


def temizle(db: Session, uygula: bool = False) -> dict[str, int | list[str]]:
    """Sayilari dondurur; uygula=False iken hicbir sey yazmaz (islem geri alinir)."""
    partiler = list(db.scalars(select(IngestBatch).where(IngestBatch.created_by == ESKI_AKTARAN)))
    sonuc: dict[str, int | list[str]] = {
        "eski_parti": len(partiler),
        "eski_parti_satir": sum(p.row_count or 0 for p in partiler),
        "partiler": [f"#{p.id} {p.label} ({p.row_count} satir)" for p in partiler],
        "onedesk_numarasiz": db.scalar(select(func.count()).select_from(OnedeskRecord).where(_numarasiz_aktarim())) or 0,
        "onedesk_kalan": 0,
        "sayaci_degisen_musteri": 0,
    }
    for p in partiler:
        depo.sil(db, p.id, kontrol=False)  # bagli dagitim gunlugu da gider (eski verinin geri alinacak hali kalmaz)
    db.execute(delete(OnedeskRecord).where(_numarasiz_aktarim()))
    sonuc["onedesk_kalan"] = db.scalar(select(func.count()).select_from(OnedeskRecord)) or 0
    musteriler = list(db.scalars(select(Customer)))
    once = {c.id: tuple(getattr(c, a) or 0 for a in SAYACLAR) for c in musteriler}
    sayaclari_yenile(db, set(once))
    sonuc["sayaci_degisen_musteri"] = sum(1 for c in musteriler if tuple(getattr(c, a) or 0 for a in SAYACLAR) != once[c.id])
    if uygula:
        db.add(AuditEvent(at=simdi(), actor="gecmis_temizle", action="gecmis.temizle", outcome="allow", module_key="yonetim",
                          detail=str({k: v for k, v in sonuc.items() if k != "partiler"})[:500]))  # fmt: skip
        db.commit()
    else:
        db.rollback()
    return sonuc


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--uygula", action="store_true", help="sil (verilmezse yalniz kuru deneme)")
    a = p.parse_args(argv)
    env_dosyasi_yukle()
    print("UYGULAMA" if a.uygula else "KURU DENEME (hicbir sey yazilmaz)")
    if a.uygula:
        from app.eski_aktar import _yedek_al

        yedek = _yedek_al("gecmis_temizle")
        print(f"  yedek: {yedek}" if yedek else "  yedek: SQLite degil, panel veritabaninin yedegini kendiniz alin.")
    with oturum() as db:
        s = temizle(db, a.uygula)
    for satir in s["partiler"]:  # type: ignore[union-attr]
        print(f"  eski panel tamponu: {satir}")
    print(f"  silinecek eski panel tampon partisi: {s['eski_parti']} ({s['eski_parti_satir']} satir)")
    print(f"  silinecek numarasiz aktarilmis Onedesk kaydi: {s['onedesk_numarasiz']}  (kalan Onedesk kaydi: {s['onedesk_kalan']})")
    print(f"  alarm/sikayet/talep sayaci yeniden hesaplanan musteri: {s['sayaci_degisen_musteri']}")
    print(
        "Bitti. Paneli yeniden baslatin (bellekteki Radar onbellegi bosalsin)."
        if a.uygula
        else "Kuru deneme bitti: hicbir sey silinmedi. Uygunsa ayni komutu --uygula ile calistirin."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
