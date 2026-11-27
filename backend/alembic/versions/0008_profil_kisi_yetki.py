# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""app_user: profil alanlari (ad, soyad, telefon, sirket, adres, web) ve kisiye verilen ek yetkiler (permissions).

Revision ID: 0008_profil_kisi_yetki
Revises: 0007_musteri_ham
Create Date: 2026-10-12

app.models import edilmez. Sutunlar zaten varsa (create_all ile kurulmus DB) yeniden eklenmez.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_profil_kisi_yetki"
down_revision: str | Sequence[str] | None = "0007_musteri_ham"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUTUNLAR = (
    sa.Column("first_name", sa.String(100), nullable=False, server_default=""),
    sa.Column("last_name", sa.String(100), nullable=False, server_default=""),
    sa.Column("phone", sa.String(40), nullable=False, server_default=""),
    sa.Column("company", sa.String(200), nullable=False, server_default=""),
    sa.Column("address", sa.String(500), nullable=False, server_default=""),
    sa.Column("website", sa.String(200), nullable=False, server_default=""),
    sa.Column("permissions", sa.JSON(), nullable=True),
)


def upgrade() -> None:
    mevcut = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("app_user")}
    eksik = [c for c in SUTUNLAR if c.name not in mevcut]
    if eksik:
        with op.batch_alter_table("app_user") as toplu:
            for sutun in eksik:
                toplu.add_column(sutun)


def downgrade() -> None:
    mevcut = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("app_user")}
    with op.batch_alter_table("app_user") as toplu:
        for sutun in SUTUNLAR:
            if sutun.name in mevcut:
                toplu.drop_column(sutun.name)
