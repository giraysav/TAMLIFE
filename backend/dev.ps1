# Yerel gelistirme sunucusu: API 127.0.0.1:8117 (SQLite, yerel admin). Canli AD/Oracle ve baska sisteme baglanti yok.
#   .\dev.ps1            yalniz API. Arayuz icin ayri terminalde: cd ..\ekran-react ; npm run dev  (Vite /api'yi 8117'ye yonlendirir)
#   .\dev.ps1 -Arayuz    arayuzu derler (taban "/") ve ayni portta sunar: http://127.0.0.1:8117/
param([switch]$Arayuz)

Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"   # venv .exe kisayollari yerine python -m: kisayollar tasinmis venv'de bozulur

$env:TAMLIFE_ENV = "dev"
$env:TAMLIFE_DATABASE_URL = "sqlite:///./var/dev.db"
$env:TAMLIFE_LOCAL_USER = "admin"
$env:TAMLIFE_LOCAL_PASSWORD = "0000"
$env:TAMLIFE_LOCAL_ROLE = "admin"
$env:TAMLIFE_ALLOWED_ORIGINS = "http://127.0.0.1:5173,http://127.0.0.1:5174,http://localhost:5173,http://localhost:5174"
New-Item -ItemType Directory -Force var | Out-Null

if ($Arayuz) {
    Push-Location (Join-Path $PSScriptRoot "..\ekran-react")
    npm.cmd run build
    $derlendi = $LASTEXITCODE -eq 0
    Pop-Location
    if (-not $derlendi) { Write-Error "Arayuz derlenemedi."; exit 1 }
    $env:TAMLIFE_STATIC_DIR = (Resolve-Path (Join-Path $PSScriptRoot "..\ekran-react\dist")).Path
}

& $py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { Write-Error "Sema guncellenemedi."; exit 1 }
# Oturumlar bellekte: tek surec. Yalniz yerel adres.
& $py -m uvicorn app.main:app --host 127.0.0.1 --port 8117
