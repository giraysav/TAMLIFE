"""Denetim olaylari (2026-11-26 kullanici): giris yapan kullanicinin IP'si (audit_event.ip) ve kullaniciya gore agac gorunumu icin
actor indeksi.

Revision ID: 0032_denetim_ip
Revises: 0031_topo_kural_lokasyon
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0032_denetim_ip"
down_revision: str | Sequence[str] | None = "0031_topo_kural_lokasyon"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEKS = "ix_audit_event_actor_lower"


def upgrade() -> None:
    denetci = sa.inspect(op.get_bind())
    if "ip" not in {c["name"] for c in denetci.get_columns("audit_event")}:
        op.add_column("audit_event", sa.Column("ip", sa.String(64), nullable=False, server_default=""))
    if INDEKS not in {i["name"] for i in denetci.get_indexes("audit_event")}:
        op.create_index(INDEKS, "audit_event", [sa.text("lower(actor)")])


def downgrade() -> None:
    op.drop_index(INDEKS, table_name="audit_event")
    op.drop_column("audit_event", "ip")
