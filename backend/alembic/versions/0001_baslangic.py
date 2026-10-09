"""Panel DB baslangic semasi (eski 0001-0009 birlestirildi, 2026-10-09).

Revision ID: 0001_baslangic
Revises:
Create Date: 2026-10-09

Yalniz ortak panel DB'si (models.Base). Kullanici basina dosyalar (models.KullaniciBase) Alembic'e girmez;
app.db.kullanici_oturumu ilk acilista kurar. Eski zincirdeki bir DB icin: `alembic stamp --purge head`
(sema zaten gunceldir) ya da dev'de sil + `alembic upgrade head` + `python -m app.ornek_veri`.
Yeni sema degisikligi yeni revizyon olarak eklenir.
"""

from collections.abc import Sequence

from alembic import op
from app.models import Base

revision: str = "0001_baslangic"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
