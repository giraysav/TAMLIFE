# TAMLIFE - Citrix gelistirme makinesine tasima paketi (saf ASCII; PS 5.1). Cagiran: E:\TAMLIFE\TAMLIFE_robocopy_gonder.bat.
# 2026-10-27 kullanici: "kodu bu hali ile citrix makinaya tasiyacagim, development yapacagiz; tasirken hicbir dosya hatasi gormek
# istemiyorum". Kararlar: veritabaninin ANLIK kopyasi tasinir, backend\.env OLDUGU GIBI tasinir, hedefteki eski kopyanin UZERINE yazilir.
#
# Neden paket: \\tsclient (uzak masaustu surucu yonlendirmesi) dosya basina cok yavas (20 bin dosyayi taramak bile 20 dk+); tek tek
# kopyalama saatler surer ve kopmaya acik. Bu yuzden:
#   1) Sunucuda (yerel, hizli): E:\TAMLIFE -> E:\TAMLIFE_paket\icerik (robocopy). Haric: backend\var (canli veritabani, 11 GB ham
#      katalog, yedekler, gunlukler), var (calisma gunlukleri), __pycache__ / .pytest_cache / .ruff_cache / .mypy_cache, *.log,
#      *.db-wal, *.db-shm. Dahil: kod, .git, .venv, node_modules, ceviri_modeli, backend\data, backend\.env.
#   2) Veritabani: canli dosya DEGIL, SQLite backup API ile tutarli anlik kopya (araclar\db_yedek.py --hedef) -> icerik\...\backend\var\dev.db
#   3) Tek zip + SHA-256 ozeti + Citrix kurulum betikleri -> E:\TAMLIFE_paket\gonder
#   4) robocopy gonder -> \\tsclient\C\Users\<kullanici>\Desktop\TAMLIFE_PAKET (4 dosya), boyut dogrulamasi
# Citrix'te: Masaustu\TAMLIFE_PAKET\KUR_CITRIX.bat (zip butunlugu SHA-256 ile, yerelde acar, Masaustu\TAMLIFE\TAMLIFE_v3.5'i gunceller).

param(
    [string]$HedefKok = '\\tsclient\C\Users\tcgsav\Desktop'
)
$ErrorActionPreference = 'Stop'

$Kaynak = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent       # E:\TAMLIFE
$Proje = Join-Path $Kaynak 'TAMLIFE_v3.5'
$Paket = Join-Path (Split-Path $Kaynak -Qualifier) 'TAMLIFE_paket'     # E:\TAMLIFE_paket (kaynagin disinda)
$Icerik = Join-Path $Paket 'icerik'
$Gonder = Join-Path $Paket 'gonder'
$Zip = Join-Path $Gonder 'TAMLIFE_paket.zip'
$Hedef = Join-Path $HedefKok 'TAMLIFE_PAKET'
$Py = Join-Path $Proje '.venv\Scripts\python.exe'
$Gunluk = Join-Path $Paket 'paket.log'

function Adim($m) { Write-Host ''; Write-Host "=== $m ===" -ForegroundColor Cyan }
function Tamam($m) { Write-Host "  [TAMAM] $m" -ForegroundColor Green }
function Dur($m) { Write-Host "  [HATA] $m" -ForegroundColor Red; Write-Host "  Gunluk: $Gunluk"; exit 1 }
function Robocopy-Calistir($argumanlar, $ad) {
    # robocopy cikis kodu: 0-7 basari (1 = kopyalandi, 2/3 = fazlalik), 8+ = HATA
    $s = Start-Process -FilePath 'robocopy.exe' -ArgumentList $argumanlar -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$Gunluk.$ad.txt"
    Get-Content "$Gunluk.$ad.txt" | Add-Content -Path $Gunluk
    return $s.ExitCode
}

Write-Host '========================================================' -ForegroundColor Cyan
Write-Host ' TAMLIFE - Citrix gelistirme paketi' -ForegroundColor Cyan
Write-Host " Kaynak: $Kaynak" -ForegroundColor Cyan
Write-Host " Hedef : $Hedef" -ForegroundColor Cyan
Write-Host '========================================================' -ForegroundColor Cyan

# --- 0) On denetim -----------------------------------------------------------------------------------------------------
Adim '0/5 On denetim'
if (-not (Test-Path (Join-Path $Proje 'CLAUDE.md'))) { Dur "Kaynak proje bulunamadi: $Proje" }
if (-not (Test-Path $Py)) { Dur "Python bulunamadi: $Py" }
if (-not (Test-Path $HedefKok)) { Dur "Hedef erisilemiyor: $HedefKok (uzak masaustunde yerel surucu paylasimi acik mi? Baglanti > Yerel kaynaklar > Surucular)" }
New-Item -ItemType Directory -Force -Path $Paket, $Icerik, $Gonder | Out-Null
Set-Content -Path $Gunluk -Value "TAMLIFE Citrix paketi - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -Encoding ASCII
Tamam 'kaynak, python ve hedef erisilebilir'

