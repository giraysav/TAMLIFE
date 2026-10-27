# TAMLIFE - Citrix gelistirme makinesinde kurulum (saf ASCII; PS 5.1). Cagiran: KUR_CITRIX.bat (Masaustu\TAMLIFE_PAKET icinde).
# Paketi sunucuda kurulum\citrix_paket.ps1 hazirlar. Bu betik:
#   1) TAMLIFE_paket.zip'in SHA-256 ozetini dogrular (aktarimda bozulduysa durur, hicbir sey degismez)
#   2) Zip'i YEREL gecici klasore acar (hizli; \\tsclient yok)
#   3) Masaustu\TAMLIFE klasorunde calisan surec (python / node / VS Code terminali) varsa kapatmayi sorar
#   4) Masaustu\TAMLIFE\TAMLIFE_v3.5'i paketle AYNI yapar (robocopy /MIR: kaynakta olmayan eski dosyalar silinir; karar 2026-10-27
#      "eskinin uzerine"). backend\var ve var aynalanmaz: icindeki eski gunluk / yedekler korunur; dev.db paketteki anlik kopyayla
#      degisir, eski dev.db-wal / dev.db-shm silinir (yeni kopyayla karisirsa veritabanini bozar).
#      Kok klasordeki diger seyler (wheels, yamalar ...) silinmez; kok dosyalari guncellenir.
#   5) Python ve paketlerin calistigini denetler; sonuc ozeti.
param([string]$Hedef = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'TAMLIFE'))
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8  # git ciktisindaki Turkce harfler bozulmasin

