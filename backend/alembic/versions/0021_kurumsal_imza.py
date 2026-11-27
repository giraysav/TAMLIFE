# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Kurumsal e-posta imzasi (2026-10-26 kullanici: "imza.html tasarimini panele tasiyalim"): app_user.signature_mode, title,
department, landline, email. Mevcut serbest imzasi olan kisi 'serbest' kipine alinir.

Revision ID: 0021_kurumsal_imza
Revises: 0020_profil_imza
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_kurumsal_imza"
down_revision: str | Sequence[str] | None = "0020_profil_imza"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUTUNLAR = (("signature_mode", 20), ("title", 120), ("department", 120), ("landline", 40), ("email", 200))


def upgrade() -> None:
    var = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("app_user")}
    with op.batch_alter_table("app_user", recreate="never") as t:
        for ad, boy in SUTUNLAR:
            if ad not in var:
                t.add_column(sa.Column(ad, sa.String(boy), nullable=False, server_default=""))
    op.execute("UPDATE app_user SET signature_mode = 'serbest' WHERE coalesce(signature_html, '') <> '' AND coalesce(signature_mode, '') = ''")


def downgrade() -> None:
    with op.batch_alter_table("app_user", recreate="never") as t:
        for ad, _ in reversed(SUTUNLAR):
            t.drop_column(ad)
