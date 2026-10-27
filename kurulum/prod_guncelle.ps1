# TAMLIFE - Citrix'teki gelistirmeyi PROD'a 1:1 alma (saf ASCII; PS 5.1). Cagiran: depo kokundeki PROD_GUNCELLE.bat (cift tikla).
# 2026-10-27 kullanici: "Citrix'te yapilan gelistirme buraya 1:1 gonderilip calismasi gerekiyor". Paketi Citrix'te PRODA_GONDER.bat
# (kurulum\gonder_prod.ps1) hazirlar: Masaustu\TAMLIFE_GONDER (kod.bundle, python_venv.zip, node_modules.zip, manifest.json).
#
# Canli sisteme DOKUNMADAN once:
#   1 Paket \\tsclient uzerinden yerel klasore alinir, SHA-256'lari manifestle dogrulanir
#   2 Kod incelenir: prod'da Citrix'te olmayan commit varsa DURUR (1:1 bozulmasin); gelen commit'ler, degisen dosyalar ve yeni
#     veritabani gocleri listelenir; Python / arayuz paketleri degismis mi (pip freeze ve package-lock parmak izi)
#   3 ADAY TESTI: yeni surum ayri bir git worktree'de (canli klasorun disinda) test edilir: pytest + tsc + oxlint + vitest + derleme.
#     Basarisizsa durur, prod degismez.
# Onay [E/H] -> 4 Uygulama (YONETICI, Windows onay penceresi; kurulum\prod_uygula.ps1): DB yedegi, durdur, kod, paketler, derleme,
#   baslat (alembic upgrade) -> 5 Denetim (saglik + panel_saglik.py). Sorun varsa GERI ALMA onerilir (eski commit; yeni veritabani
#   gocu calistiysa yedek de geri yazilir).
param(
    [string]$Kaynak = '\\tsclient\C\Users\tcgsav\Desktop\TAMLIFE_GONDER',
    [switch]$YalnizDene          # 1-3 adimlari: hicbir sey uygulanmaz, soru sorulmaz
)
$ErrorActionPreference = 'Stop'
$Proje = Split-Path $PSScriptRoot -Parent
$Py = Join-Path $Proje '.venv\Scripts\python.exe'
$Zaman = Get-Date -Format 'yyyyMMdd-HHmmss'
$Calisma = Join-Path (Split-Path (Split-Path $Proje -Parent) -Qualifier) "TAMLIFE_gelen\$Zaman"     # E:\TAMLIFE_gelen\<zaman>
$Aday = Join-Path $Calisma 'aday'
$Rapor = Join-Path $Calisma 'rapor.txt'

