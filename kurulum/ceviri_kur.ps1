# TAMLIFE v3.5 aylik rapor "Ingilizceye cevir" dugmesi icin cevrimdisi TR->EN ceviri modelini kurar ve dener.
# Eski panelin isletim\guncelle_indir.ps1 -Model uyarlamasi. Betik saf ASCII (PS 5.1). Panel/API'ye dokunmaz; bitince API yeniden baslatilir.
#   .\ceviri_kur.ps1                       : model yoksa -Kaynak (varsayilan bos; eski panel klasoru silindi) verildiyse oradan kopyalar, yoksa argos-net.com'dan indirir;
#                                            kutuphane (ctranslate2, sentencepiece) yoksa pip ile kurar; sonra deneme cevirisi yapar
#   .\ceviri_kur.ps1 -Paket C:\x\translate-tr_en-1_5.argosmodel : internetsiz sunucu: baska makinede indirilmis paketi acar
#   .\ceviri_kur.ps1 -Wheels C:\x\wheels   : internetsiz sunucu: kutuphaneleri yerel wheel klasorunden kurar (pip --no-index)
#   .\ceviri_kur.ps1 -Dogrula              : hicbir sey kurmaz/indirmez; yalniz dosya, SHA256 ve deneme cevirisini kontrol eder
# Model ~126 MB, git'te DEGIL (.gitignore: ceviri_modeli/). Varsayilan yer: TAMLIFE_v3.5\ceviri_modeli\tr_en.
# backend\.env icinde TAMLIFE_CEVIRI_MODEL_DIZINI verildiyse ayni yolu -Hedef ile verin.
# Indirme adresi ve SHA256 uretim dokuman\INTERNETTEN_ALINACAKLAR.md ile aynidir; tarayici benzeri User-Agent gerekir (yoksa 403).
param([string]$Kaynak = '',
      [string]$Paket = '',
      [string]$Wheels = '',
      [string]$Hedef = '',
      [switch]$Dogrula)
$ErrorActionPreference = 'Stop'
$Kok = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Kok 'backend'
$Py = Join-Path $Kok '.venv\Scripts\python.exe'
if (-not $Hedef) { $Hedef = Join-Path $Kok 'ceviri_modeli\tr_en' }
$Url = 'https://argos-net.com/v1/translate-tr_en-1_5.argosmodel'
$Sha = '726DB5B058C058142B23695F600BE3CCDED3A379DA764A459EDD30848B931B81'
$Ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36'
# Paketten yalniz bu dort dosya alinir (stanza/ alinmaz: torch ister; cumle bolmeyi panel kendisi yapar).
$Dosyalar = @('model\model.bin', 'model\shared_vocabulary.txt', 'sentencepiece.model', 'metadata.json')

