"""Kullanilmayan radar_prospect tablosu kalkar (Musteri Radar ReportDB tamponundan okur, bu tabloya hic yazmaz).

Revision ID: 0010_radar_prospect_kaldir
Revises: 0009_gelir_uretim
Create Date: 2026-10-14

Tabloda satir varsa dokunulmaz (veri silinmez, acilis da durmaz); yalniz bos ise kaldirilir. app.models import edilmez.
Geri alma tabloyu bos olarak yeniden kurar (0001'in downgrade'i onu siler).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_radar_prospect_kaldir"
down_revision: str | Sequence[str] | None = "0009_gelir_uretim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bag = op.get_bind()
    if sa.inspect(bag).has_table("radar_prospect") and not bag.execute(sa.text("SELECT COUNT(*) FROM radar_prospect")).scalar():
        op.drop_table("radar_prospect")


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("radar_prospect"):
        op.create_table(
            "radar_prospect",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("stage", sa.String(length=40), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
