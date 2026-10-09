"""Kisisel tablolar (takvim gunu, ICT SMS, APN kurulum, APN calisma) kullanici basina SQLite dosyalarina tasinir.

Revision ID: 0009_kullanici_dosyalari
Revises: 0008_ozellik_modulleri
Create Date: 2026-10-09

Sahip: calendar_day -> user_id; gelir -> TAM adi (display_name/username) bir kisiye denk geliyorsa o, degilse created_by.
Satirlar app.db.kullanici_oturumu dosyalarina yazildiktan sonra panel tablosu kaldirilir. Geri alma yok (veri dosyalardadir).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db import kullanici_oturumu
from app.models import ApnRevenue, ApnWork, CalendarDay, SmsRevenue

revision: str = "0009_kullanici_dosyalari"
down_revision: str | Sequence[str] | None = "0008_ozellik_modulleri"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MODELLER = (CalendarDay, SmsRevenue, ApnRevenue, ApnWork)


def upgrade() -> None:
    bind = op.get_bind()
    mevcut = set(sa.inspect(bind).get_table_names())
    kisiler = bind.execute(sa.text("SELECT id, username, display_name FROM app_user")).all()
    kimlikten = {k.id: k.username for k in kisiler}
    adindan = {**{k.username: k.username for k in kisiler}, **{k.display_name: k.username for k in kisiler if k.display_name}}
    for model in MODELLER:
        tablo = model.__tablename__
        if tablo not in mevcut:
            continue
        sutunlar = {c.key for c in model.__table__.columns} - {"id"}
        dosyalar: dict[str, list[dict]] = {}
        for satir in bind.execute(sa.select(sa.Table(tablo, sa.MetaData(), autoload_with=bind))).mappings():
            sahip = kimlikten.get(satir.get("user_id")) or adindan.get(satir.get("tam_name") or "") or satir.get("created_by") or "_sahipsiz"
            dosyalar.setdefault(sahip, []).append({k: v for k, v in satir.items() if k in sutunlar})
        for sahip, satirlar in dosyalar.items():
            with kullanici_oturumu(sahip) as k:
                k.execute(sa.insert(model), satirlar)
                k.commit()
        op.drop_table(tablo)


def downgrade() -> None:
    raise NotImplementedError("Kisisel veriler kullanici dosyalarindadir; geri alma desteklenmez.")
