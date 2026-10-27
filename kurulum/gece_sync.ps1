# TAMLIFE - gece senkronu (saf ASCII; PS 5.1). Gorev TAMLIFE_v35_Gece_Sync her gun 04:00 calistirir (canli_gorev_kur.ps1 kaydeder).
# Elle (YONETICI): powershell -File kurulum\gece_sync.ps1 [-Dene]
# 2026-10-27 kullanici: "LADIN01 prod ve Citrix dev surekli sync kalsin; her gun 04:00 sync iscisi; isciler isini bitirdikten sonra
# panel restart etsin, panel acilmazsa full_reboot.bat devreye girsin".
# Sira:
#   1 Citrix erisimi: \\tsclient yalniz Citrix'ten LADIN01'e uzak masaustu baglantisi ACIKKEN vardir. Yoksa 2-3 atlanir, 4-6 yine yapilir.
#   2 VERI prod -> Citrix: canli veritabaninin tutarli kopyasi (araclar\db_yedek.py) Citrix'teki TAMLIFE_v3.5\backend\var\dev.db olur.
#     Citrix'in onceki dev.db'si backend\var\yedek\dev_citrix_onceki.db'ye alinir (tek, her gece yenilenir). Citrix paneli aciksa
#     (dosya kilitli) atlanir.
#   3 KOD Citrix -> prod: Citrix'te PRODA_GONDER.bat'in hazirladigi paket prod'dan farkliysa prod_guncelle.ps1 -Otomatik (aday testi,
#     uygulama, canli dogrulama, basarisizsa kendiliginden geri alma). Commit edilip paketlenmemis Citrix gelistirmesi alinmaz.
#   4 Isciler: ReportDB iscisinin turu bitene kadar beklenir (en cok 10 dk).
#   5 Panel yeniden baslatilir (canli_gorev_kur.ps1 -PanelYenile, 120 sn); acilmazsa full_reboot.bat /oto.
#   6 Son denetim (prod_dogrula.ps1). Sorun varsa yoneticiye bildirim: TL-SNC-01 (panel ust cubuk zili + Yonetim > Arizalar).
# Gunluk: var\log\gece_sync\<zaman>.txt ; son sonuc: var\log\gece_sync\son.json. Cikis: 0 tamam, 1 uyari (senkron eksik), 2 hata.
param([switch]$Dene)   # canli sisteme dokunmaz: 2 Citrix'e deneme kopyasi yazip siler, 3 -YalnizDene, 4-5 yapilmaz
$ErrorActionPreference = 'Continue'
$Proje = Split-Path $PSScriptRoot -Parent
$Backend = Join-Path $Proje 'backend'
$Py = Join-Path $Proje '.venv\Scripts\python.exe'
$CitrixMasaustu = '\\tsclient\C\Users\tcgsav\Desktop'
$CitrixProje = Join-Path $CitrixMasaustu 'TAMLIFE\TAMLIFE_v3.5'
$Paket = Join-Path $CitrixMasaustu 'TAMLIFE_GONDER'
$Zaman = Get-Date -Format 'yyyyMMdd-HHmmss'
$GunlukDizini = Join-Path $Proje 'var\log\gece_sync'
$Gunluk = Join-Path $GunlukDizini "$Zaman.txt"
$Calisma = Join-Path (Split-Path (Split-Path $Proje -Parent) -Qualifier) 'TAMLIFE_gelen\gece'   # E:\TAMLIFE_gelen\gece
New-Item -ItemType Directory -Force -Path $GunlukDizini, $Calisma | Out-Null
$baslangic = Get-Date
$sonuc = [ordered]@{ baslangic = $baslangic.ToString('s'); dene = [bool]$Dene; citrix = ''; veri = ''; kod = ''; isci = ''; panel = ''; full_reboot = ''; dogrulama = '' }
$hatalar = @(); $uyarilar = @()

