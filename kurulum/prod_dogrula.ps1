# TAMLIFE - PROD canli dogrulama (saf ASCII; PS 5.1; yalniz OKUR). prod_guncelle.ps1 uygulamadan sonra cagirir; elle de calisir:
#   powershell -File kurulum\prod_dogrula.ps1 -Commit <sha> -Baslangic "YYYY-MM-DD HH:MM:SS"
# 2026-10-27 kullanici: "prod'a gonder calisinca prod'a gelen tum gelistirmenin sorunsuz calistiginin teyit edilmesi".
# Denetimler: zamanlanmis gorevler calisiyor mu, https://tamlife, backend\araclar\panel_saglik.py (veritabani butunlugu, sema, arizalar,
# dis baglantilar) ve backend\araclar\guncelleme_dogrula.py (kod tam gonderilen commit'te mi, sema kodla ayni mi, arayuz bu
# guncellemede derlenip canlida yukleniyor mu, tum ana modul API uclari ayakta mi, ReportDB iscisi guncellemeden sonra basariyla
# calisti mi (en cok 8 dk beklenir), guncellemeden sonra yeni sunucu hatasi var mi). Cikis kodu = HATA sayisi.
param(
    [string]$Commit = '',
    [string]$Baslangic = (Get-Date).AddMinutes(-15).ToString('yyyy-MM-dd HH:mm:ss'),
    [string]$Rapor = '',
    [int]$Bekle = 480
)
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$Proje = Split-Path $PSScriptRoot -Parent
$Backend = Join-Path $Proje 'backend'
$Py = Join-Path $Proje '.venv\Scripts\python.exe'
if (-not $Rapor) { $Rapor = Join-Path $Proje ("var\log\prod_dogrula_" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.txt') }
New-Item -ItemType Directory -Force -Path (Split-Path $Rapor) | Out-Null
$hata = 0; $uyari = 0; $tamam = 0

function Kaydet($durum, $ad, $ayrinti) {
    $renk = @{ TAMAM = 'Green'; UYARI = 'Yellow'; HATA = 'Red'; BILGI = 'DarkGray' }[$durum]
    Write-Host ("  [{0,-5}] {1}" -f $durum, $ad) -ForegroundColor $renk -NoNewline
    if ($ayrinti) { Write-Host "  - $ayrinti" -ForegroundColor DarkGray } else { Write-Host '' }
    Add-Content -Path $Rapor -Value ("[{0,-5}] {1}  {2}" -f $durum, $ad, $ayrinti) -Encoding UTF8
    switch ($durum) { 'HATA' { $script:hata++ } 'UYARI' { $script:uyari++ } 'TAMAM' { $script:tamam++ } }
}
function Python-Denetim($betik, $argumanlar) {
    $f = "$Rapor.$([IO.Path]::GetFileNameWithoutExtension($betik)).txt"
    $s = Start-Process -FilePath $Py -ArgumentList "$betik $argumanlar" -WorkingDirectory $Backend -NoNewWindow -Wait -PassThru -RedirectStandardOutput $f -RedirectStandardError "$f.err"
    foreach ($satir in (Get-Content $f -Encoding UTF8)) {
        $p = $satir -split '\|', 3
        if ($p.Count -eq 3 -and $p[0] -in @('TAMAM', 'UYARI', 'HATA', 'BILGI')) { Kaydet $p[0] $p[1] $p[2] }
    }
    if ($s.ExitCode -lt 0 -or (Test-Path "$f.err") -and (Get-Content "$f.err" | Select-String 'Traceback')) { Kaydet 'HATA' $betik "calismadi: $f.err" }
}

Set-Content -Path $Rapor -Value "TAMLIFE prod dogrulama - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - commit $Commit - guncelleme $Baslangic" -Encoding UTF8
Write-Host ''
Write-Host '=== Canli dogrulama ===' -ForegroundColor Cyan
foreach ($g in @(@('TAMLIFE_v35_Panel', 'Panel gorevi'), @('TAMLIFE_v35_TLS_Vekil', 'TLS vekili gorevi'))) {
    $t = Get-ScheduledTask -TaskName $g[0] -ErrorAction SilentlyContinue
    if ($t -and $t.State -eq 'Running') { Kaydet 'TAMAM' $g[1] 'calisiyor' } else { Kaydet 'HATA' $g[1] "durum: $(if ($t) { $t.State } else { 'kayitli degil' })" }
}
$t = Get-ScheduledTask -TaskName 'TAM_Life_v35_ReportDB_6dk' -ErrorAction SilentlyContinue
if ($t -and $t.State -ne 'Disabled') { Kaydet 'TAMAM' 'ReportDB isci gorevi' "durum $($t.State)" } else { Kaydet 'HATA' 'ReportDB isci gorevi' 'devre disi ya da yok' }
try { $ok = ((Invoke-WebRequest -Uri 'https://tamlife/api/v1/health' -UseBasicParsing -TimeoutSec 10).StatusCode -eq 200) } catch { $ok = $false }
if ($ok) { Kaydet 'TAMAM' 'Kullanici adresi (https://tamlife)' 'yanit veriyor' } else { Kaydet 'HATA' 'Kullanici adresi (https://tamlife)' 'yanit yok' }
Python-Denetim 'araclar\panel_saglik.py' ''
Python-Denetim 'araclar\guncelleme_dogrula.py' "--commit `"$Commit`" --baslangic `"$Baslangic`" --bekle $Bekle"

Write-Host ''
$renk = if ($hata) { 'Red' } elseif ($uyari) { 'Yellow' } else { 'Green' }
Write-Host '========================================================' -ForegroundColor $renk
if ($hata) { Write-Host " DOGRULANAMADI: $hata HATA, $uyari UYARI, $tamam TAMAM" -ForegroundColor Red }
else { Write-Host " DOGRULANDI: yeni surum canlida sorunsuz calisiyor ($tamam TAMAM, $uyari UYARI)" -ForegroundColor Green }
Write-Host " Rapor: $Rapor"
Write-Host '========================================================' -ForegroundColor $renk
Add-Content -Path $Rapor -Value "SONUC: $tamam TAMAM, $uyari UYARI, $hata HATA" -Encoding UTF8
exit $hata
