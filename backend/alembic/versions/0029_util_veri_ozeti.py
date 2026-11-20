"""Utilizasyon veri ozeti (2026-11-21 kullanici: "her sabah 06:00'da isci calissin ve skoru guncellesin; skor hesabi icin kapanmis
kayitlari baz alacagiz"): util_source_summary.

Revision ID: 0029_util_veri_ozeti
Revises: 0028_kritik_ci_isaret
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029_util_veri_ozeti"
down_revision: str | Sequence[str] | None = "0028_kritik_ci_isaret"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "util_source_summary" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "util_source_summary",
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id"), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("alarm", sa.Integer(), nullable=True),
        sa.Column("sikayet", sa.Integer(), nullable=True),
        sa.Column("talep", sa.Integer(), nullable=True),
        sa.Column("ci", sa.Integer(), nullable=True),
        sa.Column("lokasyon", sa.Integer(), nullable=True),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("util_source_summary")
