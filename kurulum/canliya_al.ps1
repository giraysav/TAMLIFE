# TAMLIFE - GitHub'daki etiketli surumu canliya alir (saf ASCII; PS 5.1). 2026-11-25 kullanici karari:
#   "gelistirmeleri D:'de yapip testler gecince GitHub'a gonderip, sunucudaki oturumda degisimi kontrol edip uygulayacagiz".
# Kaynak tek: github.com/giraysav/TAMLIFE, dal main, etiket canli-YYYYMMDD-N. Sunucuda kod DUZENLENMEZ, derleme YAPILMAZ
# (ekran-react\dist gelistirmede derlenip git'e girer; sunucuda Node gerekmez).
#
# Kullanim (sunucuda, TURKCELL\TAMLIFEADLOG ile YONETICI PowerShell):
#   .\kurulum\canliya_al.ps1 -Etiket canli-20261126-1 -YalnizDene   : yalniz kontrol + ne gelecegini gosterir; HICBIR SEY degismez
#   .\kurulum\canliya_al.ps1 -Etiket canli-20261126-1               : kontrol, ozet, onay [E/H], uygulama, dogrulama
#   .\kurulum\canliya_al.ps1 -Etiket canli-20261125-1 -GeriAl       : eski bir etikete bilerek donus (geri sarma izni)
#   -Evet : onay sorulmaz (yalniz kontrolu goren oturum kullanir)
#   -Kok  : canli klasor (varsayilan: bu betigin bir ustu). ILK KEZ (betik sunucuda henuz yokken) GitHub'dan alinip gecici klasorden:
#     git -C E:\TAMLIFE fetch --tags origin; git -C E:\TAMLIFE show canli-YYYYMMDD-N:kurulum/canliya_al.ps1 | Out-File $env:TEMP\canliya_al.ps1 -Encoding ascii
#     & $env:TEMP\canliya_al.ps1 -Kok E:\TAMLIFE -Etiket canli-YYYYMMDD-N -YalnizDene
# Adimlar: 1 on kontrol (yonetici, kimlik, temiz agac, origin = GitHub)  2 fetch + hedef cozumleme (etiket main'de olmali)
#   3 yon kontrolu (yalniz ileri; sunucuda GitHub'da olmayan commit varsa DURUR)  4 gelen degisiklik ozeti
#   5 DB yedegi (backend\araclar\db_yedek.py -> backend\var\yedek)  6 durdur (canli_gorev_kur -Durdur)  7 git checkout -B canli <hedef>
#   8 requirements.txt degistiyse pip install  9 baslat (canli_gorev_kur -YenidenBaslat; panel acilisinda alembic upgrade head)
#   10 dogrulama: HEAD = hedef, 127.0.0.1 ve https saglik 200, sunulan index.html = git'teki dist\index.html
#   Basarisizsa ONCEKI commit'e otomatik donulur (ayni adimlarla). Yeni DB gocu calistiysa yedek elle geri yazilir (mesajda yazar).
# Kayit: var\log\canliya_al\<zaman>.txt (tam cikti) ve var\log\canliya_al\gecmis.csv (her calisma bir satir).
# Cikis: 0 uygulandi ve dogrulandi, 10 degisiklik yok (zaten bu surum), 1 uygulanmadi (canli degismedi),
#        3 dogrulanamadi ve onceki surume donuldu, 4 dogrulanamadi ve geri donus de basarisiz (ELLE MUDAHALE).
param(
    [Parameter(Mandatory = $true)][string]$Etiket,
    [switch]$YalnizDene,
    [switch]$GeriAl,
    [switch]$Evet,
    [string]$Kok = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$Kok = (Resolve-Path $Kok).Path
$GitHubAdresi = 'https://github.com/giraysav/TAMLIFE.git'
$Py = Join-Path $Kok '.venv\Scripts\python.exe'
$GorevBetigi = Join-Path $Kok 'kurulum\canli_gorev_kur.ps1'
$Zaman = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogKlasoru = Join-Path $Kok 'var\log\canliya_al'
New-Item -ItemType Directory -Force -Path $LogKlasoru | Out-Null
$Log = Join-Path $LogKlasoru "$Zaman.txt"
$Gecmis = Join-Path $LogKlasoru 'gecmis.csv'
$script:Eski = $null
$script:Hedef = $null

function Adim-Yaz($m) { Write-Host ''; Write-Host "=== $m ===" -ForegroundColor Cyan }
function Tamam-Yaz($m) { Write-Host "  [TAMAM] $m" -ForegroundColor Green }
function Uyari-Yaz($m) { Write-Host "  [UYARI] $m" -ForegroundColor Yellow }
function Gecmis-Yaz($sonuc) {
    $kim = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    if (-not (Test-Path $Gecmis)) { Add-Content -Path $Gecmis -Value 'zaman;kullanici;etiket;onceki;hedef;sonuc' -Encoding ASCII }
    Add-Content -Path $Gecmis -Value "$Zaman;$kim;$Etiket;$($script:Eski);$($script:Hedef);$sonuc" -Encoding ASCII
}
function Bitir($kod, $sonuc) {
    Gecmis-Yaz $sonuc
    Write-Host ''
    Write-Host "Sonuc: $sonuc (cikis $kod). Gunluk: $Log"
    try { Stop-Transcript | Out-Null } catch { }
    exit $kod
}
function Hata-Dur($m) {
    Write-Host "  [HATA] $m" -ForegroundColor Red
    Write-Host '  Canli sisteme DOKUNULMADI.' -ForegroundColor Red
    Bitir 1 "uygulanmadi: $m"
}
function Git-Komut {
    # PS 5.1: Stop altinda git'in stderr bilgi satirlari hata sayilmasin; cikis koduna bakilir.
    $onceki = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $c = & git -C $Kok @args 2>&1 | ForEach-Object { "$_" }
    $kod = $LASTEXITCODE; $ErrorActionPreference = $onceki
    if ($kod -ne 0) { throw "git $($args -join ' ') (kod $kod): $($c -join ' ')" }
    return $c
}
function Git-Dogru {
    # cikis kodu 0 ise $true (merge-base --is-ancestor, cat-file -e gibi evet/hayir sorulari)
    $onceki = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & git -C $Kok @args 2>&1 | Out-Null
    $kod = $LASTEXITCODE; $ErrorActionPreference = $onceki
    return ($kod -eq 0)
}
function Gorev-Calistir($kip) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $GorevBetigi $kip
    return $LASTEXITCODE
}
function Saglik-Bekle($adres, $sn) {
    for ($i = 0; $i -lt $sn; $i += 3) {
        try { if ((Invoke-WebRequest -Uri $adres -UseBasicParsing -TimeoutSec 10).StatusCode -eq 200) { return $true } } catch { }
        Start-Sleep -Seconds 3
    }
    return $false
}
function Paket-Kur {
    Adim-Yaz 'Python paketleri (requirements.txt degisti)'
    $onceki = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $Py -m pip install --disable-pip-version-check -q -r (Join-Path $Kok 'requirements.txt') 2>&1 | ForEach-Object { "    $_" }
    $kod = $LASTEXITCODE; $ErrorActionPreference = $onceki
    return ($kod -eq 0)
}
function Surume-Gec($commit, $paketDegisti) {
    # durdur -> checkout -> (paket) -> baslat. Basarili baslatma $true.
    Adim-Yaz "Panel durduruluyor (canli_gorev_kur -Durdur)"
    if ((Gorev-Calistir '-Durdur') -ne 0) { Uyari-Yaz 'Durdurma tam olmadi; yine de devam ediliyor (port birakilmadiysa baslatma bunu gosterir).' }
    Adim-Yaz "Kod $($commit.Substring(0, 7)) surumune geciriliyor"
    Git-Komut checkout -q -B canli $commit | Out-Null
    Tamam-Yaz "HEAD = $((Git-Komut rev-parse HEAD) | Select-Object -First 1)"
    if ($paketDegisti -and -not (Paket-Kur)) { Uyari-Yaz 'pip install basarisiz.'; return $false }
    Adim-Yaz 'Panel baslatiliyor (canli_gorev_kur -YenidenBaslat; acilista alembic upgrade head)'
    $kod = Gorev-Calistir '-YenidenBaslat'
    if ($kod -eq 2) { Uyari-Yaz 'Panel acik ama zamanlanmis gorevlerle degil (kod 2): sunucu yeniden baslayinca kapanir. Sonra: canli_gorev_kur.ps1 -Hemen' }
    return ($kod -eq 0 -or $kod -eq 2)
}
function Dogrula($commit) {
    Adim-Yaz 'Dogrulama'
    $sorun = @()
    $head = (Git-Komut rev-parse HEAD) | Select-Object -First 1
    if ($head -ne $commit) { $sorun += "HEAD $head, beklenen $commit" } else { Tamam-Yaz 'Kod = hedef commit' }
    if (Saglik-Bekle 'http://127.0.0.1:8117/api/v1/health' 120) { Tamam-Yaz 'Panel 127.0.0.1:8117 saglik 200' } else { $sorun += 'panel saglik ucu yanit vermiyor' }
    if (Saglik-Bekle 'https://tamlife/api/v1/health' 60) { Tamam-Yaz 'https://tamlife saglik 200' } else { $sorun += 'https://tamlife saglik ucu yanit vermiyor' }
    try {
        $beklenen = [regex]::Match((Get-Content -Raw (Join-Path $Kok 'ekran-react\dist\index.html')), 'assets/index-[A-Za-z0-9_-]+\.js').Value
        $sunulan = [regex]::Match((Invoke-WebRequest -Uri 'http://127.0.0.1:8117/' -UseBasicParsing -TimeoutSec 10).Content, 'assets/index-[A-Za-z0-9_-]+\.js').Value
        if ($beklenen -and $beklenen -eq $sunulan) { Tamam-Yaz "Arayuz: sunulan $sunulan = git'teki dist" } else { $sorun += "arayuz: sunulan '$sunulan', beklenen '$beklenen'" }
    } catch { $sorun += "arayuz denetlenemedi: $($_.Exception.Message)" }
    foreach ($s in $sorun) { Write-Host "  [HATA] $s" -ForegroundColor Red }
    return ($sorun.Count -eq 0)
}