$Paket = $PSScriptRoot
$Zip = Join-Path $Paket 'TAMLIFE_paket.zip'
$Gecici = Join-Path $env:TEMP ("tamlife_kur_" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
$Gunluk = Join-Path $Paket ("kurulum_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log')

function Adim($m) { Write-Host ''; Write-Host "=== $m ===" -ForegroundColor Cyan }
function Tamam($m) { Write-Host "  [TAMAM] $m" -ForegroundColor Green }
function Uyari($m) { Write-Host "  [UYARI] $m" -ForegroundColor Yellow }
function Dur($m) {
    Write-Host "  [HATA] $m" -ForegroundColor Red
    Write-Host "  Masaustu\TAMLIFE degistirilmedi (ya da yarim kaldiysa ayni betigi yeniden calistirin). Gunluk: $Gunluk"
    if (Test-Path $Gecici) { Remove-Item -Recurse -Force -LiteralPath $Gecici -ErrorAction SilentlyContinue }
    Read-Host 'Kapatmak icin Enter'
    exit 1
}
function Robocopy-Calistir($argumanlar, $ad) {
    $s = Start-Process -FilePath 'robocopy.exe' -ArgumentList $argumanlar -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$Gunluk.$ad.txt"
    Get-Content "$Gunluk.$ad.txt" | Add-Content -Path $Gunluk
    Remove-Item "$Gunluk.$ad.txt" -Force -ErrorAction SilentlyContinue
    return $s.ExitCode
}

Write-Host '========================================================' -ForegroundColor Cyan
Write-Host ' TAMLIFE - Citrix gelistirme kurulumu' -ForegroundColor Cyan
Write-Host " Paket: $Paket" -ForegroundColor Cyan
Write-Host " Hedef: $Hedef" -ForegroundColor Cyan
Write-Host '========================================================' -ForegroundColor Cyan
Set-Content -Path $Gunluk -Value "TAMLIFE Citrix kurulumu - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $env:USERNAME" -Encoding ASCII

# --- 1) Butunluk -----------------------------------------------------------------------------------------------------------
Adim '1/5 Paket butunlugu'
if (-not (Test-Path $Zip)) { Dur "Paket yok: $Zip" }
$beklenen = (Get-Content (Join-Path $Paket 'TAMLIFE_paket.sha256') -ErrorAction SilentlyContinue | Select-Object -First 1)
if (-not $beklenen) { Dur 'TAMLIFE_paket.sha256 yok' }
$gercek = (Get-FileHash -Algorithm SHA256 -LiteralPath $Zip).Hash
if ($gercek -ne $beklenen.Trim()) { Dur 'Zip aktarimda bozulmus (SHA-256 tutmuyor). Sunucuda TAMLIFE_robocopy_gonder.bat dosyasini yeniden calistirin.' }
Tamam "SHA-256 dogrulandi ($($gercek.Substring(0, 12))...)"

# --- 2) Yerelde ac ---------------------------------------------------------------------------------------------------------
Adim '2/5 Paket aciliyor (yerel gecici klasor)'
Add-Type -AssemblyName System.IO.Compression.FileSystem
try { [IO.Compression.ZipFile]::ExtractToDirectory($Zip, $Gecici) } catch { Dur "Zip acilamadi: $($_.Exception.Message)" }
$kaynak = Join-Path $Gecici 'TAMLIFE_v3.5'
if (-not (Test-Path (Join-Path $kaynak 'CLAUDE.md'))) { Dur 'Paket icerigi beklenen yapida degil (TAMLIFE_v3.5 yok)' }
Tamam "$((Get-ChildItem $Gecici -Recurse -File -Force | Measure-Object).Count) dosya acildi"

# --- 3) Hedefte calisan surec ----------------------------------------------------------------------------------------------
Adim '3/5 Hedefte calisan surec denetimi'
$desen = [regex]::Escape($Hedef + '\')
$surecler = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessId -ne $PID -and (($_.CommandLine -match $desen) -or ($_.ExecutablePath -match $desen)) })
if ($surecler.Count -gt 0) {
    $surecler | ForEach-Object { Write-Host "    $($_.ProcessId) $($_.Name)" }
    Uyari 'Bu surecler Masaustu\TAMLIFE dosyalarini kullaniyor; acik kalirlarsa bazi dosyalar guncellenemez.'
    $c = (Read-Host '  Kapatayim mi? [E/H] (H: once VS Code ve terminalleri kendiniz kapatin, sonra betigi yeniden calistirin)').Trim().ToUpper()
    if ($c -ne 'E') { Dur 'Kurulum durduruldu; acik surecleri kapatip yeniden calistirin.' }
    $surecler | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}
Tamam 'hedef klasoru kullanan surec yok'

# --- 4) Guncelle -----------------------------------------------------------------------------------------------------------
Adim '4/5 Masaustu\TAMLIFE guncelleniyor'
New-Item -ItemType Directory -Force -Path $Hedef | Out-Null
$hedefProje = Join-Path $Hedef 'TAMLIFE_v3.5'
# Proje: ayna (eski dosyalar temizlenir); backend\var ve var haric (yerel gunluk / yedekler korunur)
$arg = "`"$kaynak`" `"$hedefProje`" /MIR /COPY:DAT /DCOPY:DAT /XJ /R:3 /W:3 /NP /NFL /NDL /MT:8 /XD `"$kaynak\backend\var`" `"$kaynak\var`" `"$hedefProje\backend\var`" `"$hedefProje\var`""
$kod = Robocopy-Calistir $arg 'proje'
if ($kod -ge 8) { Dur "Proje guncellenemedi (robocopy kodu $kod). Ayrinti: $Gunluk" }
Tamam "TAMLIFE_v3.5 guncellendi (robocopy kodu $kod)"
# Veritabani: anlik kopya; eski WAL/SHM silinir
$hedefVar = Join-Path $hedefProje 'backend\var'
New-Item -ItemType Directory -Force -Path $hedefVar | Out-Null
foreach ($ek in @('-wal', '-shm')) { Remove-Item -LiteralPath (Join-Path $hedefVar "dev.db$ek") -Force -ErrorAction SilentlyContinue }
Copy-Item -LiteralPath (Join-Path $kaynak 'backend\var\dev.db') -Destination (Join-Path $hedefVar 'dev.db') -Force
Tamam "dev.db yerlestirildi ($([math]::Round((Get-Item (Join-Path $hedefVar 'dev.db')).Length / 1MB)) MB)"
# Kok dosyalari ve klasorleri (TAMLIFE_v3.5 disi): guncellenir, hedefteki baska seyler silinmez
$arg = "`"$Gecici`" `"$Hedef`" /E /COPY:DAT /XJ /R:3 /W:3 /NP /NFL /NDL /XD `"$kaynak`""
$kod = Robocopy-Calistir $arg 'kok'
if ($kod -ge 8) { Dur "Kok dosyalari guncellenemedi (robocopy kodu $kod)" }
Tamam 'kok dosyalari guncellendi'

# --- 5) Denetim ------------------------------------------------------------------------------------------------------------
Adim '5/5 Denetim'
$cfg = Join-Path $hedefProje '.venv\pyvenv.cfg'
$satirlar = Get-Content $cfg
$home_ = (($satirlar | Where-Object { $_ -match '^home\s*=' }) -replace '^home\s*=\s*', '').Trim()
$surum = (($satirlar | Where-Object { $_ -match '^version\s*=' }) -replace '^version\s*=\s*', '').Trim()
if (-not (Test-Path (Join-Path $home_ 'python.exe'))) {
    # Prod'un Python'u (ayni surum) kullanici klasorune: yonetici / internet gerekmez. .venv pyvenv.cfg bu klasore baglanir.
    $kisisel = Join-Path $env:LOCALAPPDATA ('Programs\Python\Python' + ($surum -replace '^(\d+)\.(\d+).*', '$1$2'))
    $pyZip = Join-Path $Paket 'python.zip'
    if (-not (Test-Path (Join-Path $kisisel 'python.exe'))) {
        if (-not (Test-Path $pyZip)) { Dur "Python $surum bu makinede yok ve pakette python.zip yok." }
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $pyZip).Hash -ne (Get-Content (Join-Path $Paket 'python.sha256') | Select-Object -First 1).Trim()) { Dur 'python.zip aktarimda bozulmus (SHA-256).' }
        try { [IO.Compression.ZipFile]::ExtractToDirectory($pyZip, $kisisel) } catch { Dur "Python acilamadi: $($_.Exception.Message)" }
        Tamam "Python $surum kuruldu: $kisisel (yalniz bu kullanici)"
    }
    $satirlar = $satirlar | ForEach-Object {
        if ($_ -match '^home\s*=') { "home = $kisisel" } elseif ($_ -match '^executable\s*=') { "executable = $kisisel\python.exe" } else { $_ }
    }
    Set-Content -Path $cfg -Value $satirlar -Encoding ASCII
    $home_ = $kisisel
    Tamam ".venv bu Python'a baglandi"
}
if (-not (Test-Path (Join-Path $home_ 'python.exe'))) {
    Uyari ".venv Python'u bulamiyor: $home_\python.exe yok."
} else {
    $py = Join-Path $hedefProje '.venv\Scripts\python.exe'
    Push-Location (Join-Path $hedefProje 'backend')
    $cikti = & $py -c "import app.main, fastapi, sqlalchemy; print('ok')" 2>&1
    Pop-Location
    if (($cikti | Select-Object -Last 1) -eq 'ok') { Tamam 'Python ve paketler calisiyor (uygulama yuklenebiliyor)' } else { Uyari "Uygulama yuklenemedi: $(($cikti | Select-Object -Last 2) -join ' ')" }
}
if (Test-Path (Join-Path $hedefProje 'ekran-react\node_modules')) { Tamam 'arayuz paketleri (node_modules) yerinde' } else { Uyari 'node_modules yok: ekran-react klasorunde npm ci calistirin' }
if (Get-Command git -ErrorAction SilentlyContinue) {
    Push-Location $hedefProje
    $dal = (& git rev-parse --abbrev-ref HEAD 2>$null); $son = (& git log --oneline -1 2>$null)
    Pop-Location
    Tamam "git: $dal / $son"
}
Remove-Item -Recurse -Force -LiteralPath $Gecici -ErrorAction SilentlyContinue
Write-Host ''
Write-Host '========================================================' -ForegroundColor Green
Write-Host " Kurulum bitti: $hedefProje" -ForegroundColor Green
Write-Host ' VS Code: File > Open Folder > Masaustu\TAMLIFE\TAMLIFE_v3.5' -ForegroundColor Green
Write-Host " Gunluk: $Gunluk" -ForegroundColor Green
Write-Host '========================================================' -ForegroundColor Green
Read-Host 'Kapatmak icin Enter'
exit 0
