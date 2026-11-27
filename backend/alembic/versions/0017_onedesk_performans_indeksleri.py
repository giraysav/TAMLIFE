# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""onedesk_record: Veri Girisi akislari ve RCA / oneriler icin iki indeks (2026-10-20 kullanici: "panelde asiri yavaslik var").

Revision ID: 0017_onedesk_performans_indeksleri
Revises: 0016_musteri_alani
Create Date: 2026-10-20

353 bin TEMIP kaydinda (canli DB kopyasi): /tampon/akislar 2,4 sn -> 0,34 sn (kaynak + durum + musteri ortu indeksi);
/onedesk/rca ve /onedesk/oneriler 0,9 sn -> ~0 (kok sebebi dolu kapananlar icin kismi indeks). Indeks varsa yeniden olusturulmaz.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_onedesk_performans_indeksleri"
down_revision: str | Sequence[str] | None = "0016_musteri_alani"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RCA_KOSULU = "status = 'closed' AND root_cause <> ''"


def upgrade() -> None:
    mevcut = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("onedesk_record")}
    if "ix_onedesk_kaynak_durum_musteri" not in mevcut:
        op.create_index("ix_onedesk_kaynak_durum_musteri", "onedesk_record", ["source", "status", "customer_id"])
    if "ix_onedesk_rca" not in mevcut:
        op.create_index("ix_onedesk_rca", "onedesk_record", ["closed_at"], sqlite_where=sa.text(RCA_KOSULU), postgresql_where=sa.text(RCA_KOSULU))


def downgrade() -> None:
    mevcut = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("onedesk_record")}
    for ad in ("ix_onedesk_rca", "ix_onedesk_kaynak_durum_musteri"):
        if ad in mevcut:
            op.drop_index(ad, table_name="onedesk_record")
