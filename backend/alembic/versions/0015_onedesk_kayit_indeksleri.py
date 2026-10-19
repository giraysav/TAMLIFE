"""onedesk_record: Musteri Yonetimi kayit listeleri icin iki bilesik indeks (2026-10-18; TEMIP ile ~350 bin kayit).

Revision ID: 0015_onedesk_kayit_indeksleri
Revises: 0014_kaynak_katalog
Create Date: 2026-10-18

Portfoy acik kayitlari (status, customer_id) ve kart kapananlari (customer_id, status, closed_at). Indeks varsa yeniden olusturulmaz.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_onedesk_kayit_indeksleri"
down_revision: str | Sequence[str] | None = "0014_kaynak_katalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEKSLER = (
    ("ix_onedesk_durum_musteri", ["status", "customer_id"]),
    ("ix_onedesk_musteri_durum_kapanis", ["customer_id", "status", "closed_at"]),
)


def upgrade() -> None:
    mevcut = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("onedesk_record")}
    for ad, sutunlar in INDEKSLER:
        if ad not in mevcut:
            op.create_index(ad, "onedesk_record", sutunlar)


def downgrade() -> None:
    mevcut = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("onedesk_record")}
    for ad, _ in INDEKSLER:
        if ad in mevcut:
            op.drop_index(ad, table_name="onedesk_record")
