$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root 'var\log\kimlik-kontrol.log'
[Security.Principal.WindowsIdentity]::GetCurrent().Name | Set-Content -LiteralPath $log -Encoding UTF8
Set-Location -LiteralPath (Join-Path $root 'backend')
try {
    $raw = & (Join-Path $root '.venv\Scripts\python.exe') -m app.tampon.oracle test oracle_reportdb 2>$null
    $result = ($raw | Where-Object { $_ -like '{*' } | Select-Object -Last 1) | ConvertFrom-Json
    $result | ConvertTo-Json -Compress | Add-Content -LiteralPath $log -Encoding UTF8
    if (-not $result.ok) { exit 1 }
    exit 0
} catch {
    'Oracle identity check failed.' | Add-Content -LiteralPath $log -Encoding UTF8
    exit 1
}