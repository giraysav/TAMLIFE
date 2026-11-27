# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Utilizasyon veri ozeti: ONENT envanterinden servis kategorileri ve baglanti tipleri (2026-11-21 kullanici: "Servis Cesitliligi ve
Baglanti Tipi ONENT'ten doldurulsun").

Revision ID: 0030_util_ozet_servis
Revises: 0029_util_veri_ozeti
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030_util_ozet_servis"
down_revision: str | Sequence[str] | None = "0029_util_veri_ozeti"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    mevcut = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("util_source_summary")}
    for ad in ("servisler", "baglanti"):
        if ad not in mevcut:
            op.add_column("util_source_summary", sa.Column(ad, sa.JSON(), nullable=True))


def downgrade() -> None:
    for ad in ("baglanti", "servisler"):
        op.drop_column("util_source_summary", ad)
