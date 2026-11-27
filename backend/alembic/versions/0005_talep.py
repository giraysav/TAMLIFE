# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Gelistirme talepleri: demand / demand_log iskeleti uretimdeki talep formu ve degisiklik gecmisi semasina cevrilir.

Revision ID: 0005_talep
Revises: 0004_sunum_ayar
Create Date: 2026-10-10

0001'deki iskelet tablolari (demand: title/status/opened_by, demand_log: at/note) hicbir kod yazmiyordu; bu yuzden
bos olduklari surece kaldirilip yeni semayla kurulur. Satir varsa goc durur (veri sessizce silinmez).
Yeni model ile create_all kurulmus DB'de (sutun 'kind' zaten var) islem yapilmaz. app.models import edilmez.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_talep"
down_revision: str | Sequence[str] | None = "0004_sunum_ayar"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _yeni_sema_var() -> bool:
    bakis = sa.inspect(op.get_bind())
    return bakis.has_table("demand") and "kind" in {c["name"] for c in bakis.get_columns("demand")}


def _bos_olmali(tablo: str) -> None:
    bag = op.get_bind()
    if sa.inspect(bag).has_table(tablo) and bag.execute(sa.text(f"SELECT COUNT(*) FROM {tablo}")).scalar():
        raise RuntimeError(f"{tablo} tablosunda kayit var; 0005_talep iskelet tabloyu yeniden kuramaz. Kayitlari tasiyip tekrar deneyin.")


def upgrade() -> None:
    if _yeni_sema_var():
        return
    for tablo in ("demand_log", "demand"):
        _bos_olmali(tablo)
    bakis = sa.inspect(op.get_bind())
    if bakis.has_table("demand_log"):
        op.drop_table("demand_log")
    if bakis.has_table("demand"):
        op.drop_table("demand")
    op.create_table(
        "demand",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("module", sa.String(length=40), nullable=False),
        sa.Column("current_state", sa.Text(), nullable=False),
        sa.Column("expected_state", sa.Text(), nullable=False),
        sa.Column("acceptance", sa.Text(), nullable=False),
        sa.Column("opened_by_id", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("assignee_id", sa.Integer(), nullable=True),
        sa.Column("target_version", sa.String(length=40), nullable=False),
        sa.Column("admin_note", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assignee_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["opened_by_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_demand_opened_by_id", "demand", ["opened_by_id"])
    op.create_index("ix_demand_status", "demand", ["status"])
    op.create_table(
        "demand_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("demand_id", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(length=30), nullable=False),
        sa.Column("old_value", sa.String(length=200), nullable=False),
        sa.Column("new_value", sa.String(length=200), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["demand_id"], ["demand.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_demand_log_demand_id", "demand_log", ["demand_id"])


def downgrade() -> None:
    for tablo in ("demand_log", "demand"):
        _bos_olmali(tablo)
    op.drop_index("ix_demand_log_demand_id", table_name="demand_log")
    op.drop_table("demand_log")
    op.drop_index("ix_demand_status", table_name="demand")
    op.drop_index("ix_demand_opened_by_id", table_name="demand")
    op.drop_table("demand")
    op.create_table(
        "demand",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("opened_by", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "demand_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("demand_id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(["demand_id"], ["demand.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
