"""Gelir Faydasi Saglanan Isler: revenue_benefit ve revenue_benefit_person tablolari; bos income_production iskeleti kalkar.

Revision ID: 0009_gelir_uretim
Revises: 0008_profil_kisi_yetki
Create Date: 2026-10-13

0001'deki income_production (period/label/amount) hicbir kod tarafindan yazilmayan bos bir iskeletti; yerini revenue_benefit alir.
Iskelette satir varsa dokunulmaz (veri silinmez, acilis da durmaz); yalniz bos ise kaldirilir.
Yeni modelle create_all ile kurulmus DB'de tablolar zaten vardir, yeniden olusturulmaz. app.models import edilmez.
Geri alma income_production'i bos olarak yeniden kurar (0001'in downgrade'i onu siler).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_gelir_uretim"
down_revision: str | Sequence[str] | None = "0008_profil_kisi_yetki"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bag = op.get_bind()
    bakis = sa.inspect(bag)
    if not bakis.has_table("revenue_benefit"):
        op.create_table(
            "revenue_benefit",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False),
            sa.Column("benefit_type", sa.String(length=20), nullable=False),
            sa.Column("title", sa.String(length=300), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("status_note", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("customers", sa.String(length=500), nullable=False),
            sa.Column("revenue_amount", sa.Float(), nullable=True),
            sa.Column("revenue_currency", sa.String(length=3), nullable=False),
            sa.Column("revenue_period", sa.String(length=10), nullable=False),
            sa.Column("revenue_note", sa.String(length=500), nullable=False),
            sa.Column("year_revenue", sa.Float(), nullable=True),
            sa.Column("hours_per_month", sa.Float(), nullable=True),
            sa.Column("hours_note", sa.String(length=500), nullable=False),
            sa.Column("extra_note", sa.Text(), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("other_people", sa.String(length=300), nullable=False),
            sa.Column("created_by", sa.String(length=200), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_by", sa.String(length=200), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not bakis.has_table("revenue_benefit_person"):
        op.create_table(
            "revenue_benefit_person",
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["item_id"], ["revenue_benefit.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["app_user.id"]),
            sa.PrimaryKeyConstraint("item_id", "user_id"),
        )
    if bakis.has_table("income_production") and not bag.execute(sa.text("SELECT COUNT(*) FROM income_production")).scalar():
        op.drop_table("income_production")


def downgrade() -> None:
    bakis = sa.inspect(op.get_bind())
    if bakis.has_table("revenue_benefit_person"):
        op.drop_table("revenue_benefit_person")
    if bakis.has_table("revenue_benefit"):
        op.drop_table("revenue_benefit")
    if not bakis.has_table("income_production"):
        op.create_table(
            "income_production",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("period", sa.String(length=20), nullable=False),
            sa.Column("label", sa.String(length=200), nullable=False),
            sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
