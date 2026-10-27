"""Ariza kaydi (cekirdek): her hata bir KOD ve KAYIT NO tasir. Ham istisna metni kullaniciya donmez; yigin izi dosya gunlugune yazilir.

Kullanici ekranda "(kod TL-DB-01, kayit 3f9a1c2b)" gorur. Yonetici Yonetim > Arizalar'dan kayit numarasiyla bulur,
Gunlukler > Uygulama gunlugu'nden yigin izine ulasir. Listeleme/durum yonetimi: app.yonetim.arizalar.
"""

from __future__ import annotations

import logging
import re
import threading
import uuid

from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.ortak import simdi
from app.yonetim.models import FaultEvent

_log = logging.getLogger("tamlife.ariza")

# kod -> (kullaniciya gorunen kisa aciklama, yoneticiye ilk cozum adimi)
KODLAR: dict[str, tuple[str, str]] = {
    "TL-DB-01": (
        "Veritabanı işlemi tamamlanamadı",
        "Disk alanını ve veritabanı dosyasının yazma iznini kontrol edin (Yönetim › Veritabanı).",
    ),
    "TL-DB-02": ("Veritabanı şu an meşgul", "Kısa süre sonra tekrar deneyin; sürerse kilidi tutan süreci bulun."),
    "TL-TAM-01": ("Tampon verisi işlenemedi", "Yönetim › Veri Girişi: partinin hata mesajına bakın."),
    "TL-KAY-01": ("Veri kaynağına erişilemiyor", "Kaynak yapılandırma anahtarlarını (Veri Girişi › Kaynaklar) kontrol edin."),
    "TL-YDK-01": ("Yedek alınamadı", "Yedek klasörünün yazma iznini ve boş alanı kontrol edin."),
    "TL-RAP-01": (
        "Aylık rapor gönderilemedi",
        "Kayıttaki müşteri ve nedene bakın; SMTP ise Kurum Bağlantıları › E-posta testi. Personel raporu yeniden gönderebilir (ay kilitlenmedi).",
    ),
    "TL-SRV-01": ("Beklenmeyen sunucu hatası", "Kayıt numarasıyla uygulama günlüğünde yığın izini arayın."),
    "TL-SNC-01": (
        "Gece senkronu / panel yeniden başlatma sorunu",
        "Sunucuda var\\log\\gece_sync günlüğüne bakın; panel kapalıysa full_reboot.bat (yönetici). Citrix erişimi yoksa uzak masaüstü bağlantısı açık mı?",
    ),
}
SEVIYELER = ("error", "warning")
_SIR = re.compile(r"(?i)(password|parola|pwd|secret)\s*[=:]\s*\S+")


def siniflandir(hata: BaseException) -> str:
    if isinstance(hata, OperationalError) and "locked" in str(hata).lower():
        return "TL-DB-02"
    if isinstance(hata, SQLAlchemyError):
        return "TL-DB-01"
    return "TL-SRV-01"


def temizle(metin: object, azami: int = 300) -> str:
    """Tek satir, sir benzeri degerler maskeli, kirpilmis."""
    ilk = " ".join(str(metin or "").split())
    return _SIR.sub(lambda m: f"{m.group(1)}=***", ilk)[:azami]


def mesaj(kod: str, kayit_no: str) -> str:
    metin = KODLAR.get(kod, KODLAR["TL-SRV-01"])[0]
    return f"{metin} (kod {kod}, kayıt {kayit_no[:8]})."


def kaydet(
    kod: str,
    ayrinti: str = "",
    *,
    exc: BaseException | None = None,
    kaynak: str = "",
    kullanici: str = "",
    seviye: str = "error",
    arka_plan: bool = False,
) -> str:
    """Arizayi dosya gunlugune ve fault_event'e yazar; kayit numarasini doner. ASLA istisna firlatmaz.
    arka_plan: fault_event satiri ayri is parcacigiyla yazilir (kilitli DB'de yanit bir busy_timeout daha beklemesin)."""
    kayit_no = uuid.uuid4().hex
    ozet = temizle(ayrinti or (str(exc) if exc else ""))
    seviye = seviye if seviye in SEVIYELER else "error"
    _log.log(
        logging.ERROR if seviye == "error" else logging.WARNING,
        "[%s] [kayit %s] %s kullanici=%s %s",
        kod,
        kayit_no[:8],
        kaynak or "-",
        kullanici or "-",
        ozet,
        exc_info=exc,
    )
    satir = FaultEvent(
        record_no=kayit_no,
        code=kod,
        severity=seviye,
        source=temizle(kaynak, 160),
        message=ozet,
        exc_type=type(exc).__name__ if exc is not None else "",
        actor=temizle(kullanici, 120),
        at=simdi(),
        status="open",
    )

    def yaz() -> None:
        try:
            from app.db import oturum

            with oturum() as db:
                db.add(satir)
                db.commit()
        except Exception:  # noqa: BLE001 - ariza kaydi yazilamasa da yanit donmeli
            _log.warning("ariza kaydi veritabanina yazilamadi (kayit %s)", kayit_no[:8], exc_info=True)

    if arka_plan:
        threading.Thread(target=yaz, name="ariza-kaydi", daemon=True).start()
    else:
        yaz()
    return kayit_no
