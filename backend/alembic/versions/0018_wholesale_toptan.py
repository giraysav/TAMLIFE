"""Segmenti WHOLESALE olan cati kartlar (istirakleriyle) Toptan alanina (2026-10-20 kullanici: "hedef modulu Toptan olacak").

Revision ID: 0018_wholesale_toptan
Revises: 0017_onedesk_performans_indeksleri
Create Date: 2026-10-20

Veri tasimasi; tekrar calistirmak bir sey degistirmez. Sonraki yazimlarda kurali app.musteri_alani._segment_alani uygular.
Geri alma kartlari Musteri Yonetimi'ne dondurmez (hangi kartin elle Toptan'da acildigi bilinmez).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_wholesale_toptan"
down_revision: str | Sequence[str] | None = "0017_onedesk_performans_indeksleri"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bag = op.get_bind()
    catilar = "SELECT id FROM customer WHERE parent_id IS NULL AND upper(trim(segment)) = 'WHOLESALE'"
    bag.execute(sa.text(f"UPDATE customer SET modul = 'toptan' WHERE modul <> 'toptan' AND (id IN ({catilar}) OR parent_id IN ({catilar}))"))


def downgrade() -> None:
    pass
