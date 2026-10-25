# TAMLIFE kok klasorunu E:\TAMLIFE_Dev -> E:\TAMLIFE yapar (2026-10-21 kullanici karari). Betik saf ASCII (PS 5.1).
# ONCE VS Code'u (Claude Code dahil) ve klasorde acik tum terminalleri kapatin; acik dosya tutan surec yeniden adlandirmayi engeller.
# YONETICI PowerShell'de, klasorun DISINDAN calistirin:
#   cd E:\
#   powershell -NoProfile -ExecutionPolicy Bypass -File E:\TAMLIFE_Dev\TAMLIFE_v3.5\kurulum\klasor_adi_degistir.ps1
# Parola sormaz: gorevler once canli_gorev_kur.ps1 -Hemen ile parolasiz kipe alinmis olmali (degilse hicbir sey degismeden durur).
# Adimlar: gorev yedegi (XML, %TEMP%) -> gorevleri
# durdur -> klasordeki surecleri kapat -> yeniden adlandir -> gorev yollarini guncelle -> venv activate yollari -> Claude hafizasi
# kopyasi -> panel + TLS vekili baslat, saglik denetimi -> isci gorevini ac. Yeniden adlandirmadan sonra hata olursa klasor eski
# adina dondurulur ve gorevler yedekten geri yuklenir. Sonra VS Code'da E:\TAMLIFE klasorunu acin.
param([string]$Eski = 'E:\TAMLIFE_Dev', [string]$Yeni = 'E:\TAMLIFE')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'calisma_kimligi.ps1')

$Gorevler = @('TAMLIFE_v35_Panel', 'TAMLIFE_v35_TLS_Vekil', 'TAM_Life_v35_ReportDB_6dk')
$Isci = 'TAM_Life_v35_ReportDB_6dk'