function Adim($m) { Write-Host ''; Write-Host "=== $m ===" -ForegroundColor Cyan; Add-Content -Path $Rapor -Value "`r`n=== $m ===" -Encoding ASCII }
function Tamam($m) { Write-Host "  [TAMAM] $m" -ForegroundColor Green; Add-Content -Path $Rapor -Value "[TAMAM] $m" -Encoding UTF8 }
function Uyari($m) { Write-Host "  [UYARI] $m" -ForegroundColor Yellow; Add-Content -Path $Rapor -Value "[UYARI] $m" -Encoding UTF8 }
function Temizle {
    # aday klasorundeki baglantilar (junction) once tek tek kaldirilir: git worktree remove baglanti hedefini (canli .venv!) silmesin
    foreach ($j in "$Aday\.venv", "$Aday\ekran-react\node_modules", "$Aday\ceviri_modeli") {
        if ((Test-Path $j) -and ((Get-Item $j -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { & cmd.exe /c "rmdir `"$j`"" }
    }
    if (Test-Path $Aday) { G worktree remove --force $Aday | Out-Null }
    G worktree prune | Out-Null
}
function Dur($m) {
    Write-Host "  [HATA] $m" -ForegroundColor Red
    Add-Content -Path $Rapor -Value "[HATA] $m" -Encoding UTF8
    try { Temizle } catch { }
    Write-Host "  Prod DEGISMEDI. Rapor: $Rapor"
    if (-not $YalnizDene) { Read-Host 'Kapatmak icin Enter' }
    exit 1
}
function G {
    $onceki = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $c = & git -C $Proje @args 2>&1 | ForEach-Object { "$_" }
    $kod = $LASTEXITCODE; $ErrorActionPreference = $onceki
    if ($kod -ne 0) { throw "git $($args -join ' '): $c" }
    return $c
}
function Calistir($dizin, $program, $argumanlar, $dosya) {
    $s = Start-Process -FilePath $program -ArgumentList $argumanlar -WorkingDirectory $dizin -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $dosya -RedirectStandardError "$dosya.err"
    if (Test-Path "$dosya.err") { Get-Content "$dosya.err" | Add-Content $dosya; Remove-Item "$dosya.err" -Force }
    return $s.ExitCode
}
function Parmak-Izi($metin) {
    $b = [Text.Encoding]::UTF8.GetBytes(($metin -join "`n"))
    return ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($b)) -replace '-', '')
}
function Ac($zip, $hedef) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($zip, $hedef)
}
function Saglik {
    $sonuc = @()
    foreach ($a in 'http://127.0.0.1:8117/api/v1/health', 'https://tamlife/api/v1/health') {
        try { $ok = ((Invoke-WebRequest -Uri $a -UseBasicParsing -TimeoutSec 10).StatusCode -eq 200) } catch { $ok = $false }
        $sonuc += [pscustomobject]@{ Adres = $a; Ok = $ok }
    }
    return $sonuc
}

New-Item -ItemType Directory -Force -Path $Calisma | Out-Null
Set-Content -Path $Rapor -Value "TAMLIFE prod guncelleme - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $env:USERNAME" -Encoding ASCII
Write-Host '========================================================' -ForegroundColor Cyan
Write-Host ' TAMLIFE - Citrix gelistirmesini PRODa alma' -ForegroundColor Cyan
Write-Host " Paket : $Kaynak" -ForegroundColor Cyan
Write-Host " Prod  : $Proje" -ForegroundColor Cyan
Write-Host '========================================================' -ForegroundColor Cyan

# --- 1) Paket ---------------------------------------------------------------------------------------------------------------
Adim '1/5 Paket aliniyor ve dogrulaniyor'
if (-not (Test-Path (Join-Path $Kaynak 'manifest.json'))) { Dur "Paket bulunamadi: $Kaynak\manifest.json (Citrix'te PRODA_GONDER.bat calistirildi mi? Uzak masaustunde surucu paylasimi acik mi?)" }
$s = Start-Process -FilePath 'robocopy.exe' -ArgumentList "`"$Kaynak`" `"$Calisma\paket`" kod.bundle python_venv.zip node_modules.zip manifest.json /R:5 /W:10 /NP /NFL /NDL" -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$Calisma\robocopy.txt"
if ($s.ExitCode -ge 8) { Dur "Paket kopyalanamadi (robocopy $($s.ExitCode))." }
$m = Get-Content (Join-Path $Calisma 'paket\manifest.json') -Raw | ConvertFrom-Json
foreach ($d in 'kod.bundle', 'python_venv.zip', 'node_modules.zip') {
    $h = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Calisma "paket\$d")).Hash
    if ($h -ne $m.dosyalar.$d) { Dur "$d aktarimda bozulmus (SHA-256 tutmuyor). Citrix'te paketi yeniden olusturun." }
}
Tamam "paket dogrulandi: $($m.dal) / $($m.ozet) ($($m.olusturma), $($m.kullanici)@$($m.makine), testler: $($m.testler))"

