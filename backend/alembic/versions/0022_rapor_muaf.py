# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Raporu atilmayan musteri (2026-10-31 kullanici: "musteri bilgisinde raporu atilmamaktadir diye bir tik"): customer.report_exempt.
Isaretli birim Gonderilen Aylik Rapor durum ozetinde bekleyen sayilmaz.

Revision ID: 0022_rapor_muaf
Revises: 0021_kurumsal_imza
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_rapor_muaf"
down_revision: str | Sequence[str] | None = "0021_kurumsal_imza"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "report_exempt" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("customer")}:
        with op.batch_alter_table("customer", recreate="never") as t:
            t.add_column(sa.Column("report_exempt", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("customer", recreate="never") as t:
        t.drop_column("report_exempt")
