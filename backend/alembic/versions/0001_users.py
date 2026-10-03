"""Bos sema: users. pin_code ve totp_secret yok. Veri INSERT yok.

Revision ID: 0001_users
Revises:
Create Date: 2026-10-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_users"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("full_name", sa.String(length=256), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("allowed_modules", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ad_domain", sa.String(length=128), nullable=True),
        sa.Column("is_ad_user", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_2fa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )


def downgrade() -> None:
    op.drop_table("users")
