# TAMLIFE v3.5 canli paneli KALICI calistirir: TURKCELL\TAMLIFEADLOG oturumunda otomatik baslayan zamanlanmis gorevler. Saf ASCII (PS 5.1).
#   TAMLIFE_v35_Panel         -> kurulum\canli_baslat.ps1  (panel, 127.0.0.1:8117, canli mod)        oturum acilinca
#   TAMLIFE_v35_TLS_Vekil     -> kurulum\tls_vekili.ps1    (https://<VekilAd>:443/ -> panel)          oturum acilinca
#   TAM_Life_v35_ReportDB_6dk -> python -m app.isci reportdb (reportdb_gorev_kur.ps1 ile ayni eylem)  her 6 dk
# PAROLA YOK (2026-10-25): hesap parolasi kurum PAM'i ile 24 saatte bir donduruluyor; parolali (Password) gorev her donusten sonra
# 0x8007052E ile baslamiyordu. Gorevler LogonType Interactive + en yuksek yetki: parola saklanmaz/sorulmaz, donus gorevleri bozmaz.
# Kosul: hesabin oturumu ACIK olmali. RDP penceresini kapatmak / baglantinin kopmasi sorun degil (oturum surer); "Oturumu kapat"
# (sign out) gorevleri durdurur. Sunucu yeniden baslayinca TAMLIFEADLOG ile bir kez RDP oturumu acilir; panel ve vekil kendiliginden kalkar.
# Panel/vekil gorevi bu betigin -Calistir kipini kullanir: asil betigi cagirir, ciktisini var\log\canli_panel.log / canli_vekil.log
# dosyasina yazar (10 MB'ta .1'e doner) ve kapanirsa 15 sn sonra yeniden baslatir.
# Gerekli: TAMLIFEADLOG oturumunda YONETICI PowerShell.
#   .\canli_gorev_kur.ps1                  : uc gorevi kaydeder (baslatmaz; bir sonraki oturum acilisinda calisir)
#   .\canli_gorev_kur.ps1 -Hemen           : kaydeder, hemen baslatir, gorevlerin gercekten basladigini ve panel sagligini dogrular
#   .\canli_gorev_kur.ps1 -YenidenBaslat   : (full_reboot.bat) her seyi durdurur, gorevleri baslatir; gorev baslamazsa paneli ve
#                                            vekili dogrudan surec olarak acar (bir sonraki yeniden baslatmaya kadar)
#   .\canli_gorev_kur.ps1 -Durum           : gorevleri, panel portunu ve gunluklerin son satirlarini gosterir
#   .\canli_gorev_kur.ps1 -Kaldir          : panel ve vekil gorevlerini durdurur ve siler (ReportDB: reportdb_gorev_kur.ps1 -Kaldir)
#   -VekilAd '+'                           : tum adlar (tamlife, FQDN, IP) (varsayilan: +)
#   -PanelPort 8117 -VekilPort 443         : portlar;  -Istemci : Oracle Instant Client klasoru (ReportDB gorevi)
param([switch]$Hemen,
      [switch]$Kaldir,
      [switch]$Durum,
      [switch]$YenidenBaslat,
      [ValidateSet('', 'panel', 'vekil')]
      [string]$Calistir = '',
      [string]$VekilAd = '+',
      [int]$PanelPort = 8117,
      [int]$VekilPort = 443,
      [string]$Istemci = 'E:\oracle\instantclient_19_32')
$ErrorActionPreference = 'Stop'
$Betik = $MyInvocation.MyCommand.Path
$Kok = Split-Path -Parent $PSScriptRoot
$LogKlasoru = Join-Path $Kok 'var\log'
$GorevPanel = 'TAMLIFE_v35_Panel'
$GorevVekil = 'TAMLIFE_v35_TLS_Vekil'
$GorevRapor = 'TAM_Life_v35_ReportDB_6dk'
$PsExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

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
. (Join-Path $PSScriptRoot 'calisma_kimligi.ps1')

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

