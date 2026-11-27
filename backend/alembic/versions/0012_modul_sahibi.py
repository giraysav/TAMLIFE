# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""app_user.module_owner: kisinin sahibi oldugu modul (katalog anahtari) (2026-10-17 kullanici istegi).

Revision ID: 0012_modul_sahibi
Revises: 0011_gelir_onay
Create Date: 2026-10-17

Modul sahibi musteri sorumlusu (TAM) olmaz: Musteri Yonetimi personel listesinde yer almaz (kullanicilar.musteri_personeli).
Ilk atamalar kullanici adiyla yapilir; satir yoksa atlanir. app.models import edilmez.
Sutun zaten varsa (create_all ile kurulmus DB) yeniden eklenmez; atama yine yapilir.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_modul_sahibi"
down_revision: str | Sequence[str] | None = "0011_gelir_onay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUTUN = "module_owner"
ILK_SAHIPLER = {
    "ngocolak": "tamsms",  # OKAN COLAK: ICT Sms & Gelir
    "tcasozmen": "tamapn",  # AHMET SOZMEN: APN
    "tcahustun": "toptan",  # KAAN USTUN: Toptan
    "tcukulekci": "baglantili",  # UGUR KULEKCI: Baglantili Araclar
}


def upgrade() -> None:
    bag = op.get_bind()
    if SUTUN not in {c["name"] for c in sa.inspect(bag).get_columns("app_user")}:
        with op.batch_alter_table("app_user") as toplu:
            toplu.add_column(sa.Column(SUTUN, sa.String(40), nullable=False, server_default=""))
    tablo = sa.table("app_user", sa.column("username", sa.String), sa.column(SUTUN, sa.String))
    for kullanici, modul in ILK_SAHIPLER.items():
        bag.execute(sa.update(tablo).where(sa.func.lower(tablo.c.username) == kullanici).values({SUTUN: modul}))


def downgrade() -> None:
    if SUTUN in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("app_user")}:
        with op.batch_alter_table("app_user") as toplu:
            toplu.drop_column(SUTUN)
