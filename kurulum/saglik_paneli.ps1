# TAMLIFE saglik paneli: panelden BAGIMSIZ, yalniz bu sunucuda (127.0.0.1:8118) calisan kucuk dashboard. Saf ASCII (PS 5.1).
# Calistirma (YONETICI PowerShell, TAMLIFEADLOG oturumu):  powershell -NoProfile -ExecutionPolicy Bypass -File E:\TAMLIFE\kurulum\saglik_paneli.ps1
# Pencere kapaninca durur; kalici gorev / ayar degistirmez. Tarayici adresi (gizli anahtarli) konsola yazilir ve otomatik acilir.
# Guvenlik: yalniz loopback, her istekte rastgele anahtar (X-Token), Host/Origin denetimi, islem yalniz POST. -Kaldir / gorev silme YOK.
param([int]$Port = 8118)
$ErrorActionPreference = 'Stop'
$Kok = Split-Path -Parent $PSScriptRoot
$Gorev = Join-Path $PSScriptRoot 'canli_gorev_kur.ps1'
$HtmlYolu = Join-Path $PSScriptRoot 'saglik_paneli.html'
$Pyw = Join-Path $Kok '.venv\Scripts\pythonw.exe'
$Backend = Join-Path $Kok 'backend'
$IsciLog = Join-Path $Backend 'var\logs\isci.log'
$Kilit = Join-Path $Backend 'var\logs\isci_reportdb.kilit'
$PsExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$Istemci = 'E:\oracle\instantclient_19_32'
. (Join-Path $PSScriptRoot 'calisma_kimligi.ps1')
Tamlife-KimlikDogrula
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host '[!] YONETICI PowerShell gerekli (panel yeniden baslatma yuksek yetki ister).' -ForegroundColor Red; exit 1
}
$bayt = New-Object byte[] 16; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bayt)
$Anahtar = -join ($bayt | ForEach-Object { $_.ToString('x2') })
$script:Is = $null

function Son-Satirlar($yol, $n) {
    try { if (Test-Path $yol) { return @(Get-Content -Path $yol -Tail $n -Encoding UTF8 -ErrorAction Stop | ForEach-Object { "$_" }) } } catch { }
    return @()
}
function Istek-Sure($url, $sn) {
    $t = [Diagnostics.Stopwatch]::StartNew()
    try { $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec $sn; return @{ ok = ($r.StatusCode -eq 200); kod = [int]$r.StatusCode; ms = [int]$t.ElapsedMilliseconds } }
    catch { return @{ ok = $false; kod = 0; ms = [int]$t.ElapsedMilliseconds } }
}
function Uzunluk($yol) { try { if (Test-Path $yol) { return [math]::Round((Get-Item $yol).Length / 1MB, 1) } } catch { } return $null }

