"""Kaynak katalogu (ham tampon): source_catalog + source_catalog_object (2026-10-18 kullanici istegi: ReportDB TEMIP semasinin
tablo -> alt tablo -> sutun agaci ve ornek satirlari Veri Girisi'nde).

Revision ID: 0014_kaynak_katalog
Revises: 0013_onedesk_temip
Create Date: 2026-10-18

app.models import edilmez; tablo varsa yeniden olusturulmaz.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_kaynak_katalog"
down_revision: str | Sequence[str] | None = "0013_onedesk_temip"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    ins = sa.inspect(op.get_bind())
    if not ins.has_table("source_catalog"):
        op.create_table(
            "source_catalog",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("source_key", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.String(length=120), nullable=False),
            sa.Column("summary", sa.JSON(), nullable=False),
            sa.Column("error", sa.String(length=500), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not ins.has_table("source_catalog_object"):
        op.create_table(
            "source_catalog_object",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("catalog_id", sa.Integer(), nullable=False),
            sa.Column("owner", sa.String(length=128), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("kind", sa.String(length=30), nullable=False),
            sa.Column("parent", sa.String(length=260), nullable=False),
            sa.Column("row_count", sa.BigInteger(), nullable=True),
            sa.Column("analyzed", sa.String(length=20), nullable=False),
            sa.Column("comment", sa.String(length=1000), nullable=False),
            sa.Column("columns", sa.JSON(), nullable=False),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("sample_columns", sa.JSON(), nullable=False),
            sa.Column("sample_rows", sa.Integer(), nullable=False),
            sa.Column("sample_note", sa.String(length=300), nullable=False),
            sa.Column("sample_data", sa.LargeBinary(), nullable=True),
            sa.ForeignKeyConstraint(["catalog_id"], ["source_catalog.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_source_catalog_object_catalog_id", "source_catalog_object", ["catalog_id"])


def downgrade() -> None:
    op.drop_index("ix_source_catalog_object_catalog_id", table_name="source_catalog_object")
    op.drop_table("source_catalog_object")
    op.drop_table("source_catalog")
