# TAMLIFE kodunu Citrix oturumundan yerel PC'ye 1:1 tasir (2026-11-25 kullanici: "kodu citrix uzerinden lokal pc ye 1:1
# tasiyabilecegim robocopy betigini hazirla").
#
# Neden zip + tek dosya robocopy: istemci surucu yonlendirmesi (\\Client\C$, \\tsclient\C) dosya basina cok yavas
# (20 bin dosya taramak bile 20 dk+). Bu yuzden agac once sunucuda tek zip'e konur, robocopy yalniz zip + kurulum
# dosyalarini gonderir, yerelde KUR_YEREL.bat zip'i acip hedefe robocopy /MIR ile 1:1 yansitir.
#
# Dahil (1:1): kod, .git (tum dallar/gecmis), .venv, node_modules, ekran-react\dist, ceviri_modeli, backend\.env (SIR icerir!).
# Haric: backend\var (canli calisma verisi, GB'larca), var (calisma gunlukleri), __pycache__/.pytest_cache/.ruff_cache/.mypy_cache,
#        *.log. Veritabani (PostgreSQL) bu agacta degildir, tasinmaz.
#
# Kullanim (sunucuda, Citrix oturumunda):
#   powershell -ExecutionPolicy Bypass -File E:\TAMLIFE\kurulum\yerele_kopyala.ps1
#   powershell -ExecutionPolicy Bypass -File E:\TAMLIFE\kurulum\yerele_kopyala.ps1 -Hedef "\\Client\C$\Users\<yerel kullanici>\Desktop\TAMLIFE_PAKET"
#   -EnvHaric : backend\.env (parolalar) pakete konmaz.
# Yerel PC'de: Masaustu\TAMLIFE_PAKET\KUR_YEREL.bat  (varsayilan hedef %USERPROFILE%\Desktop\TAMLIFE; ilk arguman baska klasor)
param(
    [string]$Kaynak = 'E:\TAMLIFE',
    [string]$Hedef = '',
    [switch]$EnvHaric
)
$ErrorActionPreference = 'Stop'

function Yaz([string]$m) { Write-Host ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m) }

