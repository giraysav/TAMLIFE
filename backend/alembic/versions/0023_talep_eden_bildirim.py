# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Gelistirme talebinde talep eden ve gelis yolu; kisiye ozel bildirim (2026-10-31 kullanici: "talep eden kisi bilgisi ve
kullanici adi olsun, talep eden secilebilir olsun - talep mail yoluyla da gelebilir; durum degisince talep sahibine bildirim gitsin").
demand.requester_id (bos = talebi giren kisi, mevcut satirlar giren kisiyle doldurulur), demand.channel; user_notification tablosu.

Revision ID: 0023_talep_eden_bildirim
Revises: 0022_rapor_muaf
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_talep_eden_bildirim"
down_revision: str | Sequence[str] | None = "0022_rapor_muaf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bakis = sa.inspect(op.get_bind())
    if "requester_id" not in {c["name"] for c in bakis.get_columns("demand")}:
        with op.batch_alter_table("demand") as t:
            t.add_column(sa.Column("requester_id", sa.Integer(), nullable=True))
            t.add_column(sa.Column("channel", sa.String(20), nullable=False, server_default="panel"))
            t.create_foreign_key("fk_demand_requester_id_app_user", "app_user", ["requester_id"], ["id"])
            t.create_index("ix_demand_requester_id", ["requester_id"])
        op.execute("UPDATE demand SET requester_id = opened_by_id WHERE requester_id IS NULL")
    if not bakis.has_table("user_notification"):
        op.create_table(
            "user_notification",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=False),
            sa.Column("kind", sa.String(30), nullable=False),
            sa.Column("ref_id", sa.Integer(), nullable=True),
            sa.Column("message", sa.String(400), nullable=False),
            sa.Column("link", sa.String(200), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_user_notification_user_id", "user_notification", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_notification_user_id", table_name="user_notification")
    op.drop_table("user_notification")
    with op.batch_alter_table("demand") as t:
        t.drop_index("ix_demand_requester_id")
        t.drop_constraint("fk_demand_requester_id_app_user", type_="foreignkey")
        t.drop_column("channel")
        t.drop_column("requester_id")
