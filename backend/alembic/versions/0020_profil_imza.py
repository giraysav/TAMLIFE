"""Profil e-posta imzasi (2026-10-26 kullanici: "adres alanini kaldir, yerine Outlook'taki gibi resim + yazi imza; aylik rapor mail
govdesinde de olacak"; ayni gun: "acik adres olmayacak, olan varsa da temizle"): app_user.signature_html eklenir, app_user.address
silinir (dolu adresler de gider; once yedek). Geri alma adres sutununu bos olarak geri ekler.

Revision ID: 0020_profil_imza
Revises: 0019_cacti_kaldir
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_profil_imza"
down_revision: str | Sequence[str] | None = "0019_cacti_kaldir"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sutunlar = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("app_user")}
    with op.batch_alter_table("app_user", recreate="never") as t:
        if "signature_html" not in sutunlar:
            t.add_column(sa.Column("signature_html", sa.Text(), nullable=False, server_default=""))
        if "address" in sutunlar:
            t.drop_column("address")


def downgrade() -> None:
    with op.batch_alter_table("app_user", recreate="never") as t:
        t.drop_column("signature_html")
        t.add_column(sa.Column("address", sa.String(500), nullable=False, server_default=""))
