#TAMLIFE DEMO ornegi: gercek panelin AYNI kodu + SAHTE veri + SALT OKUNUR + parolasiz misafir girisi. 0.0.0.0:8118 (duz HTTP, sertifika yok; gercek veri yok). Betik saf ASCII (PS 5.1).
#   .\demo_baslat.ps1             : demo DB yoksa kurar ve sahte veriyi uretir, sonra demoyu bu pencerede calistirir
#   .\demo_baslat.ps1 -Sifirla    : demo DB'yi SILIP sahte veriyi bastan uretir (gercek panel DB'sine dokunmaz)
# Guvenlik: gercek .env OKUNMAZ (TAMLIFE_ENV_DOSYASI = bos demo.env); AD/ReportDB/OneDesk baglantisi YOK; yazma istekleri 403.
# Arayuz: ekran-react\dist-demo (dist'in kopyasi + demo-giris.js + ayri csrf cerez adi). Gercek arayuz guncellenince: .\demo_baslat.ps1 -ArayuzYenile
param([int]$Port = 8118, [string]$Dinle = '0.0.0.0', [switch]$Sifirla, [switch]$ArayuzYenile)
$ErrorActionPreference = 'Stop'
$Kok = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Kok 'backend'
$Py = Join-Path $Kok '.venv\Scripts\python.exe'
$Demo = Join-Path $Backend 'var\demo'
$Dist = Join-Path $Kok 'ekran-react\dist'
$DistDemo = Join-Path $Kok 'ekran-react\dist-demo'
$Db = Join-Path $Demo 'demo.db'
foreach ($d in 'kullanicilar', 'log', 'yedek') { New-Item -ItemType Directory -Force (Join-Path $Demo $d) | Out-Null }
if (-not (Test-Path (Join-Path $Demo 'demo.env'))) { New-Item -ItemType File (Join-Path $Demo 'demo.env') | Out-Null }

if ($ArayuzYenile -or -not (Test-Path (Join-Path $DistDemo 'index.html'))) {
    $giris = Join-Path $DistDemo 'assets\demo-giris.js'
    $yedekGiris = if (Test-Path $giris) { Get-Content $giris -Raw -Encoding UTF8 } else { $null }
    if (Test-Path $DistDemo) { Remove-Item -Recurse -Force $DistDemo }
    Copy-Item -Recurse $Dist $DistDemo
    Remove-Item -Force (Join-Path $DistDemo 'misafir.html') -ErrorAction SilentlyContinue
    Get-ChildItem (Join-Path $DistDemo 'assets') -Filter 'misafir.*' | Remove-Item -Force
    Get-ChildItem (Join-Path $DistDemo 'assets') -Filter 'sorgu-*.js' | ForEach-Object {
        (Get-Content $_.FullName -Raw -Encoding UTF8).Replace('tamlife_csrf=', 'tamlife_demo_csrf=') | Set-Content $_.FullName -Encoding UTF8 -NoNewline }
    if ($yedekGiris) { Set-Content $giris $yedekGiris -Encoding UTF8 }
    $ix = Join-Path $DistDemo 'index.html'
    (Get-Content $ix -Raw -Encoding UTF8) -replace '(<script type="module")', ('<script src="/assets/demo-giris.js"></script>' + "`n    " + '$1') | Set-Content $ix -Encoding UTF8
    Write-Host '[+] dist-demo yenilendi (demo-giris.js yerinde kalmali).' -ForegroundColor Green
}

$env:TAMLIFE_DATABASE_URL = 'sqlite:///' + ($Db -replace '\\', '/')
$env:TAMLIFE_SQLITE_IZIN = 'true'
$env:TAMLIFE_KULLANICI_DB_DIZINI = (Join-Path $Demo 'kullanicilar') -replace '\\', '/'
$env:TAMLIFE_ENV_DOSYASI = (Join-Path $Demo 'demo.env') -replace '\\', '/'
$env:TAMLIFE_ENV = 'prod'
$env:TAMLIFE_DEMO = '1'
$env:TAMLIFE_COOKIE_NAME = 'tamlife_demo'
$env:TAMLIFE_CSRF_COOKIE_NAME = 'tamlife_demo_csrf'
$env:TAMLIFE_STATIC_DIR = $DistDemo
$env:TAMLIFE_TRUSTED_PROXIES = '127.0.0.1'
$env:TAMLIFE_ALLOWED_HOSTS = 'tamlife,tamlife.turkcell.entp.tgc,127.0.0.1,localhost'
$env:TAMLIFE_LOG_DIR = (Join-Path $Demo 'log') -replace '\\', '/'
$env:TAMLIFE_BACKUP_DIR = (Join-Path $Demo 'yedek') -replace '\\', '/'
$env:AD_ENABLED = 'false'
$env:TAMLIFE_COOKIE_SECURE = 'false'   # demo duz HTTP (sertifika yok): Secure cerez http'de saklanmaz

if ($Sifirla -and (Test-Path $Db)) {
    Remove-Item -Force "$Db*"
    Remove-Item -Recurse -Force (Join-Path $Demo 'kullanicilar\*') -ErrorAction SilentlyContinue
    Write-Host '[+] Demo DB silindi (yalniz demo).' -ForegroundColor Yellow
}
Set-Location $Backend
$ErrorActionPreference = 'Continue'
if (-not (Test-Path $Db)) {
    & $Py -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { Write-Host '[!] Sema kurulamadi.' -ForegroundColor Red; exit 1 }
    & $Py -I (Join-Path $PSScriptRoot 'demo_tohum.py')
    if ($LASTEXITCODE -ne 0) { Write-Host '[!] Sahte veri uretilemedi.' -ForegroundColor Red; exit 1 }
}
Write-Host "[*] DEMO: http://${Dinle}:$Port (salt okunur, ornek veri). Durdurmak: Ctrl+C" -ForegroundColor Cyan
& $Py -m uvicorn app.main:app --host $Dinle --port $Port --no-proxy-headers
