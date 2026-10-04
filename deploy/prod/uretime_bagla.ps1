# Yeni paneli (TAMLIFE_Dev) uretim paneline /admin/dev ile baglar. YONETICI (ladinadmin) PowerShell'de calistirin.
#   .\uretime_bagla.ps1            : sir uret/oku, uretim kaydini ekle, .env'e iki satir yaz, yeni paneli baslat ve dogrula
#   .\uretime_bagla.ps1 -Yeniden   : ayrica uretim panelini yeniden baslatir (yonet.bat yeniden)
#   .\uretime_bagla.ps1 -GeriAl    : en son yedekten __init__.py ve .env'i geri yukler, dev_panel_bp.py'yi kaldirir
# Sir ekrana yazilmaz. Betik saf ASCII; kullanici-dostu mesajlar Turkce harfsizdir (PS 5.1).
param([switch]$Yeniden, [switch]$GeriAl)
$ErrorActionPreference = 'Stop'

$Uretim = 'E:\TAMLIFE'
$Dev    = 'E:\TAMLIFE_Dev\TAMLIFE_v3.5'
$Deploy = "$Dev\deploy\prod"
$Init   = "$Uretim\backend\app\__init__.py"
$EnvDos = "$Uretim\.env"
$BpUret = "$Uretim\backend\app\blueprints\dev_panel_bp.py"
$BpKaynak = "$Deploy\dev_panel_bp.py"
$EnvBat = "$Deploy\dev-panel.env.bat"
$Yedek  = "$Dev\backend\var\prod_geri_al"
$Port   = 8117
$BeklenenInitHash = 'C65FD8CA356C3727BFC86C366719871DCC8109B1C83CA3B8DCB97B406F15B3DF'
$UretimPy = "$Uretim\.venv\Scripts\python.exe"
$Utf8Bomsuz = New-Object System.Text.UTF8Encoding($false)
$Utf8Bomlu  = New-Object System.Text.UTF8Encoding($true)

function Adim($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Dur($m)  { Write-Host "[!] $m" -ForegroundColor Red; exit 1 }
# Sir iceren dosya/klasor yalniz Administrators + SYSTEM (S-1-5-32-544, S-1-5-18) okuyabilsin.
function Kilitle($yol) {
    $dizinMi = (Get-Item $yol -Force).PSIsContainer
    $hak = if ($dizinMi) { '(OI)(CI)(F)' } else { '(F)' }
    & icacls $yol /inheritance:r /grant:r "*S-1-5-32-544:$hak" "*S-1-5-18:$hak" | Out-Null
}

$kimlik = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]$kimlik).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Dur "Yonetici (yukseltilmis) PowerShell gerekli. Su an: $($kimlik.Name)"
}
Write-Host "Kimlik: $($kimlik.Name)"
foreach ($y in @($Uretim, $Dev, $UretimPy, $BpKaynak)) { if (-not (Test-Path $y)) { Dur "Yol yok: $y" } }

if ($GeriAl) {
    $son = Get-ChildItem $Yedek -Directory -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
    if (-not $son) { Dur "Yedek bulunamadi: $Yedek" }
    Adim "Geri yukleniyor: $($son.FullName)"
    foreach ($ad in '__init__.py', '.env') {
        $k = Join-Path $son.FullName $ad
        if (Test-Path $k) { Copy-Item $k $(if ($ad -eq '.env') { $EnvDos } else { $Init }) -Force }
    }
    if (Test-Path $BpUret) { Remove-Item $BpUret -Force }
    Adim "Tamam. Uretim panelini yeniden baslatin: $Uretim\yonet.bat yeniden"
    exit 0
}

# 1) Uretim __init__.py beklenen surumde mi (baska degisiklik araya girmis olmasin)
Adim "Uretim __init__.py dogrulaniyor"
$metin = [IO.File]::ReadAllText($Init, $Utf8Bomsuz)
$zatenVar = $metin.Contains('dev_panel_bp')
if (-not $zatenVar) {
    $h = (Get-FileHash $Init -Algorithm SHA256).Hash
    if ($h -ne $BeklenenInitHash) { Dur "__init__.py degismis (hash farkli). Once inceleyin; betik durdu. Gecerli: $h" }
}