function Panel-Saglik($sn) {
    for ($i = 0; $i -lt $sn; $i += 3) {
        try {
            if ((Invoke-WebRequest -Uri "http://127.0.0.1:$PanelPort/api/v1/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds 3
    }
    return $false
}

# Gorevi baslatir ve GERCEKTEN calistigini dogrular: schtasks/Start-ScheduledTask oturum acilamasa da hata vermez (2026-10-23).
function Gorev-Baslat($ad) {
    $g = Get-ScheduledTask -TaskName $ad -ErrorAction SilentlyContinue
    if (-not $g) { Uyari "$ad kayitli degil."; return $false }
    if ($g.State -eq 'Running') { Tamam "$ad zaten calisiyor."; return $true }   # IgnoreNew: ikinci calisma baslamaz
    $once = Get-Date
    Start-ScheduledTask -TaskName $ad
    for ($i = 0; $i -lt 8; $i++) {
        Start-Sleep -Seconds 1
        $b = Get-ScheduledTaskInfo -TaskName $ad
        if ($b.LastRunTime -ge $once.AddSeconds(-2)) { Tamam "$ad basladi."; return $true }
    }
    $hata = Get-WinEvent -FilterHashtable @{ LogName = 'Microsoft-Windows-TaskScheduler/Operational'; Id = 104, 101; StartTime = $once } -ErrorAction SilentlyContinue |
        Where-Object { $_.Message -match [regex]::Escape($ad) } | Select-Object -First 1
    if ($hata -and $hata.Message -match '2147943726') { Uyari "$ad BASLAMADI: gorev eski parolali kipte (0x8007052E). Yeniden kaydedin: .\canli_gorev_kur.ps1 -Hemen" }
    else { Uyari "$ad BASLAMADI (TAMLIFEADLOG oturumu acik mi? Gorev Zamanlayici gunlugune bakin)." }
    return $false
}

# Panel ve vekil donguleri (gorevden ya da dogrudan acilmis) ve portu tutan surec agaclari kapatilir. Bu betigin kendisi haric.
function Hepsini-Durdur {
    foreach ($ad in $GorevVekil, $GorevPanel) { Stop-ScheduledTask -TaskName $ad -ErrorAction SilentlyContinue }
    $surecler = Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='python.exe' OR Name='pythonw.exe' OR Name='cmd.exe'" |
        Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and (
            ($_.CommandLine -match 'canli_gorev_kur\.ps1' -and $_.CommandLine -match '-Calistir') -or
            $_.CommandLine -match 'canli_baslat\.ps1' -or $_.CommandLine -match 'tls_vekili\.ps1') }
    $portu = Get-NetTCPConnection -LocalPort $PanelPort -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in @($surecler.ProcessId) + @($portu) | Where-Object { $_ } | Sort-Object -Unique) {
        & cmd.exe /c "taskkill /PID $p /T /F >nul 2>&1"   # PS 5.1: dogrudan 2>$null, Stop altinda hata kaydina donusur
    }
    for ($i = 0; $i -lt 10 -and (Get-NetTCPConnection -LocalPort $PanelPort -State Listen -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Seconds 1 }
}

# Gorev oturum acamazsa: ayni -Calistir dongusu WMI ile bu oturumun surec agaci DISINDA acilir (bu pencere kapansa da calisir;
# sunucu yeniden baslayinca durur).
function Dogrudan-Baslat($kip, $ekArg) {
    $satir = "`"$PsExe`" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Betik`" -Calistir $kip$ekArg"
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $satir; CurrentDirectory = $Kok }
    if ($r.ReturnValue -eq 0) { Uyari "$kip dogrudan surec olarak acildi (PID $($r.ProcessId))." } else { Uyari "$kip acilamadi (WMI $($r.ReturnValue))." }
}

$PanelEk = " -PanelPort $PanelPort"
$VekilEk = " -VekilAd `"$VekilAd`" -PanelPort $PanelPort -VekilPort $VekilPort"

function Gorevleri-Kaydet {
    foreach ($d in 'kurulum\canli_baslat.ps1', 'kurulum\tls_vekili.ps1') {
        if (-not (Test-Path (Join-Path $Kok $d))) { Dur "Dosya yok: $Kok\$d" }
    }
    if (-not (Test-Path (Join-Path $Kok 'ekran-react\dist\index.html'))) { Dur 'Arayuz derlemesi yok (ekran-react\dist\index.html).' }
    Tamlife-KimlikDogrula
    $kimlik = Tamlife-OturumKimligi   # parolasiz: hesabin acik oturumunda kosar (PAM 24 sa donusu gorevleri bozmaz)
    $ayar = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
    $tetik = New-ScheduledTaskTrigger -AtLogOn -User $TamlifeCalismaHesabi
    $liste = @(@($GorevPanel, 'panel', $PanelEk, 'TAMLIFE v3.5 paneli (canli mod, 127.0.0.1)'),
               @($GorevVekil, 'vekil', $VekilEk, 'TAMLIFE v3.5 TLS vekili (http.sys, https)'))
    foreach ($g in $liste) {
        $arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Betik`" -Calistir $($g[1])$($g[2])"
        $eylem = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg -WorkingDirectory $Kok
        [void](Register-ScheduledTask -TaskName $g[0] -Action $eylem -Trigger $tetik -Settings $ayar -Principal $kimlik -Description $g[3] -Force)
        Tamam "Gorev kaydedildi: $($g[0]) (oturum acilinca, parolasiz)"
    }
    # ReportDB iscisi: reportdb_gorev_kur.ps1 ile ayni eylem; "Once + tekrar" tetigi suresizdir, yeniden baslatmadan sonra da surer.
    $Pyw = Join-Path $Kok '.venv\Scripts\pythonw.exe'
    if ((Test-Path $Pyw) -and (Test-Path (Join-Path $Istemci 'oci.dll'))) {
        $eylem = New-ScheduledTaskAction -Execute $Pyw -Argument ('-m app.isci reportdb --client "{0}"' -f $Istemci) -WorkingDirectory (Join-Path $Kok 'backend')
        $rTetik = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 6)
        $rAyar = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        [void](Register-ScheduledTask -TaskName $GorevRapor -Action $eylem -Trigger $rTetik -Settings $rAyar -Principal $kimlik -Description 'TAMLIFE v3.5 ReportDB alarm senkronu (6 dk)' -Force)
        Tamam "Gorev kaydedildi: $GorevRapor (her 6 dk, parolasiz)"
    } else {
        Uyari "ReportDB gorevi atlandi: $Pyw ya da $Istemci\oci.dll yok."
    }
}

