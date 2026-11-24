"""TopoMaker cizim kurallari (2026-11-24 kullanici): kartta duzeltilmis CI lokasyon adi (customer_ci_flag.location_name) ve
Urun-Tutar aktif devre no / acik adres listesi (urun_tutar_ozet.circuits).

Revision ID: 0031_topo_kural_lokasyon
Revises: 0030_util_ozet_servis
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031_topo_kural_lokasyon"
down_revision: str | Sequence[str] | None = "0030_util_ozet_servis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _sutunlar(tablo: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tablo)}


def upgrade() -> None:
    if "location_name" not in _sutunlar("customer_ci_flag"):
        op.add_column("customer_ci_flag", sa.Column("location_name", sa.String(300), nullable=True))
    if "circuits" not in _sutunlar("urun_tutar_ozet"):
        op.add_column("urun_tutar_ozet", sa.Column("circuits", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("urun_tutar_ozet", "circuits")
    op.drop_column("customer_ci_flag", "location_name")