# Veri kaynaklari (OneDesk, ONENT): surec degil, cekme isleri; ayar + ag erisimi + son tampon partisi. Gizli deger (parola/adres) disari verilmez.
function Env-Oku {
    $d = @{}
    try { foreach ($s in (Get-Content (Join-Path $Backend '.env') -Encoding UTF8)) { if ($s -match '^\s*([A-Z0-9_]+)=(.*)$') { $d[$Matches[1]] = $Matches[2].Trim() } } } catch { }
    return $d
}
function Tcp-Dene($h, $p) {
    if (-not $h -or -not $p) { return $null }
    try {
        $c = New-Object Net.Sockets.TcpClient
        $a = $c.BeginConnect($h, [int]$p, $null, $null)
        $ok = $a.AsyncWaitHandle.WaitOne(2000) -and $c.Connected
        $c.Close(); return [bool]$ok
    } catch { return $false }
}
function Kaynaklar-Al {
    $e = Env-Oku
    $son = @{}
    try {
        $kod = 'import sqlite3,json;c=sqlite3.connect(''file:E:/TAMLIFE/backend/var/dev.db?mode=ro'',uri=True);print(json.dumps([list(r) for r in c.execute(''select source_key,status,received_at,substr(error,1,120) from ingest_batch where id in (select max(id) from ingest_batch group by source_key)'')]))'
        $cikti = & (Join-Path $Kok '.venv\Scripts\python.exe') -I -c $kod
        foreach ($r in @($cikti | ConvertFrom-Json)) { $son[[string]$r[0]] = $r }
    } catch { }
    $liste = @(
        @{ ad = 'OneDesk (PostgreSQL)'; on = 'ONEDESKDB_PG'; anahtar = 'onedesk'; sorgu = 'ONEDESKDB_PG_IMPORT_QUERY'; port = 'ONEDESKDB_PG_PORT'; host = 'ONEDESKDB_PG_HOST' },
        @{ ad = 'ONENT (PostgreSQL)'; on = 'ONENTDB_PG'; anahtar = 'onent'; sorgu = 'ONENTDB_PG_IMPORT_QUERY'; port = 'ONENTDB_PG_PORT'; host = 'ONENTDB_PG_HOST' }
    )
    $sonuc = @()
    foreach ($k in $liste) {
        $acik = ($e[$k.on + '_ENABLED'] -match '^(1|true|yes|on)$')
        $ayarli = [bool]($e[$k.host]) -and [bool]($e[$k.on + '_USER'])
        $port = $e[$k.port]; if (-not $port) { $port = $(if ($k.on -like '*_PG') { '5432' } else { '1521' }) }
        $tcp = $null; if ($ayarli) { $tcp = Tcp-Dene $e[$k.host] $port }
        $parti = $null
        foreach ($anahtar in $son.Keys) { if ($anahtar -like "*$($k.anahtar)*" -and $anahtar -like '*import*') { $parti = $son[$anahtar] } }
        $sonuc += @{ ad = $k.ad; acik = $acik; ayarli = $ayarli; tcp = $tcp; sorgu = [bool]($e[$k.sorgu]); parti_zaman = $(if ($parti) { "$($parti[2])" } else { $null }); parti_durum = $(if ($parti) { "$($parti[1])" } else { $null }); parti_hata = $(if ($parti -and $parti[3]) { "$($parti[3])" } else { $null }) }
    }
    return $sonuc
}

$script:KaynakZaman = [datetime]::MinValue; $script:KaynakVeri = @()
function Kaynaklar-Onbellek {
    if (((Get-Date) - $script:KaynakZaman).TotalSeconds -ge 60) { $script:KaynakVeri = @(Kaynaklar-Al); $script:KaynakZaman = Get-Date }
    return $script:KaynakVeri
}