# --- 1) Kaynagi yerel paket klasorune ayna ---------------------------------------------------------------------------------
Adim '1/5 Dosyalar paket klasorune aliniyor (yerel)'
$haricKlasor = @(
    (Join-Path $Proje 'backend\var'), (Join-Path $Proje 'var'),
    '__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache'
)
$arg = @("`"$Kaynak`"", "`"$Icerik`"", '/MIR', '/COPY:DAT', '/DCOPY:DAT', '/XJ', '/R:3', '/W:3', '/NP', '/NFL', '/NDL', '/MT:8',
         '/XD') + ($haricKlasor | ForEach-Object { "`"$_`"" }) + @('/XF', '*.log', '*.db-wal', '*.db-shm', '*.pyc')
$kod = Robocopy-Calistir ($arg -join ' ') 'ayna'
if ($kod -ge 8) { Dur "Yerel kopyalama basarisiz (robocopy kodu $kod)" }
$sayi = (Get-ChildItem $Icerik -Recurse -File -Force | Measure-Object).Count
Tamam "$sayi dosya alindi (robocopy kodu $kod)"

# --- 2) Veritabaninin tutarli anlik kopyasi -------------------------------------------------------------------------------
Adim '2/5 Veritabaninin anlik kopyasi (canli dosya kopyalanmaz)'
$dbHedef = Join-Path $Icerik 'TAMLIFE_v3.5\backend\var\dev.db'
Push-Location (Join-Path $Proje 'backend')
$cikti = & $Py 'araclar\db_yedek.py' '--hedef' $dbHedef 2>&1
$dbKod = $LASTEXITCODE
Pop-Location
Add-Content -Path $Gunluk -Value $cikti
if ($dbKod -ne 0) { Dur "Veritabani kopyasi alinamadi: $cikti" }
Tamam "dev.db $([math]::Round((Get-Item $dbHedef).Length / 1MB)) MB, butunluk denetimi tamam"

# --- 3) Tek zip + SHA-256 ------------------------------------------------------------------------------------------------
Adim '3/5 Zip olusturuluyor (birkac dakika)'
Add-Type -AssemblyName System.IO.Compression.FileSystem
if (Test-Path $Zip) { Remove-Item -LiteralPath $Zip -Force }
[IO.Compression.ZipFile]::CreateFromDirectory($Icerik, $Zip, [IO.Compression.CompressionLevel]::Optimal, $false)
$ozet = (Get-FileHash -Algorithm SHA256 -LiteralPath $Zip).Hash
Set-Content -Path (Join-Path $Gonder 'TAMLIFE_paket.sha256') -Value $ozet -Encoding ASCII
Copy-Item -Force (Join-Path $PSScriptRoot 'kur_citrix.ps1') $Gonder
Copy-Item -Force (Join-Path $PSScriptRoot 'KUR_CITRIX.bat') $Gonder
$boyut = (Get-Item $Zip).Length
Tamam "TAMLIFE_paket.zip $([math]::Round($boyut / 1MB)) MB, SHA-256 $($ozet.Substring(0, 12))..."

# --- 4) Hedefe gonder ------------------------------------------------------------------------------------------------------
Adim '4/5 Hedefe gonderiliyor (uzak masaustu baglantisinin hizina gore birkac dakika)'
try { $bos = (New-Object -ComObject Scripting.FileSystemObject).GetDrive(($HedefKok -replace '^(\\\\[^\\]+\\[^\\]+).*', '$1')).FreeSpace } catch { $bos = $null }
if ($bos -and $bos -lt (3 * $boyut)) { Dur "Hedefte yer yetersiz: $([math]::Round($bos / 1GB, 1)) GB bos, en az $([math]::Round(3 * $boyut / 1GB, 1)) GB gerekli (zip + acilmis hali)" }
$arg = "`"$Gonder`" `"$Hedef`" /E /COPY:DAT /R:5 /W:10 /NP /XJ"
$kod = Robocopy-Calistir $arg 'gonder'
if ($kod -ge 8) { Dur "Hedefe kopyalama basarisiz (robocopy kodu $kod). Baglantiyi kontrol edip yeniden calistirin; zaten giden dosyalar tekrar gonderilmez." }
$uzak = Get-Item -LiteralPath (Join-Path $Hedef 'TAMLIFE_paket.zip')
if ($uzak.Length -ne $boyut) { Dur "Hedefteki zip boyutu farkli ($($uzak.Length) / $boyut bayt)" }
Tamam "4 dosya gonderildi, zip boyutu dogrulandi"

# --- 5) Sonuc --------------------------------------------------------------------------------------------------------------
Adim '5/5 Bitti'
Write-Host '  Citrix makinede simdi sunu yapin:' -ForegroundColor Cyan
Write-Host '    1) VS Code ve Masaustu\TAMLIFE klasorunde acik terminalleri kapatin'
Write-Host '    2) Masaustu\TAMLIFE_PAKET\KUR_CITRIX.bat dosyasina cift tiklayin'
Write-Host '       (zip butunlugunu dogrular, yerelde acar, Masaustu\TAMLIFE\TAMLIFE_v3.5 klasorunu gunceller)'
Write-Host "  Gunluk: $Gunluk"
exit 0
