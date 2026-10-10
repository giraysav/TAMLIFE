"""Utilizasyon: Urun-Tutar Excel ozeti (urun_tutar_ozet) ve skor gecmisinde eski skor (score_history.old_score).

Revision ID: 0003_utilizasyon
Revises: 0002_ad_kimlik
Create Date: 2026-10-10

0001 canli modelden create_all yaptigi icin taze veritabaninda tablo/sutun zaten vardir; yalniz eksik olan eklenir.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models import UrunTutarOzet

revision: str = "0003_utilizasyon"
down_revision: str | Sequence[str] | None = "0002_ad_kimlik"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bag = op.get_bind()
    UrunTutarOzet.__table__.create(bag, checkfirst=True)
    if "old_score" not in {c["name"] for c in sa.inspect(bag).get_columns("score_history")}:
        with op.batch_alter_table("score_history") as toplu:
            toplu.add_column(sa.Column("old_score", sa.Float(), nullable=True))


def downgrade() -> None:
    bag = op.get_bind()
    if "old_score" in {c["name"] for c in sa.inspect(bag).get_columns("score_history")}:
        with op.batch_alter_table("score_history") as toplu:
            toplu.drop_column("old_score")
    UrunTutarOzet.__table__.drop(bag, checkfirst=True)
