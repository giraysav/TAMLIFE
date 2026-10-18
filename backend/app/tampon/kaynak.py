"""Kaynaklar: tampona veri getiren yollar. CSV yukleme ve Oracle kaynaklari (REPORTDB, ONENTDB, GALAPAGOSDB).

Oracle: <ON EK>_ENABLED=true + zorunlu anahtarlar doluyken 'hazir'. Cekimi panel DEGIL isci surec yapar (python -m app.isci; uretimde de
boyleydi: surucu web surecine yuklenmez, panel kimligi Oracle giris tetikleyicisinden gecmez). Panel yalniz durumu gosterir ve
baglanti testini ayri surecte calistirir (oracle.baglanti_testi).
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from collections.abc import Iterator
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dil import m
from app.models import IngestBatch
from app.ortak import UygulamaHatasi, iso
from app.tampon import depo, oracle, reportdb
from app.tampon.musteri_ham import KAYNAK

CSV_ON_EK = "csv_"
_AYRACLAR = (";", ",", "\t", "|")
_SLUG = re.compile(r"[^a-z0-9]+")


_ASCII = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iIsSgGuUoOcC")


def _parti_adi(anahtar: str) -> str:
    """Oracle kaynakli parti adi (istegin dilinde)."""
    if anahtar == reportdb.KAYIT_KAYNAGI:
        return m("REPORTDB alarm kayıtları (Onedesk'e)", "REPORTDB alarm records (to Onedesk)")
    for k, s in oracle.KAYNAKLAR.items():
        if anahtar == f"{k}_import":
            return f"{s.label} · " + m("içeri alma sorgusu", "import query")
    return anahtar


def kaynak_anahtari(ad: str) -> str:
    """Yukleme kaynak adi -> 'csv_<slug>' (en fazla 40 karakter); bos/gecersizse 'csv_dosya'."""
    slug = _SLUG.sub("_", ad.translate(_ASCII).lower()).strip("_")
    return (CSV_ON_EK + (slug or "dosya"))[:40]


def _metne_cevir(veri: bytes) -> str:
    for kodlama in ("utf-8-sig", "cp1254"):
        try:
            return veri.decode(kodlama)
        except UnicodeDecodeError:
            continue
    return veri.decode("latin-1")


def _basliklari_tekillestir(ham: list[str]) -> list[str]:
    sonuc, sayac = [], Counter[str]()
    for i, h in enumerate(ham, 1):
        ad = h.strip() or f"Sütun {i}"
        sayac[ad] += 1
        sonuc.append(ad if sayac[ad] == 1 else f"{ad} ({sayac[ad]})")
    return sonuc


def csv_oku(veri: bytes) -> tuple[list[str], Iterator[list[Any]]]:
    """(basliklar, satir ureteci). Kodlama (UTF-8/Windows-1254) ve ayrac (; , TAB |) kendiliginden bulunur."""
    metin = _metne_cevir(veri)
    ilk = next((s for s in metin.splitlines() if s.strip()), "")
    ayrac = max(_AYRACLAR, key=ilk.count) if any(a in ilk for a in _AYRACLAR) else ","
    okuyucu = csv.reader(io.StringIO(metin, newline=""), delimiter=ayrac)
    for ham in okuyucu:
        if any(h.strip() for h in ham):
            while ham and not ham[-1].strip():
                ham.pop()
            basliklar = _basliklari_tekillestir(ham)
            break
    else:
        raise UygulamaHatasi(400, "Dosyada başlık satırı yok.")
    if len(basliklar) < 2:
        raise UygulamaHatasi(400, "En az iki sütun gerekir (ayraç ';' ',' sekme ya da '|' olmalı).")

    def satirlar() -> Iterator[list[Any]]:
        for ham in okuyucu:
            if ham:  # bos satir ([]); yalniz ayraclardan olusan satirlari ice_al eler
                yield [(h.strip() or None) for h in ham]

    return basliklar, satirlar()


def _oracle_durum(db: Session) -> list[dict[str, Any]]:
    cikti = []
    for anahtar, s in oracle.KAYNAKLAR.items():
        d = oracle.durum(anahtar)
        if not d["acik"]:
            neden = f"Kaynak kapalı ({s.enabled_key}=true değil)."
        elif d["eksik"]:
            neden = "Bağlantı ayarı eksik."
        else:
            neden = "Çekim ayrı işçi süreçte (python -m app.isci); panel Oracle'a bağlanmaz."
        satir: dict[str, Any] = {
            "anahtar": anahtar,
            "ad": s.label,
            "tur": "oracle",
            "hazir": d["hazir"],
            "neden": neden,
            "yapilandirma": "kapalı" if not d["acik"] else ("eksik" if d["eksik"] else "tamam"),
            "eksik": d["eksik"],
        }
        if anahtar == reportdb.KAYNAK:
            satir["reportdb"] = reportdb.durum(db)
        cikti.append(satir)
    return cikti


def durumlar(db: Session) -> list[dict[str, Any]]:
    """Kaynak listesi + her kaynagin son partisi ve parti sayisi."""
    liste: list[dict[str, Any]] = [
        {
            "anahtar": KAYNAK,
            "ad": m("Ham Müşteri Verisi", "Raw Customer Data"),
            "tur": "dosya",
            "hazir": True,
            "neden": "",
            "yapilandirma": "tamam",
            "eksik": [],
        },
    ]
    liste.extend(_oracle_durum(db))
    anahtarlar = db.scalars(select(IngestBatch.source_key).distinct()).all()
    for k in anahtarlar:
        csv_mi = k.startswith(CSV_ON_EK)
        if (csv_mi or k.startswith("oracle_")) and not any(x["anahtar"] == k for x in liste):
            liste.append(
                {
                    "anahtar": k,
                    "ad": f"CSV · {k[len(CSV_ON_EK) :]}" if csv_mi else _parti_adi(k),
                    "tur": "dosya" if csv_mi else "oracle_parti",
                    "hazir": True,
                    "neden": "",
                    "yapilandirma": "tamam",
                    "eksik": [],
                }
            )
    # Kaynak basina sayi + son parti: iki sorgu (kaynak sayisindan bagimsiz)
    sayim = {
        k: (n, son_id)
        for k, n, son_id in db.execute(
            select(IngestBatch.source_key, func.count(), func.max(IngestBatch.id))
            .where(IngestBatch.source_key.in_([x["anahtar"] for x in liste]))
            .group_by(IngestBatch.source_key)
        )
    }
    sonlar = {p.id: p for p in db.scalars(select(IngestBatch).where(IngestBatch.id.in_([s for _, s in sayim.values()])))} if sayim else {}
    for kaynak in liste:
        sayi, son_id = sayim.get(kaynak["anahtar"], (0, None))
        son = sonlar.get(son_id) if son_id else None
        kaynak["parti_sayisi"] = sayi
        kaynak["son"] = (
            None
            if son is None
            else {"id": son.id, "durum": son.status, "satir": son.row_count, "zaman": iso(son.received_at), "hata": son.error}
        )
    return liste


def oracle_parti(db: Session, anahtar: str, kullanici: str) -> IngestBatch:
    """<ON EK>_IMPORT_QUERY sonucu -> tampon partisi '<kaynak>_import' (uretim db_al.calistir). YALNIZ isci surec cagirir.

    Satirlar blok blok akar (bellekte tum sonuc yok); sinir asilirsa sessizce kesmek yerine parti 'failed' olur. Hata metni
    oracle.hata_metni'nden gecer (adres/parola tasimaz); basarisiz parti ekranda kalir (kaynagin yalniz son hatasi).
    """
    a = oracle.ayar(anahtar)
    sorgu = oracle.sorgu_temizle(a.IMPORT_QUERY)
    parti = depo.parti_olustur(db, f"{anahtar}_import", f"{a.kaynak.label} (içeri alma sorgusu)", kullanici)
    db.commit()
    parti_id = parti.id
    try:
        akis = a.akis(sorgu, get_settings().ingest_max_rows + 1)
        basliklar = _basliklari_tekillestir([str(b or "") for b in next(akis)])
        return depo.ice_al(db, parti, basliklar, ([oracle.deger(v) for v in s] for blok in akis for s in blok))
    except UygulamaHatasi as e:
        depo.basarisiz(db, parti_id, e.mesaj)
        raise
    except Exception as e:
        mesaj = " ".join(oracle.hata_metni(e, a.gizliler())).strip()
        depo.basarisiz(db, parti_id, mesaj)
        raise oracle.OracleHata(mesaj, 502) from e