Start-Transcript -Path $Log -Append | Out-Null
Write-Host '========================================================' -ForegroundColor Cyan
Write-Host " TAMLIFE - canliya alma: $Etiket $(if ($YalnizDene) { '(YALNIZ DENE)' })" -ForegroundColor Cyan
Write-Host " Klasor: $Kok" -ForegroundColor Cyan
Write-Host '========================================================' -ForegroundColor Cyan

# --- 1 On kontrol -----------------------------------------------------------------------------------------------------------------
Adim-Yaz '1 On kontrol'
$yonetici = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $YalnizDene -and -not $yonetici) { Hata-Dur 'Yonetici PowerShell gerekli (gorevler durdurulup baslatiliyor).' }
. (Join-Path $Kok 'kurulum\calisma_kimligi.ps1')
if (-not $YalnizDene) { try { Tamlife-KimlikDogrula } catch { Hata-Dur $_.Exception.Message } }
if ($Etiket -notmatch '^canli-\d{8}-\d+$') { Hata-Dur "Etiket bicimi canli-YYYYMMDD-N olmali (verilen: $Etiket)." }
if (-not (Git-Dogru rev-parse --is-inside-work-tree)) { Hata-Dur "$Kok bir git calisma kopyasi degil." }
$origin = (Git-Komut remote get-url origin) | Select-Object -First 1
if ($origin -ne $GitHubAdresi) {
    Hata-Dur "origin GitHub degil ($origin). Bir kez su komutu calistirin: git -C `"$Kok`" remote set-url origin $GitHubAdresi"
}
$kirli = Git-Komut status --porcelain --untracked-files=normal
if ($kirli) {
    $kirli | Select-Object -First 20 | ForEach-Object { Write-Host "    $_" }
    Hata-Dur 'Calisma agaci temiz degil: sunucuda git disi degisiklik var. Kod sunucuda duzenlenmez; once bu farki gelistirmeye (D:) alin.'
}
Tamam-Yaz 'Yonetici, kimlik, git, origin = GitHub, agac temiz'

# --- 2 Fetch + hedef ---------------------------------------------------------------------------------------------------------------
Adim-Yaz '2 GitHub''dan cekiliyor'
Git-Komut fetch --prune --tags origin | Out-Null
if (-not (Git-Dogru rev-parse -q --verify "refs/tags/$Etiket")) { Hata-Dur "Etiket GitHub'da yok: $Etiket" }
$script:Hedef = (Git-Komut rev-parse "$Etiket^{commit}") | Select-Object -First 1
$script:Eski = (Git-Komut rev-parse HEAD) | Select-Object -First 1
if (-not (Git-Dogru merge-base --is-ancestor $script:Hedef origin/main)) { Hata-Dur "Etiket $Etiket main dalinda degil: yalniz main'den etiketlenen surum canliya alinir." }
if (-not (Git-Dogru cat-file -e "$($script:Hedef):ekran-react/dist/index.html")) { Hata-Dur 'Hedef surumde ekran-react/dist/index.html yok (arayuz derlemesi git''e girmemis).' }
Tamam-Yaz "Hedef $Etiket = $($script:Hedef.Substring(0, 7)); canlidaki = $($script:Eski.Substring(0, 7))"
if ($script:Hedef -eq $script:Eski) { Tamam-Yaz 'Canli zaten bu surumde; yapilacak bir sey yok.'; Bitir 10 'degisiklik yok' }

# --- 3 Yon ------------------------------------------------------------------------------------------------------------------------
Adim-Yaz '3 Yon kontrolu'
$ileri = Git-Dogru merge-base --is-ancestor $script:Eski $script:Hedef
$geri = Git-Dogru merge-base --is-ancestor $script:Hedef $script:Eski
if ($ileri) { Tamam-Yaz 'Ileri sarma: canlidaki her commit hedefte de var.' }
elseif ($geri -and $GeriAl) { Uyari-Yaz 'GERI DONUS: hedef, canlidaki surumden eski (-GeriAl verildi).' }
elseif ($geri) { Hata-Dur 'Hedef canlidakinden ESKI. Bilerek geri donmek icin -GeriAl ekleyin.' }
else {
    Write-Host '  Sunucuda olup hedefte olmayan commitler:'
    Git-Komut log --oneline "$($script:Hedef)..$($script:Eski)" | Select-Object -First 20 | ForEach-Object { Write-Host "    $_" }
    Hata-Dur 'Gecmis ayrismis: sunucuda GitHub main''de olmayan commit var. Once bunlar main''e alinmali.'
}

# --- 4 Ozet -----------------------------------------------------------------------------------------------------------------------
Adim-Yaz '4 Gelen degisiklik'
$aralik = if ($ileri) { "$($script:Eski)..$($script:Hedef)" } else { "$($script:Hedef)..$($script:Eski)" }
Git-Komut log --format='    %h %ad %s' --date=short $aralik | Select-Object -First 40 | ForEach-Object { Write-Host $_ }
$dosyalar = @(Git-Komut diff --name-only $script:Eski $script:Hedef)
$paketDegisti = [bool]($dosyalar -contains 'requirements.txt')
$gocler = @($dosyalar | Where-Object { $_ -like 'backend/alembic/versions/*' })
$arayuz = @($dosyalar | Where-Object { $_ -like 'ekran-react/dist/*' }).Count
$backend = @($dosyalar | Where-Object { $_ -like 'backend/app/*' }).Count
$kurulum = @($dosyalar | Where-Object { $_ -like 'kurulum/*' })
Write-Host ''
Write-Host "  Degisen dosya: $($dosyalar.Count)  (backend/app: $backend, arayuz dist: $arayuz, kurulum: $($kurulum.Count))"
Write-Host "  Python paketleri: $(if ($paketDegisti) { 'DEGISTI (pip install yapilacak)' } else { 'ayni' })"
Write-Host "  Veritabani gocleri: $(if ($gocler.Count) { ($gocler -join ', ') } else { 'yok' })"
if ($kurulum) { Write-Host "  Kurulum betikleri: $($kurulum -join ', ')" }
if (-not $ileri -and $gocler.Count) { Uyari-Yaz 'Geri donuste goc DOSYASI geri alinir ama sema geri alinmaz (alembic downgrade yapilmaz); eski kod yeni semayla calisir (gocler ekleyici).' }

if ($YalnizDene) { Tamam-Yaz 'YALNIZ DENE: hicbir sey degistirilmedi.'; Bitir 0 'yalniz dene' }
if (-not $Evet) {
    $cevap = Read-Host "`n  $Etiket canliya alinsin mi? Panel kisa sure kapanacak. [E/H]"
    if ($cevap -notmatch '^[Ee]') { Hata-Dur 'Kullanici onaylamadi.' }
}

