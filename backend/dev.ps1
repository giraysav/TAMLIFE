# Gelistirme sunucusu: API 8117 (SQLite, yerel admin). Canli AD/Oracle yok.
$env:TAMLIFE_DATABASE_URL = "sqlite:///./var/dev.db"
$env:TAMLIFE_LOCAL_USER = "admin"
$env:TAMLIFE_LOCAL_PASSWORD = "0000"
$env:TAMLIFE_LOCAL_ROLE = "admin"
$env:TAMLIFE_ALLOWED_ORIGINS = "http://127.0.0.1:5173,http://127.0.0.1:5174,http://localhost:5173,http://localhost:5174"
New-Item -ItemType Directory -Force var | Out-Null
..\.venv\Scripts\alembic.exe upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8117