# --- 2) Kod incelemesi --------------------------------------------------------------------------------------------------------
Adim '2/5 Degisiklikler inceleniyor'
$bundle = Join-Path $Calisma 'paket\kod.bundle'
G bundle verify $bundle | Out-Null
G fetch --quiet $bundle "+refs/heads/$($m.dal):refs/citrix/$($m.dal)" | Out-Null
$yeni = $m.commit
if ((G rev-parse "refs/citrix/$($m.dal)").Trim() -ne $yeni) { Dur 'Paketteki dal manifestteki commit ile ayni degil.' }
$eski = (G rev-parse HEAD).Trim()
if ($eski -eq $yeni) { Tamam 'Prod zaten bu commit''te; kod degisikligi yok.' }
$onde = $true
try { G merge-base --is-ancestor $eski $yeni | Out-Null } catch { $onde = $false }
if (-not $onde) {
    $fazla = G log --oneline "$yeni..$eski"
    $fazla | ForEach-Object { Write-Host "    $_" }
    Dur "Prod'da Citrix'te OLMAYAN commit(ler) var (yukarida). 1:1 icin once bunlari Citrix'e alin; prod'da gelistirme yapilmamali."
}
$kirli = @(G status --porcelain --untracked-files=no)
if ($kirli.Count -gt 0) {
    $kirli | ForEach-Object { Write-Host "    $_" }
    G diff HEAD | Set-Content -Path (Join-Path $Calisma 'prod_yerel_degisiklikler.patch') -Encoding UTF8
    Uyari "Prod'da commit edilmemis $($kirli.Count) dosya degisikligi var; uygulamada SILINECEK (yedek: $Calisma\prod_yerel_degisiklikler.patch)."
}
$commitler = @(G log --oneline "$eski..$yeni")
$dosyalar = @(G diff --stat --stat-width=110 $eski $yeni)
$goc = @(G diff --name-only --diff-filter=A $eski $yeni -- backend/alembic/versions | Where-Object { $_ -like '*.py' })
Write-Host "  Gelen commit ($($commitler.Count)):"; $commitler | Select-Object -First 30 | ForEach-Object { Write-Host "    $_" }
if ($dosyalar.Count) { Write-Host "  $($dosyalar[-1])" }
Add-Content -Path $Rapor -Value ($commitler + $dosyalar) -Encoding UTF8
if ($goc.Count) { Uyari "Yeni veritabani gocu ($($goc.Count)): $($goc -join ', ') - panel baslarken uygulanir; oncesinde yedek alinir." } else { Tamam 'veritabani gocu yok' }
# Paketler
$ErrorActionPreference = 'Continue'
$prodFreeze = @(& $Py -m pip freeze --disable-pip-version-check 2>$null)
$prodPy = (& $Py -c "import sys; print(sys.version.split()[0])" 2>$null)
$ErrorActionPreference = 'Stop'
$pyFarkli = ((Parmak-Izi $prodFreeze) -ne $m.pip_freeze)
$kilit = Join-Path $Proje 'ekran-react\package-lock.json'
$nodeFarkli = ((Get-FileHash -Algorithm SHA256 -LiteralPath $kilit).Hash -ne $m.package_lock)
if ($pyFarkli) {
    if ("$prodPy".Trim() -ne $m.python) { Dur "Python surumu farkli (prod $prodPy, Citrix $($m.python)); .venv tasinamaz. Ayni surumu kullanin." }
    Uyari 'Python paketleri degismis: .venv paketten guncellenecek'
} else { Tamam 'Python paketleri ayni' }
if ($nodeFarkli) { Uyari 'Arayuz paketleri (package-lock) degismis: node_modules paketten guncellenecek' } else { Tamam 'arayuz paketleri ayni' }

