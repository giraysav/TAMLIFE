# Ariza aninda salt okunur tani; -Tam ile izole regresyon, arayuz ve yuk testleri.
param([switch]$Tam, [switch]$Backend, [switch]$Arayuz, [switch]$Yuk,
      [string]$Python = '', [ValidateRange(1,7200)][int]$ZamanAsimi = 900)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'calisma_kimligi.ps1')
Tamlife-KimlikDogrula
$root = Split-Path -Parent $PSScriptRoot
$choices = @($Tam, $Backend, $Arayuz, $Yuk) | Where-Object { $_.IsPresent }
if ($choices.Count -gt 1) { throw 'Yalniz bir kip secin: -Tam, -Backend, -Arayuz veya -Yuk.' }
$mode = 'hizli'
if ($Tam) { $mode = 'tam' }
if ($Backend) { $mode = 'backend' }
if ($Arayuz) { $mode = 'arayuz' }
if ($Yuk) { $mode = 'yuk' }
if (-not $Python) {
    $Python = Join-Path $root 'var\test\ortam\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $Python)) { $Python = Join-Path $root '.venv\Scripts\python.exe' }
}
if (-not (Test-Path -LiteralPath $Python)) { throw 'Python bulunamadi. -Python ile yorumlayici yolunu verin.' }
$env:PYTHONUTF8 = '1'
$runner = Join-Path $root 'backend\araclar\genel_test.py'
# Yerel komutun stderr ciktisi PS 5.1'de istisna olarak test sonucunu gizlememeli.
$ErrorActionPreference = 'Continue'
& $Python $runner --mode $mode --python $Python --timeout $ZamanAsimi
exit $LASTEXITCODE
