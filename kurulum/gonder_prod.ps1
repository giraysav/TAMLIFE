# TAMLIFE - Citrix gelistirme makinesinden PROD'a gonderim paketi (saf ASCII; PS 5.1). Cagiran: depo kokundeki PRODA_GONDER.bat.
# 2026-10-27 kullanici: "gelistirme artik Citrix makinede; prod'da gelistirme yapilmayacak. Citrix'te yapilan gelistirme buraya 1:1
# gonderilip calismasi gerekiyor".
#
# 1:1 ilkesi: prod'a giden sey bir GIT COMMIT'idir (calisma agaci temiz olmali). Prod o commit'e birebir gecer (prod_guncelle.ps1).
# Paket (Masaustu\TAMLIFE_GONDER):
#   kod.bundle            : git bundle (dalin tum gecmisi; kucuk). Prod bunu fetch edip commit'e gecer.
#   python_venv.zip       : .venv (yalniz prod'daki paketlerden FARKLIYSA kullanilir; pip freeze parmak izi manifestte)
#   node_modules.zip      : ekran-react\node_modules (yalniz package-lock.json farkliysa kullanilir)
#   manifest.json         : dal, commit, commit zamani, Python surumu, pip freeze / package-lock parmak izleri, dosya SHA-256'lari
#                           (commit + commit zamani = surumun imzasi; gece senkronu prod'dakiyle ayniysa hicbir sey yapmaz)
# Prod'da: sunucuda E:\TAMLIFE\TAMLIFE_v3.5\PROD_GUNCELLE.bat (paketi \\tsclient uzerinden alir, dogrular, test eder, uygular).
# Gonderilmeyenler: backend\.env, veritabani, gunlukler, var\ (prod kendi canli verisini ve ayarlarini korur).

param([switch]$TestYok, [string]$Cikis = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'TAMLIFE_GONDER'))
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8  # git ciktisindaki Turkce harfler bozulmasin

$Proje = Split-Path $PSScriptRoot -Parent
$Py = Join-Path $Proje '.venv\Scripts\python.exe'
$Gecici = Join-Path $Cikis '_hazirlaniyor'

function Adim($m) { Write-Host ''; Write-Host "=== $m ===" -ForegroundColor Cyan }
function Tamam($m) { Write-Host "  [TAMAM] $m" -ForegroundColor Green }
function Dur($m) { Write-Host "  [HATA] $m" -ForegroundColor Red; if (-not $TestYok) { Read-Host 'Kapatmak icin Enter' }; exit 1 }
function G {
    # git sarmali (adi git olamaz: kendini cagirirdi). PS 5.1: Stop altinda git'in stderr ilerleme satirlari hata sayilmasin.
    $onceki = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $c = & git -C $Proje @args 2>&1 | ForEach-Object { "$_" }
    $kod = $LASTEXITCODE; $ErrorActionPreference = $onceki
    if ($kod -ne 0) { throw "git $($args -join ' '): $c" }
    return $c
}
# 2026-10-27: Citrix'te Start-Process -Wait "Access is denied" verdi (surec basliyor, PowerShell onu bekleyemiyordu; venv python.exe
# asil Python'u alt surec acar). Surec .NET Process ile acilir: tutamac bizde, bekleme ve cikis kodu ondan.
function Calistir($dizin, $program, $argumanlar, $dosya) {
    # tam yol: yalniz adla acilan npx.cmd kendi klasorunu (%~dp0) bulamiyor
    if (-not [IO.Path]::IsPathRooted($program)) { $program = (Get-Command $program -CommandType Application | Select-Object -First 1).Source }
    $bilgi = New-Object Diagnostics.ProcessStartInfo $program, $argumanlar
    $bilgi.WorkingDirectory = $dizin
    $bilgi.UseShellExecute = $false
    $bilgi.RedirectStandardOutput = $true
    $bilgi.RedirectStandardError = $true
    $bilgi.StandardOutputEncoding = [Text.Encoding]::UTF8
    $bilgi.StandardErrorEncoding = [Text.Encoding]::UTF8
    $s = [Diagnostics.Process]::Start($bilgi)
    $hata = $s.StandardError.ReadToEndAsync()   # iki akis birden okunur: biri dolup sureci kilitlemesin
    $cikti = $s.StandardOutput.ReadToEnd()
    $s.WaitForExit()
    [IO.File]::WriteAllText($dosya, $cikti + $hata.Result, (New-Object Text.UTF8Encoding $false))
    return $s.ExitCode
}
function Parmak-Izi($metin) {
    $b = [Text.Encoding]::UTF8.GetBytes(($metin -join "`n"))
    return ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($b)) -replace '-', '')
}

Write-Host '========================================================' -ForegroundColor Cyan
Write-Host ' TAMLIFE - Prod gonderim paketi (Citrix)' -ForegroundColor Cyan
Write-Host " Proje: $Proje" -ForegroundColor Cyan
Write-Host " Cikis: $Cikis" -ForegroundColor Cyan
Write-Host '========================================================' -ForegroundColor Cyan

# --- 1) Depo temiz mi -----------------------------------------------------------------------------------------------------
Adim '1/4 Kod durumu'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Dur 'git bulunamadi.' }
$kirli = @(G status --porcelain)
if ($kirli.Count -gt 0) {
    $kirli | Select-Object -First 20 | ForEach-Object { Write-Host "    $_" }
    Dur 'Commit edilmemis degisiklik var. Prod 1:1 bir commit alir: once VS Code > Source Control ile commit edin (silinen dosyalar dahil), sonra yeniden calistirin.'
}
$dal = (G rev-parse --abbrev-ref HEAD).Trim()
$commit = (G rev-parse HEAD).Trim()
$ozet = (G log -1 --format='%h %s').Trim()
$commitZamani = (G log -1 --format='%ci').Trim()
if ($dal -eq 'HEAD') { Dur 'Bir dalda degilsiniz (detached HEAD). Bir dala gecin.' }
Tamam "dal $dal, commit $ozet ($commitZamani)"