if ($Durum) {
    foreach ($ad in $GorevPanel, $GorevVekil, $GorevRapor) {
        $g = Get-ScheduledTask -TaskName $ad -ErrorAction SilentlyContinue
        if ($g) {
            $b = Get-ScheduledTaskInfo -TaskName $ad
            Write-Host "$ad : durum=$($g.State) kip=$($g.Principal.LogonType) son sonuc=0x$('{0:X}' -f $b.LastTaskResult) son calisma=$($b.LastRunTime) sonraki=$($b.NextRunTime)"
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

if ($YenidenBaslat) {
    Adim 'Calisan panel, vekil ve donguleri durduruluyor'
    Hepsini-Durdur
    Adim 'Gorevler baslatiliyor'
    $panelOk = Gorev-Baslat $GorevPanel
    if ($panelOk -and -not (Panel-Saglik 60)) { Uyari 'Panel gorevi basladi ama 60 sn icinde yanit vermedi.' }
    $vekilOk = Gorev-Baslat $GorevVekil
    $raporOk = Gorev-Baslat $GorevRapor
    if (-not ($panelOk -and $vekilOk -and $raporOk)) {
        Uyari 'Bazi gorevler baslamadi; eski parolali kipteyse bir kez yeniden kaydedin: .\canli_gorev_kur.ps1 -Hemen (parola sormaz).'
        if (-not $panelOk) { Dogrudan-Baslat 'panel' $PanelEk; [void](Panel-Saglik 90) }
        if (-not $vekilOk) { Dogrudan-Baslat 'vekil' $VekilEk; Start-Sleep -Seconds 5 }
    }
    $saglik = Panel-Saglik 30
    $https = $false
    try { $https = ((Invoke-WebRequest -Uri 'https://tamlife/api/v1/health' -UseBasicParsing -TimeoutSec 10).StatusCode -eq 200) } catch { }
    Write-Host ''
    Write-Host "    Panel (127.0.0.1:$PanelPort) : $(if ($saglik) { 'CALISIYOR' } else { 'YANIT YOK' })"
    Write-Host "    https://tamlife/        : $(if ($https) { 'CALISIYOR' } else { 'YANIT YOK' })"
    Write-Host "    Gorevler (acilista)     : panel=$panelOk vekil=$vekilOk reportdb=$raporOk"
    if ($saglik -and $https -and $panelOk -and $vekilOk -and $raporOk) { Tamam 'Tamam: her sey gorevlerle calisiyor; yeniden baslatmadan sonra TAMLIFEADLOG oturumu acilinca kalkar.'; exit 0 }
    if ($saglik -and $https) { Uyari 'Panel acik ama gorevlerle degil: sunucu yeniden baslayinca KAPANIR. Gorevleri kaydedin: .\canli_gorev_kur.ps1 -Hemen'; exit 2 }
    Log-Sonu 'canli_panel.log'
    Log-Sonu 'canli_vekil.log'
    Dur 'Panel acilamadi; yukaridaki gunluk satirlarina bakin.'
}

# --- Kayit ----------------------------------------------------------------------------------------------------------------------------
$tutan = Get-NetTCPConnection -LocalPort $PanelPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($tutan -and $Hemen) { Adim "Port $PanelPort dolu (surec $($tutan.OwningProcess)): once durdurulacak" }
Adim 'Gorevler kaydediliyor (TURKCELL\TAMLIFEADLOG oturumu, parolasiz)'
Gorevleri-Kaydet

if (-not $Hemen) {
    Tamam 'Tamam. Simdi baslatmak icin: .\canli_gorev_kur.ps1 -YenidenBaslat  (ya da full_reboot.bat)'
    exit 0
}

Adim 'Gorevler baslatiliyor'
Hepsini-Durdur
$panelOk = Gorev-Baslat $GorevPanel
if ($panelOk -and (Panel-Saglik 60)) { Tamam "Panel yanit veriyor: http://127.0.0.1:$PanelPort/api/v1/health = 200" } else { Uyari 'Panel 60 sn icinde yanit vermedi: var\log\canli_panel.log dosyasina bakin (-Durum).' }
[void](Gorev-Baslat $GorevVekil)
[void](Gorev-Baslat $GorevRapor)
Start-Sleep -Seconds 5
Log-Sonu 'canli_vekil.log'
Tamam "Denetim: curl.exe -s -i --noproxy `"*`" https://tamlife/api/v1/health"