# 2) Sir: env.bat varsa oradan oku, yoksa uret ve yaz
if (Test-Path $EnvBat) {
    Adim "Mevcut dev-panel.env.bat okunuyor"
    $satir = Get-Content $EnvBat | Where-Object { $_ -match '^set TAMLIFE_SSO_SECRET=(.+)$' } | Select-Object -First 1
    if (-not $satir) { Dur "dev-panel.env.bat icinde TAMLIFE_SSO_SECRET yok" }
    $sir = ([regex]::Match($satir, '^set TAMLIFE_SSO_SECRET=(.+)$')).Groups[1].Value.Trim()
} else {
    Adim "Sir uretiliyor ve dev-panel.env.bat yaziliyor"
    $sir = (& $UretimPy -c "import secrets; print(secrets.token_urlsafe(48))").Trim()
    $py = "$Dev\.venv\Scripts\python.exe"
    $s = @(
        'rem dev-panel.env.bat: git''e girmez. Sirri paylasmayin, ekrana yazmayin.',
        'rem Ayni sir uretim .env icinde DEV_PANEL_SECRET olarak bulunmali (uretime_bagla.ps1 yazar).',
        "set PYTHON_EXE=$py",
        "set DEV_PANEL_PORT=$Port",
        'set TAMLIFE_ENV=production',
        'set TAMLIFE_BASE_PATH=/admin/dev',
        "set TAMLIFE_SSO_SECRET=$sir",
        'set TAMLIFE_TRUSTED_PROXIES=127.0.0.1',
        'set TAMLIFE_ALLOWED_HOSTS=tamlife,tamlife.turkcell.entp.tgc,172.28.100.7,localhost,127.0.0.1',
        'set TAMLIFE_SQLITE_IZIN=true',
        'set TAMLIFE_DATABASE_URL=sqlite:///E:/TAMLIFE_Dev/TAMLIFE_v3.5/backend/var/panel.db',
        "set TAMLIFE_STATIC_DIR=$Dev\ekran-react\dist",
        "set TAMLIFE_REPORT_DIR=$Dev\data\reports"
    )
    [IO.File]::WriteAllText($EnvBat, ($s -join "`r`n") + "`r`n", [Text.Encoding]::ASCII)
}
Kilitle $EnvBat
if ($sir.Length -lt 32) { Dur "Sir 32 karakterden kisa" }
New-Item -ItemType Directory -Force "$Dev\data\reports", "$Dev\backend\var" | Out-Null

# 3) Yedek (E:\TAMLIFE disinda)
$yd = Join-Path $Yedek (Get-Date -Format 'yyyyMMdd_HHmmss')
New-Item -ItemType Directory -Force $yd | Out-Null
Kilitle $Yedek
Copy-Item $Init (Join-Path $yd '__init__.py')
Copy-Item $EnvDos (Join-Path $yd '.env')
Adim "Yedek: $yd"

# 4) Vekil blueprint dosyasi (kaynakla ayni olmali)
if (-not (Test-Path $BpUret) -or (Get-FileHash $BpUret).Hash -ne (Get-FileHash $BpKaynak).Hash) {
    Copy-Item $BpKaynak $BpUret -Force
    Adim "dev_panel_bp.py kopyalandi"
}

