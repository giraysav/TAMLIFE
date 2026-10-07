"""Kullanilmayan ingest_record tablosunu kaldirir (yerini ingest_block aldi).

Revision ID: 0006_ingest_record_kaldir
Revises: 0005_yonetim_tampon
Create Date: 2026-10-07

ingest_record satir basina JSONB kayit tutan, hicbir kodun yazmadigi/okumadigi bos bir inis tablosuydu. Tampon artik
sikistirilmis bloklari (ingest_block) kullanir. Satir varsa islem durur (elle karar gerekir). Taze veritabaninda
0001 create_all artik bu tabloyu uretmedigi icin adim bir sey yapmaz.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_ingest_record_kaldir"
down_revision: str | Sequence[str] | None = "0005_yonetim_tampon"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if "ingest_record" not in sa.inspect(bind).get_table_names():
        return
    if bind.execute(sa.text("SELECT COUNT(*) FROM ingest_record")).scalar_one() != 0:
        raise RuntimeError("ingest_record bos degil; elle karar verilmeli")
    op.drop_table("ingest_record")


def downgrade() -> None:
    if "ingest_record" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "ingest_record",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("ingest_batch.id"), nullable=False),
        sa.Column("source_key", sa.String(40), nullable=False),
        sa.Column("external_key", sa.String(120), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
    )
