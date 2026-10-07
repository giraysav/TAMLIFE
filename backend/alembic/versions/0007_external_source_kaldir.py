"""Kullanilmayan external_source tablosunu kaldirir.

Revision ID: 0007_external_source_kaldir
Revises: 0006_ingest_record_kaldir
Create Date: 2026-10-07

Tablo yalniz 0001'de kaynak yuvalariyla (anahtar adi, enabled=false) tohumlaniyordu; hicbir kod okumuyor/yazmiyordu.
Kaynak listesi artik kodda (app.external.SOURCES). Etkin (enabled=true) satir varsa islem durur (elle karar gerekir).
Taze veritabaninda 0001 create_all artik bu tabloyu uretmedigi icin adim bir sey yapmaz.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_external_source_kaldir"
down_revision: str | Sequence[str] | None = "0006_ingest_record_kaldir"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if "external_source" not in sa.inspect(bind).get_table_names():
        return
    if bind.execute(sa.text("SELECT COUNT(*) FROM external_source WHERE enabled")).scalar_one() != 0:
        raise RuntimeError("external_source icinde etkin satir var; elle karar verilmeli")
    op.drop_table("external_source")


def downgrade() -> None:
    if "external_source" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "external_source",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_key", sa.String(40), nullable=False, unique=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("dsn_env", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
