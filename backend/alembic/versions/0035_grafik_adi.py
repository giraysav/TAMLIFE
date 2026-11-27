"""Rapor devre grafigi adi kullanicinin (2026-11-27 kullanici: "grafige kullanici kendisi isim versin; ONENT ya da CMDB'den aldigi
detaylari yazmasin"). report_circuit.label bugune kadar hep otomatik (CMDB / envanter ayrintisi) uretildi; bosaltilir, baslik CI adi
olur, kullanici panelden ad verir. Geri alinmaz.

Revision ID: 0035_grafik_adi
Revises: 0034_devre_etiketi_ip
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0035_grafik_adi"
down_revision: str | Sequence[str] | None = "0034_devre_etiketi_ip"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "report_circuit" in sa.inspect(op.get_bind()).get_table_names():
        op.execute(sa.text("UPDATE report_circuit SET label = ''"))


def downgrade() -> None:
    pass  # otomatik etiketler yeniden uretilmez
