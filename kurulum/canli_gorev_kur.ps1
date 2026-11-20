# TAMLIFE v3.5 canli paneli KALICI calistirir: TURKCELL\TAMLIFEADLOG oturumunda otomatik baslayan zamanlanmis gorevler. Saf ASCII (PS 5.1).
#   TAMLIFE_Servis (TEK GOREV, 2026-11-09) -> bu betigin -Calistir servis kipi (supervizor dongu), oturum acilinca + 5 dk bekci:
#       panel dongusu   -> kurulum\canli_baslat.ps1  (panel, 127.0.0.1:8117, canli mod)
#       vekil dongusu   -> kurulum\tls_vekili.ps1    (https://<VekilAd>:443/ -> panel)
#       ReportDB iscisi -> python -m app.isci reportdb, her 6 dk, tur siniri 20 dk (eski ayri gorevin 5 dk siniri turu yariyda oldurdu)
#   TAMLIFE_Utilizasyon_0600 (2026-11-21) -> python -m app.isci utilizasyon, HER GUN 06:00, SYSTEM (oturum gerekmez; Oracle'a
#       baglanmaz: OneDesk/ONENT PostgreSQL + panel DB). Kapanan kayit + envanter ozeti ve final skor. Kacirilirsa ilk firsatta calisir.
#   Eski ayri gorevler (TAMLIFE_v35_Panel / _TLS_Vekil / TAM_Life_v35_ReportDB_6dk / _Gece_Sync) kayitta silinir.
# PAROLA YOK (2026-10-25): hesap parolasi kurum PAM'i ile 24 saatte bir donduruluyor; parolali (Password) gorev her donusten sonra
# 0x8007052E ile baslamiyordu. Gorevler LogonType Interactive + en yuksek yetki: parola saklanmaz/sorulmaz, donus gorevleri bozmaz.
# Kosul: hesabin oturumu ACIK olmali. RDP penceresini kapatmak / baglantinin kopmasi sorun degil (oturum surer); "Oturumu kapat"
# (sign out) gorevleri durdurur. Sunucu yeniden baslayinca TAMLIFEADLOG ile bir kez RDP oturumu acilir; panel ve vekil kendiliginden kalkar.
# Panel/vekil gorevi bu betigin -Calistir kipini kullanir: asil betigi cagirir, ciktisini var\log\canli_panel.log / canli_vekil.log
# dosyasina yazar (10 MB'ta .1'e doner) ve kapanirsa 15 sn sonra yeniden baslatir.
# Gerekli: TAMLIFEADLOG oturumunda YONETICI PowerShell.
#   .\canli_gorev_kur.ps1                  : uc gorevi kaydeder (baslatmaz; bir sonraki oturum acilisinda calisir)
#   .\canli_gorev_kur.ps1 -Hemen           : kaydeder, hemen baslatir, gorevlerin gercekten basladigini ve panel sagligini dogrular
#   .\canli_gorev_kur.ps1 -YenidenBaslat   : (full_reboot.bat) panel, vekil, donguler, sahipsiz surecler ve ReportDB iscisi durdurulur;
#                                            gorevler koddaki tanimla yeniden kaydedilir (silinmis / bozulmus gorev onarilir) ve
#                                            baslatilir; gorev baslamazsa panel ve vekil dogrudan surec olarak acilir (bir sonraki
#                                            yeniden baslatmaya kadar). Cikis: 0 tamam, 2 panel acik ama gorevsiz, 1 panel acilamadi
#   .\canli_gorev_kur.ps1 -PanelYenile     : yalniz paneli yeniden baslatir (vekil / isci dokunulmaz); 0 = 120 sn icinde saglikli
#   .\canli_gorev_kur.ps1 -UtilizasyonGorevi : yalniz 06:00 utilizasyon gorevini kaydeder (panel / vekil / isciye dokunmaz)
#   .\canli_gorev_kur.ps1 -Durum           : gorevleri, panel portunu ve gunluklerin son satirlarini gosterir
#   .\canli_gorev_kur.ps1 -Durdur          : panel, vekil ve ReportDB iscisini durdurur (gorevler kayitli kalir; prod_uygula.ps1 kod /
#                                            bagimlilik degistirmeden once kullanir). Baslatmak: -YenidenBaslat
#   .\canli_gorev_kur.ps1 -Kaldir          : panel ve vekil gorevlerini durdurur ve siler (ReportDB gorevi icin Unregister-ScheduledTask -TaskName TAM_Life_v35_ReportDB_6dk)
#   -VekilAd '+'                           : tum adlar (tamlife, FQDN, IP) (varsayilan: +)
#   -PanelPort 8117 -VekilPort 443         : portlar;  -Istemci : Oracle Instant Client klasoru (ReportDB gorevi)
param([switch]$Hemen,
      [switch]$Kaldir,
      [switch]$Durum,
      [switch]$YenidenBaslat,
      [switch]$Durdur,
      [switch]$PanelYenile,
      [switch]$UtilizasyonGorevi,
      [ValidateSet('', 'panel', 'vekil', 'servis')]
      [string]$Calistir = '',
      [string]$VekilAd = '+',
      [int]$PanelPort = 8117,
      [int]$VekilPort = 443,
      [string]$Istemci = 'E:\oracle\instantclient_19_32')