# 1) Hedef: verilmediyse istemci surucusunde (Citrix \\Client\C$, uzak masaustu \\tsclient\C) tek kullanici masaustu
if (-not $Hedef) {
    $kokler = @('\\Client\C$', '\\tsclient\C') | Where-Object { Test-Path "$_\Users" }
    if (-not $kokler) { throw "Istemci C: surucusu gorunmuyor (\\Client\C$ / \\tsclient\C). Citrix'te istemci surucu erisimine izin verin ya da -Hedef verin." }
    $adaylar = foreach ($k in $kokler) {
        Get-ChildItem "$k\Users" -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notin @('Public', 'Default', 'Default User', 'All Users') -and (Test-Path "$($_.FullName)\Desktop") } |
            ForEach-Object { "$($_.FullName)\Desktop\TAMLIFE_PAKET" }
    }
    $adaylar = @($adaylar | Select-Object -Unique)
    if ($adaylar.Count -ne 1) {
        throw ("Yerel masaustu tek anlamli bulunamadi ({0} aday): {1}`n-Hedef ile verin, or. -Hedef `"\\Client\C$\Users\<kullanici>\Desktop\TAMLIFE_PAKET`"" -f $adaylar.Count, ($adaylar -join ', '))
    }
    $Hedef = $adaylar[0]
}
Yaz "Kaynak: $Kaynak"
Yaz "Hedef : $Hedef"

# 2) Paket: gecici klasorde tek zip (tar = Windows yerlesik bsdtar)
$is = Join-Path $env:TEMP ("tamlife_paket_" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Force $is | Out-Null
$zip = Join-Path $is 'TAMLIFE.zip'
$haric = @('./backend/var', './var', '*/__pycache__', '*/.pytest_cache', '*/.ruff_cache', '*/.mypy_cache', '*.log')
if ($EnvHaric) { $haric += './backend/.env' }
$tarArg = @('-a', '-c', '-f', $zip, '-C', $Kaynak) + ($haric | ForEach-Object { "--exclude=$_" }) + @('.')
Yaz "Zip hazirlaniyor (birkac dakika surebilir)..."
& tar.exe @tarArg
if ($LASTEXITCODE -ne 0) { throw "tar hatasi ($LASTEXITCODE)" }
$ozet = (Get-FileHash $zip -Algorithm SHA256).Hash
$boyut = (Get-Item $zip).Length
$sha = Join-Path $is 'TAMLIFE.zip.sha256'
Set-Content -Path $sha -Value "$ozet  TAMLIFE.zip" -Encoding ascii
$commit = (& git -C $Kaynak log -1 --format='%h %s' 2>$null) -join ''
$dal = (& git -C $Kaynak rev-parse --abbrev-ref HEAD 2>$null) -join ''
Set-Content -Path (Join-Path $is 'PAKET_BILGI.txt') -Encoding utf8 -Value @(
    "Tarih  : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", "Kaynak : $Kaynak", "Dal    : $dal", "Commit : $commit",
    "Zip    : $boyut bayt", "SHA256 : $ozet", "Haric  : $($haric -join ', ')")
Yaz ("Zip: {0:N1} MB, SHA256 {1}" -f ($boyut / 1MB), $ozet)

# 3) Yerel kurulum betigi: SHA dogrula -> gecici klasore ac -> hedefe robocopy /MIR (1:1)
$bat = @'
@echo off
setlocal
rem TAMLIFE yerel kurulum: zip butunlugu (SHA-256) -> ac -> hedefe robocopy /MIR (1:1).
rem /MIR: pakette olmayan dosyalar hedeften SILINIR. backend\var ve var (yerel calisma verisi) korunur (/XD).
set "PAKET=%~dp0"
set "HEDEF=%~1"
if "%HEDEF%"=="" set "HEDEF=%USERPROFILE%\Desktop\TAMLIFE"
echo Hedef: %HEDEF%
for /f "tokens=1" %%h in ('type "%PAKET%TAMLIFE.zip.sha256"') do set "BEKLENEN=%%h"
for /f "tokens=* delims=" %%h in ('certutil -hashfile "%PAKET%TAMLIFE.zip" SHA256 ^| findstr /v ":"') do if not defined GERCEK set "GERCEK=%%h"
set "GERCEK=%GERCEK: =%"
if /i not "%BEKLENEN%"=="%GERCEK%" (echo HATA: zip bozuk ^(SHA256 uyusmuyor^). Paketi yeniden kopyalayin. & exit /b 2)
echo SHA256 dogru.
set "AC=%TEMP%\tamlife_ac_%RANDOM%"
mkdir "%AC%" || exit /b 3
tar -x -f "%PAKET%TAMLIFE.zip" -C "%AC%" || (echo HATA: zip acilamadi & exit /b 3)
robocopy "%AC%" "%HEDEF%" /MIR /XD "%AC%\backend\var" "%AC%\var" "%HEDEF%\backend\var" "%HEDEF%\var" /R:2 /W:2 /NP /NFL /NDL /LOG:"%PAKET%kur_yerel_robocopy.log"
set "RC=%ERRORLEVEL%"
rmdir /s /q "%AC%"
if %RC% GEQ 8 (echo HATA: robocopy %RC% - ayrinti: %PAKET%kur_yerel_robocopy.log & exit /b %RC%)
echo Tamam: %HEDEF% paketle 1:1 (robocopy %RC%). Ayrinti: %PAKET%kur_yerel_robocopy.log
type "%PAKET%PAKET_BILGI.txt"
exit /b 0
'@
Set-Content -Path (Join-Path $is 'KUR_YEREL.bat') -Value $bat -Encoding ascii

# 4) robocopy: paket klasoru -> istemci masaustu (/MIR: hedefteki eski paket dosyalari silinir)
# /Z yeniden baslatilabilir (kopma olursa kaldigi yerden), /R:5 /W:5 tekrar, /FFT ag paylasiminda 2 sn zaman toleransi
Yaz "robocopy ile gonderiliyor..."
$log = Join-Path $is 'robocopy_gonder.log'
& robocopy.exe $is $Hedef /MIR /Z /R:5 /W:5 /FFT /NP "/LOG:$log" /XF 'robocopy_gonder.log'
$rc = $LASTEXITCODE
if ($rc -ge 8) { throw "robocopy HATA ($rc). Gunluk: $log" }
$uzak = Get-Item (Join-Path $Hedef 'TAMLIFE.zip')
if ($uzak.Length -ne $boyut) { throw "Boyut uyusmuyor: yerel $boyut, hedef $($uzak.Length)" }
Copy-Item $log (Join-Path $Hedef 'robocopy_gonder.log') -Force
Remove-Item $is -Recurse -Force
Yaz "TAMAM (robocopy $rc). Yerel PC'de calistirin: $Hedef\KUR_YEREL.bat"
