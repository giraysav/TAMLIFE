"""Tek audit_event tablosu. Gizli kolon yok.

Revision ID: 0002_audit
Revises: 0001_users
Create Date: 2026-10-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_audit"
down_revision = "0001_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("path", sa.String(length=256), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("audit_event")
