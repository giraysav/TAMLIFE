# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Bildirim yaniti (2026-11-27): Erken Uyari bildirimine TAM'in "ilgilendim / gerekmedi" geri bildirimi (user_notification.response).

Revision ID: 0033_bildirim_yanit
Revises: 0032_denetim_ip
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033_bildirim_yanit"
down_revision: str | Sequence[str] | None = "0032_denetim_ip"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sutunlar = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("user_notification")}
    if "response" not in sutunlar:
        op.add_column("user_notification", sa.Column("response", sa.String(20), nullable=False, server_default=""))
    if "responded_at" not in sutunlar:
        op.add_column("user_notification", sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("user_notification", "responded_at")
    op.drop_column("user_notification", "response")
