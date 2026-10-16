# TAMLIFE v3.5 canli paneli KALICI calistirir: Windows acilisinda otomatik baslayan iki zamanlanmis gorev. Betik saf ASCII (PS 5.1).
#   TAMLIFE_v35_Panel     -> kurulum\canli_baslat.ps1  (panel, 127.0.0.1:8117, canli mod)
#   TAMLIFE_v35_TLS_Vekil -> kurulum\tls_vekili.ps1    (https://<VekilAd>:443/ -> panel)
# Gorevler TURKCELL\TAMLIFEADLOG hesabiyla, en yuksek yetkiyle calisir; pencere yoktur. Her gorev bu betigin -Calistir kipini kullanir: asil betigi
# cagirir, ciktisini var\log\canli_panel.log / canli_vekil.log dosyasina yazar (10 MB'ta .1'e doner) ve kapanirsa 15 sn sonra yeniden baslatir.
# Kurulum Windows kimlik bilgisi penceresinden parola alir; dosyaya/gunluge yazmaz. Gerekli: YONETICI PowerShell.
#   .\canli_gorev_kur.ps1                  : iki gorevi kaydeder (baslatmaz; bir sonraki acilista calisir)
#   .\canli_gorev_kur.ps1 -Hemen           : kaydeder ve hemen baslatir, panel saglik denetimini yapar
#   .\canli_gorev_kur.ps1 -Durum           : gorevleri (panel, vekil ve ReportDB 6 dk), panel portunu ve gunluklerin son satirlarini gosterir
#   .\canli_gorev_kur.ps1 -Kaldir          : iki gorevi durdurur ve siler
#   -VekilAd '+'                           : eski panel kapaliyken tum adlari (tamlife, FQDN, IP) yeni panele alir (varsayilan: tamlife)
#   -PanelPort 8117 -VekilPort 443         : portlar
# ON KOSUL: elle acilmis panel penceresini ve elle acilmis vekil penceresini KAPATIN (ayni port / onek iki kez tutulamaz).
param([switch]$Hemen,
      [switch]$Kaldir,
      [switch]$Durum,
      [ValidateSet('', 'panel', 'vekil')]
      [string]$Calistir = '',
      [string]$VekilAd = 'tamlife',
      [int]$PanelPort = 8117,
      [int]$VekilPort = 443)
$ErrorActionPreference = 'Stop'
$Betik = $MyInvocation.MyCommand.Path
$Kok = Split-Path -Parent $PSScriptRoot
$LogKlasoru = Join-Path $Kok 'var\log'
$GorevPanel = 'TAMLIFE_v35_Panel'
$GorevVekil = 'TAMLIFE_v35_TLS_Vekil'
$GorevRapor = 'TAM_Life_v35_ReportDB_6dk'   # kurulum\reportdb_gorev_kur.ps1 kurar; Oracle izni gelene kadar Disabled olabilir

