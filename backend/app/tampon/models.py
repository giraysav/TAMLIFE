# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Tampon tablolari. Partinin kendisi (ingest_batch) app.models'te; burada blok, kural ve uygulama gunlugu."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class IngestBlock(Base):
    """Ham satirlar: BLOK_SATIR'lik JSON listesi zlib ile sikistirilmis (satir basina kayit 6-8 kat buyuk tutuyordu)."""

    __tablename__ = "ingest_block"
    batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batch.id"), primary_key=True)
    block_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class DistributionRule(Base):
    """Dagitim kurali: hangi sutun hangi karta, hangi SABIT hedefe, hangi islemle. Varsayilan kapali."""

    __tablename__ = "distribution_rule"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    source_key: Mapped[str] = mapped_column(String(40))
    match_field: Mapped[str] = mapped_column(String(20), default="customer_no")  # customer_no | ncst | name
    key_column: Mapped[str] = mapped_column(String(160))
    target: Mapped[str] = mapped_column(String(60))
    operation: Mapped[str] = mapped_column(String(20))
    value_column: Mapped[str] = mapped_column(String(160), default="")
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    zero_unmatched: Mapped[bool] = mapped_column(Boolean, default=False)
    max_age_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(120), default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DistributionLog(Base):
    """Her yazilan deger icin eski/yeni: geri alma yalniz hala yazilan degerde duranlari dondurur."""

    __tablename__ = "distribution_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), index=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("distribution_rule.id"))
    batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batch.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))
    target: Mapped[str] = mapped_column(String(60))
    old_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(String(120), default="")
    reverted: Mapped[bool] = mapped_column(Boolean, default=False)


class CustomerImportRun(Base):
    """Ham Musteri Verisi aktarimi: kartlara yazilan her degerin onceki/sonraki hali (geri alma icin) ve ozet.

    record: {'guncellenen': [{id, unvan, onceki, sonraki, iletisim_onceki, iletisim_sonraki}], 'olusturulan': [{id, unvan}],
    'iletisim_olusturulan': [musteri id]}. Parti silinse de kayit kalir (batch_id yabanci anahtar degildir)."""

    __tablename__ = "customer_import_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(String(120), default="")
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    record: Mapped[dict] = mapped_column(JSON, default=dict)
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reverted_by: Mapped[str] = mapped_column(String(120), default="")


class FileImportRun(Base):
    """Elle yuklenen dosya aktarimi (2026-11-01 kullanici: "importa manuel eklenen dosya olursa geri alma secenegi de olmali"):
    Urun-Tutar, Gelir Faydasi ve Proje Excel'i. kind: urun_tutar | gelir_uretim | proje. record turune gore geri alma bilgisi
    (olusturulan kayit id + yazildigi andaki updated_at; Urun-Tutar'da musteri basina onceki ozet). Bkz. app/tampon/ice_aktarma_gecmisi.py."""

    __tablename__ = "file_import_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    file_name: Mapped[str] = mapped_column(String(200), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(String(120), default="")
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    record: Mapped[dict] = mapped_column(JSON, default=dict)
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reverted_by: Mapped[str] = mapped_column(String(120), default="")


class SourceCatalog(Base):
    """Kaynak katalogu (ham tampon): bir Oracle kaynaginin semalari / nesneleri / sutunlari ve ornek satirlari, tarama basina tek kayit.
    Isci sureci yazar (python -m app.isci reportdb-katalog); panel yalniz okur. status: receiving | ready | failed."""

    __tablename__ = "source_catalog"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="receiving")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), default="")
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(500), default="")


class SourceCatalogObject(Base):
    """Katalogdaki tek nesne (tablo / gorunum / es ad). parent: agacta ust nesne ('SAHIP.AD'; bos = ana nesne).
    columns: [{ad, tip, bos_olabilir, aciklama, doluluk, farkli, ornekler}] (profil ornek satirlardan). details: es ad hedefi,
    bagimliliklar, bolumler, indeksler. sample_data: ornek satirlar (zlib JSON); kisisel veri iceren nesnede bos."""

    __tablename__ = "source_catalog_object"
    id: Mapped[int] = mapped_column(primary_key=True)
    catalog_id: Mapped[int] = mapped_column(ForeignKey("source_catalog.id", ondelete="CASCADE"), index=True)
    owner: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(30))
    parent: Mapped[str] = mapped_column(String(260), default="")
    row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # istatistik NUM_ROWS (2 milyar ustu olabilir)
    analyzed: Mapped[str] = mapped_column(String(20), default="")
    comment: Mapped[str] = mapped_column(String(1000), default="")
    columns: Mapped[list] = mapped_column(JSON, default=list)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    sample_columns: Mapped[list] = mapped_column(JSON, default=list)
    sample_rows: Mapped[int] = mapped_column(Integer, default=0)
    sample_note: Mapped[str] = mapped_column(String(300), default="")
    sample_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