$ErrorActionPreference = 'Stop'
$Betik = $MyInvocation.MyCommand.Path
$Kok = Split-Path -Parent $PSScriptRoot
$LogKlasoru = Join-Path $Kok 'var\log'
$GorevServis = 'TAMLIFE_Servis'
$GorevAcilis = 'TAMLIFE_Servis_Acilis'   # 2026-11-18: ayni servis, SYSTEM olarak sunucu acilisinda (oturum acilmasini beklemez)
# Eski ayri gorev adlari: yalniz gecis icin (durdurma ve silme); yeni kayitta bunlar silinir.
$GorevPanel = 'TAMLIFE_v35_Panel'
$GorevVekil = 'TAMLIFE_v35_TLS_Vekil'
$GorevRapor = 'TAM_Life_v35_ReportDB_6dk'
$GorevGece = 'TAMLIFE_v35_Gece_Sync'
$GorevUtil = 'TAMLIFE_Utilizasyon_0600'   # 2026-11-21: gunluk utilizasyon turu (kapanan kayitlar + envanter -> skor)
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
    if ($Calistir -eq 'servis') {
        # 2026-11-09 TEK GOREV: panel ve vekil donguleri (mevcut -Calistir panel / vekil kipleri) ile ReportDB iscisi tek surecten yonetilir.
        # Donguler kapanirsa 15 sn icinde yeniden acilir; panel yeniden baslatmasi yalniz panel dongusunu oldurur (-PanelYenile), vekil ve isci dokunulmaz.
        $Pyw = Join-Path $Kok '.venv\Scripts\pythonw.exe'
        $Backend = Join-Path $Kok 'backend'
        $IsciAralikDk = 6
        $IsciSinirDk = 20
        function Servis-Gunluk($m) { try { Add-Content -Path $Log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [servis] $m" -Encoding ASCII } catch { } }
        function Dongu-Var($kip) {
            return [bool](Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
                Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match 'canli_gorev_kur\.ps1' -and $_.CommandLine -match "-Calistir $kip" })
        }
        function Dongu-Ac($kip, $ek) {
            $komut = '/c ""{0}" -NoProfile -ExecutionPolicy Bypass -File "{1}" -Calistir {2}{3}"' -f $PsExe, $Betik, $kip, $ek
            [void](Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\cmd.exe') -ArgumentList $komut -WindowStyle Hidden -PassThru)
            Servis-Gunluk "dongu acildi: $kip"
        }
        function Isci-Calisiyor {
            return [bool](Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
                Where-Object { $_.CommandLine -match 'app\.isci reportdb' -and $_.CommandLine -notmatch 'reportdb-katalog' })
        }
        $baskasi = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match 'canli_gorev_kur\.ps1' -and $_.CommandLine -match '-Calistir servis' }
        # 2026-11-18: iki servis kopyasi bir arada olabilir (SYSTEM acilis gorevi + TAMLIFEADLOG oturum gorevi). Panel / vekil donguleri Dongu-Var ve
        # sahipsiz-sunucu bekcisiyle tekil kalir. ReportDB iscisi YALNIZ TAMLIFEADLOG kimliginde calisir: Oracle giris tetikleyicisi (DB_LOGIN_TR)
        # SYSTEM / makine hesabini reddeder (ORA-04088). SYSTEM acilisinda panel+vekil kalkar, isci TAMLIFEADLOG oturumu acilinca baslar.
        $Kimlik = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $IsciKimligiUygun = ($Kimlik -ieq $TamlifeCalismaHesabi)
        if ($baskasi) { Servis-Gunluk "baska servis kopyasi var (PID $(@($baskasi)[0].ProcessId)); donguler tekil kalir" }
        if (-not $IsciKimligiUygun) { Servis-Gunluk "ReportDB iscisi bu kimlikte (SYSTEM) calistirilmaz; TAMLIFEADLOG servis kopyasi calistirir" }
        Servis-Gunluk "servis basladi (PID $PID, kimlik $([Security.Principal.WindowsIdentity]::GetCurrent().Name))"
        $isci = $null
        $isciBas = [datetime]::MinValue
        $isciSon = [datetime]::MinValue
        while ($true) {
            try {
                if (-not (Dongu-Var 'panel')) { Dongu-Ac 'panel' " -PanelPort $PanelPort" }
                if (-not (Dongu-Var 'vekil')) { Dongu-Ac 'vekil' " -VekilAd `"$VekilAd`" -PanelPort $PanelPort -VekilPort $VekilPort" }
                if ($isci -and $isci.HasExited) { $isci = $null }
                if ($isci -and ((Get-Date) - $isciBas).TotalMinutes -gt $IsciSinirDk) {
                    & cmd.exe /c "taskkill /PID $($isci.Id) /T /F >nul 2>&1"
                    Servis-Gunluk "ReportDB turu $IsciSinirDk dk'yi asti; sonlandirildi"
                    $isci = $null
                }
                if ($IsciKimligiUygun -and -not $isci -and ((Get-Date) - $isciSon).TotalMinutes -ge $IsciAralikDk -and (Test-Path $Pyw) -and (Test-Path (Join-Path $Istemci 'oci.dll')) -and -not (Isci-Calisiyor)) {
                    $isciSon = Get-Date
                    $isciBas = $isciSon
                    $isci = Start-Process -FilePath $Pyw -ArgumentList ('-m app.isci reportdb --client "{0}"' -f $Istemci) -WorkingDirectory $Backend -WindowStyle Hidden -PassThru
                }
            } catch { Servis-Gunluk "hata: $($_.Exception.Message)" }
            Start-Sleep -Seconds 15
        }
    }
    if ($Calistir -eq 'panel') {
        $Hedef = Join-Path $PSScriptRoot 'canli_baslat.ps1'
        $Ek = " -Port $PanelPort"
    } else {
        $Hedef = Join-Path $PSScriptRoot 'tls_vekili.ps1'
        $Ek = " -Ad `"$VekilAd`" -Port $VekilPort -HedefPort $PanelPort"
    }
    # 2026-10-26/27: dongu bes kez 0xC000013A ile kapandi, alttaki sunucu sahipsiz calismayi surdurdu. Gorev 5 dk'da bir yeniden
    # tetiklenir (bekci); yeni dongu calisan sahipsiz sunucu bulursa ikinci kopya acmaz (port cakisirdi): o durana kadar izler, sonra devralir.
    function Sahipsiz-Calisiyor {
        if ($Calistir -eq 'panel') { return [bool](Get-NetTCPConnection -LocalPort $PanelPort -State Listen -ErrorAction SilentlyContinue) }
        return [bool](Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match 'tls_vekili\.ps1' })
    }
    if (Sahipsiz-Calisiyor) {
        # 2026-10-27: sahipsiz sunucunun cmd'si canli_<kip>.log'u acik tutar; oraya yazmak hata verip donguyu dusuruyordu. Ayri gunluk.
        $bekciLog = Join-Path $LogKlasoru 'canli_bekci.log'
        try { Add-Content -Path $bekciLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [$Calistir] calisan sahipsiz sunucu bulundu; izleniyor, durunca devralinacak" -Encoding ASCII } catch { }
        while (Sahipsiz-Calisiyor) { Start-Sleep -Seconds 20 }
        try { Add-Content -Path $bekciLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [$Calistir] sahipsiz sunucu durdu; devraliniyor" -Encoding ASCII } catch { }
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

# Panel ve vekil donguleri (gorevden ya da dogrudan acilmis), sahipsiz kalmis sunucular ve portu tutan surec agaclari kapatilir.
# Bu betigin kendisi haric. -Yalniz 'panel': vekile dokunulmaz.
function Hepsini-Durdur([string]$Yalniz = '') {
    # Tek gorev (2026-11-09): -Yalniz 'panel' servise dokunmaz (servis panel dongusunu 15 sn icinde yeniden acar); tam durdurmada once servis oldurulur.
    $gorevler = if ($Yalniz -eq 'panel') { @() } else { @($GorevServis, $GorevAcilis, $GorevVekil, $GorevPanel) }
    foreach ($ad in $gorevler) { Stop-ScheduledTask -TaskName $ad -ErrorAction SilentlyContinue }
    if ($Yalniz -ne 'panel') {
        $servis = Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='cmd.exe' OR Name='conhost.exe'" |
            Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match 'canli_gorev_kur\.ps1' -and $_.CommandLine -match '-Calistir servis' }
        foreach ($p in $servis) { & cmd.exe /c "taskkill /PID $($p.ProcessId) /T /F >nul 2>&1" }
    }
    $surecler = Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='python.exe' OR Name='pythonw.exe' OR Name='cmd.exe' OR Name='conhost.exe'" |
        Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and (
            ($_.CommandLine -match 'canli_gorev_kur\.ps1' -and $_.CommandLine -match '-Calistir panel') -or $_.CommandLine -match 'canli_baslat\.ps1' -or
            ($Yalniz -ne 'panel' -and (($_.CommandLine -match 'canli_gorev_kur\.ps1' -and $_.CommandLine -match '-Calistir vekil') -or $_.CommandLine -match 'tls_vekili\.ps1'))) }
    $portu = Get-NetTCPConnection -LocalPort $PanelPort -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in @($surecler.ProcessId) + @($portu) | Where-Object { $_ } | Sort-Object -Unique) {
        & cmd.exe /c "taskkill /PID $p /T /F >nul 2>&1"   # PS 5.1: dogrudan 2>$null, Stop altinda hata kaydina donusur
    }
    for ($i = 0; $i -lt 10 -and (Get-NetTCPConnection -LocalPort $PanelPort -State Listen -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Seconds 1 }
    # 2026-10-27: Stop-ScheduledTask'tan hemen sonra gorev birkac sn 'Running' gorunur; Gorev-Baslat onu "zaten calisiyor" sayip
    # baslatmiyordu (panel kapali kalirdi). Gorevler gercekten durana kadar beklenir.
    for ($i = 0; $i -lt 20; $i++) {
        if (-not ($gorevler | Where-Object { (Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue).State -eq 'Running' })) { break }
        Start-Sleep -Seconds 1
    }
}

# ReportDB iscisi: gorev durdurulur, takili kalmis isci surecleri kapatilir (Gorev-Baslat bir sonraki turu hemen baslatir).
function Isci-Durdur {
    Stop-ScheduledTask -TaskName $GorevRapor -ErrorAction SilentlyContinue
    $isci = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" | Where-Object { $_.CommandLine -match 'app\.isci' }
    foreach ($p in $isci) { & cmd.exe /c "taskkill /PID $($p.ProcessId) /T /F >nul 2>&1" }
}

# 2026-10-27 full_reboot_testi: vekil gorevi basladiktan 3-7 sn sonra 443'u dinler; tek deneme "YANIT YOK" deyip basarili yeniden
# baslatmayi hata (kod 1) sayiyordu. $sn boyunca 3 sn arayla denenir.
function Https-Saglik($sn = 30) {
    for ($i = 0; $i -lt $sn; $i += 3) {
        try { if ((Invoke-WebRequest -Uri 'https://tamlife/api/v1/health' -UseBasicParsing -TimeoutSec 10).StatusCode -eq 200) { return $true } } catch { }
        Start-Sleep -Seconds 3
    }
    return $false
}

# Gorev oturum acamazsa: ayni -Calistir dongusu WMI ile bu oturumun surec agaci DISINDA acilir (bu pencere kapansa da calisir;
# sunucu yeniden baslayinca durur).
function Dogrudan-Baslat($kip, $ekArg) {
    $satir = "`"$(Join-Path $env:SystemRoot 'System32\conhost.exe')`" --headless `"$PsExe`" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Betik`" -Calistir $kip$ekArg"
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $satir; CurrentDirectory = $Kok }
    if ($r.ReturnValue -eq 0) { Uyari "$kip dogrudan surec olarak acildi (PID $($r.ProcessId))." } else { Uyari "$kip acilamadi (WMI $($r.ReturnValue))." }
}

# Servis zaten calisiyorsa (SYSTEM acilis gorevi ya da oturum gorevi) dokunmaz; degilse once SYSTEM gorevini (oturum gerekmez), olmazsa oturum gorevini baslatir.
function Servis-Baslat {
    $tamam = $false
    foreach ($ad in $GorevAcilis, $GorevServis) {
        if ((Get-ScheduledTask -TaskName $ad -ErrorAction SilentlyContinue).State -eq 'Running') { Tamam "$ad zaten calisiyor."; $tamam = $true }
    }
    if (-not $tamam) { $tamam = (Gorev-Baslat $GorevAcilis) }
    if (-not $tamam) { $tamam = (Gorev-Baslat $GorevServis) }
    # ReportDB iscisi yalniz TAMLIFEADLOG kimliginde calisir: oturum gorevi de (oturum aciksa) kalkar; oturum yoksa sessizce atlanir.
    if ((Get-ScheduledTask -TaskName $GorevServis -ErrorAction SilentlyContinue).State -ne 'Running') { Start-ScheduledTask -TaskName $GorevServis -ErrorAction SilentlyContinue }
    return $tamam
}

$PanelEk = " -PanelPort $PanelPort"
$VekilEk = " -VekilAd `"$VekilAd`" -PanelPort $PanelPort -VekilPort $VekilPort"
$ServisEk = " -PanelPort $PanelPort -VekilAd `"$VekilAd`" -VekilPort $VekilPort"

# 2026-10-27 KOK NEDEN (bes kez 0xC000013A): oturumun varsayilan terminali Windows Terminal; -WindowStyle Hidden powershell gorevi
# de WT'ye (OpenConsole.exe) devrediliyor, o WT penceresi kapaninca dongu 'konsol kapandi' ile oluyordu (Guvenlik gunlugu 4688/4689:
# 12:47:30 OpenConsole ile dongu ayni anda cikti). conhost.exe --headless: penceresiz klasik konsol, hicbir terminale devredilmez.
function Gizli-Eylem($arg, $dizin) {
    New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'System32\conhost.exe') -Argument "--headless powershell.exe $arg" -WorkingDirectory $dizin
}

function Util-Gorevi-Kaydet {
    $pyw = Join-Path $Kok '.venv\Scripts\pythonw.exe'
    if (-not (Test-Path $pyw)) { throw "Python yok: $pyw" }
    $eylem = New-ScheduledTaskAction -Execute $pyw -Argument '-m app.isci utilizasyon' -WorkingDirectory (Join-Path $Kok 'backend')
    $tetik = New-ScheduledTaskTrigger -Daily -At '06:00'
    $ayar = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    $sistem = New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    [void](Register-ScheduledTask -TaskName $GorevUtil -Action $eylem -Trigger $tetik -Settings $ayar -Principal $sistem -Description 'TAMLIFE gunluk utilizasyon: kapanan sikayet/talep/alarm + envanter ozeti ve final skor (her gun 06:00)' -Force)
    Tamam "Gorev kaydedildi: $GorevUtil (her gun 06:00, SYSTEM)"
}

function Gorevleri-Kaydet {
    foreach ($d in 'kurulum\canli_baslat.ps1', 'kurulum\tls_vekili.ps1') {
        if (-not (Test-Path (Join-Path $Kok $d))) { throw "Dosya yok: $Kok\$d" }
    }
    if (-not (Test-Path (Join-Path $Kok 'ekran-react\dist\index.html'))) { throw 'Arayuz derlemesi yok (ekran-react\dist\index.html).' }
    Tamlife-KimlikDogrula
    $kimlik = Tamlife-OturumKimligi   # parolasiz: hesabin acik oturumunda kosar (PAM 24 sa donusu gorevleri bozmaz)
    $ayar = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
    $tetik = New-ScheduledTaskTrigger -AtLogOn -User $TamlifeCalismaHesabi
    # Bekci (2026-10-27): ikinci tetik hemen baslar ve 5 dk'da bir surekli yinelenir (oturum acilisina bagli tetigin tekrari ancak bir
    # sonraki girisle baslardi). Dongu calisiyorsa MultipleInstances IgnoreNew yeni ornegi yok sayar; olmusse en gec 5 dk icinde kalkar.
    $bekci = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
    $tetik = @($tetik, $bekci)
    $arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Betik`" -Calistir servis$ServisEk -Istemci `"$Istemci`""
    $eylem = Gizli-Eylem $arg $Kok
    [void](Register-ScheduledTask -TaskName $GorevServis -Action $eylem -Trigger $tetik -Settings $ayar -Principal $kimlik -Description 'TAMLIFE paneli + TLS vekili + ReportDB iscisi (tek gorev)' -Force)
    Tamam "Gorev kaydedildi: $GorevServis (oturum acilinca, parolasiz)"
    # 2026-11-18 SYSTEM acilis gorevi: sunucu gece yeniden baslayinca kimse oturum acmadan panel + vekil + isci kalkar.
    $sistem = New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $acilis = New-ScheduledTaskTrigger -AtStartup
    $acilis.Delay = 'PT1M'
    $bekci2 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 5)
    [void](Register-ScheduledTask -TaskName $GorevAcilis -Action $eylem -Trigger @($acilis, $bekci2) -Settings $ayar -Principal $sistem -Description 'TAMLIFE servisi (SYSTEM, sunucu acilisinda oturumsuz): panel + TLS vekili + ReportDB iscisi' -Force)
    Tamam "Gorev kaydedildi: $GorevAcilis (SYSTEM, sunucu acilisinda)"
    Util-Gorevi-Kaydet
    # Eski ayri gorevler (panel / vekil / ReportDB / gece senkronu) artik gereksiz: varsa silinir.
    foreach ($eski in $GorevPanel, $GorevVekil, $GorevRapor, $GorevGece) {
        if (Get-ScheduledTask -TaskName $eski -ErrorAction SilentlyContinue) { Gorev-Sil $eski }
    }
}

if ($UtilizasyonGorevi) {
    try { Util-Gorevi-Kaydet } catch { Dur $_.Exception.Message }
    $b = Get-ScheduledTaskInfo -TaskName $GorevUtil
    Write-Host "    Sonraki calisma: $($b.NextRunTime)"
    exit 0
}

if ($Durum) {
    foreach ($ad in $GorevAcilis, $GorevServis, $GorevUtil, $GorevPanel, $GorevVekil, $GorevRapor) {
        $g = Get-ScheduledTask -TaskName $ad -ErrorAction SilentlyContinue
        if (-not $g -and $ad -ne $GorevServis -and $ad -ne $GorevAcilis -and $ad -ne $GorevUtil) { continue }   # eski ayri gorevler yoksa gurultu yapma
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
    Log-Sonu 'canli_servis.log'
    Log-Sonu 'isci.log' (Join-Path $Kok 'backend\var\logs')
    exit 0
}

if ($Kaldir) {
    Adim 'Gorevler durdurulup siliniyor'
    Hepsini-Durdur
    Isci-Durdur
    foreach ($ad in $GorevServis, $GorevAcilis, $GorevUtil, $GorevVekil, $GorevPanel, $GorevRapor) { if (Get-ScheduledTask -TaskName $ad -ErrorAction SilentlyContinue) { Gorev-Sil $ad } }
    Uyari "Gorev durunca panel ve vekil de kapanmis olmali. Denetim: Get-NetTCPConnection -LocalPort $PanelPort -State Listen"
    exit 0
}

if ($Durdur) {
    Adim 'Panel, vekil ve ReportDB iscisi durduruluyor (gorevler kayitli kalir)'
    Hepsini-Durdur
    Isci-Durdur
    if (Get-NetTCPConnection -LocalPort $PanelPort -State Listen -ErrorAction SilentlyContinue) { Dur "Port $PanelPort hala dolu; panel durdurulamadi." }
    Tamam 'Durduruldu. Baslatmak icin: .\canli_gorev_kur.ps1 -YenidenBaslat'
    exit 0
}

if ($PanelYenile) {
    # gece_sync.ps1: isciler bittikten sonra olagan yeniden baslatma. Basarisizsa cagiran full_reboot.bat'i calistirir.
    Adim 'Panel yeniden baslatiliyor (vekil ve isci dokunulmaz)'
    Hepsini-Durdur 'panel'
    $panelOk = Servis-Baslat   # servis calisiyorsa dokunmaz; panel dongusunu 15 sn icinde kendisi yeniden acar, calismiyorsa baslatir
    $saglik = $panelOk -and (Panel-Saglik 120)
    $https = $saglik -and (Https-Saglik)
    Write-Host "    Panel gorevi: $panelOk  127.0.0.1:$PanelPort : $(if ($saglik) { 'CALISIYOR' } else { 'YANIT YOK' })  https: $(if ($https) { 'CALISIYOR' } else { 'YANIT YOK' })"
    if ($https) { Tamam 'Panel yeniden baslatildi ve yanit veriyor.'; exit 0 }
    Log-Sonu 'canli_panel.log'
    Dur 'Panel yeniden baslatmadan sonra acilmadi.'
}

if ($YenidenBaslat) {
    Adim 'Calisan panel, vekil, donguler, sahipsiz surecler ve ReportDB iscisi durduruluyor'
    Hepsini-Durdur
    Isci-Durdur
    Adim 'Gorevler koddaki tanimla yeniden kaydediliyor (silinmis / bozulmus gorev onarilir)'
    try { Gorevleri-Kaydet } catch { Uyari "Gorevler yeniden kaydedilemedi ($($_.Exception.Message)); mevcut kayitlarla devam ediliyor." }
    Adim 'Gorevler baslatiliyor'
    $panelOk = Servis-Baslat
    $vekilOk = $panelOk   # tek gorev: panel, vekil ve ReportDB ayni servisten kalkar
    $raporOk = $panelOk
    if ($panelOk -and -not (Panel-Saglik 120)) { Uyari 'Servis basladi ama panel 120 sn icinde yanit vermedi.' }
    if (-not $panelOk) {
        Uyari 'Servis gorevi baslamadi; eski parolali kipteyse bir kez yeniden kaydedin: .\canli_gorev_kur.ps1 -Hemen (parola sormaz).'
        Dogrudan-Baslat 'servis' $ServisEk
        [void](Panel-Saglik 90)
    }
    $saglik = Panel-Saglik 30
    $https = Https-Saglik
    Write-Host ''
    Write-Host "    Panel (127.0.0.1:$PanelPort) : $(if ($saglik) { 'CALISIYOR' } else { 'YANIT YOK' })"
    Write-Host "    https://tamlife/        : $(if ($https) { 'CALISIYOR' } else { 'YANIT YOK' })"
    Write-Host "    Gorevler (acilista)     : panel=$panelOk vekil=$vekilOk reportdb=$raporOk"
    if ($saglik -and $https -and $panelOk -and $vekilOk -and $raporOk) { Tamam 'Tamam: her sey gorevlerle calisiyor; yeniden baslatmadan sonra SYSTEM acilis gorevi ile oturumsuz kalkar.'; exit 0 }
    if ($saglik -and $https) { Uyari 'Panel acik ama gorevlerle degil: sunucu yeniden baslayinca KAPANIR. Gorevleri kaydedin: .\canli_gorev_kur.ps1 -Hemen'; exit 2 }
    Log-Sonu 'canli_panel.log'
    Log-Sonu 'canli_vekil.log'
    Dur 'Panel acilamadi; yukaridaki gunluk satirlarina bakin.'
}

# --- Kayit ----------------------------------------------------------------------------------------------------------------------------
$tutan = Get-NetTCPConnection -LocalPort $PanelPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($tutan -and $Hemen) { Adim "Port $PanelPort dolu (surec $($tutan.OwningProcess)): once durdurulacak" }
Adim 'Gorevler kaydediliyor (TURKCELL\TAMLIFEADLOG oturumu, parolasiz)'
try { Gorevleri-Kaydet } catch { Dur $_.Exception.Message }

if (-not $Hemen) {
    Tamam 'Tamam. Simdi baslatmak icin: .\canli_gorev_kur.ps1 -YenidenBaslat  (ya da full_reboot.bat)'
    exit 0
}

Adim 'Gorevler baslatiliyor'
Hepsini-Durdur
$panelOk = Servis-Baslat
if ($panelOk -and (Panel-Saglik 60)) { Tamam "Panel yanit veriyor: http://127.0.0.1:$PanelPort/api/v1/health = 200" } else { Uyari 'Panel 60 sn icinde yanit vermedi: var\log\canli_panel.log dosyasina bakin (-Durum).' }
Start-Sleep -Seconds 5
Log-Sonu 'canli_vekil.log'
Tamam "Denetim: curl.exe -s -i --noproxy `"*`" https://tamlife/api/v1/health"
