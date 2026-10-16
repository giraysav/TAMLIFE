"""revenue_benefit: Yol Haritasi, yillik verimlilik ve onay akisi sutunlari (2026-10-15 kullanici istegi).

Revision ID: 0011_gelir_onay
Revises: 0010_radar_prospect_kaldir
Create Date: 2026-10-15

Mevcut kayitlar onayli sayilir (server_default 'onayli'): canli veri ve sunum degismez. app.models import edilmez.
Sutunlar zaten varsa (create_all ile kurulmus DB) yeniden eklenmez.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_gelir_onay"
down_revision: str | Sequence[str] | None = "0010_radar_prospect_kaldir"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUTUNLAR = (
    sa.Column("hours_per_year", sa.Float(), nullable=True),
    sa.Column("roadmap", sa.Text(), nullable=False, server_default=""),
    sa.Column("approval", sa.String(length=20), nullable=False, server_default="onayli"),
    sa.Column("approval_note", sa.Text(), nullable=False, server_default=""),
    sa.Column("approved_by", sa.String(length=200), nullable=False, server_default=""),
    sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_by_id", sa.Integer(), nullable=True),
)


def upgrade() -> None:
    mevcut = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("revenue_benefit")}
    eksik = [c for c in SUTUNLAR if c.name not in mevcut]
    if eksik:
        with op.batch_alter_table("revenue_benefit") as toplu:
            for sutun in eksik:
                toplu.add_column(sutun)


def downgrade() -> None:
    mevcut = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("revenue_benefit")}
    with op.batch_alter_table("revenue_benefit") as toplu:
        for sutun in SUTUNLAR:
            if sutun.name in mevcut:
                toplu.drop_column(sutun.name)
