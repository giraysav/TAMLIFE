# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Utilizasyon: Urun-Tutar Excel ozeti (urun_tutar_ozet) ve skor gecmisinde eski skor (score_history.old_score).

Revision ID: 0003_utilizasyon
Revises: 0002_ad_kimlik
Create Date: 2026-10-10

Eski 0001 (create_all) ile kurulmus DB'de tablo/sutun zaten vardir; bu yuzden yalniz eksik olan eklenir. app.models import edilmez.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_utilizasyon"
down_revision: str | Sequence[str] | None = "0002_ad_kimlik"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bag = op.get_bind()
    if not sa.inspect(bag).has_table("urun_tutar_ozet"):
        op.create_table(
            "urun_tutar_ozet",
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("summary", sa.JSON(), nullable=False),
            sa.Column("file_name", sa.String(length=200), nullable=False),
            sa.Column("uploaded_by", sa.String(length=120), nullable=False),
            sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
            sa.PrimaryKeyConstraint("customer_id"),
        )
    if "old_score" not in {c["name"] for c in sa.inspect(bag).get_columns("score_history")}:
        with op.batch_alter_table("score_history") as toplu:
            toplu.add_column(sa.Column("old_score", sa.Float(), nullable=True))


def downgrade() -> None:
    bag = op.get_bind()
    if "old_score" in {c["name"] for c in sa.inspect(bag).get_columns("score_history")}:
        with op.batch_alter_table("score_history") as toplu:
            toplu.drop_column("old_score")
    if sa.inspect(bag).has_table("urun_tutar_ozet"):
        op.drop_table("urun_tutar_ozet")
