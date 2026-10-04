"""Final skor tablolari ve musteri sahip/ust/skor alanlari.

Revision ID: 0002_final_skor
Revises: 0001_panel_schema
Create Date: 2026-10-04

0001 `Base.metadata.create_all` kullandigi icin taze veritabaninda bu tablolar zaten gelir;
mevcut (0001'li) veritabaninda eksik olani ekler. Bu yuzden adimlar tekrar calisabilir.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models import Base

revision: str = "0002_final_skor"
down_revision: str | Sequence[str] | None = "0001_panel_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

YENI_TABLOLAR = (
    "util_criteria_set",
    "score_detail",
    "score_history",
    "score_approval_request",
    "scoring_exclusion",
    "affiliate_final_flag",
)
ESKI_TABLOLAR = ("utilization_score", "utilization_criterion")  # bos, yerine yenileri geldi


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    mevcut = set(insp.get_table_names())

    sutunlar = {c["name"] for c in insp.get_columns("customer")} if "customer" in mevcut else set()
    if "customer" in mevcut:
        with op.batch_alter_table("customer") as batch:
            if "owner_id" not in sutunlar:
                batch.add_column(sa.Column("owner_id", sa.Integer(), sa.ForeignKey("app_user.id", name="fk_customer_owner"), nullable=True))
            if "parent_id" not in sutunlar:
                batch.add_column(sa.Column("parent_id", sa.Integer(), sa.ForeignKey("customer.id", name="fk_customer_parent"), nullable=True))
            if "score" not in sutunlar:
                batch.add_column(sa.Column("score", sa.Float(), nullable=True))

    Base.metadata.create_all(bind, tables=[Base.metadata.tables[n] for n in YENI_TABLOLAR], checkfirst=True)

    for ad in ESKI_TABLOLAR:
        if ad in mevcut:
            satir = bind.execute(sa.text(f"SELECT COUNT(*) FROM {ad}")).scalar_one()
            if satir:
                raise RuntimeError(f"{ad} bos degil; elle tasinmali")
            op.drop_table(ad)


def downgrade() -> None:
    for ad in reversed(YENI_TABLOLAR):
        op.drop_table(ad)
    with op.batch_alter_table("customer") as batch:
        batch.drop_constraint("fk_customer_parent", type_="foreignkey")
        batch.drop_constraint("fk_customer_owner", type_="foreignkey")
        for ad in ("score", "parent_id", "owner_id"):
            batch.drop_column(ad)
