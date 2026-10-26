"""Cacti kaldirildi (2026-10-26 kullanici: "aylik rapor CACTI alanini kaldir, buraya bagli sifre vb baglamlari da yok et; yalniz
GALAPAGOS'tan veri girisi"): customer.cacti_urls ve report.cacti_data sutunlari silinir.

Revision ID: 0019_cacti_kaldir
Revises: 0018_wholesale_toptan
Create Date: 2026-10-26

Tablo yeniden kurulmaz (recreate="never": ALTER TABLE ... DROP COLUMN; SQLite >= 3.35). Geri alma sutunlari bos olarak geri ekler;
silinen baglanti adresleri geri gelmez (once yedek: Yonetim > Veritabani).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_cacti_kaldir"
down_revision: str | Sequence[str] | None = "0018_wholesale_toptan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _sutunlar(tablo: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tablo)}


def upgrade() -> None:
    # Modelden (create_all) kurulmus eski veritabaninda sutun hic olmayabilir: yalniz varsa silinir.
    for tablo, sutun in (("customer", "cacti_urls"), ("report", "cacti_data")):
        if sutun in _sutunlar(tablo):
            with op.batch_alter_table(tablo, recreate="never") as t:
                t.drop_column(sutun)


def downgrade() -> None:
    with op.batch_alter_table("customer", recreate="never") as t:
        t.add_column(sa.Column("cacti_urls", sa.JSON(), nullable=False, server_default="[]"))
    with op.batch_alter_table("report", recreate="never") as t:
        t.add_column(sa.Column("cacti_data", sa.Text(), nullable=True))
