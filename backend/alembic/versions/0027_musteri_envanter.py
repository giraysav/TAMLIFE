# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Musteri envanteri / Kritik CI (2026-11-20 kullanici: "onent'ten gelen NEMS_CMDB verilerinde musteri no ile eslesen CI'lari musteri
kartindaki KRITIK CI alanina ekle; kritik ci artik excel ile degil onent db'den dinamik beslenecek"): customer_ci.

Revision ID: 0027_musteri_envanter
Revises: 0026_rapor_devre_grafik
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_musteri_envanter"
down_revision: str | Sequence[str] | None = "0026_rapor_devre_grafik"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "customer_ci" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "customer_ci",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_key", sa.String(40), nullable=False),
        sa.Column("ci_no", sa.String(40), nullable=False),
        sa.Column("ci_name", sa.String(300), nullable=False),
        sa.Column("service", sa.String(200), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("attrs", sa.JSON(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_customer_ci_customer_key", "customer_ci", ["customer_key"])


def downgrade() -> None:
    op.drop_index("ix_customer_ci_customer_key", "customer_ci")
    op.drop_table("customer_ci")
