#TAMLIFE v3.5 paneli CANLI modda (AD girisi, yerel admin/0000 YOK) baslatir: 127.0.0.1:8117. Betik saf ASCII (PS 5.1).
#   .\canli_baslat.ps1            : onkosullari denetler, semayi gunceller, paneli bu pencerede calistirir (pencere kapaninca panel durur)
#   .\canli_baslat.ps1 -Kontrol   : yalniz onkosullari denetler; hicbir sey baslatmaz / yazmaz
# HTTPS icin ayrica (yonetici PowerShell): kurulum\tls_vekili.ps1. Panel yalniz 127.0.0.1'e baglanir; disariya vekil acar.
# Ayarlar backend\.env (git disi). Burada yalniz ANAHTAR ADI aranir, deger okunmaz/yazdirilmaz.
#   Zorunlu: TAMLIFE_DATABASE_URL (SQLite ise TAMLIFE_SQLITE_IZIN=true de), AD_ENABLED=true, AD_SERVER, AD_DOMAIN.
# Bu betik surece sunlari yazar (.env'deki ayni anahtarlari ezer): TAMLIFE_ENV=prod, TAMLIFE_TRUSTED_PROXIES=127.0.0.1,
# TAMLIFE_STATIC_DIR=<ekran-react\dist>. TAMLIFE_ALLOWED_HOSTS .env'de yoksa: tamlife, FQDN, 127.0.0.1, localhost.
param([switch]$Kontrol,
      [int]$Port = 8117,
      [string]$Alanlar = 'tamlife,tamlife.turkcell.entp.tgc,127.0.0.1,localhost')
$ErrorActionPreference = 'Stop'
$Kok = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Kok 'backend'
$Py = Join-Path $Kok '.venv\Scripts\python.exe'
$Dist = Join-Path $Kok 'ekran-react\dist'
$EnvDosyasi = Join-Path $Backend '.env'
 
function Adim($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Tamam($m) { Write-Host "[+] $m" -ForegroundColor Green }
function Uyari($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Dur($m)  { Write-Host "[!] $m" -ForegroundColor Red; exit 1 }
 
function Anahtar-Var($ad) {
    if (-not (Test-Path $EnvDosyasi)) { return $false }
    return [bool](Select-String -Path $EnvDosyasi -Pattern ('^\s*' + [regex]::Escape($ad) + '\s*=') -Quiet)
}
 
if (-not (Test-Path $Py)) { Dur "Python yok: $Py (once .venv kurulmali)" }
if (-not (Test-Path (Join-Path $Backend 'app\main.py'))) { Dur "Panel kodu yok: $Backend\app\main.py" }
if (-not (Test-Path (Join-Path $Dist 'index.html'))) { Dur "Arayuz derlemesi yok: $Dist\index.html (yerel PC'de npm run build, sonra dist klasorunu tasiyin)" }
if (-not (Test-Path $EnvDosyasi)) { Dur "Ayar dosyasi yok: $EnvDosyasi" }
if (-not (Anahtar-Var 'TAMLIFE_DATABASE_URL')) { Dur "backend\.env'de TAMLIFE_DATABASE_URL yok (ornek: TAMLIFE_DATABASE_URL=sqlite:///./var/panel.db ve TAMLIFE_SQLITE_IZIN=true)." }
if ((Select-String -Path $EnvDosyasi -Pattern '^\s*TAMLIFE_DATABASE_URL\s*=\s*sqlite' -Quiet) -and -not (Anahtar-Var 'TAMLIFE_SQLITE_IZIN')) {
    Dur "SQLite icin backend\.env'de TAMLIFE_SQLITE_IZIN=true gerekli (PostgreSQL gelene kadar)."
}
foreach ($k in 'AD_ENABLED', 'AD_SERVER', 'AD_DOMAIN') {
    if (-not (Anahtar-Var $k)) { Dur "backend\.env'de $k yok: canli modda AD olmadan kimse giris yapamaz." }
}
if (-not (Select-String -Path $EnvDosyasi -Pattern '^\s*AD_ENABLED\s*=\s*true\s*$' -Quiet)) { Uyari 'AD_ENABLED=true gorunmuyor: AD girisi kapali olabilir.' }
$tutan = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($tutan) { Dur "Port $Port dolu (surec kimligi: $(($tutan | Select-Object -First 1).OwningProcess)). Eski paneli kapatin ya da -Port ile baska port verin." }
Tamam "Onkosullar tamam (port $Port bos, arayuz derlemesi ve .env anahtarlari var)."
if ($Kontrol) { exit 0 }
 
$env:TAMLIFE_ENV = 'prod'
$env:TAMLIFE_STATIC_DIR = $Dist
$env:TAMLIFE_TRUSTED_PROXIES = '127.0.0.1'
if (-not (Anahtar-Var 'TAMLIFE_ALLOWED_HOSTS')) { $env:TAMLIFE_ALLOWED_HOSTS = $Alanlar }
 
Set-Location $Backend
$ErrorActionPreference = 'Continue'   # alembic / uvicorn bilgi satirlarini stderr'e yazar; PS 5.1'de 'Stop' bunu hata sayabilir
Adim 'Veritabani semasi guncelleniyor (alembic upgrade head)'
& $Py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { Dur 'Sema guncellenemedi.' }
Adim "Panel baslatiliyor: http://127.0.0.1:$Port (canli mod). Durdurmak: Ctrl+C"
& $Py -m uvicorn app.main:app --host 127.0.0.1 --port $Port