function Adim($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Tamam($m) { Write-Host "[+] $m" -ForegroundColor Green }
function Uyari($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Dur($m)  { Write-Host "[!] $m" -ForegroundColor Red; exit 1 }

# --- Gorevin icinde calisan kip: asil betigi surekli ayakta tutar --------------------------------------------------------------
if ($Calistir) {
    . (Join-Path $PSScriptRoot 'calisma_kimligi.ps1')
    Tamlife-KimlikDogrula
    New-Item -ItemType Directory -Force -Path $LogKlasoru | Out-Null
    $Log = Join-Path $LogKlasoru "canli_$Calistir.log"
    $PsExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if ($Calistir -eq 'panel') {
        $Hedef = Join-Path $PSScriptRoot 'canli_baslat.ps1'
        $Ek = " -Port $PanelPort"
    } else {
        $Hedef = Join-Path $PSScriptRoot 'tls_vekili.ps1'
        $Ek = " -Ad `"$VekilAd`" -Port $VekilPort -HedefPort $PanelPort"
    }
    while ($true) {
        if ((Test-Path $Log) -and ((Get-Item $Log).Length -gt 10MB)) { Move-Item -Path $Log -Destination "$Log.1" -Force }
        $an = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        Add-Content -Path $Log -Value "$an [gorev] baslatiliyor: $Calistir$Ek" -Encoding ASCII
        # cmd yonlendirmesi: uvicorn / alembic bilgi satirlari stderr'e yazar, PS 5.1 bunlari hata kaydi gibi bozardi.
        $komut = '/c ""{0}" -NoProfile -ExecutionPolicy Bypass -File "{1}"{2} >> "{3}" 2>&1"' -f $PsExe, $Hedef, $Ek, $Log
        $kod = -1
        try {
            $surec = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\cmd.exe') -ArgumentList $komut -Wait -PassThru -WindowStyle Hidden
            $kod = $surec.ExitCode
        } catch {
            Add-Content -Path $Log -Value "$an [gorev] baslatilamadi: $($_.Exception.Message)" -Encoding ASCII
        }
        $an = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        Add-Content -Path $Log -Value "$an [gorev] cikti (kod $kod); 15 sn sonra yeniden baslatilacak" -Encoding ASCII
        Start-Sleep -Seconds 15
    }
}

# --- Yonetim kipleri -------------------------------------------------------------------------------------------------------------
$yonetici = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $yonetici) { Dur 'YONETICI (yukseltilmis) PowerShell gerekli.' }

function Gorev-Sil($ad) {
    $g = Get-ScheduledTask -TaskName $ad -ErrorAction SilentlyContinue
    if ($g) {
        Stop-ScheduledTask -TaskName $ad -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $ad -Confirm:$false
        Tamam "Gorev silindi: $ad"
    } else {
        Write-Host "    $ad zaten yok."
    }
}

function Log-Sonu($dosya, $klasor = $LogKlasoru) {
    $yol = Join-Path $klasor $dosya
    if (Test-Path $yol) {
        Write-Host "    --- $dosya (son 6 satir) ---"
        Get-Content -Path $yol -Tail 6 | ForEach-Object { Write-Host "    $_" }
    } else {
        Write-Host "    $dosya henuz yok."
    }
}

if ($Durum) {
    foreach ($ad in $GorevPanel, $GorevVekil, $GorevRapor) {
        $g = Get-ScheduledTask -TaskName $ad -ErrorAction SilentlyContinue
        if ($g) {
            $b = Get-ScheduledTaskInfo -TaskName $ad
            Write-Host "$ad : durum=$($g.State) son sonuc=$($b.LastTaskResult) son calisma=$($b.LastRunTime)"
        } else {
            Write-Host "$ad : kayitli degil"
        }
    }
    $tutan = Get-NetTCPConnection -LocalPort $PanelPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($tutan) { Write-Host "Panel portu $PanelPort dinleniyor (surec $($tutan.OwningProcess))." } else { Write-Host "Panel portu $PanelPort dinlenmiyor." }
    Log-Sonu 'canli_panel.log'
    Log-Sonu 'canli_vekil.log'
    Log-Sonu 'isci.log' (Join-Path $Kok 'backend\var\logs')
    exit 0
}

if ($Kaldir) {
    Adim 'Gorevler durdurulup siliniyor'
    Gorev-Sil $GorevVekil
    Gorev-Sil $GorevPanel
    Uyari "Gorev durunca panel ve vekil de kapanmis olmali. Denetim: Get-NetTCPConnection -LocalPort $PanelPort -State Listen"
    exit 0
}

# --- Kayit ----------------------------------------------------------------------------------------------------------------------------
foreach ($d in 'kurulum\canli_baslat.ps1', 'kurulum\tls_vekili.ps1') {
    if (-not (Test-Path (Join-Path $Kok $d))) { Dur "Dosya yok: $Kok\$d" }
}
if (-not (Test-Path (Join-Path $Kok 'ekran-react\dist\index.html'))) { Dur 'Arayuz derlemesi yok (ekran-react\dist\index.html).' }
$tutan = Get-NetTCPConnection -LocalPort $PanelPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($tutan -and -not (Get-ScheduledTask -TaskName $GorevPanel -ErrorAction SilentlyContinue)) {
    Uyari "Port $PanelPort su an dolu (surec $($tutan.OwningProcess)). Elle acilmis panel penceresini kapatmadan -Hemen kullanmayin."
}

$ayar = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
. (Join-Path $PSScriptRoot 'calisma_kimligi.ps1')
Tamlife-KimlikDogrula
$gorevBilgi = Tamlife-GorevKimlikBilgisi
$tetik = New-ScheduledTaskTrigger -AtStartup

function Gorev-Kaydet($ad, $kip, $ekArg, $acik) {
    $arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Betik`" -Calistir $kip$ekArg"
    $eylem = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg -WorkingDirectory $Kok
    [void](Register-ScheduledTask -TaskName $ad -Action $eylem -Trigger $tetik -Settings $ayar -User $TamlifeCalismaHesabi -Password ($gorevBilgi.GetNetworkCredential().Password) -RunLevel Highest -Description $acik -Force)
    Tamam "Gorev kaydedildi: $ad"
}

Adim 'Gorevler kaydediliyor (TURKCELL\TAMLIFEADLOG, acilista baslar)'
Gorev-Kaydet $GorevPanel 'panel' " -PanelPort $PanelPort" 'TAMLIFE v3.5 paneli (canli mod, 127.0.0.1)'
Gorev-Kaydet $GorevVekil 'vekil' " -VekilAd `"$VekilAd`" -PanelPort $PanelPort -VekilPort $VekilPort" 'TAMLIFE v3.5 TLS vekili (http.sys, https)'
$gorevBilgi = $null

if (-not $Hemen) {
    Tamam 'Tamam. Simdi baslatmak icin: .\canli_gorev_kur.ps1 -Hemen   (ya da Start-ScheduledTask -TaskName TAMLIFE_v35_Panel, sonra TAMLIFE_v35_TLS_Vekil)'
    exit 0
}

Adim 'Gorevler baslatiliyor'
Start-ScheduledTask -TaskName $GorevPanel
$saglik = $false
for ($i = 0; $i -lt 30 -and -not $saglik; $i++) {
    Start-Sleep -Seconds 2
    try {
        $c = Invoke-WebRequest -Uri "http://127.0.0.1:$PanelPort/api/v1/health" -UseBasicParsing -TimeoutSec 3
        $saglik = ($c.StatusCode -eq 200)
    } catch { }
}
if ($saglik) { Tamam "Panel yanit veriyor: http://127.0.0.1:$PanelPort/api/v1/health = 200" } else { Uyari 'Panel 60 sn icinde yanit vermedi: var\log\canli_panel.log dosyasina bakin (-Durum).' }
Start-ScheduledTask -TaskName $GorevVekil
Start-Sleep -Seconds 5
Log-Sonu 'canli_vekil.log'
Tamam "Denetim: curl.exe -s -i --noproxy `"*`" https://$($VekilAd.Replace('+', 'tamlife'))/api/v1/health"