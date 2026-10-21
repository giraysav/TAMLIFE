# TAMLIFE v3.5 GERI DONUS: yedekten geri yukleme. Betik saf ASCII (PS 5.1). YONETICI (yukseltilmis) PowerShell gerekir.
# Konum: <yedek klasoru>\ROLLBACK\geri_don.ps1 (panel her "Yedek al"da kurulum\yedek_geri_don.ps1'den tazeler; elle degistirmeyin).
# Baslatici: GERI_DON.bat (cift tik, yonetici ister). Panelden geri donus YOKTUR (yikici islem; panelin kendisini durdurur).
#   .\geri_don.ps1                          : yedekleri listeler, secilen yedege doner
#   .\geri_don.ps1 -Yedek tamlife_20261021_101500   : belirli yedege doner (yine sifre + onay ister)
# Akis: sifre (PBKDF2, 3 hak) -> yedek secimi -> manifest SHA-256 dogrulamasi -> yedek adini yazarak onay -> panel/isci gorevleri durur
#       -> MEVCUT veri GERI_DONUSU_ONCESI\<tarih>\ altina kopyalanir -> yedek geri yazilir -> gorevler baslar -> /health beklenir.
# Sifre dosyasi: sifre.hash (parola DEGIL, ozet). Yoksa betik HICBIR sey yapmaz. Sifre degistirmek: kurulum\yedek_kur.ps1 -SifreDegistir.
# Yedek ONCEKI sema surumundeyse panel acilirken `alembic upgrade head` semayi kendiliginden yukseltir (canli_baslat.ps1).
# Geri yuklenen: panel DB'si, kisi basina SQLite dosyalari (kullanicilar), aylik rapor arsivi, profil fotograflari. Geri yuklenmeyen:
#   backend\.env (sirlar), var\ham (ham katalog; yeniden taranir), gunlukler, program dosyalari.
# -ServisYok : gorevlere dokunmaz (YALNIZ test/sandbox; canlida kullanmayin).
param([string]$Yedek = '',
      [switch]$ServisYok)
$ErrorActionPreference = 'Stop'
$YedekKlasoru = Split-Path -Parent $PSScriptRoot
$SifreDosyasi = Join-Path $PSScriptRoot 'sifre.hash'
$GunlukDosyasi = Join-Path $PSScriptRoot 'geri_don.log'
$PanelGorevi = 'TAMLIFE_v35_Panel'
$IsciGorevi = 'TAM_Life_v35_ReportDB_6dk'
$SaglikAdresi = 'http://127.0.0.1:8117/api/v1/health'

function Gunluk($m) {
    $satir = "{0} [{1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), [Security.Principal.WindowsIdentity]::GetCurrent().Name, $m
    try { Add-Content -Path $GunlukDosyasi -Value $satir -Encoding ASCII } catch { }
}
function Yaz($m, $renk = 'Cyan') { Write-Host "[*] $m" -ForegroundColor $renk }
function Dur($m, $kod = 1) { Gunluk "DURDU: $m"; Write-Host "[!] $m" -ForegroundColor Red; exit $kod }

$yonetici = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $yonetici) { Dur 'YONETICI olarak calistirin (GERI_DON.bat bunu kendisi ister).' 2 }

# --- 1) SIFRE ---------------------------------------------------------------------------------------------------------
if (-not (Test-Path $SifreDosyasi)) { Dur 'sifre.hash yok: geri donus sifresi tanimli degil, HICBIR sey yapilmadi (kurulum\yedek_kur.ps1 -SifreDegistir).' 3 }
$kisimlar = (Get-Content -Raw $SifreDosyasi).Trim().Split('$')
if ($kisimlar.Count -ne 4 -or $kisimlar[0] -ne 'pbkdf2-sha256') { Dur 'sifre.hash bicimi gecersiz.' 3 }
$tur = [int]$kisimlar[1]; $tuz = [Convert]::FromBase64String($kisimlar[2]); $beklenen = [Convert]::FromBase64String($kisimlar[3])

function Sifre-Dogru($duz) {
    $kdf = New-Object Security.Cryptography.Rfc2898DeriveBytes($duz, $tuz, $tur, [Security.Cryptography.HashAlgorithmName]::SHA256)
    $hesap = $kdf.GetBytes($beklenen.Length)
    $fark = 0
    for ($i = 0; $i -lt $beklenen.Length; $i++) { $fark = $fark -bor ($hesap[$i] -bxor $beklenen[$i]) }
    return ($fark -eq 0)
}

