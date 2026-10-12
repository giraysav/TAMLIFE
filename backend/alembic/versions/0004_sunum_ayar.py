"""Ceyrek bazli sunum: panel ayari tablosu (app_setting) ve rol ek yetkisi takvim.sunuma_gonder -> sunum.gonder.

Revision ID: 0004_sunum_ayar
Revises: 0003_utilizasyon
Create Date: 2026-10-10

Eski 0001 (create_all) ile kurulmus DB'de tablo zaten vardir; bu yuzden yalniz eksikse eklenir. app.models import edilmez.
Kayitli rol yetkileri yeni kimlige tasinir (yetki kaybolmaz); downgrade geri cevirir.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_sunum_ayar"
down_revision: str | Sequence[str] | None = "0003_utilizasyon"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL = sa.table("role_view", sa.column("role", sa.String), sa.column("permissions", sa.JSON))


def _yetki_tasi(eski: str, yeni: str) -> None:
    bag = op.get_bind()
    for rol, yetkiler in bag.execute(sa.select(ROL.c.role, ROL.c.permissions)).all():
        if isinstance(yetkiler, list) and eski in yetkiler:
            temiz = sorted({yeni if y == eski else y for y in yetkiler})
            bag.execute(ROL.update().where(ROL.c.role == rol).values(permissions=temiz))


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("app_setting"):
        op.create_table(
            "app_setting",
            sa.Column("key", sa.String(length=80), nullable=False),
            sa.Column("value", sa.JSON(), nullable=False),
            sa.Column("updated_by", sa.String(length=120), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("key"),
        )
    _yetki_tasi("takvim.sunuma_gonder", "sunum.gonder")


def downgrade() -> None:
    _yetki_tasi("sunum.gonder", "takvim.sunuma_gonder")
    if sa.inspect(op.get_bind()).has_table("app_setting"):
        op.drop_table("app_setting")
