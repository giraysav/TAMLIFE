# Mevcut TAMLIFE gorevlerini tek Windows hesabina tasir. Parola dosyaya/gunluge yazilmaz.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'calisma_kimligi.ps1')
Tamlife-KimlikDogrula
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'Yukseltilmis PowerShell gerekli.' }
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root 'var\log'
$log = Join-Path $logDir 'kimlik-gecis.log'
$checkLog = Join-Path $logDir 'kimlik-kontrol.log'
$checkScript = Join-Path $PSScriptRoot 'kimlik_kontrol.ps1'
$checkTask = 'TAMLIFE_IdentityCheck'
$mainTasks = @('TAMLIFE_v35_Panel', 'TAMLIFE_v35_TLS_Vekil')
$taskNames = @('TAMLIFE_v35_Panel', 'TAMLIFE_v35_TLS_Vekil', 'TAM_Life_v35_ReportDB_6dk')
# Gorev surecleri betik yolundan taninir; yol klasorun bulundugu yerden uretilir (2026-10-21 E:\TAMLIFE_Dev -> E:\TAMLIFE).
$gorevBetigi = '(?i)-File\s+"?' + [regex]::Escape($root) + '\\kurulum\\(?:canli_gorev_kur|canli_baslat|tls_vekili)\.ps1(?:["\s]|$)'

function Durum-Yaz($message) {
    $line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ' + $message
    Add-Content -LiteralPath $log -Value $line -Encoding ASCII
    Write-Host $line
}
function Saglik-Bekle($uri) {
    for ($i = 0; $i -lt 30; $i++) {
        try { $r = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { return } } catch {}
        Start-Sleep -Seconds 2
    }
    throw ('Health check failed: ' + $uri)
}
function Gorev-Kaydet($task) {
    $task.Principal = Tamlife-GorevKimligi
    Register-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath -InputObject $task -User $TamlifeCalismaHesabi -Password ($script:credential.GetNetworkCredential().Password) -Force | Out-Null
}

$credential = $null
$stage = 'credential'
try {
    Durum-Yaz 'WINDOWS_CREDENTIAL_REQUIRED'
    $credential = Tamlife-GorevKimlikBilgisi
    $stage = 'preflight'
    $checkAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $checkScript) -WorkingDirectory $root
    $checkSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
    Register-ScheduledTask -TaskName $checkTask -Action $checkAction -Settings $checkSettings -User $TamlifeCalismaHesabi -Password ($credential.GetNetworkCredential().Password) -RunLevel Highest -Force | Out-Null
    [IO.File]::WriteAllText($checkLog, '')
    $oldRun = (Get-ScheduledTaskInfo -TaskName $checkTask).LastRunTime
    Start-ScheduledTask -TaskName $checkTask
    $done = $false
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 1
        $info = Get-ScheduledTaskInfo -TaskName $checkTask
        $state = (Get-ScheduledTask -TaskName $checkTask).State
        if ($info.LastRunTime -gt $oldRun -and $state -ne 'Running' -and $state -ne 'Queued') {
            if ($info.LastTaskResult -ne 0) { throw 'Oracle preflight failed; live processes untouched.' }
            $done = $true
            break
        }
    }
    if (-not $done) { throw 'Credential preflight did not start; live processes untouched.' }
    $checkLines = Get-Content -LiteralPath $checkLog
    $checkResult = ($checkLines | Where-Object { $_ -like '{*' } | Select-Object -Last 1) | ConvertFrom-Json
    if ($checkLines[0] -ine $TamlifeCalismaHesabi -or -not $checkResult.ok) { throw 'Unexpected preflight identity or result.' }
    Durum-Yaz 'ORACLE_PASSWORD_LOGON_OK'

    $stage = 'snapshot'
    $snapshotDir = Join-Path $root ('var\isletim\kimlik-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Path $snapshotDir -Force | Out-Null
    $tasks = @()
    foreach ($name in $taskNames) {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction Stop
        Export-ScheduledTask -TaskName $name | Set-Content -LiteralPath (Join-Path $snapshotDir ($name + '.xml')) -Encoding Unicode
        $tasks += $task
    }

    $stage = 'register'
    foreach ($task in $tasks) {
        $disabled = -not $task.Settings.Enabled
        Gorev-Kaydet $task
        if ($disabled) { Disable-ScheduledTask -TaskName $task.TaskName | Out-Null }
        Durum-Yaz ('ACCOUNT_UPDATED ' + $task.TaskName)
    }

    $stage = 'restart'
    $oldProcesses = @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" | Where-Object {
        $_.CommandLine -match $gorevBetigi
    })
    foreach ($name in $mainTasks) { Stop-ScheduledTask -TaskName $name }
    foreach ($old in $oldProcesses) {
        $live = Get-CimInstance Win32_Process -Filter ("ProcessId = " + $old.ProcessId)
        if ($live -and $live.CreationDate -eq $old.CreationDate) {
            & taskkill.exe /PID $old.ProcessId /T /F | Out-Null
            if ($LASTEXITCODE -ne 0 -and (Get-Process -Id $old.ProcessId -ErrorAction SilentlyContinue)) { throw 'Old process could not be stopped.' }
        }
    }
    Start-ScheduledTask -TaskName 'TAMLIFE_v35_Panel'
    Saglik-Bekle 'http://127.0.0.1:8117/api/v1/health'
    Durum-Yaz 'HTTP_HEALTH_OK'
    Start-ScheduledTask -TaskName 'TAMLIFE_v35_TLS_Vekil'
    Saglik-Bekle 'https://tamlife/api/v1/health'
    Durum-Yaz 'HTTPS_HEALTH_OK'

    $stage = 'verify'
    $processes = @(Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -eq 'python.exe' -and $_.CommandLine -match 'uvicorn app.main:app --host 127.0.0.1 --port 8117') -or
        ($_.Name -eq 'powershell.exe' -and $_.CommandLine -match $gorevBetigi)
    })
    foreach ($p in $processes) {
        $owner = Invoke-CimMethod -InputObject $p -MethodName GetOwner
        $name = $owner.Domain + '\' + $owner.User
        if ($owner.ReturnValue -ne 0 -or $name -ine $TamlifeCalismaHesabi) { throw ('Unexpected process owner: ' + $p.ProcessId) }
        Durum-Yaz ('PROCESS_OWNER_OK ' + $p.ProcessId + ' ' + $name)
    }
    foreach ($name in $taskNames) {
        $task = Get-ScheduledTask -TaskName $name
        if ($task.Principal.LogonType -ne 'Password') { throw ('Wrong logon type: ' + $name) }
        Durum-Yaz ('TASK_OK ' + $name + ' ' + $task.Principal.UserId + ' ' + $task.State)
    }
    Unregister-ScheduledTask -TaskName $checkTask -Confirm:$false
    Durum-Yaz 'MIGRATION_COMPLETE'
    Write-Host 'Tamamlandi. Panelde ReportDB baglanti testini tekrar calistirabilirsiniz.' -ForegroundColor Green
} catch {
    Durum-Yaz ('FAILED_STAGE ' + $stage + ' HRESULT=' + $_.Exception.HResult)
    Write-Host ('Islem tamamlanamadi. Asama: ' + $stage + '. Gunluk: ' + $log) -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} finally {
    $credential = $null
}