function Durum-Al {
    $sur = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine })
    function Bul($desen, $ad) { $x = $sur | Where-Object { $_.Name -match $ad -and $_.CommandLine -match $desen } | Select-Object -First 1; if ($x) { return @{ var = $true; pid = [int]$x.ProcessId; baslangic = $x.CreationDate.ToString('yyyy-MM-dd HH:mm:ss'); bellek_mb = [math]::Round($x.WorkingSetSize / 1MB) } } else { return @{ var = $false } } }
    $panel = Istek-Sure 'http://127.0.0.1:8117/api/v1/health' 4
    $https = Istek-Sure 'https://tamlife/api/v1/health' 6
    $g = Get-ScheduledTask -TaskName 'TAMLIFE_Servis' -ErrorAction SilentlyContinue
    $gb = if ($g) { Get-ScheduledTaskInfo -TaskName 'TAMLIFE_Servis' } else { $null }
    $os = Get-CimInstance Win32_OperatingSystem
    $cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='E:'"
    $son = Son-Satirlar $IsciLog 400 | Where-Object { $_ -match ' reportdb ' } | Select-Object -Last 1
    $sonDk = $null; $sonOk = $null
    if ($son -match '^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) reportdb (\w+)') {
        $sonDk = [int]((Get-Date) - [datetime]::ParseExact($Matches[1], 'yyyy-MM-dd HH:mm:ss', $null)).TotalMinutes
        $sonOk = $Matches[2]
    }
    $kilitDk = $null; if (Test-Path $Kilit) { $kilitDk = [int]((Get-Date) - (Get-Item $Kilit).LastWriteTime).TotalMinutes }
    $db = Join-Path $Backend 'var\dev.db'
    $yedek = Get-ChildItem (Join-Path $Backend 'var\yedek') -Filter *.db -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $isDurum = $null
    if ($script:Is) {
        $bitti = $script:Is.proc -and $script:Is.proc.HasExited
        $cikti = ''
        try { if (Test-Path $script:Is.log) { $cikti = ((Get-Content $script:Is.log -Tail 40 -Encoding UTF8) -join "`n") } } catch { }
        $isDurum = @{ ad = $script:Is.ad; calisiyor = (-not $bitti); cikis = $(if ($bitti) { $script:Is.proc.ExitCode } else { $null }); cikti = $cikti; baslangic = $script:Is.baslangic }
    }
    return @{
        zaman = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
        panel = $panel; https = $https
        gorev = @{ var = [bool]$g; durum = $(if ($g) { "$($g.State)" } else { 'yok' }); son_calisma = $(if ($gb) { "$($gb.LastRunTime)" } else { '' }) }
        surecler = @{
            servis = (Bul 'canli_gorev_kur\.ps1.*-Calistir servis' 'powershell')
            panel_dongu = (Bul 'canli_gorev_kur\.ps1.*-Calistir panel' 'powershell')
            vekil_dongu = (Bul 'canli_gorev_kur\.ps1.*-Calistir vekil' 'powershell')
            uvicorn = (Bul 'uvicorn app\.main:app' 'python')
            isci = (Bul 'app\.isci reportdb( |$)' 'python')
        }
        kaynaklar = @(Kaynaklar-Onbellek)
        reportdb = @{ son = $son; son_dk = $sonDk; sonuc = $sonOk; kilit_dk = $kilitDk }
        sunucu = @{
            cpu = [int]$cpu
            bellek_yuzde = [int](100 - 100 * $os.FreePhysicalMemory / $os.TotalVisibleMemorySize)
            disk_e_bos_gb = [math]::Round($disk.FreeSpace / 1GB, 1); disk_e_yuzde = [int](100 - 100 * $disk.FreeSpace / $disk.Size)
            acik_kalma_saat = [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalHours, 1)
            kullanici = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        }
        db = @{ mb = (Uzunluk $db); wal_mb = (Uzunluk "$db-wal"); son_yedek = $(if ($yedek) { $yedek.LastWriteTime.ToString('yyyy-MM-dd HH:mm') } else { $null }); son_yedek_ad = $(if ($yedek) { $yedek.Name } else { $null }) }
        gunluk = @{
            panel = (Son-Satirlar (Join-Path $Kok 'var\log\canli_panel.log') 8)
            servis = (Son-Satirlar (Join-Path $Kok 'var\log\canli_servis.log') 8)
            isci = (Son-Satirlar $IsciLog 8)
        }
        is = $isDurum
    }
}

