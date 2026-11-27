# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Takip edilen projeler: project / project_item / project_action iskeleti uretimdeki proje takibi semasina cevrilir,
musteri bazli calisma isaretleri (project_customer_work) eklenir.

Revision ID: 0006_proje
Revises: 0005_talep
Create Date: 2026-10-10

0001'deki iskelet tablolari hicbir kod yazmiyordu; bos olduklari surece kaldirilip yeni semayla kurulur. Satir varsa goc durur
(veri sessizce silinmez). Uretimdeki yil/ceyrek sayi tablosu (projects) tasinmadi: uretimde de yalniz Excel semasi icindi,
ozet tekil projelerden hesaplanir. Yeni model ile create_all kurulmus DB'de islem yapilmaz. app.models import edilmez.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_proje"
down_revision: str | Sequence[str] | None = "0005_talep"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ISKELET = ("project_action", "project_item", "project")


def _bos_olmali(tablo: str) -> None:
    bag = op.get_bind()
    if sa.inspect(bag).has_table(tablo) and bag.execute(sa.text(f"SELECT COUNT(*) FROM {tablo}")).scalar():
        raise RuntimeError(f"{tablo} tablosunda kayit var; 0006_proje iskelet tabloyu yeniden kuramaz. Kayitlari tasiyip tekrar deneyin.")


def upgrade() -> None:
    bakis = sa.inspect(op.get_bind())
    if bakis.has_table("project_customer_work"):
        return
    for tablo in ISKELET:
        _bos_olmali(tablo)
    for tablo in ISKELET:
        if bakis.has_table(tablo):
            op.drop_table(tablo)
    op.create_table(
        "project_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("closed_date", sa.Date(), nullable=True),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_item_owner_id", "project_item", ["owner_id"])
    op.create_index("ix_project_item_status", "project_item", ["status"])
    op.create_table(
        "project_action",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["project_item.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_action_item_id", "project_action", ["item_id"])
    op.create_table(
        "project_customer_work",
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.String(length=200), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("customer_id", "category"),
    )


def downgrade() -> None:
    for tablo in ("project_customer_work", "project_action", "project_item"):
        _bos_olmali(tablo)
    op.drop_table("project_customer_work")
    op.drop_index("ix_project_action_item_id", table_name="project_action")
    op.drop_table("project_action")
    op.drop_index("ix_project_item_status", table_name="project_item")
    op.drop_index("ix_project_item_owner_id", table_name="project_item")
    op.drop_table("project_item")
    op.create_table(
        "project",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "project_action",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=False),
        sa.Column("acted_on", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "project_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
