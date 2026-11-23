"""ReportDB (Oracle) ortak tanimlari: kaynak anahtari, isci adi, tur sikligi ve TEMIP alarm kayit turunun durum kaydi.

2026-11-23 kullanici karari: "ozet sorguyu kaldir, db'lerden guncel veriyi 30 dk'lik periyotla cek". Eski alarm OZET sorgusu (musteri
basina aktif / kapanan sayi -> tampon partisi -> kartlara dagitim) kaldirildi: kart sayaclari yalniz alarm KAYITLARINDAN gelir
(tampon/temip_kayit.py -> onedesk/sayac.sayaclari_yenile). Isci turu (python -m app.isci reportdb) 30 dakikada bir: TEMIP alarm
kayitlari + LOE devre grafikleri + CI envanteri + OneDesk sikayet / talep kayitlari (kurulum/canli_gorev_kur.ps1 servis dongusu).
Panel sureci Oracle'a baglanmaz; Oracle'a yalniz SELECT gider (oracle.sorgu_temizle).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSetting
from app.ortak import UygulamaHatasi, simdi

KAYNAK = "oracle_reportdb"
KAYIT_KAYNAGI = "oracle_reportdb_kayit"  # 2026-10-17 oncesi kayit partileri (adlandirma icin; yeni parti yazilmaz)
ISCI = "reportdb"  # kayit / ayar yazari
TUR_DK = 30  # isci turu araligi (canli_gorev_kur.ps1 $IsciAralikDk ile ayni)
BAYAT_DK = 75  # iki tur kacirildi (+ tur suresi): veri bayat sayilir
DURUM_ANAHTARI = "temip.kayit_durum"  # son deneme / son basari / hata (Veri Ozeti, Veri Akisi)


class ReportdbHata(UygulamaHatasi):
    """Yoneticiye / gunluge gosterilecek hata."""

    def __init__(self, mesaj: str, kod: int = 400) -> None:
        super().__init__(kod, mesaj)


def durum_oku(db: Session) -> dict[str, Any]:
    kayit = db.get(AppSetting, DURUM_ANAHTARI)
    return dict(kayit.value) if kayit is not None and isinstance(kayit.value, dict) else {}


def durum_yaz(db: Session, hata: str = "") -> None:
    """Tur sonucu: basarida son_basari guncellenir ve hata silinir; hatada yalniz son_deneme + hata."""
    an = simdi().isoformat()
    deger = {**durum_oku(db), "son_deneme": an, "hata": hata[:500]}
    if not hata:
        deger["son_basari"] = an
    kayit = db.get(AppSetting, DURUM_ANAHTARI)
    if kayit is None:
        db.add(AppSetting(key=DURUM_ANAHTARI, value=deger, updated_by=ISCI, updated_at=simdi()))
    else:
        kayit.value, kayit.updated_by, kayit.updated_at = deger, ISCI, simdi()
    db.commit()


def son_hata(d: dict[str, Any]) -> str:
    """Son denemede hata varsa metni (sonra basarili tur olduysa bos)."""
    return d.get("hata", "") if d.get("hata") and d.get("son_deneme", "") >= d.get("son_basari", "") else ""
