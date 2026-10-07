"""Yonetim (ariza kaydi) ve Veri Girisi tamponu (blok, kural, uygulama gunlugu).

Revision ID: 0005_yonetim_tampon
Revises: 0004_musteri_karti_rapor
Create Date: 2026-10-07

0001 `create_all` kullandigi icin taze veritabaninda her sey zaten gelir; mevcut veritabaninda yalniz eksikler
eklenir (ingest_batch sutunlari + yeni tablolar). Adimlar tekrar calisabilir.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models import Base

revision: str = "0005_yonetim_tampon"
down_revision: str | Sequence[str] | None = "0004_musteri_karti_rapor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

YENI_TABLOLAR = ("fault_event", "ingest_block", "distribution_rule", "distribution_log")

# (sutun, tip, sunucu varsayilani, bos olabilir)
BATCH_SUTUNLARI = (
    ("label", sa.String(200), "", False),
    ("row_count", sa.Integer(), "0", False),
    ("columns", sa.JSON(), "[]", False),
    ("profile", sa.JSON(), "{}", False),
    ("created_by", sa.String(120), "", False),
    ("finished_at", sa.DateTime(timezone=True), None, True),
    ("error", sa.String(300), "", False),
)


def upgrade() -> None:
    bind = op.get_bind()
    sutunlar = {c["name"] for c in sa.inspect(bind).get_columns("ingest_batch")}
    eksik = [s for s in BATCH_SUTUNLARI if s[0] not in sutunlar]
    if eksik:
        with op.batch_alter_table("ingest_batch") as batch:
            for ad, tip, varsayilan, bos_olabilir in eksik:
                batch.add_column(
                    sa.Column(
                        ad,
                        tip,
                        nullable=bos_olabilir,
                        server_default=None if varsayilan is None else sa.text(f"'{varsayilan}'"),
                    )
                )
    Base.metadata.create_all(bind, tables=[Base.metadata.tables[n] for n in YENI_TABLOLAR], checkfirst=True)


def downgrade() -> None:
    for ad in ("distribution_log", "distribution_rule", "ingest_block", "fault_event"):
        op.drop_table(ad)
    with op.batch_alter_table("ingest_batch") as batch:
        for ad, *_ in BATCH_SUTUNLARI:
            batch.drop_column(ad)
