# TAMLIFE - full_reboot.bat dogrulamasi (saf ASCII; PS 5.1; YONETICI). CANLI SISTEMDE calisir: her senaryoda panel ~1 dk kapanir.
#   powershell -File kurulum\full_reboot_testi.ps1 [-Senaryo normal,sahipsiz,durmus,gorevsiz]
# 2026-10-27 kullanici: "herhangi bir sorun aninda paneli sifirdan baslatip tum surecleri yeniden tetikleyen full_reboot.bat'in
# sorunsuz ve eksiksiz calistigini teyit et". Her senaryo bir ariza durumu kurar, full_reboot.bat /oto calistirir ve denetler:
#   cikis kodu 0; 127.0.0.1:8117 ve https://tamlife saglikli; panel + vekil gorevi Running, ReportDB ve gece gorevi kayitli ve etkin;
#   port 8117'yi TEK surec dinliyor; panel ve vekil dongusu ile tls_vekili.ps1 birer tane (cift kopya / sahipsiz surec yok).
# Senaryolar:
#   normal   : her sey calisirken
#   sahipsiz : gorev donguleri olmus, alttaki panel / vekil sahipsiz calisiyor (2026-10-26/27'de bes kez yasanan 0xC000013A)
#   durmus   : panel, vekil, isci tamamen kapali (canli_gorev_kur.ps1 -Durdur)
#   gorevsiz : her sey kapali VE panel / vekil gorevleri silinmis (full_reboot gorevleri yeniden kaydetmeli)
# Rapor: var\log\full_reboot_testi_<zaman>.txt. Cikis kodu = basarisiz senaryo sayisi.
param([string[]]$Senaryo = @('normal', 'sahipsiz', 'durmus', 'gorevsiz'))
$ErrorActionPreference = 'Continue'
$Proje = Split-Path $PSScriptRoot -Parent
$Gorev = Join-Path $PSScriptRoot 'canli_gorev_kur.ps1'
$Rapor = Join-Path $Proje ("var\log\full_reboot_testi_" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.txt')
New-Item -ItemType Directory -Force -Path (Split-Path $Rapor) | Out-Null
Set-Content -Path $Rapor -Value "TAMLIFE full_reboot testi - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -Encoding UTF8
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'YONETICI PowerShell gerekli.' -ForegroundColor Red; exit 99
}

function Yaz($m, $renk = 'Gray') { Write-Host $m -ForegroundColor $renk; Add-Content -Path $Rapor -Value $m -Encoding UTF8 }
function Saglik($adres) { try { return ((Invoke-WebRequest -Uri $adres -UseBasicParsing -TimeoutSec 10).StatusCode -eq 200) } catch { return $false } }
function Surecler($desen) {
    @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match $desen })
}
function Durum {
    $d = [ordered]@{}
    foreach ($g in 'TAMLIFE_v35_Panel', 'TAMLIFE_v35_TLS_Vekil', 'TAM_Life_v35_ReportDB_6dk', 'TAMLIFE_v35_Gece_Sync') {
        $t = Get-ScheduledTask -TaskName $g -ErrorAction SilentlyContinue
        $d[$g] = if ($t) { "$($t.State)" } else { 'yok' }
    }
    $d.port = @(Get-NetTCPConnection -LocalPort 8117 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique).Count
    # @(): tek eleman donunce PS 5.1'de CimInstance.Count bos geliyordu (2026-10-27 ilk calisma)
    $d.panel_dongu = @(Surecler 'canli_gorev_kur\.ps1.*-Calistir panel').Count
    $d.vekil_dongu = @(Surecler 'canli_gorev_kur\.ps1.*-Calistir vekil').Count
    $d.vekil = @(Surecler 'tls_vekili\.ps1').Count
    return $d
}

