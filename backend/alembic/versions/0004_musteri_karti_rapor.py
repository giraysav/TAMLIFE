"""Musteri karti ve aylik rapor semasi (uretim customers, destech_contacts, reports, rapor_*).

Revision ID: 0004_musteri_karti_rapor
Revises: 0003_rol_gorunumu
Create Date: 2026-10-04

0001 `create_all` kullandigi icin taze veritabaninda her sey zaten gelir; mevcut veritabaninda
yalniz eksikler eklenir. Eski ince tablolar (customer_contact, report, report_recipient,
sms_revenue, apn_revenue) BOS ise silinip uretimle uyumlu semayla yeniden kurulur; satir varsa
islem durur (elle tasima gerekir).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models import Base

revision: str = "0004_musteri_karti_rapor"
down_revision: str | Sequence[str] | None = "0003_rol_gorunumu"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Yeniden kurulacak tablolar: (ad, yeni semada bulunan isaret sutunu). Silme sirasi bagimliliga gore.
YENIDEN = (
    ("report_recipient", "to_addrs"),
    ("report", "report_month"),
    ("sms_revenue", "customer_name"),
    ("apn_revenue", "customer_name"),
)
ESKI_TABLOLAR = ("customer_contact",)
YENI_TABLOLAR = (
    "customer_team",
    "matrix_config",
    "report",
    "report_draft",
    "report_dispatch",
    "report_recipient",
    "sms_revenue",
    "apn_revenue",
)

# (sutun, tip, NOT NULL varsayilani)
CUSTOMER_SUTUNLARI = (
    ("customer_no", sa.String(50), None, True),
    ("ncst", sa.String(50), "", False),
    ("sector", sa.String(100), None, True),
    ("inventory_count", sa.Integer(), "0", False),
    ("ft_volume", sa.String(100), "0,00 ₺", False),
    ("tam_ft", sa.String(100), "0,00 ₺", False),
    ("alarm_count", sa.Integer(), "0", False),
    ("complaint_count", sa.Integer(), "0", False),
    ("request_count", sa.Integer(), "0", False),
    ("alarm_closed_count", sa.Integer(), "0", False),
    ("complaint_closed_count", sa.Integer(), "0", False),
    ("request_closed_count", sa.Integer(), "0", False),
    ("report_count", sa.Integer(), "0", False),
    ("cacti_urls", sa.JSON(), "[]", False),
    ("separate_report", sa.Boolean(), "0", False),
)


def _bos_mu(bind, ad: str) -> bool:
    return bind.execute(sa.text(f"SELECT COUNT(*) FROM {ad}")).scalar_one() == 0


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    mevcut = set(insp.get_table_names())

    for ad, isaret in YENIDEN:
        if ad in mevcut and isaret not in {c["name"] for c in insp.get_columns(ad)}:
            if not _bos_mu(bind, ad):
                raise RuntimeError(f"{ad} bos degil; elle tasinmali")
            op.drop_table(ad)
    for ad in ESKI_TABLOLAR:
        if ad in mevcut:
            if not _bos_mu(bind, ad):
                raise RuntimeError(f"{ad} bos degil; elle tasinmali")
            op.drop_table(ad)

    sutunlar = {c["name"] for c in sa.inspect(bind).get_columns("customer")}
    eksik = [s for s in CUSTOMER_SUTUNLARI if s[0] not in sutunlar]
    if eksik:
        with op.batch_alter_table("customer") as batch:
            for ad, tip, varsayilan, bos_olabilir in eksik:
                batch.add_column(
                    sa.Column(
                        ad,
                        tip,
                        nullable=bos_olabilir,
                        server_default=None if varsayilan is None else sa.text(f"'{varsayilan}'"),
                    )
                )

    Base.metadata.create_all(bind, tables=[Base.metadata.tables[n] for n in YENI_TABLOLAR], checkfirst=True)


def downgrade() -> None:
    for ad in ("report_dispatch", "report_draft", "report_recipient", "report", "matrix_config", "customer_team"):
        op.drop_table(ad)