# --- 5 DB yedegi ------------------------------------------------------------------------------------------------------------------
Adim-Yaz '5 Veritabani yedegi'
$onceki = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
Push-Location (Join-Path $Kok 'backend')
$yedek = & $Py araclar\db_yedek.py "once_$Etiket" 2>&1 | ForEach-Object { "$_" }
$yedekKod = $LASTEXITCODE
Pop-Location
$ErrorActionPreference = $onceki
if ($yedekKod -ne 0) { Hata-Dur "Veritabani yedegi alinamadi: $($yedek -join ' ')" }
$yedekYolu = $yedek | Select-Object -Last 1
Tamam-Yaz "Yedek: $yedekYolu"

# --- 6-9 Uygulama -----------------------------------------------------------------------------------------------------------------
$basladi = Surume-Gec $script:Hedef $paketDegisti
if ($basladi -and (Dogrula $script:Hedef)) {
    Tamam-Yaz "$Etiket canlida ve dogrulandi."
    Bitir 0 'uygulandi'
}

# --- Geri donus -------------------------------------------------------------------------------------------------------------------
Write-Host ''
Write-Host '!!! Yeni surum dogrulanamadi; ONCEKI surume donuluyor !!!' -ForegroundColor Red
$geriOk = (Surume-Gec $script:Eski $paketDegisti) -and (Dogrula $script:Eski)
if ($gocler.Count -and $ileri) {
    Uyari-Yaz "Bu surumde yeni veritabani gocu vardi ($($gocler -join ', ')). Eski kod sorun cikarirsa yedegi geri yazin: $yedekYolu"
    Uyari-Yaz 'Geri yazma: paneli durdurun (canli_gorev_kur.ps1 -Durdur), backend\var\dev.db yerine yedegi koyun (-wal/-shm silinir), -YenidenBaslat.'
}
if ($geriOk) { Bitir 3 'dogrulanamadi, onceki surume donuldu' }
Write-Host 'GERI DONUS DA DOGRULANAMADI: ELLE MUDAHALE GEREKLI (full_reboot / canli_gorev_kur.ps1 -Durum, gunluk: var\log\canli_panel.log).' -ForegroundColor Red
Bitir 4 'dogrulanamadi, geri donus basarisiz'
