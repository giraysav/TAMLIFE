"""Saglik kontrolleri: hafif, dis baglanti ACMAZ (uretim izleme.py'nin panel ici karsiligi). Her kontrol ok | uyari | hata."""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app import baglantilar
from app import session as oturum
from app.models import Base, IngestBatch
from app.ortak import iso, simdi
from app.tampon.models import DistributionRule
from app.yonetim import arizalar, dosya_gunlugu, veritabani

SIRA = {"ok": 0, "uyari": 1, "hata": 2}
DISK_UYARI_YUZDE = 15  # uretim izlemesiyle ayni esikler
DISK_KRITIK_YUZDE = 7
Kontrol = dict[str, Any]


def _k(kimlik: str, durum: str, ayrinti: str, **veri: Any) -> Kontrol:
    return {"id": kimlik, "durum": durum, "ayrinti": ayrinti, "veri": veri}


def _veritabani(db: Session) -> Kontrol:
    t0 = time.perf_counter()
    db.execute(text("SELECT 1"))
    ms = round((time.perf_counter() - t0) * 1000, 1)
    return _k("veritabani", "ok" if ms < 500 else "uyari", f"Yanıt {ms} ms", ms=ms)


def _sema(db: Session) -> Kontrol:
    baglanti = db.connection()
    eksik = sorted(set(Base.metadata.tables) - set(inspect(baglanti).get_table_names()))
    if eksik:
        return _k("sema", "hata", f"Eksik tablo: {', '.join(eksik[:5])}", eksik=eksik)
    kayitli, hedef = veritabani.surum(baglanti), veritabani.surum_head()
    if kayitli is None:
        return _k("sema", "uyari", "Sürüm kaydı yok (alembic upgrade head çalışmamış).", surum=None, hedef=hedef)
    if hedef and kayitli != hedef:
        return _k("sema", "uyari", f"Sürüm {kayitli}, beklenen {hedef}: alembic upgrade head gerekli.", surum=kayitli, hedef=hedef)
    return _k("sema", "ok", f"Şema güncel ({kayitli}).", surum=kayitli, hedef=hedef)


def _disk(_: Session) -> Kontrol:
    yol = veritabani.sqlite_yolu()
    if yol is None:
        return _k("disk", "ok", "Uzak/bellek veritabanı: yerel disk kontrolü atlandı.")
    kullanim = shutil.disk_usage(yol.parent)
    serbest = round(kullanim.free * 100 / kullanim.total, 1)
    durum = "hata" if serbest < DISK_KRITIK_YUZDE else "uyari" if serbest < DISK_UYARI_YUZDE else "ok"
    return _k("disk", durum, f"Boş alan %{serbest}", serbest_yuzde=serbest, serbest_bayt=kullanim.free)


def _gunluk(_: Session) -> Kontrol:
    yer = dosya_gunlugu.klasor()
    try:
        yer.mkdir(parents=True, exist_ok=True)
        deneme = yer / ".yazma_denemesi"
        deneme.write_text("x", encoding="utf-8")
        deneme.unlink()
    except OSError:
        return _k("gunluk", "hata", "Günlük klasörüne yazılamıyor.")
    return _k("gunluk", "ok", "Günlük klasörü yazılabilir.")


def _oturum(_: Session) -> Kontrol:
    adet = len(oturum.aktif_oturumlar())
    oran = adet / oturum.MAX_SESSIONS
    return _k("oturum", "uyari" if oran >= 0.8 else "ok", f"{adet} aktif oturum", aktif=adet, sinir=oturum.MAX_SESSIONS)


def _tampon(db: Session) -> Kontrol:
    esik = simdi() - timedelta(hours=24)
    basarisiz = (
        db.scalar(
            select(func.count())
            .select_from(IngestBatch)
            .where(IngestBatch.received_at >= esik, IngestBatch.status.in_(("failed", "rejected")))
        )
        or 0
    )
    kurallar = db.scalar(select(func.count()).select_from(DistributionRule).where(DistributionRule.enabled.is_(True))) or 0
    if basarisiz:
        return _k("tampon", "uyari", f"Son 24 saatte {basarisiz} parti başarısız/reddedildi.", basarisiz=basarisiz, kurallar=kurallar)
    return _k("tampon", "ok", f"{kurallar} etkin dağıtım kuralı.", basarisiz=0, kurallar=kurallar)


def _entegrasyon(_: Session) -> Kontrol:
    eksik = [o["label"] for o in baglantilar.integrations()["items"] if o["state"] == "incomplete"]  # type: ignore[index, union-attr]
    if eksik:
        return _k("entegrasyon", "uyari", f"Yapılandırması yarım: {', '.join(map(str, eksik))}", eksik=eksik)
    return _k("entegrasyon", "ok", "Yarım yapılandırma yok (kapalı kaynaklar normal).")


def _ariza(db: Session) -> Kontrol:
    ozet = arizalar.ozet(db)
    hata = int(ozet["son_24s_hata"])  # type: ignore[call-overload]
    durum = "hata" if hata >= 20 else "uyari" if hata >= 5 else "ok"
    return _k("ariza", durum, f"Son 24 saatte {hata} hata kaydı.", son_24s_hata=hata, acik=ozet["acik"])


KONTROLLER: tuple[tuple[str, Callable[[Session], Kontrol]], ...] = (
    ("veritabani", _veritabani),
    ("sema", _sema),
    ("disk", _disk),
    ("gunluk", _gunluk),
    ("oturum", _oturum),
    ("tampon", _tampon),
    ("entegrasyon", _entegrasyon),
    ("ariza", _ariza),
)


def calistir(db: Session) -> dict[str, Any]:
    """Tum kontroller; bir kontrol patlarsa 'hata' olarak raporlanir, digerleri surer."""
    sonuc: list[Kontrol] = []
    for kimlik, islev in KONTROLLER:
        try:
            sonuc.append(islev(db))
        except Exception as hata:  # noqa: BLE001 - kontrol hatasi baska kontrolleri durdurmasin
            sonuc.append(_k(kimlik, "hata", f"Kontrol çalıştırılamadı ({type(hata).__name__})."))
    genel = max((k["durum"] for k in sonuc), key=SIRA.__getitem__)
    return {"genel": genel, "zaman": iso(simdi()), "kontroller": sonuc}
