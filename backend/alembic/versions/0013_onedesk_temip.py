"""onedesk_record: TEMIP kayitlari icin ticket_no, customer_no, detail ve iki indeks (2026-10-17 kullanici istegi).

Revision ID: 0013_onedesk_temip
Revises: 0012_modul_sahibi
Create Date: 2026-10-17

ReportDB TEMIP alarmlari 01.01.2026'dan itibaren tek tek alinir (external_key = IDENTIFIER, source = 'temip'); karti olmayan kayit
customer_no ile TAM Radar'da gruplanir. Mevcut kayitlar bos degerle kalir. app.models import edilmez; sutun/indeks varsa yeniden eklenmez.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_onedesk_temip"
down_revision: str | Sequence[str] | None = "0012_modul_sahibi"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUTUNLAR = (
    sa.Column("ticket_no", sa.String(40), nullable=False, server_default=""),
    sa.Column("customer_no", sa.String(20), nullable=False, server_default=""),
    sa.Column("detail", sa.String(80), nullable=False, server_default=""),
)
INDEKSLER = (("ix_onedesk_source_key", ["source", "external_key"]), ("ix_onedesk_source_mno", ["source", "customer_no"]))


def upgrade() -> None:
    ins = sa.inspect(op.get_bind())
    mevcut = {c["name"] for c in ins.get_columns("onedesk_record")}
    eksik = [c for c in SUTUNLAR if c.name not in mevcut]
    if eksik:
        with op.batch_alter_table("onedesk_record") as toplu:
            for sutun in eksik:
                toplu.add_column(sutun)
    indeksler = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("onedesk_record")}
    for ad, sutunlar in INDEKSLER:
        if ad not in indeksler:
            op.create_index(ad, "onedesk_record", sutunlar)


def downgrade() -> None:
    ins = sa.inspect(op.get_bind())
    indeksler = {i["name"] for i in ins.get_indexes("onedesk_record")}
    for ad, _ in INDEKSLER:
        if ad in indeksler:
            op.drop_index(ad, table_name="onedesk_record")
    mevcut = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("onedesk_record")}
    with op.batch_alter_table("onedesk_record") as toplu:
        for sutun in SUTUNLAR:
            if sutun.name in mevcut:
                toplu.drop_column(sutun.name)