function Yaz($durum, $m) {
    $satir = "$(Get-Date -Format 'HH:mm:ss') [$durum] $m"
    Write-Host $satir
    Add-Content -Path $Gunluk -Value $satir -Encoding UTF8
}
function Adim($m) { Add-Content -Path $Gunluk -Value '' -Encoding UTF8; Yaz '====' $m }
# Alt betik: ciktisi gunluge eklenir, cikis kodu doner. cmd /c ile degil: ayrintidaki '|' cmd'de boru olurdu.
function Alt($dosya, $argumanlar) {
    $f = Join-Path $Calisma "alt_$([IO.Path]::GetFileNameWithoutExtension($dosya)).txt"
    $p = Start-Process -FilePath $dosya -ArgumentList $argumanlar -WorkingDirectory $(if ($dosya -eq $Py) { $Backend } else { $Proje }) -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $f -RedirectStandardError "$f.err"
    foreach ($x in $f, "$f.err") { if (Test-Path $x) { Get-Content $x | ForEach-Object { "    $_" } | Add-Content -Path $Gunluk -Encoding UTF8 } }
    return $p.ExitCode
}
function Ps($betik, $argumanlar) { return (Alt 'powershell.exe' "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\$betik`" $argumanlar") }
function Bitir {
    $sonuc.bitis = (Get-Date).ToString('s')
    $sonuc.hatalar = $hatalar; $sonuc.uyarilar = $uyarilar
    $sonuc.durum = if ($hatalar.Count) { 'HATA' } elseif ($uyarilar.Count) { 'UYARI' } else { 'TAMAM' }
    $sonuc.gunluk = $Gunluk
    $sonuc | ConvertTo-Json -Depth 3 | Set-Content -Path (Join-Path $GunlukDizini 'son.json') -Encoding UTF8
    if (($hatalar.Count -or $uyarilar.Count) -and -not $Dene) {
        # yonetici bildirimi; panel kapaliyken de yazilir (veritabanina dogrudan)
        $ozet = (@($hatalar) + @($uyarilar)) -join ' | '
        $sev = if ($hatalar.Count) { 'error' } else { 'warning' }
        $ayrinti = "gece senkronu $($sonuc.durum): $ozet (gunluk var\log\gece_sync\$Zaman.txt)"
        $kod = Alt $Py "araclar\ariza_bildir.py TL-SNC-01 `"$($ayrinti -replace '"', "'")`" --seviye $sev --kaynak gece_sync"
        Yaz 'BILGI' "yonetici bildirimi (TL-SNC-01) $(if ($kod -eq 0) { 'yazildi' } else { 'YAZILAMADI' })"
    }
    Yaz 'SONUC' "$($sonuc.durum) - $([int]((Get-Date) - $baslangic).TotalMinutes) dk"
    exit $(if ($hatalar.Count) { 2 } elseif ($uyarilar.Count) { 1 } else { 0 })
}

# Ayni anda iki senkron (elle + gorev) calismasin
$kilit = New-Object Threading.Mutex($false, 'Global\TAMLIFE_gece_sync')
if (-not $kilit.WaitOne(0)) { Write-Host 'Baska bir gece senkronu calisiyor; cikiliyor.'; exit 1 }
Set-Content -Path $Gunluk -Value "TAMLIFE gece senkronu - $($baslangic.ToString('yyyy-MM-dd HH:mm:ss')) - $env:USERNAME$(if ($Dene) { ' - DENEME' })" -Encoding UTF8
Set-Location $Proje

# --- 1) Citrix erisimi ------------------------------------------------------------------------------------------------------------
Adim '1/6 Citrix erisimi'
$citrix = Test-Path (Join-Path $CitrixProje '.git')
if ($citrix) { Yaz 'TAMAM' "Citrix erisilebilir: $CitrixProje"; $sonuc.citrix = 'erisilebilir' }
else {
    $sonuc.citrix = 'yok'
    $uyarilar += 'Citrix erisilemedi (uzak masaustu baglantisi / surucu paylasimi kapali); veri ve kod senkronu yapilmadi'
    Yaz 'UYARI' "Citrix erisilemedi ($CitrixProje). Citrix'ten LADIN01'e uzak masaustu baglantisi (surucu paylasimi acik) gece de acik kalmali."
}

# --- 2) Veri prod -> Citrix ------------------------------------------------------------------------------------------------------
Adim '2/6 Veri: prod veritabani -> Citrix'
if (-not $citrix) { $sonuc.veri = 'atlandi (Citrix yok)'; Yaz 'BILGI' 'atlandi' }
else {
    $kopya = Join-Path $Calisma 'dev.db'
    $kod = Alt $Py "araclar\db_yedek.py --hedef `"$kopya`""
    $cVar = Join-Path $CitrixProje 'backend\var'
    $cDb = Join-Path $cVar 'dev.db'
    $kilitli = $false
    if (Test-Path $cDb) {
        try { $fs = [IO.File]::Open($cDb, 'Open', 'ReadWrite', 'None'); $fs.Close() } catch { $kilitli = $true }
    }
    if ($kod -ne 0 -or -not (Test-Path $kopya)) {
        $sonuc.veri = 'kopya alinamadi'; $uyarilar += 'prod veritabaninin kopyasi alinamadi'; Yaz 'UYARI' 'db_yedek.py basarisiz'
    } elseif ($kilitli) {
        $sonuc.veri = 'atlandi (Citrix dev.db kullanimda)'; $uyarilar += "Citrix'te dev.db kullanimda (Citrix paneli acik?); veri senkronu yapilmadi"
        Yaz 'UYARI' "Citrix'teki dev.db kilitli (Citrix'te panel acik kalmis olabilir); atlandi"
    } else {
        $boyut = (Get-Item $kopya).Length
        $hedefAd = if ($Dene) { 'dev.db.deneme' } else { 'dev.db.gelen' }
        $t0 = Get-Date
        New-Item -ItemType Directory -Force -Path $cVar | Out-Null
        try {
            Copy-Item -LiteralPath $kopya -Destination (Join-Path $cVar $hedefAd) -Force -ErrorAction Stop
            $sn = [int]((Get-Date) - $t0).TotalSeconds
            if ((Get-Item (Join-Path $cVar $hedefAd)).Length -ne $boyut) { throw 'kopya boyutu tutmuyor' }
            if ($Dene) {
                Remove-Item -LiteralPath (Join-Path $cVar $hedefAd) -Force
                $sonuc.veri = "deneme: $([int]($boyut / 1MB)) MB $sn sn"; Yaz 'TAMAM' "deneme kopyasi yazildi ve silindi: $([int]($boyut / 1MB)) MB, $sn sn"
            } else {
                # Citrix'in onceki veritabani (ve WAL/SHM'si) yedege; yeni kopya dev.db olur (kopyayla karisan WAL birakilmaz)
                $cYedek = Join-Path $cVar 'yedek'
                New-Item -ItemType Directory -Force -Path $cYedek | Out-Null
                foreach ($ek in '', '-wal', '-shm') {
                    $x = "$cDb$ek"
                    if (Test-Path $x) { Move-Item -LiteralPath $x -Destination (Join-Path $cYedek "dev_citrix_onceki.db$ek") -Force -ErrorAction Stop }
                    elseif (Test-Path (Join-Path $cYedek "dev_citrix_onceki.db$ek")) { Remove-Item (Join-Path $cYedek "dev_citrix_onceki.db$ek") -Force }
                }
                Move-Item -LiteralPath (Join-Path $cVar $hedefAd) -Destination $cDb -ErrorAction Stop
                $sonuc.veri = "aktarildi: $([int]($boyut / 1MB)) MB $sn sn"; Yaz 'TAMAM' "Citrix dev.db prod'un $(Get-Date -Format 'HH:mm') kopyasi oldu ($([int]($boyut / 1MB)) MB, $sn sn; onceki: backend\var\yedek\dev_citrix_onceki.db)"
            }
        } catch {
            $sonuc.veri = "hata: $($_.Exception.Message)"; $uyarilar += "Citrix'e veri aktarilamadi: $($_.Exception.Message)"; Yaz 'UYARI' "aktarilamadi: $($_.Exception.Message)"
            Remove-Item -LiteralPath (Join-Path $cVar $hedefAd) -Force -ErrorAction SilentlyContinue
        }
    }
}

# --- 3) Kod Citrix -> prod -------------------------------------------------------------------------------------------------------
Adim '3/6 Kod: Citrix -> prod'
$prodCommit = (& git -C $Proje rev-parse HEAD 2>$null | Out-String).Trim()
if (-not $citrix) { $sonuc.kod = 'atlandi (Citrix yok)'; Yaz 'BILGI' 'atlandi' }
else {
    $citrixCommit = (& git -C $CitrixProje -c safe.directory=* rev-parse HEAD 2>$null | Out-String).Trim()
    $manifest = Join-Path $Paket 'manifest.json'
    $m = if ((Test-Path $manifest) -and -not (Test-Path (Join-Path $Paket '_hazirlaniyor'))) { Get-Content $manifest -Raw | ConvertFrom-Json } else { $null }
    if ($null -eq $m) {
        $sonuc.kod = 'paket yok'; Yaz 'BILGI' "Citrix'te hazir paket yok ($Paket)"
    } elseif ($m.commit -eq $prodCommit) {
        $sonuc.kod = "guncel ($($prodCommit.Substring(0, 7)))"; Yaz 'TAMAM' "prod paketteki surumde: $($prodCommit.Substring(0, 7))"
    } else {
        Yaz 'BILGI' "paket $($m.commit.Substring(0, 7)) ($($m.olusturma)), prod $($prodCommit.Substring(0, 7)): prod_guncelle.ps1 -Otomatik"
        $kod = Ps 'prod_guncelle.ps1' $(if ($Dene) { '-YalnizDene' } else { '-Otomatik' })
        $aciklama = @{ 0 = 'uygulandi ve dogrulandi'; 10 = 'degisiklik yok'; 1 = 'uygulanmadi (aday testi / denetim; prod degismedi)'; 3 = 'dogrulanamadi, GERI ALINDI'; 4 = 'dogrulanamadi, geri alma TAMAMLANAMADI' }[$kod]
        if (-not $aciklama) { $aciklama = "beklenmeyen cikis $kod" }
        $sonuc.kod = "$($m.commit.Substring(0, 7)): $aciklama"
        if ($kod -in 0, 10) { Yaz 'TAMAM' $aciklama }
        elseif ($kod -eq 1 -or $kod -eq 3) { $uyarilar += "kod senkronu: $aciklama"; Yaz 'UYARI' $aciklama }
        else { $hatalar += "kod senkronu: $aciklama"; Yaz 'HATA' $aciklama }
    }
    if ($citrixCommit -and $m -and $citrixCommit -ne $m.commit) {
        Yaz 'BILGI' "Citrix'te paketlenmemis commit var (Citrix $($citrixCommit.Substring(0, 7)), paket $($m.commit.Substring(0, 7))): gondermek icin Citrix'te PRODA_GONDER.bat"
    }
}

if ($Dene) {
    Adim '4-5/6 Deneme: isci bekleme ve panel yeniden baslatma yapilmadi'
    $sonuc.isci = 'deneme'; $sonuc.panel = 'deneme'
    Adim '6/6 Son denetim'
    $kod = Ps 'prod_dogrula.ps1' "-Commit $prodCommit -Bekle 0 -Rapor `"$Calisma\dogrulama_deneme.txt`""
    $sonuc.dogrulama = if ($kod -eq 0) { 'DOGRULANDI' } else { "$kod HATA" }
    Yaz $(if ($kod -eq 0) { 'TAMAM' } else { 'UYARI' }) "canli dogrulama: $($sonuc.dogrulama)"
    Bitir
}

# --- 4) Iscilerin bitmesi -------------------------------------------------------------------------------------------------------
Adim '4/6 Iscilerin bitmesi bekleniyor'
$t0 = Get-Date
while (((Get-Date) - $t0).TotalMinutes -lt 10) {
    $gorev = (Get-ScheduledTask -TaskName 'TAM_Life_v35_ReportDB_6dk' -ErrorAction SilentlyContinue).State -eq 'Running'
    $surec = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" | Where-Object { $_.CommandLine -match 'app\.isci' }
    if (-not $gorev -and -not $surec) { break }
    Start-Sleep -Seconds 10
}
$bekleme = [int]((Get-Date) - $t0).TotalSeconds
if ($bekleme -ge 600) { $sonuc.isci = 'zaman asimi (10 dk)'; $uyarilar += 'ReportDB iscisi 10 dk icinde bitmedi; yine de yeniden baslatildi'; Yaz 'UYARI' $sonuc.isci }
else { $sonuc.isci = "bitti ($bekleme sn beklendi)"; Yaz 'TAMAM' "isci calismiyor ($bekleme sn beklendi)" }

# --- 5) Panel yeniden baslatma; acilmazsa full_reboot ----------------------------------------------------------------------------
Adim '5/6 Panel yeniden baslatiliyor'
$yenidenBaslangic = (Get-Date).AddSeconds(-5).ToString('yyyy-MM-dd HH:mm:ss')
$kod = Ps 'canli_gorev_kur.ps1' '-PanelYenile'
if ($kod -eq 0) { $sonuc.panel = 'yeniden baslatildi'; $sonuc.full_reboot = 'gerekmedi'; Yaz 'TAMAM' 'panel yeniden baslatildi ve yanit veriyor' }
else {
    $sonuc.panel = "acilmadi (kod $kod)"
    Yaz 'UYARI' "panel yeniden baslatmadan sonra acilmadi (kod $kod): full_reboot.bat /oto"
    $kod = Alt (Join-Path $Proje 'full_reboot.bat') '/oto'
    $sonuc.full_reboot = @{ 0 = 'TAMAM'; 2 = 'panel acik ama gorevsiz' }[$kod]
    if (-not $sonuc.full_reboot) { $sonuc.full_reboot = "BASARISIZ (kod $kod)" }
    if ($kod -eq 0) { $uyarilar += 'panel ilk yeniden baslatmada acilmadi; full_reboot ile acildi'; Yaz 'UYARI' 'full_reboot ile acildi' }
    elseif ($kod -eq 2) { $hatalar += 'full_reboot: panel acik ama gorevlerle degil (sunucu yeniden baslayinca kapanir)'; Yaz 'HATA' $sonuc.full_reboot }
    else { $hatalar += "PANEL ACILAMADI: full_reboot da basarisiz (kod $kod)"; Yaz 'HATA' $sonuc.full_reboot }
}

# --- 6) Son denetim ------------------------------------------------------------------------------------------------------------
Adim '6/6 Son denetim (ReportDB iscisinin bir turu beklenir, en cok ~8 dk)'
$prodCommit = (& git -C $Proje rev-parse HEAD 2>$null | Out-String).Trim()
$kod = Ps 'prod_dogrula.ps1' "-Commit $prodCommit -Baslangic `"$yenidenBaslangic`" -Rapor `"$GunlukDizini\$Zaman.dogrulama.txt`""
$sonuc.dogrulama = if ($kod -eq 0) { 'DOGRULANDI' } else { "$kod HATA" }
if ($kod -eq 0) { Yaz 'TAMAM' 'canli dogrulama: DOGRULANDI' } else { $hatalar += "canli dogrulama: $kod HATA"; Yaz 'HATA' "canli dogrulama: $kod HATA" }
Bitir
