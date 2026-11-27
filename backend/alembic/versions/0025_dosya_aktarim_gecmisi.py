# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Elle yuklenen dosya aktarimlarinin geri alinabilir gecmisi (2026-11-01 kullanici: "urun-tutar'i eklenen musteri icin geri alma
secenegi yok; importa manuel eklenen dosya olursa geri alma secenegi de olmali"): file_import_run.

Revision ID: 0025_dosya_aktarim_gecmisi
Revises: 0024_rapor_ice_aktarma
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_dosya_aktarim_gecmisi"
down_revision: str | Sequence[str] | None = "0024_rapor_ice_aktarma"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "file_import_run" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "file_import_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("file_name", sa.String(200), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(120), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("record", sa.JSON(), nullable=False),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverted_by", sa.String(120), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("file_import_run")
