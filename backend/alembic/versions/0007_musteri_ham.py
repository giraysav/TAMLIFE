"""Ham Musteri Verisi aktarimi: customer_import_run (geri alma kaydi); customer.customer_no 50 -> 200 karakter
(bir kartta birden cok Musteri No virgulle tutulur).

Revision ID: 0007_musteri_ham
Revises: 0006_proje
Create Date: 2026-10-11

app.models import edilmez. Yeni model ile create_all kurulmus DB'de tablo zaten varsa yeniden kurulmaz.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_musteri_ham"
down_revision: str | Sequence[str] | None = "0006_proje"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("customer") as tablo:
        tablo.alter_column("customer_no", existing_type=sa.String(length=50), type_=sa.String(length=200), existing_nullable=True)
    if sa.inspect(op.get_bind()).has_table("customer_import_run"):
        return
    op.create_table(
        "customer_import_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("record", sa.JSON(), nullable=False),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverted_by", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("customer_import_run")
    with op.batch_alter_table("customer") as tablo:
        tablo.alter_column("customer_no", existing_type=sa.String(length=200), type_=sa.String(length=50), existing_nullable=True)
