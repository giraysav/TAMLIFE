# TAMLIFE v3.5: ReportDB TEMIP alarm kayitlarini panele ilk kez ice alma (01.01.2026'dan bugune). Betik saf ASCII (PS 5.1).
# Musteri No -> TEMIP unvani -> kart -> sorumlu personel -> acik kayit eslesmesi her adimda yazdirilir.
#   .\temip_kayit_ice_al.ps1                     : Durum (yazmaz): sema surumu, TEMIP kayit sayisi, gorev durumu
#   .\temip_kayit_ice_al.ps1 -Adim Yedek         : panel DB yedegi (panelin yedek dugmesiyle ayni SQLite backup API, var\yedek\)
#   .\temip_kayit_ice_al.ps1 -Adim Sema          : alembic upgrade head (0013_onedesk_temip: ticket_no/customer_no/detail + 2 indeks)
#   .\temip_kayit_ice_al.ps1 -Adim Kuru          : Oracle'dan okur, YAZMAZ; eslesme ozeti + CSV (-Kip artimli|mutabakat|tam, vars. artimli)
#   .\temip_kayit_ice_al.ps1 -Adim Yukle         : ilk yukleme (--kip tam, ay ay; dakikalar surer) + eslesme CSV
#   .\temip_kayit_ice_al.ps1 -Adim Eslesme       : Oracle'siz; paneldeki kayitlarin eslesmesi + CSV
#   .\temip_kayit_ice_al.ps1 -Adim Temizlik      : eski numarasiz 'import' Onedesk kayitlari (kuru; silmek icin -Uygula)
#   .\temip_kayit_ice_al.ps1 -Adim Hepsi         : Yedek -> Sema -> Kuru -> Yukle -> Eslesme (ilk hata durdurur)
# Panel ve 6 dk gorev ayni SQLite dosyasina yazar (WAL + busy_timeout). Yukle, 6 dk senkronla ayni kilidi alir (cakisma: cikis 2).
# Yukle sonrasi panelin yeni kodla calismasi icin yeniden baslatilmasi ve 6 dk gorevin etkinlestirilmesi kullanicinin karari
# (bu betik ikisine de dokunmaz). CSV'ler backend\var\kesif\ (git disi, musteri unvani icerir).
param([ValidateSet('Durum', 'Yedek', 'Sema', 'Kuru', 'Yukle', 'Eslesme', 'Temizlik', 'Hepsi')]
      [string]$Adim = 'Durum',
      [ValidateSet('artimli', 'mutabakat', 'tam')]
      [string]$Kip = 'artimli',
      [switch]$Uygula,
      [string]$Istemci = 'E:\oracle\instantclient_19_32',
      [string]$Gorev = 'TAM_Life_v35_ReportDB_6dk')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'calisma_kimligi.ps1')
Tamlife-KimlikDogrula
$Kok = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Kok 'backend'
$Py = Join-Path $Kok '.venv\Scripts\python.exe'