$gecti = $false
for ($hak = 1; $hak -le 3 -and -not $gecti; $hak++) {
    if ($env:TAMLIFE_GERI_DON_SIFRE) {
        $duz = $env:TAMLIFE_GERI_DON_SIFRE   # otomasyon/test; yine de dogru sifre sart
    } else {
        $guvenli = Read-Host "Geri donus sifresi ($hak/3)" -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($guvenli)
        try { $duz = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }
    if (Sifre-Dogru $duz) { $gecti = $true } else { Gunluk "YANLIS SIFRE ($hak/3)"; Write-Host '[!] Sifre yanlis.' -ForegroundColor Red; Start-Sleep -Seconds 3 }
    $duz = $null
    if ($env:TAMLIFE_GERI_DON_SIFRE -and -not $gecti) { break }
}
if (-not $gecti) { Dur 'Sifre dogrulanamadi. Geri donus YAPILMADI.' 4 }
Gunluk 'sifre dogrulandi'

# --- 2) YEDEK SECIMI ---------------------------------------------------------------------------------------------------
$liste = @(Get-ChildItem -Path $YedekKlasoru -Filter 'tamlife_*.manifest.json' -File | Sort-Object Name -Descending)
if ($liste.Count -eq 0) { Dur "Manifestli yedek yok: $YedekKlasoru (panelde Yedek al ile alinan yedekler gerekir)." }
if ($Yedek -eq '') {
    Write-Host ''
    for ($i = 0; $i -lt $liste.Count; $i++) { Write-Host ("  [{0}] {1}   {2}" -f ($i + 1), $liste[$i].Name.Replace('.manifest.json', ''), $liste[$i].LastWriteTime.ToString('yyyy-MM-dd HH:mm')) }
    $secim = Read-Host 'Yedek numarasi (bos = vazgec)'
    if ($secim -notmatch '^\d+$' -or [int]$secim -lt 1 -or [int]$secim -gt $liste.Count) { Dur 'Vazgecildi.' 0 }
    $Yedek = $liste[[int]$secim - 1].Name.Replace('.manifest.json', '')
}
$Yedek = $Yedek -replace '\.db$', ''
if ($Yedek -notmatch '^tamlife_\d{8}_\d{6}$') { Dur "Gecersiz yedek adi: $Yedek" }
$manifestYolu = Join-Path $YedekKlasoru "$Yedek.manifest.json"
if (-not (Test-Path $manifestYolu)) { Dur "Manifest yok: $manifestYolu" }
$manifest = Get-Content -Raw $manifestYolu | ConvertFrom-Json
$h = $manifest.hedefler

# --- 3) YEDEGI DOGRULA -------------------------------------------------------------------------------------------------
Yaz "Yedek dogrulaniyor: $Yedek ($($manifest.dosyalar.Count) dosya, SHA-256)"
$bozuk = 0
foreach ($d in $manifest.dosyalar) {
    $yol = Join-Path $YedekKlasoru ($d.yol -replace '/', '\')
    if (-not (Test-Path -LiteralPath $yol)) { Write-Host "    eksik: $($d.yol)" -ForegroundColor Red; $bozuk++; continue }
    if ((Get-FileHash -LiteralPath $yol -Algorithm SHA256).Hash.ToLowerInvariant() -ne $d.sha256) { Write-Host "    ozet uyusmuyor: $($d.yol)" -ForegroundColor Red; $bozuk++ }
}
if ($bozuk -gt 0) { Dur "Yedek BOZUK ($bozuk dosya). Geri donus yapilmadi; baska bir yedek secin." }
foreach ($yol in $h.db, $h.kullanici_dizini, $h.rapor_dizini, $h.foto_dizini) {
    if ([string]::IsNullOrWhiteSpace($yol) -or $yol.Length -le 3) { Dur "Manifestte guvensiz hedef yol: '$yol'" }
}

# --- 4) ONAY -----------------------------------------------------------------------------------------------------------
Write-Host ''
Write-Host '  GERI YUKLENECEK (mevcut icerigin USTUNE yazilir):' -ForegroundColor Yellow
Write-Host "    panel DB          : $($h.db)"
Write-Host "    kisi dosyalari    : $($h.kullanici_dizini)   (yedekte olmayan kisi dosyalari silinir)"
Write-Host "    rapor arsivi      : $($h.rapor_dizini)"
Write-Host "    profil fotograflari: $($h.foto_dizini)"
Write-Host "  Yedek zamani: $($manifest.zaman)   sema: $($manifest.alembic)" -ForegroundColor Yellow
Write-Host '  Mevcut veri once GERI_DONUSU_ONCESI klasorune kopyalanir. Panel birkac dakika kapali kalir.' -ForegroundColor Yellow
$onay = Read-Host "Onaylamak icin yedek adini aynen yazin ($Yedek)"
if ($onay -ne $Yedek) { Dur 'Onay eslesmedi. Geri donus YAPILMADI.' 0 }
Gunluk "ONAYLANDI: $Yedek"

# --- 5) SERVISLERI DURDUR ----------------------------------------------------------------------------------------------
$isciHazirdi = $false
if (-not $ServisYok) {
    Yaz 'Panel ve isci gorevleri durduruluyor'
    $isci = Get-ScheduledTask -TaskName $IsciGorevi -ErrorAction SilentlyContinue
    if ($isci) {
        $isciHazirdi = ($isci.State -ne 'Disabled')
        Disable-ScheduledTask -TaskName $IsciGorevi | Out-Null
        Stop-ScheduledTask -TaskName $IsciGorevi -ErrorAction SilentlyContinue
    }
    Stop-ScheduledTask -TaskName $PanelGorevi -ErrorAction SilentlyContinue
    for ($i = 0; $i -lt 30; $i++) {
        $tutan = Get-NetTCPConnection -LocalPort 8117 -State Listen -ErrorAction SilentlyContinue
        if (-not $tutan) { break }
        foreach ($t in $tutan) { Stop-Process -Id $t.OwningProcess -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 1
    }
    if (Get-NetTCPConnection -LocalPort 8117 -State Listen -ErrorAction SilentlyContinue) { Dur 'Panel durmadi (8117 dolu). Hicbir dosya degistirilmedi.' }
    Start-Sleep -Seconds 2
}
if (Test-Path -LiteralPath $h.db) {   # DB baska bir surecte acik mi? Acikken uzerine yazmak bozar.
    try { $f = [IO.File]::Open($h.db, 'Open', 'ReadWrite', 'None'); $f.Close() }
    catch { Dur "DB baska bir surecte acik: $($h.db). Hicbir dosya degistirilmedi." }
}

# --- 6) MEVCUT VERIYI KORU, GERI YAZ ----------------------------------------------------------------------------------
$once = Join-Path $YedekKlasoru ('GERI_DONUSU_ONCESI\' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Force -Path $once | Out-Null
$basarili = $false
try {
    Yaz "Mevcut veri korunuyor: $once"
    foreach ($ek in '', '-wal', '-shm') { if (Test-Path -LiteralPath ($h.db + $ek)) { Copy-Item -LiteralPath ($h.db + $ek) -Destination (Join-Path $once ((Split-Path -Leaf $h.db) + $ek)) -Force } }
    $parcalar = @(@('kullanicilar', $h.kullanici_dizini), @('raporlar', $h.rapor_dizini), @('profil_foto', $h.foto_dizini))
    foreach ($p in $parcalar) {
        if (Test-Path -LiteralPath $p[1]) { & robocopy $p[1] (Join-Path $once $p[0]) /E /R:2 /W:2 /NP /NFL /NDL /NJH /NJS | Out-Null; if ($LASTEXITCODE -ge 8) { throw "Koruma kopyasi alinamadi: $($p[1])" } }
    }

    Yaz 'Panel DB geri yaziliyor'
    foreach ($ek in '-wal', '-shm') { Remove-Item -LiteralPath ($h.db + $ek) -Force -ErrorAction SilentlyContinue }
    Copy-Item -LiteralPath (Join-Path $YedekKlasoru "$Yedek.db") -Destination $h.db -Force

    $geri = @(
        @("${Yedek}_kullanicilar", $h.kullanici_dizini),
        @("${Yedek}_dosyalar\raporlar", $h.rapor_dizini),
        @("${Yedek}_dosyalar\profil_foto", $h.foto_dizini)
    )
    foreach ($g in $geri) {
        $kaynak = Join-Path $YedekKlasoru $g[0]
        if (-not (Test-Path -LiteralPath $kaynak)) { Yaz "Yedekte yok, mevcut korunuyor: $($g[0])" 'Yellow'; continue }
        Yaz "Geri yaziliyor: $($g[1])"
        & robocopy $kaynak $g[1] /MIR /R:3 /W:3 /NP /NFL /NDL /NJH /NJS | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "Geri yazilamadi: $($g[1]) (robocopy $LASTEXITCODE)" }
    }
    $basarili = $true
    Gunluk "GERI YAZILDI: $Yedek (onceki veri: $once)"
} catch {
    Gunluk "HATA: $($_.Exception.Message)"
    Write-Host "[!] HATA: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "[!] Mevcut veri su klasorde korunuyor: $once" -ForegroundColor Yellow
}

# --- 7) SERVISLERI BASLAT ----------------------------------------------------------------------------------------------
if (-not $ServisYok) {
    Yaz 'Panel baslatiliyor'
    Start-ScheduledTask -TaskName $PanelGorevi
    if ($isciHazirdi) { Enable-ScheduledTask -TaskName $IsciGorevi | Out-Null }
    $saglam = $false
    for ($i = 0; $i -lt 60 -and -not $saglam; $i++) {
        Start-Sleep -Seconds 3
        try { $saglam = ((Invoke-WebRequest -Uri $SaglikAdresi -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200) } catch { $saglam = $false }
    }
    if ($saglam) { Yaz 'Panel ayakta (health 200).' 'Green' } else { Write-Host '[!] Panel 3 dakikada ayaga kalkmadi: gorev gunlugune ve backend\var\logs\ klasorune bakin.' -ForegroundColor Red }
}
if ($basarili) { Yaz "TAMAM: $Yedek geri yuklendi. Onceki veri: $once" 'Green'; exit 0 }
exit 1