# --- 2) Testler (istege bagli, onerilen) -------------------------------------------------------------------------------------
Adim '2/4 Testler'
New-Item -ItemType Directory -Force -Path $Cikis | Out-Null
if (Test-Path $Gecici) { Remove-Item -Recurse -Force -LiteralPath $Gecici }
New-Item -ItemType Directory -Force -Path $Gecici | Out-Null
$test = 'H'
if (-not $TestYok) { $test = (Read-Host '  Gondermeden once testler calissin mi? (~8 dk, onerilen) [E/H]').Trim().ToUpper() }
if ($test -eq 'E') {
    $f = Join-Path $Gecici 'pytest.txt'
    Write-Host '  ... arka uc testleri' -ForegroundColor DarkGray
    if ((Calistir (Join-Path $Proje 'backend') $Py '-m pytest -q -p no:cacheprovider' $f) -ne 0) { Get-Content $f -Tail 15; Dur "Arka uc testleri basarisiz; paket olusturulmadi. Ayrinti: $f" }
    Tamam ((Get-Content $f | Select-String '(passed|failed)' | Select-Object -Last 1).Line)
    $f = Join-Path $Gecici 'arayuz.txt'
    Write-Host '  ... arayuz denetimleri' -ForegroundColor DarkGray
    $arayuz = Join-Path $Proje 'ekran-react'
    foreach ($k in @(@('npx.cmd', 'tsc -b'), @('npm.cmd', 'run lint'), @('npx.cmd', 'vitest run'))) {
        if ((Calistir $arayuz $k[0] $k[1] $f) -ne 0) { Get-Content $f -Tail 15; Dur "Arayuz denetimi basarisiz ($($k[1])); paket olusturulmadi. Ayrinti: $f" }
    }
    Tamam 'tip denetimi, lint ve arayuz testleri gecti'
} else { Write-Host '  testler atlandi (prod yine kendi testini yapar)' -ForegroundColor Yellow }

# --- 3) Paket ---------------------------------------------------------------------------------------------------------------
Adim '3/4 Paket hazirlaniyor'
G bundle create (Join-Path $Gecici 'kod.bundle') $dal | Out-Null
G bundle verify (Join-Path $Gecici 'kod.bundle') | Out-Null
Tamam 'kod.bundle'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$ErrorActionPreference = 'Continue'
$freeze = @(& $Py -m pip freeze --disable-pip-version-check 2>$null)
$ErrorActionPreference = 'Stop'
$pyVer = (& $Py -c "import sys; print(sys.version.split()[0])").Trim()
[IO.Compression.ZipFile]::CreateFromDirectory((Join-Path $Proje '.venv'), (Join-Path $Gecici 'python_venv.zip'), [IO.Compression.CompressionLevel]::Optimal, $false)
Tamam "python_venv.zip (Python $pyVer, $(@($freeze).Count) paket)"
$kilit = Join-Path $Proje 'ekran-react\package-lock.json'
[IO.Compression.ZipFile]::CreateFromDirectory((Join-Path $Proje 'ekran-react\node_modules'), (Join-Path $Gecici 'node_modules.zip'), [IO.Compression.CompressionLevel]::Optimal, $false)
Tamam 'node_modules.zip'
$dosyalar = [ordered]@{}
foreach ($d in 'kod.bundle', 'python_venv.zip', 'node_modules.zip') { $dosyalar[$d] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Gecici $d)).Hash }
$manifest = [ordered]@{
    olusturma = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'); kullanici = $env:USERNAME; makine = $env:COMPUTERNAME
    dal = $dal; commit = $commit; commit_zamani = $commitZamani; ozet = $ozet; testler = ($test -eq 'E')
    python = $pyVer; pip_freeze = (Parmak-Izi $freeze); package_lock = (Get-FileHash -Algorithm SHA256 -LiteralPath $kilit).Hash
    dosyalar = $dosyalar
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $Gecici 'manifest.json') -Encoding ASCII

# --- 4) Yayinla (eski paketin yerine, tek adimda) ---------------------------------------------------------------------------
Adim '4/4 Paket yayinlaniyor'
foreach ($d in 'kod.bundle', 'python_venv.zip', 'node_modules.zip', 'manifest.json') {
    Move-Item -Force -LiteralPath (Join-Path $Gecici $d) -Destination (Join-Path $Cikis $d)
}
Remove-Item -Recurse -Force -LiteralPath $Gecici -ErrorAction SilentlyContinue
Tamam "Masaustu\TAMLIFE_GONDER hazir: $ozet"
Write-Host ''
Write-Host 'Simdi PROD sunucuya (uzak masaustu) baglanin ve sunu cift tiklayin:' -ForegroundColor Cyan
Write-Host '    E:\TAMLIFE\TAMLIFE_v3.5\PROD_GUNCELLE.bat' -ForegroundColor Cyan
Write-Host '  (paketi bu masaustunden alir, dogrular, prod''da test eder, onayinizla uygular ve paneli yeniden baslatir)'
if (-not $TestYok) { Read-Host 'Kapatmak icin Enter' }
exit 0
