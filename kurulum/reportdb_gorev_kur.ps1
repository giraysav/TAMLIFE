# TAMLIFE v3.5 veri iscisi: ReportDB alarm senkronu (python -m app.isci reportdb) icin zamanlanmis gorevi kurar / kaldirir.
# Uretim isletim\reportdb_gorev_kur.ps1 uyarlamasi. Betik saf ASCII (PS 5.1).
#   .\reportdb_gorev_kur.ps1 -Kuru      : kurmaz; su anki kimlikle bir kez --kuru calistirir (yazmadan sorgu denemesi)
#   .\reportdb_gorev_kur.ps1            : gorevi kurar (YONETICI PowerShell; -Kullanici parolasi sorulur)
#   .\reportdb_gorev_kur.ps1 -Kaldir    : gorevi siler (Instant Client klasorune dokunmaz)
# Gorev her -Dakika dakikada -Kullanici kimligiyle kosar: Oracle giris tetikleyicisi yalniz izinli kimlik/makineyi kabul eder,
# panel (web) sureci Oracle'a baglanmaz. Ayni anda tek calisma, en fazla 5 dk. Parola yalniz gorev kaydina yazilir (dosya/gunluk yok).
# Ayarlar backend\.env (panelle AYNI dosya): ORACLE_REPORTDB_* ve panel DB adresi (TAMLIFE_DATABASE_URL). ORACLE_REPORTDB_ENABLED=true
# olmadan gorev Oracle'a baglanmaz, hicbir sey yazmaz (cikis 1). Gunluk: backend\var\logs\isci.log (ya da TAMLIFE_LOG_DIR).
param([switch]$Kaldir,
      [switch]$Kuru,
      [string]$Kullanici = '',
      [int]$Dakika = 6,
      [string]$Istemci = 'E:\oracle\instantclient_19_32',
      [string]$Ad = 'TAM_Life_v35_ReportDB_6dk')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'calisma_kimligi.ps1')
Tamlife-KimlikDogrula
if (-not $Kullanici) { $Kullanici = $TamlifeCalismaHesabi }
if ($Kullanici -ine $TamlifeCalismaHesabi) { throw "Gorev hesabi $TamlifeCalismaHesabi olmali." }
$Kok = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Kok 'backend'
$Py = Join-Path $Kok '.venv\Scripts\python.exe'

function Adim($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Uyari($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Dur($m)  { Write-Host "[!] $m" -ForegroundColor Red; exit 1 }

if ($Kaldir) {
    if (Get-ScheduledTask -TaskName $Ad -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $Ad -Confirm:$false
        Adim "Gorev silindi: $Ad"
    } else { Adim "Gorev zaten yok: $Ad" }
    exit 0
}

if (-not (Test-Path $Py)) { Dur "Python yok: $Py" }
if (-not (Test-Path (Join-Path $Backend 'app\isci.py'))) { Dur "Isci modulu yok: $Backend\app\isci.py" }
if (-not (Test-Path (Join-Path $Istemci 'oci.dll'))) { Dur "Oracle Instant Client bulunamadi: $Istemci (-Istemci ile verin)" }
& $Py -c "import oracledb" 2>$null
if ($LASTEXITCODE -ne 0) { Dur "oracledb kurulu degil: $Py -m pip install --no-index --find-links <wheels klasoru> -r $Kok\requirements.txt" }
$envDosyasi = Join-Path $Backend '.env'
if (-not (Test-Path $envDosyasi)) { Dur "Ayar dosyasi yok: $envDosyasi" }
# Yalniz anahtar ADI aranir; deger okunmaz/yazdirilmaz.
if (-not (Select-String -Path $envDosyasi -Pattern '^\s*TAMLIFE_DATABASE_URL\s*=' -Quiet)) {
    Uyari "backend\.env'de TAMLIFE_DATABASE_URL yok: isci panelle ayni DB'ye yazamaz (SQLite ise TAMLIFE_ENV / TAMLIFE_SQLITE_IZIN de gerekir)."
}

if ($Kuru) {
    Adim "Kuru deneme ($([Security.Principal.WindowsIdentity]::GetCurrent().Name)): hicbir sey yazilmaz"
    Push-Location $Backend
    try { & $Py -m app.isci reportdb --client $Istemci --kuru; $kod = $LASTEXITCODE } finally { Pop-Location }
    exit $kod
}

$kimlik = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]$kimlik).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Dur "Yonetici (yukseltilmis) PowerShell gerekli. Su an: $($kimlik.Name)"
}
if ($Dakika -lt 2 -or $Dakika -gt 60) { Dur "Dakika 2 ile 60 arasinda olmali" }

$gorevBilgi = Tamlife-GorevKimlikBilgisi
$eylem = New-ScheduledTaskAction -Execute $Py -Argument ('-m app.isci reportdb --client "{0}"' -f $Istemci) -WorkingDirectory $Backend
$tetik = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(3) -RepetitionInterval (New-TimeSpan -Minutes $Dakika)
$ayar = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
try {
    Register-ScheduledTask -TaskName $Ad -Action $eylem -Trigger $tetik -Settings $ayar -User $TamlifeCalismaHesabi -Password ($gorevBilgi.GetNetworkCredential().Password) -RunLevel Highest -Force | Out-Null
} finally { $gorevBilgi = $null }
Adim "Gorev kuruldu: $Ad (her $Dakika dk; ilk calisma ~3 dk sonra)"
Write-Host "Hemen denemek icin:  Start-ScheduledTask -TaskName $Ad ; Start-Sleep 30 ; Get-ScheduledTaskInfo -TaskName $Ad ; Get-Content $Backend\var\logs\isci.log -Tail 3" -ForegroundColor Green
Write-Host "Cikis kodu: 0 basarili | 1 hata | 2 onceki calisma suruyor (atlandi)" -ForegroundColor Green
Write-Host "Kaldirmak icin:      $PSScriptRoot\reportdb_gorev_kur.ps1 -Kaldir" -ForegroundColor Green