# --- 3) Aday testi (canli klasorun disinda) -----------------------------------------------------------------------------------
Adim '3/5 Yeni surum ayri kopyada test ediliyor (~10 dk; canli sistem etkilenmez)'
G worktree add --detach $Aday $yeni | Out-Null
if ($pyFarkli) { Ac (Join-Path $Calisma 'paket\python_venv.zip') "$Calisma\venv"; New-Item -ItemType Junction -Path "$Aday\.venv" -Target "$Calisma\venv" | Out-Null }
else { New-Item -ItemType Junction -Path "$Aday\.venv" -Target (Join-Path $Proje '.venv') | Out-Null }
if ($nodeFarkli) { Ac (Join-Path $Calisma 'paket\node_modules.zip') "$Calisma\node_modules"; New-Item -ItemType Junction -Path "$Aday\ekran-react\node_modules" -Target "$Calisma\node_modules" | Out-Null }
else { New-Item -ItemType Junction -Path "$Aday\ekran-react\node_modules" -Target (Join-Path $Proje 'ekran-react\node_modules') | Out-Null }
if (Test-Path (Join-Path $Proje 'ceviri_modeli')) { New-Item -ItemType Junction -Path "$Aday\ceviri_modeli" -Target (Join-Path $Proje 'ceviri_modeli') | Out-Null }
$adayPy = Join-Path $Aday '.venv\Scripts\python.exe'
$f = Join-Path $Calisma 'aday_ruff.txt'
if ((Calistir "$Aday\backend" $adayPy '-m ruff check app tests' $f) -ne 0) { Dur "Kod denetimi (ruff) basarisiz: $f" }
Write-Host '  ... arka uc testleri' -ForegroundColor DarkGray
$f = Join-Path $Calisma 'aday_pytest.txt'
if ((Calistir "$Aday\backend" $adayPy '-m pytest -q -p no:cacheprovider' $f) -ne 0) {
    Get-Content $f | Select-String '^(FAILED|ERROR) ' | Select-Object -First 10 | ForEach-Object { Write-Host "    $($_.Line)" }
    Dur "Arka uc testleri basarisiz: $f"
}
Tamam ((Get-Content $f | Select-String '(passed|failed)' | Select-Object -Last 1).Line)
Write-Host '  ... arayuz denetimleri' -ForegroundColor DarkGray
foreach ($k in @(@('npx.cmd', 'tsc -b', 'aday_tsc.txt'), @('npm.cmd', 'run lint', 'aday_lint.txt'), @('npx.cmd', 'vitest run', 'aday_vitest.txt'),
                 @('npx.cmd', "vite build --outDir `"$Calisma\dist_deneme`" --emptyOutDir", 'aday_derleme.txt'))) {
    $f = Join-Path $Calisma $k[2]
    if ((Calistir "$Aday\ekran-react" $k[0] $k[1] $f) -ne 0) { Dur "Arayuz denetimi basarisiz ($($k[1])): $f" }
}
Tamam 'tip denetimi, lint, arayuz testleri ve derleme gecti'
Temizle

if ($YalnizDene) { Write-Host ''; Write-Host "DENEME BITTI: yeni surum uygulanabilir. Hicbir sey degismedi. Rapor: $Rapor" -ForegroundColor Green; exit 0 }

# --- 4) Onay ve uygulama ---------------------------------------------------------------------------------------------------
Adim '4/5 Uygulama'
Write-Host "  Prod $($eski.Substring(0, 7)) -> $($yeni.Substring(0, 7)) ($($commitler.Count) commit)." -ForegroundColor Cyan
Write-Host '  Uygularken: veritabani yedegi alinir, panel 2-3 dakika kapali kalir (kullanicilar yeniden giris yapar).'
$c = ''
while ($c -notin @('E', 'H')) { $c = (Read-Host '  Uygulayayim mi? [E/H]').Trim().ToUpper() }
if ($c -ne 'E') { Write-Host '  Uygulanmadi; prod degismedi.' -ForegroundColor Yellow; Read-Host 'Kapatmak icin Enter'; exit 0 }
if ($pyFarkli -and -not (Test-Path "$Calisma\venv")) { Ac (Join-Path $Calisma 'paket\python_venv.zip') "$Calisma\venv" }
if ($nodeFarkli -and -not (Test-Path "$Calisma\node_modules")) { Ac (Join-Path $Calisma 'paket\node_modules.zip') "$Calisma\node_modules" }
$sonuc = Join-Path $Calisma 'uygula_sonuc.json'
$arg = "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\prod_uygula.ps1`" -Commit $yeni -Dal $($m.dal) -Sonuc `"$sonuc`""
if ($pyFarkli) { $arg += " -VenvDizin `"$Calisma\venv`"" }
if ($nodeFarkli) { $arg += " -NodeDizin `"$Calisma\node_modules`"" }
Write-Host '  Windows onay penceresinde "Evet" deyin (yonetici yetkisi).' -ForegroundColor Cyan
try { Start-Process -FilePath 'powershell.exe' -ArgumentList $arg -Verb RunAs -Wait } catch { Dur 'Yonetici onayi verilmedi; uygulanmadi.' }
$u = if (Test-Path $sonuc) { Get-Content $sonuc -Raw | ConvertFrom-Json } else { $null }
if ($null -eq $u) { Dur 'Uygulama sonucu okunamadi.' }

# --- 5) Denetim ve gerekirse geri alma ------------------------------------------------------------------------------------
Adim '5/5 Denetim'
$sorun = @()
if (-not $u.basari) { $sorun += "uygulama: $($u.adim): $($u.hata)" }
foreach ($x in (Saglik)) { if ($x.Ok) { Tamam "$($x.Adres) yanit veriyor" } else { $sorun += "$($x.Adres) yanit vermiyor" } }
$f = Join-Path $Calisma 'saglik_sonrasi.txt'
[void](Calistir (Join-Path $Proje 'backend') $Py 'araclar\panel_saglik.py' $f)
foreach ($satir in (Get-Content $f -Encoding UTF8)) {
    $p = $satir -split '\|', 3
    if ($p.Count -eq 3) { if ($p[0] -eq 'HATA') { $sorun += "$($p[1]): $($p[2])" } elseif ($p[0] -eq 'TAMAM') { Tamam $p[1] } else { Uyari "$($p[1]): $($p[2])" } }
}
if ($sorun.Count -eq 0) {
    Write-Host ''
    Write-Host "BITTI: prod $($yeni.Substring(0, 7)) surumunde ve calisiyor. Yedek: $($u.yedek)" -ForegroundColor Green
    Write-Host "Rapor: $Rapor"
    Read-Host 'Kapatmak icin Enter'
    exit 0
}
$sorun | ForEach-Object { Write-Host "  [HATA] $_" -ForegroundColor Red; Add-Content -Path $Rapor -Value "[HATA] $_" -Encoding UTF8 }
Write-Host ''
Write-Host "  Geri alma: kod $($eski.Substring(0, 7)) surumune doner$(if ($goc.Count) { '; yeni veritabani gocu oldugu icin veritabani da guncelleme oncesi yedekten geri yazilir (aradaki birkac dakikanin verisi gider)' })." -ForegroundColor Yellow
$c = ''
while ($c -notin @('E', 'H')) { $c = (Read-Host '  Geri alayim mi? [E/H]').Trim().ToUpper() }
if ($c -eq 'E') {
    $sonuc2 = Join-Path $Calisma 'geri_al_sonuc.json'
    $dal = (G rev-parse --abbrev-ref HEAD).Trim()
    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\prod_uygula.ps1`" -Commit $eski -Dal $dal -Sonuc `"$sonuc2`" -YedekYok"
    if ($goc.Count -and $u.yedek) { $arg += " -DbGeriYukle `"$($u.yedek)`"" }
    if ($pyFarkli) { Uyari '.venv da degismisti: geri almada eski paketler icin onceki paketi yeniden uygulayin ya da gelistiriciye haber verin.' }
    try { Start-Process -FilePath 'powershell.exe' -ArgumentList $arg -Verb RunAs -Wait } catch { Write-Host '  Onay verilmedi; geri alinmadi.' -ForegroundColor Red }
    $g = if (Test-Path $sonuc2) { Get-Content $sonuc2 -Raw | ConvertFrom-Json } else { $null }
    if ($g -and $g.basari) { Write-Host "  Geri alindi: prod $($eski.Substring(0, 7)) surumunde." -ForegroundColor Green } else { Write-Host "  Geri alma tamamlanamadi: $($g.hata)" -ForegroundColor Red }
}
Write-Host "Rapor: $Rapor"
Read-Host 'Kapatmak icin Enter'
exit 1