function Adim($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Uyari($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Dur($m)  { Write-Host "[!] $m" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $Py)) { Dur "Python yok: $Py" }
if (-not (Test-Path (Join-Path $Backend '.env'))) { Dur "Ayar dosyasi yok: $Backend\.env" }

function Py([string[]]$Argumanlar) {
    Push-Location $Backend
    try { & $Py @Argumanlar; $kod = $LASTEXITCODE } finally { Pop-Location }
    if ($kod -ne 0) { Dur "Basarisiz (cikis $kod): python $($Argumanlar -join ' ')" }
}

# Satir ici Python stdin'den verilir: PS 5.1 yerel exe argumanindaki cift tirnaklari bozar.
function PyKod([string]$Kod) {
    Push-Location $Backend
    try { $Kod | & $Py -; $kod = $LASTEXITCODE } finally { Pop-Location }
    if ($kod -ne 0) { Dur "Basarisiz (cikis $kod)" }
}

function Oracle-Hazir {
    if (-not (Test-Path (Join-Path $Istemci 'oci.dll'))) { Dur "Oracle Instant Client bulunamadi: $Istemci (-Istemci ile verin)" }
}

function Calistir-Durum {
    Adim 'Sema ve TEMIP kayitlari (yazmaz)'
    PyKod @'
from app.config import env_dosyasi_yukle; env_dosyasi_yukle()
from sqlalchemy import func, inspect, select, text
from app.db import engine, oturum
from app.models import OnedeskRecord
m = engine()
with m.connect() as b:
    print("  sema:", b.execute(text("select version_num from alembic_version")).scalar())
    sutun = {c["name"] for c in inspect(b).get_columns("onedesk_record")}
if "ticket_no" not in sutun:
    print("  onedesk_record.ticket_no yok: once -Adim Sema"); raise SystemExit(0)
with oturum() as db:
    for kaynak, durum, n in db.execute(select(OnedeskRecord.source, OnedeskRecord.status, func.count()).group_by(OnedeskRecord.source, OnedeskRecord.status)):
        print(f"  onedesk_record {kaynak or '-'}/{durum}: {n}")
'@
    $g = Get-ScheduledTask -TaskName $Gorev -ErrorAction SilentlyContinue
    if ($g) { Adim "Gorev $Gorev : $($g.State)" } else { Uyari "Gorev yok: $Gorev (kurulum\canli_gorev_kur.ps1)" }
}

function Calistir-Yedek {
    Adim 'Panel DB yedegi'
    PyKod @'
from app.config import env_dosyasi_yukle; env_dosyasi_yukle()
from app.yonetim import veritabani
r = veritabani.yedek_al("temip_ice_al")
print(f"  {r['ad']}: {r['boyut_bayt']} bayt, butunluk {r['butunluk']}, {r['kullanici_dosyasi']} kullanici dosyasi")
'@
}

function Calistir-Sema {
    Adim 'Sema: alembic upgrade head'
    Py @('-m', 'alembic', 'upgrade', 'head')
    Py @('-m', 'alembic', 'current')
}

function Calistir-Kuru {
    Oracle-Hazir
    Adim "Kuru deneme ($Kip): Oracle'dan okunur, panel DB'sine yazilmaz"
    Py @('-m', 'app.isci', 'temip-kayit', '--kip', $Kip, '--kuru', '--csv', '--client', $Istemci)
}

function Calistir-Yukle {
    Oracle-Hazir
    Adim 'Ilk yukleme (--kip tam): REPORTDB_KAYIT_BASLANGIC (vars. 2026-01-01) -> bugun, ay ay'
    Py @('-m', 'app.isci', 'temip-kayit', '--kip', 'tam', '--csv', '--client', $Istemci)
}

function Calistir-Eslesme {
    Adim 'Eslesme (Oracle yok): Musteri No -> kart -> sorumlu personel -> acik kayit'
    Py @('-m', 'app.isci', 'temip-eslesme', '--csv')
}

function Calistir-Temizlik {
    if ($Uygula) {
        Adim 'Eski numarasiz Onedesk kayitlari SILINIR (once var\yedek\ yedegi alinir)'
        Py @('-m', 'app.gecmis_temizle', '--uygula')
        Uyari 'Panel yeniden baslatilmali (gecmis_temizle notu).'
    } else {
        Adim 'Eski numarasiz Onedesk kayitlari: kuru deneme (silmek icin -Uygula)'
        Py @('-m', 'app.gecmis_temizle')
    }
}

switch ($Adim) {
    'Durum'    { Calistir-Durum }
    'Yedek'    { Calistir-Yedek }
    'Sema'     { Calistir-Sema }
    'Kuru'     { Calistir-Kuru }
    'Yukle'    { Calistir-Yukle }
    'Eslesme'  { Calistir-Eslesme }
    'Temizlik' { Calistir-Temizlik }
    'Hepsi'    { Calistir-Yedek; Calistir-Sema; Calistir-Kuru; Calistir-Yukle; Calistir-Eslesme; Calistir-Durum }
}
Adim 'Tamam.'