function Islem-Baslat($ad) {
    if ($script:Is -and $script:Is.proc -and -not $script:Is.proc.HasExited) { return @{ ok = $false; mesaj = 'Baska bir islem suruyor: ' + $script:Is.ad } }
    $bayrak = @{ yenile = '-PanelYenile'; baslat = '-YenidenBaslat'; yeniden = '-YenidenBaslat'; durdur = '-Durdur'; durum = '-Durum' }
    $log = Join-Path $env:TEMP 'tamlife_saglik_islem.log'
    if ($ad -eq 'reportdb') {
        if (Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" | Where-Object { $_.CommandLine -match 'app\.isci reportdb( |$)' }) { return @{ ok = $false; mesaj = 'ReportDB turu zaten calisiyor.' } }
        Start-Process -FilePath $Pyw -ArgumentList @('-m', 'app.isci', 'reportdb', '--client', $Istemci) -WorkingDirectory $Backend -WindowStyle Hidden | Out-Null
        Set-Content -Path $log -Value 'ReportDB turu baslatildi (sonuc isci.log ve ReportDB kartinda gorunur; tur ~8-9 dk).' -Encoding UTF8
        $script:Is = @{ ad = $ad; proc = $null; log = $log; baslangic = (Get-Date).ToString('HH:mm:ss') }
        return @{ ok = $true; mesaj = 'ReportDB turu baslatildi.' }
    }
    if (-not $bayrak.ContainsKey($ad)) { return @{ ok = $false; mesaj = 'Bilinmeyen islem.' } }
    Remove-Item $log -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $PsExe -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $Gorev, $bayrak[$ad]) -WindowStyle Hidden -PassThru -RedirectStandardOutput $log -RedirectStandardError ($log + '.err')
    $script:Is = @{ ad = $ad; proc = $p; log = $log; baslangic = (Get-Date).ToString('HH:mm:ss') }
    return @{ ok = $true; mesaj = "Baslatildi: $ad" }
}

function Yanit($ctx, $kod, $tur, [string]$metin) {
    $b = [Text.Encoding]::UTF8.GetBytes($metin)
    $ctx.Response.StatusCode = $kod; $ctx.Response.ContentType = $tur + '; charset=utf-8'
    $ctx.Response.Headers['Cache-Control'] = 'no-store'
    $ctx.Response.Headers['X-Content-Type-Options'] = 'nosniff'
    $ctx.Response.Headers['X-Frame-Options'] = 'DENY'
    $ctx.Response.ContentLength64 = $b.Length
    $ctx.Response.OutputStream.Write($b, 0, $b.Length); $ctx.Response.Close()
}

$dinle = New-Object Net.HttpListener
$dinle.Prefixes.Add("http://127.0.0.1:$Port/")
try { $dinle.Start() } catch { Write-Host "[!] Port $Port acilamadi: $($_.Exception.Message)" -ForegroundColor Red; exit 1 }
$adres = "http://127.0.0.1:$Port/?t=$Anahtar"
Write-Host "[+] TAMLIFE saglik paneli: $adres" -ForegroundColor Green
Write-Host '    Durdurmak icin bu pencereyi kapat (Ctrl+C). Yalniz bu sunucudan erisilir.'
try { Start-Process $adres } catch { }
while ($dinle.IsListening) {
    $ctx = $dinle.GetContext()
    try {
        $r = $ctx.Request
        $hostOk = $r.Headers['Host'] -in @("127.0.0.1:$Port", "localhost:$Port")
        $origin = $r.Headers['Origin']
        $originOk = (-not $origin) -or ($origin -in @("http://127.0.0.1:$Port", "http://localhost:$Port"))
        if (-not ($hostOk -and $originOk)) { Yanit $ctx 403 'text/plain' 'yasak'; continue }
        $yol = $r.Url.AbsolutePath
        if ($yol -eq '/' -and $r.HttpMethod -eq 'GET') {
            Yanit $ctx 200 'text/html' ([IO.File]::ReadAllText($HtmlYolu, [Text.Encoding]::UTF8)); continue
        }
        if ($r.Headers['X-Token'] -ne $Anahtar) { Yanit $ctx 401 'application/json' '{"hata":"anahtar"}'; continue }
        if ($yol -eq '/api/durum' -and $r.HttpMethod -eq 'GET') {
            Yanit $ctx 200 'application/json' ((Durum-Al) | ConvertTo-Json -Depth 8 -Compress); continue
        }
        if ($yol -eq '/api/islem' -and $r.HttpMethod -eq 'POST') {
            $ad = $r.QueryString['ad']
            Yanit $ctx 200 'application/json' ((Islem-Baslat $ad) | ConvertTo-Json -Compress); continue
        }
        Yanit $ctx 404 'text/plain' 'yok'
    } catch {
        try { Yanit $ctx 500 'application/json' ((@{ hata = "$($_.Exception.Message)" }) | ConvertTo-Json -Compress) } catch { }
    }
}
