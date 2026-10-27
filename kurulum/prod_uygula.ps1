# TAMLIFE - PROD'a uygulama (saf ASCII; PS 5.1; YONETICI). Yalniz kurulum\prod_guncelle.ps1 cagirir (Windows onay penceresiyle).
# Sira: veritabani yedegi -> panel / vekil / ReportDB iscisi durdurulur -> kod commit'e BIREBIR gecer (git checkout -B + reset --hard;
# git disi dosyalar: .env, veritabani, gunlukler, ceviri_modeli korunur) -> gerekiyorsa .venv / node_modules paketten aynalanir ->
# arayuz derlenir (dist git'te yok) -> gorevler baslar (panel acilista alembic upgrade head uygular) -> sonuc dosyasi.
# Geri alma (-DbGeriYukle): veritabani yedekten geri yazilir (eski WAL/SHM silinir), kod eski commit'e doner, ayni adimlar.
param(
    [Parameter(Mandatory)][string]$Commit,
    [Parameter(Mandatory)][string]$Dal,
    [Parameter(Mandatory)][string]$Sonuc,      # JSON: sonuc ve ayrintilar (cagiran okur)
    [string]$VenvDizin = '',                   # dolu ise .venv bu acilmis klasorden aynalanir
    [string]$NodeDizin = '',                   # dolu ise ekran-react\node_modules bu klasorden aynalanir
    [string]$DbGeriYukle = '',                 # geri alma: bu yedek dev.db'ye yazilir
    [switch]$YedekYok                          # geri almada yeni yedek alinmaz
)
$ErrorActionPreference = 'Stop'
$Proje = Split-Path $PSScriptRoot -Parent
$Py = Join-Path $Proje '.venv\Scripts\python.exe'
$Gorev = Join-Path $PSScriptRoot 'canli_gorev_kur.ps1'
$Gunluk = [IO.Path]::ChangeExtension($Sonuc, '.log')
$durduruldu = $false
$durum = [ordered]@{ basari = $false; adim = ''; hata = ''; yedek = ''; onceki_commit = ''; commit = $Commit }

function Yaz($m, $renk = 'Gray') { Write-Host $m -ForegroundColor $renk; Add-Content -Path $Gunluk -Value "$(Get-Date -Format 'HH:mm:ss') $m" -Encoding ASCII }
function Kaydet { $durum | ConvertTo-Json | Set-Content -Path $Sonuc -Encoding ASCII }
function Komut($dizin, $program, $argumanlar) {
    # yerel program: cikti gunluge, cikis kodu doner (PS 5.1 stderr tuzagi yok)
    $f = "$Gunluk.komut"
    $s = Start-Process -FilePath $program -ArgumentList $argumanlar -WorkingDirectory $dizin -NoNewWindow -Wait -PassThru -RedirectStandardOutput $f -RedirectStandardError "$f.err"
    foreach ($x in $f, "$f.err") { if (Test-Path $x) { Get-Content $x | Add-Content -Path $Gunluk; Remove-Item $x -Force } }
    return $s.ExitCode
}
function Adim($ad) { $durum.adim = $ad; Kaydet; Yaz "--- $ad" 'Cyan' }