function Adim($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Tamam($m) { Write-Host "[+] $m" -ForegroundColor Green }
function Uyari($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Dur($m)  { Write-Host "[!] $m" -ForegroundColor Red; exit 1 }

# PS 5.1: 'Stop' altinda yerel programin stderr ciktisi hata sayilabilir; python/pip cagrilari bu sarmalla calisir.
function Yerel([scriptblock]$is) {
    $eski = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $is } finally { $ErrorActionPreference = $eski }
}

function Model-Tam {
    foreach ($d in $Dosyalar) { if (-not (Test-Path (Join-Path $Hedef $d))) { return $false } }
    return $true
}

function Model-Ozeti {
    $bin = Join-Path $Hedef 'model\model.bin'
    return (Get-FileHash -Algorithm SHA256 -Path $bin).Hash.ToUpperInvariant()
}

function Kopyala-Kokten($kokKlasor) {
    # Paket kokunde tek alt klasor olabilir (translate-tr_en-1_5\...).
    if (-not (Test-Path (Join-Path $kokKlasor 'metadata.json'))) {
        $alt = Get-ChildItem $kokKlasor -Directory -ErrorAction SilentlyContinue | Where-Object { Test-Path (Join-Path $_.FullName 'metadata.json') } | Select-Object -First 1
        if ($null -ne $alt) { $kokKlasor = $alt.FullName }
    }
    foreach ($d in $Dosyalar) {
        $k = Join-Path $kokKlasor $d
        if (-not (Test-Path $k)) { throw "Kaynakta yok: $k" }
    }
    foreach ($d in $Dosyalar) {
        $h = Join-Path $Hedef $d
        $hk = Split-Path $h -Parent
        if (-not (Test-Path $hk)) { New-Item -ItemType Directory -Path $hk -Force | Out-Null }
        Copy-Item (Join-Path $kokKlasor $d) $h -Force
    }
}

function Paketi-Ac($paketYolu) {
    $tmp = Join-Path $env:TEMP ('tamlife_argos_' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp -Force | Out-Null
    try {
        # Expand-Archive (PS 5.1) yalniz .zip uzantisini kabul eder; .argosmodel bir zip'tir.
        $zip = Join-Path $tmp 'model.zip'
        Copy-Item $paketYolu $zip -Force
        $ac = Join-Path $tmp 'acik'
        Expand-Archive -Path $zip -DestinationPath $ac -Force
        Kopyala-Kokten $ac
    } finally {
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Indir($hedefDosya) {
    Adim "Indiriliyor: $Url (~115 MB)"
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        # --ssl-no-revoke: kurumsal agda CRL/OCSP adresleri kapali olabilir; TLS dogrulamasinin kendisi aynen calisir.
        Yerel { & curl.exe -fSL -A $Ua --ssl-no-revoke --retry 5 --retry-delay 3 --retry-connrefused --connect-timeout 15 -o $hedefDosya $Url }
        if ($LASTEXITCODE -ne 0) { throw "curl basarisiz (kod $LASTEXITCODE)" }
    } else {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $Url -OutFile $hedefDosya -UserAgent $Ua -UseBasicParsing
    }
    if (-not (Test-Path $hedefDosya) -or ((Get-Item $hedefDosya).Length -le 0)) { throw "Indirme bos: $hedefDosya" }
}

if (-not (Test-Path $Py)) { Dur "Python yok: $Py (once .venv kurulmali)" }
if (-not (Test-Path (Join-Path $Backend 'app\rapor\ceviri.py'))) { Dur "Ceviri modulu yok: $Backend\app\rapor\ceviri.py (yamalar uygulanmis mi?)" }
Adim "Model yeri: $Hedef"

# 1) Model dosyalari
if (Model-Tam) {
    Tamam 'Model dosyalari yerinde.'
} elseif ($Dogrula) {
    Dur "Model eksik: $Hedef (betigi -Dogrula olmadan calistirin)"
} elseif ($Paket) {
    if (-not (Test-Path $Paket)) { Dur "Paket yok: $Paket" }
    Adim "Paket aciliyor: $Paket"
    Paketi-Ac $Paket
} elseif ($Kaynak -and (Test-Path (Join-Path $Kaynak 'model\model.bin'))) {
    Adim "Kopyalaniyor: $Kaynak"
    Kopyala-Kokten $Kaynak
} else {
    Uyari "Kaynak klasor verilmedi ya da yok; internetten indirilecek."
    $tmp = Join-Path $env:TEMP ('tamlife_argos_' + [guid]::NewGuid().ToString('N') + '.argosmodel')
    try {
        try { Indir $tmp }
        catch {
            Dur ("Indirilemedi: " + $_.Exception.Message + "`n    Sunucu internete kapaliysa: paketi internetli makinede su adresten indirin ve -Paket ile verin:`n    $Url")
        }
        Paketi-Ac $tmp
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}
if (-not (Model-Tam)) { Dur "Model dosyalari tamamlanamadi: $Hedef" }
$ozet = Model-Ozeti
if ($ozet -ne $Sha) { Dur "model.bin SHA256 uyusmuyor: $ozet (beklenen $Sha). Dosya bozuk ya da farkli surum; klasoru silip tekrar deneyin." }
Tamam 'model.bin SHA256 dogru.'

# 2) Kutuphaneler (surumler requirements.txt ile ayni)
Yerel { & $Py -c "import ctranslate2, sentencepiece" 2>$null }
if ($LASTEXITCODE -eq 0) {
    Tamam 'ctranslate2 ve sentencepiece kurulu.'
} elseif ($Dogrula) {
    Dur 'ctranslate2 / sentencepiece kurulu degil (betigi -Dogrula olmadan calistirin).'
} else {
    $paketler = @('ctranslate2==4.8.2', 'sentencepiece==0.2.2', 'PyYAML==6.0.3')
    if ($Wheels) {
        if (-not (Test-Path $Wheels)) { Dur "Wheel klasoru yok: $Wheels" }
        Adim "Kutuphaneler yerel klasorden kuruluyor: $Wheels"
        Yerel { & $Py -m pip install --no-index --find-links $Wheels @paketler }
    } else {
        Adim 'Kutuphaneler pip ile kuruluyor (internet / kurum PyPI aynasi gerekir)'
        Yerel { & $Py -m pip install @paketler }
    }
    if ($LASTEXITCODE -ne 0) {
        Dur ("pip basarisiz. Internetsiz sunucuda: internetli makinede`n    pip download -d wheels --only-binary=:all: --python-version 3.12 --platform win_amd64 " + ($paketler -join ' ') + "`n    calistirip klasoru tasiyin ve -Wheels ile verin.")
    }
    Tamam 'Kutuphaneler kuruldu.'
}

# 3) Deneme cevirisi: panelin kullandigi ayni alt surec (python -m app.rapor.ceviri --isci). Metin ASCII: PS 5.1 boruda UTF-8 bozabilir.
Adim 'Deneme cevirisi yapiliyor'
$env:TAMLIFE_CEVIRI_MODEL_DIZINI = $Hedef
Push-Location $Backend
try {
    $cikti = Yerel { '{"deneme": "Hat kesintisi giderildi."}' | & $Py -m app.rapor.ceviri --isci }
    $kod = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($kod -ne 0) { Dur "Deneme cevirisi basarisiz (kod $kod): $cikti" }
$sonuc = ($cikti | Out-String | ConvertFrom-Json).metinler.deneme
if (-not $sonuc) { Dur "Deneme cevirisi bos dondu: $cikti" }
Tamam "Deneme: '$sonuc'"
Write-Host ''
Tamam 'Ceviri hazir. API penceresini kapatip paneli yeniden acin (paneli_ac.bat); "Ingilizceye cevir" dugmesi modeli kullanir.'
exit 0
