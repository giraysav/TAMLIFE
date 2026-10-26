# TAMLIFE v3.5 - panelin uctan uca testi (saf ASCII; PS 5.1). Cagiran: depo kokundeki PANELI_TEST_ET.bat (cift tikla).
# 2026-10-26 kullanici: "bir tusa basinca butun paneli uctan uca test etsin, hatalari bulup cikarsin ve debug yapsin; sonra onay
# isteyerek paneli yeniden baslatip tum surecleri tekrar calistirsin".
#
# Adimlar (hicbiri canli veriyi degistirmez):
#   1 Canli sistem : zamanlanmis gorevler, panel (127.0.0.1:8117) ve https://tamlife saglik ucu
#   2 Saglik       : backend\araclar\panel_saglik.py (veritabani, sema, arizalar, ReportDB iscisi, dis baglantilar)
#   3 Arka uc      : ruff (kod denetimi) + pytest (ayri test veritabaninda, ~6 dk)
#   4 On yuz       : tsc + lint + vitest + derleme denemesi (GECICI klasore; canli arayuz dosyalarina dokunmaz)
# Sonra: rapor (var\log\panel_testi\<zaman>\ozet.txt, Not Defteri'nde acilir). Hata varsa Claude Code'a analiz [A] ya da
# analiz + duzeltme [D] yaptirma secenegi (duzeltmeden sonra testler yeniden kosar). En sonda onayla yeniden baslatma: veritabani
# yedegi alinir, full_reboot.bat YONETICI olarak calisir (Windows onay penceresi), panel / TLS vekili / ReportDB iscisi kalkar.
# HATA = panelin kendisinde sorun; UYARI = dis sistem ya da izlenecek durum (ornek: SMTP portu kapali), paneli bozmaz.

param([switch]$SoruSorma)  # yalniz test / zamanlanmis calisma: hicbir soru sorulmaz, yeniden baslatma yapilmaz
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$Kok = Split-Path $PSScriptRoot -Parent
$Backend = Join-Path $Kok 'backend'
$Arayuz = Join-Path $Kok 'ekran-react'
$Py = Join-Path $Kok '.venv\Scripts\python.exe'
$Claude = 'C:\tools\Claude\claude.exe'
$Zaman = Get-Date -Format 'yyyyMMdd-HHmmss'
$Klasor = Join-Path $Kok "var\log\panel_testi\$Zaman"
New-Item -ItemType Directory -Force -Path $Klasor | Out-Null
$Ozet = Join-Path $Klasor 'ozet.txt'
$Sonuclar = New-Object System.Collections.ArrayList

function Baslik($m) { Write-Host ''; Write-Host "=== $m ===" -ForegroundColor Cyan; Add-Content -Path $Ozet -Value "`r`n=== $m ===" -Encoding UTF8 }
function Kaydet($durum, $ad, $ayrinti) {
    [void]$Sonuclar.Add([pscustomobject]@{ Durum = $durum; Ad = $ad; Ayrinti = $ayrinti })
    $renk = @{ TAMAM = 'Green'; UYARI = 'Yellow'; HATA = 'Red' }[$durum]
    Write-Host ("  [{0,-5}] {1}" -f $durum, $ad) -ForegroundColor $renk -NoNewline
    if ($ayrinti) { Write-Host "  - $ayrinti" -ForegroundColor DarkGray } else { Write-Host '' }
    Add-Content -Path $Ozet -Value ("[{0,-5}] {1}  {2}" -f $durum, $ad, $ayrinti) -Encoding UTF8
}
# Programi ayri surecte calistirir; stdout + stderr tek dosyada toplanir, cikis kodu doner. Start-Process: PS 5.1 ic ice tirnakli
# arguman aktarimini bozmaz ve stderr satirlari hata kaydina donmez.
function Calistir($dizin, $program, $argumanlar, $dosya) {
    $hata = "$dosya.err"
    $s = Start-Process -FilePath $program -ArgumentList $argumanlar -WorkingDirectory $dizin -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $dosya -RedirectStandardError $hata
    if (Test-Path $hata) { Get-Content $hata -Encoding UTF8 | Add-Content -Path $dosya -Encoding UTF8; Remove-Item $hata -Force }
    return $s.ExitCode
}
function Saglik($adres) {
    try {
        $s = [Diagnostics.Stopwatch]::StartNew()
        $r = Invoke-WebRequest -Uri $adres -UseBasicParsing -TimeoutSec 10
        return @{ ok = ($r.StatusCode -eq 200); ms = $s.ElapsedMilliseconds; hata = '' }
    } catch { return @{ ok = $false; ms = 0; hata = $_.Exception.Message } }
}
function Son($dosya, $desen) { (Select-String -Path $dosya -Pattern $desen -ErrorAction SilentlyContinue | Select-Object -Last 1).Line }