try {
    $yonetici = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $yonetici) { throw 'Yonetici yetkisi gerekli.' }
    $durum.onceki_commit = (& git -C $Proje rev-parse HEAD).Trim()

    if (-not $YedekYok) {
        Adim 'Veritabani yedegi'
        if ((Komut (Join-Path $Proje 'backend') $Py 'araclar\db_yedek.py prod_guncelleme') -ne 0) { throw 'Veritabani yedegi alinamadi; hicbir sey degismedi.' }
        $durum.yedek = (Get-Content $Gunluk | Where-Object { $_ -match 'tamlife_.*\.db$' } | Select-Object -Last 1)
        Yaz "  yedek: $($durum.yedek)" 'Green'
    }

    Adim 'Panel, vekil ve ReportDB iscisi durduruluyor'
    $durduruldu = $true
    if ((Komut $Proje 'powershell.exe' "-NoProfile -ExecutionPolicy Bypass -File `"$Gorev`" -Durdur") -ne 0) { throw 'Panel durdurulamadi.' }

    if ($DbGeriYukle) {
        Adim 'Veritabani yedekten geri yaziliyor'
        if (-not (Test-Path $DbGeriYukle)) { throw "Yedek yok: $DbGeriYukle" }
        $db = Join-Path $Proje 'backend\var\dev.db'
        foreach ($ek in '-wal', '-shm') { Remove-Item -LiteralPath "$db$ek" -Force -ErrorAction SilentlyContinue }
        Copy-Item -LiteralPath $DbGeriYukle -Destination $db -Force
    }

    Adim "Kod $($Commit.Substring(0, 7)) commit'ine geciriliyor"
    if ((Komut $Proje 'git' "checkout -f -B $Dal $Commit") -ne 0) { throw 'git checkout basarisiz.' }
    if ((Komut $Proje 'git' "reset --hard $Commit") -ne 0) { throw 'git reset basarisiz.' }
    $simdi = (& git -C $Proje rev-parse HEAD).Trim()
    if ($simdi -ne $Commit) { throw "Kod beklenen commit'te degil ($simdi)." }

    if ($VenvDizin) {
        Adim 'Python paketleri (.venv) guncelleniyor'
        # pyvenv.cfg aynalanmaz: Citrix'in Python yolunu (kullanici klasoru) tasir; prod kendi C:\Program Files\Python314 yolunu korur
        $k = Komut $Proje 'robocopy.exe' "`"$VenvDizin`" `"$Proje\.venv`" /MIR /XF pyvenv.cfg /R:3 /W:3 /NP /NFL /NDL"
        if ($k -ge 8) { throw ".venv aynalanamadi (robocopy $k)." }
    }
    if ($NodeDizin) {
        Adim 'Arayuz paketleri (node_modules) guncelleniyor'
        $k = Komut $Proje 'robocopy.exe' "`"$NodeDizin`" `"$Proje\ekran-react\node_modules`" /MIR /R:3 /W:3 /NP /NFL /NDL"
        if ($k -ge 8) { throw "node_modules aynalanamadi (robocopy $k)." }
    }

    Adim 'Arayuz derleniyor'
    if ((Komut (Join-Path $Proje 'ekran-react') 'npm.cmd' 'run build') -ne 0) { throw 'Arayuz derlenemedi (npm run build).' }

    Adim 'Gorevler koddaki tanimla yeniden kaydediliyor'
    # 1:1: gorev ayarlari da (tetikler, bekci) gelen koddaki canli_gorev_kur.ps1'den; parola sorulmaz (parolasiz kip)
    if ((Komut $Proje 'powershell.exe' "-NoProfile -ExecutionPolicy Bypass -File `"$Gorev`"") -ne 0) { throw 'Gorevler kaydedilemedi.' }

    Adim 'Panel, vekil ve ReportDB iscisi baslatiliyor (veritabani semasi otomatik guncellenir)'
    $k = Komut $Proje 'powershell.exe' "-NoProfile -ExecutionPolicy Bypass -File `"$Gorev`" -YenidenBaslat"
    $durduruldu = $false
    if ($k -ne 0) { throw "Panel yeniden baslatilamadi (kod $k); ayrinti gunlukte." }
    $durum.basari = $true
    $durum.adim = 'bitti'
    Yaz 'TAMAM: uygulandi ve panel calisiyor.' 'Green'
} catch {
    $durum.hata = "$($_.Exception.Message)"
    Yaz "HATA ($($durum.adim)): $($durum.hata)" 'Red'
    if ($durduruldu) {
        # Panel kapali kalmasin: hangi kod varsa onunla yeniden baslatilir; geri almayi prod_guncelle.ps1 onerir.
        Yaz 'Panel kapali kalmasin diye yeniden baslatiliyor...' 'Yellow'
        [void](Komut $Proje 'powershell.exe' "-NoProfile -ExecutionPolicy Bypass -File `"$Gorev`" -YenidenBaslat")
    }
} finally {
    Kaydet
}
Start-Sleep -Seconds 3
exit $(if ($durum.basari) { 0 } else { 1 })