# 5) __init__.py: blueprint dongusunden sonra, islem_gunlugune_yaz'dan once 6 satir
if (-not $zatenVar) {
    $cr = "`r`n"
    $anchor = '        app.register_blueprint(bp)' + $cr + $cr
    if (([regex]::Matches($metin, [regex]::Escape($anchor))).Count -ne 1) { Dur "Baglanti noktasi bulunamadi/tekil degil" }
    $blok = @(
        "    # Yeni panel (v3.5) /admin/dev altinda: yalniz yonetici, ayri surece vekil (bkz. TAMLIFE_Dev deploy/prod/README.md).",
        "    try:",
        "        from backend.app.blueprints import dev_panel_bp",
        "        dev_panel_bp.kur(app)",
        "    except Exception:",
        "        app.logger.exception('dev_panel_bp kaydedilemedi; /admin/dev kapali')"
    ) -join $cr
    $yeni = $metin.Replace($anchor, $anchor + $blok + $cr + $cr)
    $gecici = "$yd\__init__.yeni.py"
    [IO.File]::WriteAllText($gecici, $yeni, $Utf8Bomsuz)
    & $UretimPy -c "import ast,sys; ast.parse(open(sys.argv[1],encoding='utf-8').read())" $gecici
    if ($LASTEXITCODE -ne 0) { Dur "Yeni __init__.py sozdizimi gecersiz; uretime yazilmadi" }
    [IO.File]::WriteAllText($Init, $yeni, $Utf8Bomsuz)
    Adim "__init__.py guncellendi"
} else { Adim "__init__.py zaten kayitli, atlandi" }

# 6) .env: iki satir (BOM + CRLF korunur)
$envMetin = [IO.File]::ReadAllText($EnvDos, $Utf8Bomlu)
if ($envMetin -notmatch '(?m)^DEV_PANEL_SECRET=') {
    $ek = ''
    if (-not $envMetin.EndsWith("`n")) { $ek = "`r`n" }
    $ek += "DEV_PANEL_SECRET=$sir`r`nDEV_PANEL_PORT=$Port`r`n"
    [IO.File]::WriteAllText($EnvDos, $envMetin + $ek, $Utf8Bomlu)
    Adim ".env'e DEV_PANEL_SECRET ve DEV_PANEL_PORT eklendi"
} else { Adim ".env'de DEV_PANEL_SECRET zaten var, atlandi" }

# 7) Yeni paneli baslat (yoksa) ve bekle
function Dinliyor { try { $t = New-Object Net.Sockets.TcpClient; $t.Connect('127.0.0.1', $Port); $t.Close(); $true } catch { $false } }
if (Dinliyor) { Adim "Yeni panel zaten $Port portunda dinliyor" } else {
    Adim "Yeni panel baslatiliyor (127.0.0.1:$Port)"
    Start-Process -FilePath $env:ComSpec -ArgumentList '/c', ('"' + "$Deploy\dev-panel-baslat.bat" + '"') `
        -WindowStyle Hidden -RedirectStandardOutput "$Dev\backend\var\panel.log" -RedirectStandardError "$Dev\backend\var\panel.err.log"
    for ($i = 0; $i -lt 40 -and -not (Dinliyor); $i++) { Start-Sleep -Seconds 1 }
    if (-not (Dinliyor)) {
        Get-Content "$Dev\backend\var\panel.err.log" -Tail 15 -ErrorAction SilentlyContinue
        Dur "Yeni panel acilmadi. Uretim paneli yeniden BASLATILMADI. Log: $Dev\backend\var\panel.err.log"
    }
}
try {
    $r = Invoke-WebRequest "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 10
    Adim "Yeni panel arayuzu yanit verdi: HTTP $($r.StatusCode)"
} catch { Write-Host "[!] Arayuz yaniti alinamadi: $($_.Exception.Message)" -ForegroundColor Yellow }

# 8) Uretim yeniden baslatma
if ($Yeniden) {
    Adim "Uretim paneli yeniden baslatiliyor"
    & "$Uretim\yonet.bat" yeniden
} else {
    Adim "Kayit uretimde yeniden baslatma sonrasi etkin olur: $Uretim\yonet.bat yeniden  (veya betigi -Yeniden ile calistirin)"
}
Write-Host "Dogrulama: yonetici olarak https://tamlife/admin/dev acin. Geri alma: .\uretime_bagla.ps1 -GeriAl" -ForegroundColor Green
