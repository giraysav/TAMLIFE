"""Devre trafigi 5 dakikalik ayri seride (2026-11-27 kullanici: "LookOutEyes gosterimi ile ayni veriler"): report_circuit_data.traffic
[[epoch_sn, giris bps, cikis bps], ...]. Panel LookOutEyes'in arsiv kuraliyla (5 dk / 30 dk / 2 saat / 1 gun) konsolide eder. Eski saatlik
trafik (noktalarin 6-7. alani) bir sonraki isci turunda yeniden cekilir (summary.trafik_surum).

Revision ID: 0036_devre_trafik_5dk
Revises: 0035_grafik_adi
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036_devre_trafik_5dk"
down_revision: str | Sequence[str] | None = "0035_grafik_adi"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "traffic" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("report_circuit_data")}:
        op.add_column("report_circuit_data", sa.Column("traffic", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("report_circuit_data", "traffic")
