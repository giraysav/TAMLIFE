"""customer.modul: Musteri Yonetimi / Toptan / Baglantili Araclar kartlari ayri (2026-10-19 kullanici istegi).

Revision ID: 0016_musteri_alani
Revises: 0015_onedesk_kayit_indeksleri
Create Date: 2026-10-19

Var olan kartlarin hepsi Musteri Yonetimi'nindir ('musteri'); Toptan ve Baglantili Araclar bos baslar (app.musteri_alani).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_musteri_alani"
down_revision: str | Sequence[str] | None = "0015_onedesk_kayit_indeksleri"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    denetci = sa.inspect(op.get_bind())
    sutunlar = {s["name"] for s in denetci.get_columns("customer")}
    indeksler = {i["name"] for i in denetci.get_indexes("customer")}
    with op.batch_alter_table("customer") as tablo:
        if "modul" not in sutunlar:
            tablo.add_column(sa.Column("modul", sa.String(length=20), nullable=False, server_default="musteri"))
        if "ix_customer_modul" not in indeksler:
            tablo.create_index("ix_customer_modul", ["modul"])


def downgrade() -> None:
    with op.batch_alter_table("customer") as tablo:
        tablo.drop_index("ix_customer_modul")
        tablo.drop_column("modul")
