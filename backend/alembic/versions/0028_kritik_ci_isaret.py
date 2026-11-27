# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Kritik CI isareti (2026-11-20 kullanici: "satirin yaninda KRITIK CI ise EVET / HAYIR secimi yapacak dropdown koy; kritik ci
secildiginde satir diger satir renklerinden farkli olsun"): customer_ci_flag.

Revision ID: 0028_kritik_ci_isaret
Revises: 0027_musteri_envanter
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_kritik_ci_isaret"
down_revision: str | Sequence[str] | None = "0027_musteri_envanter"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "customer_ci_flag" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "customer_ci_flag",
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id"), primary_key=True),
        sa.Column("ci_no", sa.String(40), primary_key=True),
        sa.Column("critical", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_by", sa.String(120), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("customer_ci_flag")
