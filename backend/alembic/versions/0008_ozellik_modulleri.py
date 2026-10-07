"""Onedesk kayit alanlari, ICT SMS proje, APN kurulum/calisma, izin&takvim gunu, sunum ogesi, rol ek yetkileri.

Revision ID: 0008_ozellik_modulleri
Revises: 0007_external_source_kaldir
Create Date: 2026-10-07

0001 `create_all` canli modelden tablo urettigi icin taze veritabaninda her sey zaten vardir; adimlar yalniz eksigi tamamlar
(`checkfirst` + sutun denetimi). Kullanilmayan `calendar_entry` iskeleti bos ise kaldirilir (satir varsa islem durur).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models import Base

revision: str = "0008_ozellik_modulleri"
down_revision: str | Sequence[str] | None = "0007_external_source_kaldir"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# tablo -> eklenecek sutunlar (ad, tip, varsayilan). Yeni sutunlar bos/varsayilanla gelir.
_SUTUNLAR: dict[str, list[tuple[str, sa.types.TypeEngine, object | None]]] = {
    "app_user": [("last_login_at", sa.DateTime(timezone=True), None)],
    "role_view": [("permissions", sa.JSON(), "[]")],
    "onedesk_record": [
        ("customer_label", sa.String(200), ""),
        ("location", sa.String(200), ""),
        ("category", sa.String(200), ""),
        ("opened_at", sa.DateTime(timezone=True), None),
        ("closed_at", sa.DateTime(timezone=True), None),
        ("root_cause", sa.Text(), ""),
        ("resolution", sa.Text(), ""),
        ("source", sa.String(20), "import"),
    ],
    "sms_revenue": [("project", sa.String(200), "")],
    "apn_revenue": [
        ("apn_name", sa.String(200), ""),
        ("request_date", sa.Date(), None),
        ("delivery_date", sa.Date(), None),
    ],
    "presentation": [
        ("source", sa.String(30), ""),
        ("payload", sa.JSON(), "{}"),
        ("sent_by", sa.String(120), ""),
        ("sent_at", sa.DateTime(timezone=True), None),
    ],
}
_INDEKSLER = {
    "onedesk_record": [
        ("ix_onedesk_kind_status", ["kind", "status"]),
        ("ix_onedesk_closed_at", ["closed_at"]),
        ("ix_onedesk_opened_at", ["opened_at"]),
        ("ix_onedesk_customer", ["customer_id"]),
    ],
}


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind, tables=[Base.metadata.tables["calendar_day"], Base.metadata.tables["apn_work"]], checkfirst=True)
    for tablo, sutunlar in _SUTUNLAR.items():
        mevcut = {c["name"] for c in sa.inspect(bind).get_columns(tablo)}
        eksik = [s for s in sutunlar if s[0] not in mevcut]
        if not eksik:
            continue
        with op.batch_alter_table(tablo) as toplu:
            for ad, tip, varsayilan in eksik:
                toplu.add_column(sa.Column(ad, tip, nullable=varsayilan is None, server_default=None if varsayilan is None else sa.text(f"'{varsayilan}'")))
    for tablo, indeksler in _INDEKSLER.items():
        mevcut = {i["name"] for i in sa.inspect(bind).get_indexes(tablo)}
        for ad, sutunlar in indeksler:
            if ad not in mevcut:
                op.create_index(ad, tablo, sutunlar)
    # presentation: ceyrek+kaynak benzersiz; kaynagi bos eski satirlar kapsam disi (kismi indeks)
    if "uq_presentation_period_source" not in {i["name"] for i in sa.inspect(bind).get_indexes("presentation")}:
        op.create_index(
            "uq_presentation_period_source", "presentation", ["period", "source"], unique=True,
            sqlite_where=sa.text("source <> ''"), postgresql_where=sa.text("source <> ''"),
        )
    if "calendar_entry" in sa.inspect(bind).get_table_names():
        if bind.execute(sa.text("SELECT COUNT(*) FROM calendar_entry")).scalar_one() != 0:
            raise RuntimeError("calendar_entry bos degil; elle tasinmali")
        op.drop_table("calendar_entry")


def downgrade() -> None:
    bind = op.get_bind()
    if "calendar_entry" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "calendar_entry",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("owner_username", sa.String(120), nullable=False, server_default=""),
            sa.Column("kind", sa.String(40), nullable=False, server_default=""),
            sa.Column("title", sa.String(200), nullable=False, server_default=""),
            sa.Column("starts_on", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ends_on", sa.DateTime(timezone=True), nullable=True),
        )
    if "uq_presentation_period_source" in {i["name"] for i in sa.inspect(bind).get_indexes("presentation")}:
        op.drop_index("uq_presentation_period_source", table_name="presentation")
    for tablo, indeksler in _INDEKSLER.items():
        mevcut = {i["name"] for i in sa.inspect(bind).get_indexes(tablo)}
        for ad, _ in indeksler:
            if ad in mevcut:
                op.drop_index(ad, table_name=tablo)
    for tablo, sutunlar in _SUTUNLAR.items():
        mevcut = {c["name"] for c in sa.inspect(bind).get_columns(tablo)}
        silinecek = [s[0] for s in sutunlar if s[0] in mevcut]
        if silinecek:
            with op.batch_alter_table(tablo) as toplu:
                for ad in silinecek:
                    toplu.drop_column(ad)
    for tablo in ("apn_work", "calendar_day"):
        if tablo in sa.inspect(bind).get_table_names():
            op.drop_table(tablo)
