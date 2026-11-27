# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""app_user: AD kimligi (is_ad_user, ad_domain) ve yerel acil hesap parolasi (password_hash).

Revision ID: 0002_ad_kimlik
Revises: 0001_baslangic
Create Date: 2026-10-10

Eski 0001 (create_all) ile kurulmus DB'de sutunlar zaten vardir; bu yuzden yalniz eksik olan eklenir.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_ad_kimlik"
down_revision: str | Sequence[str] | None = "0001_baslangic"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUTUNLAR = (
    sa.Column("is_ad_user", sa.Boolean(), nullable=False, server_default=sa.false()),  # SQLite 0, PostgreSQL false
    sa.Column("ad_domain", sa.String(120), nullable=False, server_default=""),
    sa.Column("password_hash", sa.String(255), nullable=True),
)


def upgrade() -> None:
    mevcut = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("app_user")}
    eksik = [c for c in SUTUNLAR if c.name not in mevcut]
    if eksik:
        with op.batch_alter_table("app_user") as toplu:
            for sutun in eksik:
                toplu.add_column(sutun)


def downgrade() -> None:
    mevcut = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("app_user")}
    with op.batch_alter_table("app_user") as toplu:
        for sutun in SUTUNLAR:
            if sutun.name in mevcut:
                toplu.drop_column(sutun.name)
