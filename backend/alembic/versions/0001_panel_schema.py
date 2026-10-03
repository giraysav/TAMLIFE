"""Panel schema and external source slots.

Revision ID: 0001_panel_schema
Revises:
Create Date: 2026-10-03

"""

from typing import Sequence, Union

from alembic import op

from app.models import Base, seed_source_slots

revision: str = "0001_panel_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    seed_source_slots(bind)


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
