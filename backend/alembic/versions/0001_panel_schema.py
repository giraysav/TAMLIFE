"""Panel schema and external source slots.

Revision ID: 0001_panel_schema
Revises:
Create Date: 2026-10-03

"""

from collections.abc import Sequence

from alembic import op
from app.models import Base

revision: str = "0001_panel_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