function Testler {
    # --- 3 Arka uc ---------------------------------------------------------------------------------------------------------
    Baslik '3/4 Arka uc testleri (yaklasik 6 dakika; ayri test veritabaninda)'
    $f = Join-Path $Klasor 'ruff.txt'
    $kod = Calistir $Backend $Py '-m ruff check app tests araclar\panel_saglik.py araclar\db_yedek.py' $f
    if ($kod -eq 0) { Kaydet 'TAMAM' 'Kod denetimi (ruff)' 'sorun yok' } else { Kaydet 'HATA' 'Kod denetimi (ruff)' "ayrinti: $f" }
    Write-Host '  ... testler calisiyor, lutfen bekleyin' -ForegroundColor DarkGray
    $f = Join-Path $Klasor 'pytest.txt'
    $kod = Calistir $Backend $Py '-m pytest -q -p no:cacheprovider' $f
    $sonSatir = Son $f '(passed|failed|error)'
    if ($kod -eq 0) { Kaydet 'TAMAM' 'Arka uc testleri (pytest)' $sonSatir }
    else {
        $kirik = (Select-String -Path $f -Pattern '^(FAILED|ERROR) ' | ForEach-Object { $_.Line }) -join '; '
        Kaydet 'HATA' 'Arka uc testleri (pytest)' "$sonSatir :: $kirik"
    }

    # --- 4 On yuz ----------------------------------------------------------------------------------------------------------
    Baslik '4/4 On yuz (arayuz) denetimleri (yaklasik 3 dakika)'
    $f = Join-Path $Klasor 'tsc.txt'
    if ((Calistir $Arayuz 'npx.cmd' 'tsc -b' $f) -eq 0) { Kaydet 'TAMAM' 'Tip denetimi (tsc)' 'sorun yok' } else { Kaydet 'HATA' 'Tip denetimi (tsc)' ((Get-Content $f -TotalCount 3) -join ' ') }
    $f = Join-Path $Klasor 'lint.txt'
    $kod = Calistir $Arayuz 'npm.cmd' 'run lint' $f
    $uyari = @(Select-String -Path $f -Pattern ' (warning|error) ').Count
    if ($kod -ne 0) { Kaydet 'HATA' 'Kod denetimi (oxlint)' "ayrinti: $f" } elseif ($uyari) { Kaydet 'UYARI' 'Kod denetimi (oxlint)' "$uyari uyari: $f" } else { Kaydet 'TAMAM' 'Kod denetimi (oxlint)' 'sorun yok' }
    $f = Join-Path $Klasor 'vitest.txt'
    $kod = Calistir $Arayuz 'npx.cmd' 'vitest run' $f
    # Dikkat: PowerShell degisken adinda buyuk / kucuk harf ayirmaz; $Ozet (rapor yolu) ile cakisan ad kullanilmaz.
    $vitestSonuc = ((Select-String -Path $f -Pattern '^\s*(Test Files|Tests)\s' | ForEach-Object { $_.Line.Trim() }) -join ' | ')
    if ($kod -eq 0) { Kaydet 'TAMAM' 'Arayuz testleri (vitest)' $vitestSonuc } else { Kaydet 'HATA' 'Arayuz testleri (vitest)' "$vitestSonuc :: $(((Select-String -Path $f -Pattern 'FAIL ' | Select-Object -First 5 | ForEach-Object { $_.Line.Trim() }) -join '; '))" }
    $gecici = Join-Path $env:TEMP "tamlife_derleme_$Zaman"
    $f = Join-Path $Klasor 'derleme.txt'
    $kod = Calistir $Arayuz 'npx.cmd' "vite build --outDir `"$gecici`" --emptyOutDir" $f
    if ($kod -eq 0) { Kaydet 'TAMAM' 'Arayuz derlemesi (gecici klasore)' 'derlenebiliyor' } else { Kaydet 'HATA' 'Arayuz derlemesi' "ayrinti: $f" }
    Remove-Item -Recurse -Force -LiteralPath $gecici -ErrorAction SilentlyContinue
}

function CanliVeSaglik {
    # --- 1 Canli sistem ----------------------------------------------------------------------------------------------------
    Baslik '1/4 Canli sistem'
    foreach ($g in @(@('TAMLIFE_v35_Panel', 'Panel gorevi'), @('TAMLIFE_v35_TLS_Vekil', 'TLS vekili gorevi'))) {
        $t = Get-ScheduledTask -TaskName $g[0] -ErrorAction SilentlyContinue
        if ($null -eq $t) { Kaydet 'HATA' $g[1] 'gorev kayitli degil' }
        elseif ($t.State -eq 'Running') { Kaydet 'TAMAM' $g[1] 'calisiyor' }
        else { Kaydet 'HATA' $g[1] "durum $($t.State): panel calisiyor olabilir ama coktugunde kendiliginden geri gelmez (yeniden baslatin)" }
    }
    $t = Get-ScheduledTask -TaskName 'TAM_Life_v35_ReportDB_6dk' -ErrorAction SilentlyContinue
    if ($null -eq $t) { Kaydet 'HATA' 'ReportDB isci gorevi' 'gorev kayitli degil' }
    elseif ($t.State -eq 'Disabled') { Kaydet 'HATA' 'ReportDB isci gorevi' 'devre disi' }
    else { $b = $t | Get-ScheduledTaskInfo; Kaydet 'TAMAM' 'ReportDB isci gorevi' "son calisma $($b.LastRunTime)" }
    $s = Saglik 'http://127.0.0.1:8117/api/v1/health'
    if ($s.ok) { Kaydet ($(if ($s.ms -gt 2000) { 'UYARI' } else { 'TAMAM' })) 'Panel (127.0.0.1:8117)' "yanit $($s.ms) ms" } else { Kaydet 'HATA' 'Panel (127.0.0.1:8117)' "yanit yok: $($s.hata)" }
    $s = Saglik 'https://tamlife/api/v1/health'
    if ($s.ok) { Kaydet 'TAMAM' 'Kullanici adresi (https://tamlife)' "yanit $($s.ms) ms" } else { Kaydet 'HATA' 'Kullanici adresi (https://tamlife)' "yanit yok: $($s.hata)" }

    # --- 2 Saglik ----------------------------------------------------------------------------------------------------------
    Baslik '2/4 Veritabani, isci ve dis baglantilar'
    $f = Join-Path $Klasor 'saglik.txt'
    [void](Calistir $Backend $Py 'araclar\panel_saglik.py' $f)
    foreach ($satir in (Get-Content $f -Encoding UTF8)) {
        $p = $satir -split '\|', 3
        if ($p.Count -eq 3 -and $p[0] -in @('TAMAM', 'UYARI', 'HATA')) { Kaydet $p[0] $p[1] $p[2] }
    }
}

function OzetYaz($baslik) {
    $h = @($Sonuclar | Where-Object Durum -eq 'HATA').Count
    $u = @($Sonuclar | Where-Object Durum -eq 'UYARI').Count
    $t = @($Sonuclar | Where-Object Durum -eq 'TAMAM').Count
    Write-Host ''
    Write-Host '========================================================'
    Write-Host " $baslik : $t TAMAM, $u UYARI, $h HATA" -ForegroundColor $(if ($h) { 'Red' } elseif ($u) { 'Yellow' } else { 'Green' })
    Write-Host " Rapor: $Ozet"
    Write-Host '========================================================'
    Add-Content -Path $Ozet -Value "`r`n$baslik : $t TAMAM, $u UYARI, $h HATA" -Encoding UTF8
    return $h
}

function Sor($soru, $secenekler) {
    if ($SoruSorma) { return 'H' }
    while ($true) {
        $c = (Read-Host $soru).Trim().ToUpper()
        if ($secenekler -contains $c) { return $c }
        Write-Host "  Lutfen sunlardan birini yazin: $($secenekler -join ' / ')" -ForegroundColor Yellow
    }
}

# ================================== CALISMA ==================================
Write-Host '========================================================' -ForegroundColor Cyan
Write-Host ' TAMLIFE - Panelin uctan uca testi' -ForegroundColor Cyan
Write-Host ' Bu test canli verilere DOKUNMAZ. Toplam ~10 dakika surer.' -ForegroundColor Cyan
Write-Host '========================================================' -ForegroundColor Cyan
Set-Content -Path $Ozet -Value "TAMLIFE panel testi - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $env:USERNAME" -Encoding UTF8
CanliVeSaglik
Testler
$hata = OzetYaz 'SONUC'
if (-not $SoruSorma) { Start-Process notepad.exe $Ozet }

# --- Hata analizi / duzeltme (Claude Code) ---------------------------------------------------------------------------------
$duzeltildi = $false
if ($hata -gt 0 -and -not $SoruSorma) {
    if (-not (Test-Path $Claude)) {
        Write-Host "  Claude Code bulunamadi ($Claude): hata analizi yapilamiyor. Raporu bir gelistiriciye iletin." -ForegroundColor Yellow
    } else {
        Write-Host ''
        Write-Host 'Bulunan HATA(lar) icin Claude Code yardimci olabilir:' -ForegroundColor Cyan
        Write-Host '  [A] Analiz et       : nedenini bulur ve cozum onerir; HICBIR dosyayi degistirmez (onerilen)'
        Write-Host '  [D] Analiz + duzelt : kodu duzeltir, sonra testler yeniden calisir (commit / yeniden baslatma yapmaz)'
        Write-Host '  [H] Hayir           : gec'
        $secim = Sor 'Seciminiz [A/D/H]' @('A', 'D', 'H')
        if ($secim -ne 'H') {
            $istem = "TAMLIFE panelinin otomatik testi HATA buldu. Rapor: $Ozet ; ayrintili ciktilar ayni klasorde (pytest.txt, vitest.txt, tsc.txt, lint.txt, ruff.txt, saglik.txt, derleme.txt). " +
                "Depo: $Kok (CLAUDE.md kurallarina uy). Gorevin: her HATA icin kok nedeni bul. UYARI satirlari dis sistem durumudur, onlari duzeltmeye calisma. " +
                $(if ($secim -eq 'D') { 'Yalniz HATA olan maddeleri en kucuk degisiklikle DUZELT. Paneli yeniden baslatma, commit atma, .env ve veritabanina dokunma, gorevleri degistirme. ' } else { 'HICBIR dosyayi degistirme; yalniz analiz et. ' }) +
                'Sonunda Turkce, teknik olmayan biri icin kisa bir ozet yaz: ne bozuk, neden, ne yapildi ya da ne yapilmali.'
            $kip = if ($secim -eq 'D') { 'acceptEdits' } else { 'plan' }
            $araclar = if ($secim -eq 'D') { 'Read,Grep,Glob,Edit,Write' } else { 'Read,Grep,Glob' }
            $analiz = Join-Path $Klasor 'claude_analiz.txt'
            Write-Host "  Claude calisiyor ($kip), birkac dakika surebilir..." -ForegroundColor DarkGray
            Push-Location $Kok
            & $Claude -p $istem --permission-mode $kip --allowedTools $araclar 2>&1 | Tee-Object -FilePath $analiz
            Pop-Location
            Write-Host "  Claude raporu: $analiz" -ForegroundColor Cyan
            Start-Process notepad.exe $analiz
            if ($secim -eq 'D') {
                $duzeltildi = $true
                Write-Host ''
                Write-Host 'Duzeltmeden sonra testler yeniden calisiyor...' -ForegroundColor Cyan
                $Sonuclar.Clear()
                Add-Content -Path $Ozet -Value "`r`n##### DUZELTME SONRASI #####" -Encoding UTF8
                Testler
                $hata = OzetYaz 'DUZELTME SONRASI'
            }
        }
    }
}

# --- Yeniden baslatma (onayli) ---------------------------------------------------------------------------------------------
if (-not $SoruSorma) {
    Write-Host ''
    if ($hata -gt 0) { Write-Host 'DIKKAT: hala HATA var. Yeniden baslatmak sorunu cozmeyebilir.' -ForegroundColor Yellow }
    $secim = Sor 'Paneli yeniden baslatip tum surecleri (panel, TLS vekili, ReportDB iscisi) tekrar calistirayim mi? [E/H]' @('E', 'H')
    if ($secim -eq 'E') {
        Write-Host '  1) Veritabani yedegi aliniyor...' -ForegroundColor DarkGray
        $f = Join-Path $Klasor 'yedek.txt'
        if ((Calistir $Backend $Py 'araclar\db_yedek.py panel_testi' $f) -eq 0) { Write-Host ('     yedek: ' + (Get-Content $f -Raw).Trim()) -ForegroundColor Green }
        else { Write-Host "     yedek alinamadi ($f); yeniden baslatma iptal." -ForegroundColor Red; Read-Host 'Kapatmak icin Enter'; exit 1 }
        if ($duzeltildi) {
            Write-Host '  2) Kod degisti: arayuz yeniden derleniyor...' -ForegroundColor DarkGray
            if ((Calistir $Arayuz 'npm.cmd' 'run build' (Join-Path $Klasor 'canli_derleme.txt')) -ne 0) { Write-Host '     derleme basarisiz; yeniden baslatma iptal.' -ForegroundColor Red; Read-Host 'Kapatmak icin Enter'; exit 1 }
        }
        Write-Host '  3) Yeniden baslatma YONETICI olarak calisacak: Windows onay penceresinde "Evet" deyin.' -ForegroundColor Cyan
        try {
            Start-Process -FilePath (Join-Path $Kok 'full_reboot.bat') -Verb RunAs -Wait
        } catch {
            Write-Host '     Onay verilmedi; yeniden baslatma yapilmadi.' -ForegroundColor Yellow
            Read-Host 'Kapatmak icin Enter'; exit 1
        }
        Write-Host '  4) Yeniden baslatma sonrasi denetim:' -ForegroundColor DarkGray
        $Sonuclar.Clear()
        Add-Content -Path $Ozet -Value "`r`n##### YENIDEN BASLATMA SONRASI #####" -Encoding UTF8
        CanliVeSaglik
        [void](OzetYaz 'YENIDEN BASLATMA SONRASI')
    }
}
if (-not $SoruSorma) { Read-Host 'Bitti. Kapatmak icin Enter' }
exit $hata
