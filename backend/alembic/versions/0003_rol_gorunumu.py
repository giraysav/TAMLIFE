"""Rol gorunumu tablosu; Toptan modulu tablosunun kaldirilmasi.

Revision ID: 0003_rol_gorunumu
Revises: 0002_final_skor
Create Date: 2026-10-04

0001 `create_all` kullandigi icin taze veritabaninda role_view zaten gelir; adimlar tekrar calisabilir.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models import Base

revision: str = "0003_rol_gorunumu"
down_revision: str | Sequence[str] | None = "0002_final_skor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind, tables=[Base.metadata.tables["role_view"]], checkfirst=True)
    if "wholesale_item" in sa.inspect(bind).get_table_names():
        satir = bind.execute(sa.text("SELECT COUNT(*) FROM wholesale_item")).scalar_one()
        if satir:
            raise RuntimeError("wholesale_item bos degil; elle tasinmali")
        op.drop_table("wholesale_item")


def downgrade() -> None:
    op.drop_table("role_view")