function Yaz($m) { Write-Host ('[*] ' + $m) -ForegroundColor Cyan }
function Uyar($m) { Write-Host ('[!] ' + $m) -ForegroundColor Yellow }
function Saglik-Bekle($uri) {
    for ($i = 0; $i -lt 40; $i++) {
        try { $r = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 3; if ($r.StatusCode -eq 200) { return } } catch {}
        Start-Sleep -Seconds 2
    }
    throw ('Saglik denetimi gecmedi: ' + $uri)
}
function Klasor-Surecleri($kok) {
    $desen = [regex]::Escape($kok + '\')
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $PID -and (($_.CommandLine -match $desen) -or ($_.ExecutablePath -match $desen))
    })
}
function Surecleri-Kapat($kok) {
    for ($tur = 0; $tur -lt 3; $tur++) {
        $liste = Klasor-Surecleri $kok
        if ($liste.Count -eq 0) { return }
        foreach ($p in $liste) {
            Yaz ('Surec kapatiliyor: ' + $p.ProcessId + ' ' + $p.Name)
            & taskkill.exe /PID $p.ProcessId /T /F 2>$null | Out-Null
        }
        Start-Sleep -Seconds 2
    }
    $kalan = Klasor-Surecleri $kok
    if ($kalan.Count -gt 0) { throw ('Kapatilamayan surec var: ' + (($kalan | ForEach-Object { '' + $_.ProcessId + ' ' + $_.Name }) -join ', ')) }
}
# Gorevler parolasiz (Interactive) kipte olmali; parolali kip on denetimde reddedilir (PAM 24 sa donusu, 2026-10-25).
function Gorev-Kaydet($ad, $xml) {
    Register-ScheduledTask -TaskName $ad -Xml $xml -Force | Out-Null
}
function Gorevleri-Durdur {
    if (Get-ScheduledTask -TaskName $Isci -ErrorAction SilentlyContinue) { Disable-ScheduledTask -TaskName $Isci | Out-Null }
    foreach ($ad in $Gorevler) { Stop-ScheduledTask -TaskName $ad -ErrorAction SilentlyContinue }
}
function Gorevleri-Baslat {
    Start-ScheduledTask -TaskName 'TAMLIFE_v35_Panel'
    Saglik-Bekle 'http://127.0.0.1:8117/api/v1/health'
    Yaz 'Panel saglikli (http://127.0.0.1:8117)'
    Start-ScheduledTask -TaskName 'TAMLIFE_v35_TLS_Vekil'
    Saglik-Bekle 'https://tamlife/api/v1/health'
    Yaz 'TLS vekili saglikli (https://tamlife)'
    Enable-ScheduledTask -TaskName $Isci | Out-Null
    Yaz ('Isci gorevi acildi: ' + $Isci)
}
function Metin-Degistir($dosya) {
    if (-not (Test-Path -LiteralPath $dosya)) { return }
    $metin = [IO.File]::ReadAllText($dosya)
    $yeniMetin = [regex]::Replace($metin, [regex]::Escape($Eski + '\'), ($Yeni + '\').Replace('$', '$$'), 'IgnoreCase')
    if ($yeniMetin -ne $metin) { [IO.File]::WriteAllText($dosya, $yeniMetin); Yaz ('Yol guncellendi: ' + $dosya) }
}

# --- on denetim ---------------------------------------------------------------------------------------------------------
Tamlife-KimlikDogrula
$yonetici = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $yonetici) { throw 'Yonetici (yukseltilmis) PowerShell gerekli.' }
if (-not (Test-Path -LiteralPath $Eski)) { throw ('Kaynak klasor yok: ' + $Eski) }
if (Test-Path -LiteralPath $Yeni) { throw ('Hedef zaten var: ' + $Yeni + ' (dokunulmadi)') }
if ((Get-Location).Path -like ($Eski + '*')) { throw ('Klasorun disindan calistirin: once  cd E:\') }
foreach ($ad in $Gorevler) {
    if ((Get-ScheduledTask -TaskName $ad).Principal.LogonType -eq 'Password') {
        throw ($ad + ' parolali kipte. Once parolasiz kipe alin: ' + $PSScriptRoot + '\canli_gorev_kur.ps1 -Hemen')
    }
}
$acik = @(Get-Process -Name 'Code' -ErrorAction SilentlyContinue)
if ($acik.Count -gt 0) { Uyar 'VS Code acik gorunuyor. Klasorde dosya tutuyorsa yeniden adlandirma basarisiz olur (o durumda hicbir sey degismez).' }

$yedekDizin = Join-Path $env:TEMP ('tamlife_gorev_yedek_' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $yedekDizin -Force | Out-Null
$yedek = @{}
foreach ($ad in $Gorevler) {
    $yedek[$ad] = (Export-ScheduledTask -TaskName $ad) | Out-String
    Set-Content -LiteralPath (Join-Path $yedekDizin ($ad + '.xml')) -Value $yedek[$ad] -Encoding Unicode
}
Yaz ('Gorev yedegi: ' + $yedekDizin)

$asama = 'durdur'
$adlandirildi = $false
try {
    Gorevleri-Durdur
    Start-Sleep -Seconds 2
    Surecleri-Kapat $Eski

    $asama = 'yeniden-adlandir'
    $hata = $null
    for ($i = 0; $i -lt 5; $i++) {
        try { Rename-Item -LiteralPath $Eski -NewName (Split-Path -Leaf $Yeni); $adlandirildi = $true; break } catch { $hata = $_; Start-Sleep -Seconds 2 }
    }
    if (-not $adlandirildi) { throw ('Klasor yeniden adlandirilamadi (acik dosya/terminal?): ' + $hata.Exception.Message) }
    Yaz ($Eski + ' -> ' + $Yeni)

    $asama = 'gorevler'
    foreach ($ad in $Gorevler) {
        $xml = [regex]::Replace($yedek[$ad], [regex]::Escape($Eski + '\'), ($Yeni + '\').Replace('$', '$$'), 'IgnoreCase')
        Gorev-Kaydet $ad $xml
        Yaz ('Gorev guncellendi: ' + $ad)
    }
    Disable-ScheduledTask -TaskName $Isci | Out-Null  # saglik denetiminden sonra acilir

    $asama = 'venv'
    $venv = Join-Path $Yeni 'TAMLIFE_v3.5\.venv'
    foreach ($d in @('Scripts\activate', 'Scripts\activate.bat', 'Scripts\activate.fish', 'Scripts\Activate.ps1', 'pyvenv.cfg')) { Metin-Degistir (Join-Path $venv $d) }

    $asama = 'hafiza'
    $projeler = Join-Path $env:USERPROFILE '.claude\projects'
    $eskiHafiza = Join-Path $projeler 'e--TAMLIFE-Dev\memory'
    $yeniHafiza = Join-Path $projeler 'e--TAMLIFE\memory'
    if ((Test-Path -LiteralPath $eskiHafiza) -and -not (Test-Path -LiteralPath $yeniHafiza)) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $yeniHafiza) -Force | Out-Null
        Copy-Item -LiteralPath $eskiHafiza -Destination $yeniHafiza -Recurse
        Yaz ('Claude hafizasi kopyalandi: ' + $yeniHafiza)
    }

    $asama = 'baslat'
    Gorevleri-Baslat
    Write-Host ''
    Write-Host ('[OK] Tamamlandi. Klasor: ' + $Yeni + '  |  VS Code: File > Open Folder > ' + $Yeni) -ForegroundColor Green
    Write-Host ('     Gorev yedegi (silinebilir): ' + $yedekDizin) -ForegroundColor Green
} catch {
    Write-Host ('[X] Asama ' + $asama + ': ' + $_.Exception.Message) -ForegroundColor Red
    try {
        Gorevleri-Durdur
        if ($adlandirildi) {
            Uyar 'Geri aliniyor: klasor eski adina, gorevler yedekten.'
            Surecleri-Kapat $Yeni
            Rename-Item -LiteralPath $Yeni -NewName (Split-Path -Leaf $Eski)
            foreach ($ad in $Gorevler) { Gorev-Kaydet $ad $yedek[$ad] }
            Disable-ScheduledTask -TaskName $Isci | Out-Null
        }
        Gorevleri-Baslat
        Uyar ('Eski duruma donuldu: ' + $Eski + ' calisiyor.')
    } catch {
        Write-Host ('[X] Geri alma da tamamlanamadi: ' + $_.Exception.Message) -ForegroundColor Red
        Write-Host ('    Gorev yedekleri: ' + $yedekDizin + '  (Register-ScheduledTask -Xml ile geri yuklenir)') -ForegroundColor Red
    }
    exit 1
}
