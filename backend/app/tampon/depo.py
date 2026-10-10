"""Tampon deposu: parti yasam dongusu ve ham satir bloklari.

Tasarim (uretim ham_depo.py dersleri): satirlar BLOK_SATIR'lik JSON listesi olarak zlib ile sikistirilir; her blok
kendi KISA isleminde yazilir (yazma kilidi milisaniye; tek dev islem digerlerini bekletiyordu); okuyucular beklemez.
Parti degismez: hazir olduktan sonra satirlari degistirilmez, yalniz silinebilir.
"""

from __future__ import annotations

import json
import zlib
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import IngestBatch
from app.ortak import UygulamaHatasi, simdi
from app.tampon.models import DistributionLog, IngestBlock
from app.tampon.profil import Profil

BLOK_SATIR = 2_000
KORUMA_ESIGI = 200  # onceki parti bunun altindaysa kucuklme korumasi uygulanmaz
EN_AZ_ORAN = 0.5  # yeni parti oncekinin yarisindan kucukse reddedilir ("yarim sonuc korumasi")
DURUMLAR = ("receiving", "ready", "failed", "rejected")


def _sikistir(satirlar: Sequence[Sequence[object]]) -> bytes:
    return zlib.compress(json.dumps(satirlar, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)


def _ac(veri: bytes) -> list[list[Any]]:
    return json.loads(zlib.decompress(veri).decode("utf-8"))


def parti_olustur(db: Session, kaynak: str, etiket: str, kullanici: str) -> IngestBatch:
    parti = IngestBatch(
        source_key=kaynak[:40],
        received_at=simdi(),
        status="receiving",
        label=etiket[:200],
        created_by=kullanici[:120],
        columns=[],
        profile={},
    )
    db.add(parti)
    db.flush()
    return parti


def _bloklari_sil(db: Session, parti_id: int) -> None:
    db.execute(delete(IngestBlock).where(IngestBlock.batch_id == parti_id))


def _basarisiz(db: Session, parti_id: int, mesaj: str) -> None:
    """Yarida kalan parti: bloklar silinir, parti 'failed' kalir (mesaj ekranda)."""
    db.rollback()
    _bloklari_sil(db, parti_id)
    parti = db.get(IngestBatch, parti_id)
    if parti is not None:
        parti.status, parti.error, parti.finished_at = "failed", mesaj[:300], simdi()
    db.commit()


def basarisiz(db: Session, parti_id: int, mesaj: str) -> None:
    """Isci cekimi basarisiz: parti 'failed' (mesaj ekranda); ayni kaynagin ONCEKI failed partileri silinir (zamanlanmis gorev
    her turda hata verse de liste sismez, son hata kalir)."""
    _basarisiz(db, parti_id, mesaj)
    parti = db.get(IngestBatch, parti_id)
    if parti is None:
        return
    for eski in db.scalars(
        select(IngestBatch.id).where(IngestBatch.source_key == parti.source_key, IngestBatch.status == "failed", IngestBatch.id != parti_id)
    ).all():
        sil(db, eski, kontrol=False)
    db.commit()


def ice_al(db: Session, parti: IngestBatch, basliklar: Sequence[str], satirlar: Iterable[Sequence[object]]) -> IngestBatch:
    """Satirlari bloklar halinde yazar, profil cikarir, korumalari uygular. Her blok kendi islemindedir (commit).

    Hata olursa parti 'failed' olur ve UygulamaHatasi/orijinal istisna yukari gider.
    """
    ayar = get_settings()
    parti_id, n = parti.id, len(basliklar)
    profil, parca, blok_no, toplam = Profil(basliklar), [], 0, 0
    try:
        for satir in satirlar:
            hucre = list(satir[:n]) + [None] * (n - len(satir))
            if not any(h not in (None, "") for h in hucre):
                continue
            parca.append(hucre)
            if len(parca) >= BLOK_SATIR:
                toplam += len(parca)
                if toplam > ayar.ingest_max_rows:
                    raise UygulamaHatasi(413, f"Veri çok büyük: en fazla {ayar.ingest_max_rows:,} satır alınabilir.".replace(",", "."))
                profil.ekle(parca)
                db.add(IngestBlock(batch_id=parti_id, block_no=blok_no, row_count=len(parca), data=_sikistir(parca)))
                db.commit()
                parca, blok_no = [], blok_no + 1
        if parca:
            toplam += len(parca)
            if toplam > ayar.ingest_max_rows:
                raise UygulamaHatasi(413, f"Veri çok büyük: en fazla {ayar.ingest_max_rows:,} satır alınabilir.".replace(",", "."))
            profil.ekle(parca)
            db.add(IngestBlock(batch_id=parti_id, block_no=blok_no, row_count=len(parca), data=_sikistir(parca)))
            db.commit()
        if toplam == 0:
            raise UygulamaHatasi(400, "Veride satır yok.")
    except UygulamaHatasi as hata:
        _basarisiz(db, parti_id, hata.mesaj)
        raise
    except Exception as hata:
        _basarisiz(db, parti_id, f"Beklenmeyen hata: {type(hata).__name__}")
        raise

    parti = db.get(IngestBatch, parti_id)
    assert parti is not None
    onceki = db.scalars(
        select(IngestBatch)
        .where(IngestBatch.source_key == parti.source_key, IngestBatch.status == "ready", IngestBatch.id != parti_id)
        .order_by(IngestBatch.id.desc())
        .limit(1)
    ).first()
    parti.row_count, parti.columns = toplam, list(basliklar)
    parti.profile = {"sutunlar": profil.sonuc()}
    parti.finished_at = simdi()
    if onceki is not None and onceki.row_count >= KORUMA_ESIGI and toplam < onceki.row_count * EN_AZ_ORAN:
        parti.status = "rejected"
        parti.error = f"Beklenenden çok küçük ({toplam} satır, önceki parti {onceki.row_count}). Doğruysa 'Yine de kabul et' deyin."[:300]
    else:
        parti.status, parti.error = "ready", ""
    db.commit()
    if parti.status == "ready":
        eskileri_temizle(db, parti.source_key)
    return parti


def kabul_et(db: Session, parti_id: int) -> IngestBatch:
    """Kucuklme korumasina takilan partiyi yonetici onayiyla hazir yapar."""
    parti = db.get(IngestBatch, parti_id)
    if parti is None:
        raise UygulamaHatasi(404, "Parti yok.")
    if parti.status != "rejected":
        raise UygulamaHatasi(409, "Yalnız reddedilmiş parti kabul edilebilir.")
    parti.status, parti.error = "ready", ""
    db.flush()
    return parti


def kullanimda_mi(db: Session, parti_id: int) -> bool:
    """Geri alinmamis dagitim kaydi bu partiye bagliysa silinemez (geri alma bozulurdu)."""
    return (
        db.scalar(
            select(func.count())
            .select_from(DistributionLog)
            .where(DistributionLog.batch_id == parti_id, DistributionLog.reverted.is_(False))
        )
        or 0
    ) > 0


def eskileri_temizle(db: Session, kaynak: str) -> int:
    """Kaynak basina son ingest_keep_batches hazir parti kalir; bagli (geri alinmamis) olanlar korunur."""
    kalacak = get_settings().ingest_keep_batches
    hazirlar = db.scalars(
        select(IngestBatch).where(IngestBatch.source_key == kaynak, IngestBatch.status == "ready").order_by(IngestBatch.id.desc())
    ).all()
    silinen = 0
    for eski in hazirlar[kalacak:]:
        if kullanimda_mi(db, eski.id):
            continue
        sil(db, eski.id, kontrol=False)
        silinen += 1
    db.commit()
    return silinen


def sil(db: Session, parti_id: int, *, kontrol: bool = True) -> None:
    parti = db.get(IngestBatch, parti_id)
    if parti is None:
        raise UygulamaHatasi(404, "Parti yok.")
    if kontrol and kullanimda_mi(db, parti_id):
        raise UygulamaHatasi(409, "Bu parti geri alınmamış bir dağıtıma bağlı; önce uygulamayı geri alın.")
    db.execute(delete(DistributionLog).where(DistributionLog.batch_id == parti_id))
    _bloklari_sil(db, parti_id)
    db.delete(parti)
    db.flush()


def satirlari_oku(db: Session, parti_id: int) -> Iterator[list[Any]]:
    """Partinin tum satirlari, blok blok (bellekte tek blok)."""
    for veri in db.scalars(select(IngestBlock.data).where(IngestBlock.batch_id == parti_id).order_by(IngestBlock.block_no)):
        yield from _ac(veri)


def sayfa_oku(db: Session, parti_id: int, sayfa: int, adet: int) -> list[list[Any]]:
    """Yalniz gereken bloklari acar (sayfa basina en fazla 2 blok)."""
    adet = max(1, min(adet, 200))
    bas = (max(1, sayfa) - 1) * adet
    ilk_blok = bas // BLOK_SATIR
    toplanan: list[list[Any]] = []
    ilk = True
    for veri in db.scalars(
        select(IngestBlock.data).where(IngestBlock.batch_id == parti_id, IngestBlock.block_no >= ilk_blok).order_by(IngestBlock.block_no)
    ):
        satirlar = _ac(veri)
        if ilk:
            satirlar, ilk = satirlar[bas - ilk_blok * BLOK_SATIR :], False
        toplanan.extend(satirlar)
        if len(toplanan) >= adet:
            break
    return toplanan[:adet]