$basarisiz = 0
foreach ($s in $Senaryo) {
    Yaz ''
    Yaz "=== Senaryo: $s ===" 'Cyan'
    switch ($s) {
        'normal' { }
        'sahipsiz' {
            # yalniz donguler (gorev surecleri) olduruluyor; alttaki cmd / canli_baslat / uvicorn / tls_vekili sahipsiz kalir
            foreach ($p in (Surecler 'canli_gorev_kur\.ps1.*-Calistir (panel|vekil)')) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 3
        }
        'durmus' { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Gorev -Durdur | Out-Null }
        'gorevsiz' {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Gorev -Durdur | Out-Null
            foreach ($g in 'TAMLIFE_v35_Panel', 'TAMLIFE_v35_TLS_Vekil') { Unregister-ScheduledTask -TaskName $g -Confirm:$false -ErrorAction SilentlyContinue }
        }
        default { Yaz "bilinmeyen senaryo: $s" 'Red'; $basarisiz++; continue }
    }
    $once = Durum
    Yaz ("  once : " + (($once.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ' '))
    $t0 = Get-Date
    $p = Start-Process -FilePath (Join-Path $Proje 'full_reboot.bat') -ArgumentList '/oto' -WorkingDirectory $Proje -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput "$Rapor.$s.txt" -RedirectStandardError "$Rapor.$s.err"
    $sure = [int]((Get-Date) - $t0).TotalSeconds
    Start-Sleep -Seconds 5
    $son = Durum
    $yerel = Saglik 'http://127.0.0.1:8117/api/v1/health'
    $https = Saglik 'https://tamlife/api/v1/health'
    Yaz ("  sonra: " + (($son.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ' '))
    $sorun = @()
    if ($p.ExitCode -ne 0) { $sorun += "full_reboot cikis kodu $($p.ExitCode)" }
    if (-not $yerel) { $sorun += 'panel 127.0.0.1:8117 yanit vermiyor' }
    if (-not $https) { $sorun += 'https://tamlife yanit vermiyor' }
    foreach ($g in 'TAMLIFE_v35_Panel', 'TAMLIFE_v35_TLS_Vekil') { if ($son[$g] -ne 'Running') { $sorun += "$g durumu $($son[$g])" } }
    foreach ($g in 'TAM_Life_v35_ReportDB_6dk', 'TAMLIFE_v35_Gece_Sync') { if ($son[$g] -in 'yok', 'Disabled') { $sorun += "$g durumu $($son[$g])" } }
    if ($son.port -ne 1) { $sorun += "port 8117'yi $($son.port) surec dinliyor" }
    foreach ($k in 'panel_dongu', 'vekil_dongu', 'vekil') { if ($son[$k] -ne 1) { $sorun += "$k sayisi $($son[$k])" } }
    if ($sorun.Count) {
        $basarisiz++
        Yaz "  [BASARISIZ] $sure sn: $($sorun -join '; ')" 'Red'
        Get-Content "$Rapor.$s.txt" -Tail 15 -ErrorAction SilentlyContinue | ForEach-Object { Yaz "    | $_" 'DarkGray' }
    } else { Yaz "  [TAMAM] $sure sn: panel, https, gorevler ve surecler eksiksiz" 'Green' }
    Start-Sleep -Seconds 10
}

Yaz ''
if ($basarisiz) { Yaz "SONUC: $basarisiz / $($Senaryo.Count) senaryo BASARISIZ. Rapor: $Rapor" 'Red' }
else { Yaz "SONUC: $($Senaryo.Count) / $($Senaryo.Count) senaryo TAMAM - full_reboot.bat dogrulandi. Rapor: $Rapor" 'Green' }
# Son guvence: test sonunda panel kapali kaldiysa bir kez daha full_reboot
if (-not (Saglik 'https://tamlife/api/v1/health')) { Yaz 'Panel kapali kaldi: full_reboot yeniden calistiriliyor' 'Yellow'; & cmd.exe /c "`"$Proje\full_reboot.bat`" /oto" | Out-Null }
exit $basarisiz
