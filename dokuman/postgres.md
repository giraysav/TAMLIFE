# PostgreSQL

Panel deposu SQLite degil, PostgreSQL. Bu makinede `psql` ve PostgreSQL sunucusu kurulu degil; sunucu baslatilmadi.

- Adres ortam degiskeni: `TAMLIFE_DATABASE_URL`
- Dosyalarda parola yok. Degisken bos ise varsayilan: `postgresql+psycopg://localhost:5432/tamlife`
- Veritabani adi: `tamlife`, sunucu: `localhost`, port: `5432`
- SQLAlchemy (`backend/app/core/config.py`) ve Alembic (`backend/alembic.ini`, `backend/alembic/env.py`) ayni adresi kullanir.
- `data/` altindaki SQLite dosyalari silinmedi. Postgres ayakta olunca panel onlari kullanmaz. Kok klasor henuz `veri` adinda; yeniden adlandirma baska surecler tarafindan kilitli.
