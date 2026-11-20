"""Aylik rapor devre grafikleri (2026-11-20 kullanici: "reportdb'den alacagimiz veri ile grafigi cizecegiz; description ya da port
yazildiginda gelen musteri bilgisi kullanici degistirmedikce grafik olusmaya devam edecek; donem raporun ayina gore"):
report_cmdb (ReportDB CMDB kopyasi), report_circuit (musterinin secili devreleri), report_circuit_data (aylik saatlik olcumler).

Revision ID: 0026_rapor_devre_grafik
Revises: 0025_dosya_aktarim_gecmisi
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_rapor_devre_grafik"
down_revision: str | Sequence[str] | None = "0025_dosya_aktarim_gecmisi"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    var = set(sa.inspect(op.get_bind()).get_table_names())
    if "report_cmdb" not in var:
        op.create_table(
            "report_cmdb",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("customer_key", sa.String(40), nullable=False),
            sa.Column("ciname", sa.String(200), nullable=False),
            sa.Column("fields", sa.JSON(), nullable=False),
            sa.Column("search_text", sa.Text(), nullable=False),
            sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_report_cmdb_customer_key", "report_cmdb", ["customer_key"])
        op.create_index("ix_report_cmdb_ciname", "report_cmdb", ["ciname"])
    if "report_circuit" not in var:
        op.create_table(
            "report_circuit",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id"), nullable=False),
            sa.Column("ciname", sa.String(200), nullable=False),
            sa.Column("label", sa.String(300), nullable=False),
            sa.Column("added_by", sa.String(120), nullable=False),
            sa.Column("added_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("customer_id", "ciname", name="uq_report_circuit"),
        )
        op.create_index("ix_report_circuit_customer_id", "report_circuit", ["customer_id"])
    if "report_circuit_data" not in var:
        op.create_table(
            "report_circuit_data",
            sa.Column("ciname", sa.String(200), primary_key=True),
            sa.Column("year", sa.Integer(), primary_key=True),
            sa.Column("month", sa.Integer(), primary_key=True),
            sa.Column("points", sa.JSON(), nullable=False),
            sa.Column("summary", sa.JSON(), nullable=False),
            sa.Column("exchours", sa.String(100), nullable=False),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("report_circuit_data")
    op.drop_index("ix_report_circuit_customer_id", "report_circuit")
    op.drop_table("report_circuit")
    op.drop_index("ix_report_cmdb_ciname", "report_cmdb")
    op.drop_index("ix_report_cmdb_customer_key", "report_cmdb")
    op.drop_table("report_cmdb")
