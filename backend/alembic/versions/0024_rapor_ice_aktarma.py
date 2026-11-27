# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Gecmis aylik rapor ice aktarma (2026-10-31 kullanici: "eski raporlar ay ve yil secilerek musteri atamasiyla eklenebilsin; dosya genelde
Outlook dosyasi"): report_dispatch.source (panel | ice_aktarma), archive_file, archive_name.

Revision ID: 0024_rapor_ice_aktarma
Revises: 0023_talep_eden_bildirim
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_rapor_ice_aktarma"
down_revision: str | Sequence[str] | None = "0023_talep_eden_bildirim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUTUNLAR = (
    ("source", sa.String(20), {"nullable": False, "server_default": "panel"}),
    ("archive_file", sa.String(300), {"nullable": True}),
    ("archive_name", sa.String(200), {"nullable": True}),
)


def upgrade() -> None:
    var = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("report_dispatch")}
    with op.batch_alter_table("report_dispatch", recreate="never") as t:
        for ad, tur, ek in SUTUNLAR:
            if ad not in var:
                t.add_column(sa.Column(ad, tur, **ek))


def downgrade() -> None:
    with op.batch_alter_table("report_dispatch", recreate="never") as t:
        for ad, _, _ in reversed(SUTUNLAR):
            t.drop_column(ad)
