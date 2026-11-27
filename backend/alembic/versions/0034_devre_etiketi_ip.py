# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Rapor devre etiketlerinden IP adresi temizligi (2026-11-27): eski etiket uretimi 'ADDRESS' iceren alanlari gosterdigi icin
IPADDRESS degeri etikete yaziliyordu (ekranda "KURUMSAL INTERNET · 10.58.240.34"). Envanter kurali: IP gosterilmez. Etiket
" · " ile ayrilmis parcalardir; IPv4 iceren parca atilir. Geri alinmaz (silinen deger yeniden uretilmez).

Revision ID: 0034_devre_etiketi_ip
Revises: 0033_bildirim_yanit
Create Date: 2026-11-27
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034_devre_etiketi_ip"
down_revision: str | Sequence[str] | None = "0033_bildirim_yanit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def upgrade() -> None:
    baglanti = op.get_bind()
    if "report_circuit" not in sa.inspect(baglanti).get_table_names():
        return
    for kimlik, etiket in baglanti.execute(sa.text("SELECT id, label FROM report_circuit")).all():
        if etiket and _IP.search(etiket):
            temiz = " · ".join(p for p in etiket.split(" · ") if not _IP.search(p))
            baglanti.execute(sa.text("UPDATE report_circuit SET label = :e WHERE id = :i"), {"e": temiz, "i": kimlik})


def downgrade() -> None:
    pass  # silinen IP geri yazilmaz
