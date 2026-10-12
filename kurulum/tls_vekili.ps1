# TAMLIFE v3.5 TLS vekili: https://<Ad>:<Port>/ (varsayilan https://tamlife:443/) -> panel (127.0.0.1:8117). Betik saf ASCII (PS 5.1).
# Uretim isletim\tls_vekili.ps1 uyarlamasi. NEDEN: sertifikanin ozel anahtari Windows deposunda kilitli (disa aktarilamaz); Python'un ssl
# modulu kullanamaz, http.sys kullanabilir. TLS'i Windows (http.sys) sonlandirir, bu betik istekleri duz HTTP olarak panele iletir.
#   istemci --TLS--> http.sys/443 --> bu betik --> 127.0.0.1:8117 (panel, kurulum\canli_baslat.ps1)
# ESKI PANELLE BIRLIKTE: eski panelin vekili https://+:443/ (tum adlar) dinler. Burada https://tamlife:443/ (YALNIZ bu Host adi) dinlenir;
# http.sys adi acik yazilan oneki joker onekten once secer. Yani Host: tamlife gelen istek yeni panele gider, eski panelin FQDN adresi
# (tamlife.turkcell.entp.tgc) ve IP erisimi aynen eskiye gider. Geri almak: bu betigi durdurmak yeter (istekler yine eski panele duser).
# 443 icin sertifika baglantisi (netsh http sslcert) eski panelden kalma ve ortaktir; bu betik ona DOKUNMAZ. Baska bir port kullanirsaniz:
#   netsh http add sslcert ipport=0.0.0.0:<PORT> certhash=<PARMAKIZI> appid='{f1e2d3c4-b5a6-4798-8a9b-0c1d2e3f4a5b}' certstorename=MY
# Gerekli: YONETICI (yukseltilmis) PowerShell. Pencere acik kalir; kapaninca vekil durur (kalici calistirma: canli_gorev_kur.ps1).
#   .\tls_vekili.ps1                      : https://tamlife:443/ -> 127.0.0.1:8117
#   .\tls_vekili.ps1 -Test                : tek istek karsilayip cikar (kurulum dogrulamasi)
#   .\tls_vekili.ps1 -Sema http -Ad localhost -Port 18080 : YALNIZ TEST, TLS yok
param([string]$Ad = 'tamlife',
      [int]$Port = 443,
      [int]$HedefPort = 8117,
      [ValidateSet('https', 'http')]
      [string]$Sema = 'https',
      [switch]$Test)
$ErrorActionPreference = 'Stop'

# Govde akisla gecer (aylik rapor Excel'leri 50 MB'a kadar cikabilir; bellekte toplanmaz).
$TAMPON = 81920
# Hop-by-hop basliklar iletilmez. Istemcinin gonderdigi X-Forwarded-*/Forwarded/X-Real-IP de iletilmez: istemci sahte IP yazamasin.
# Gercek istemci adresini bu betik kendisi X-Forwarded-For olarak yazar (panel yalniz 127.0.0.1'den gelen XFF'ye guvenir).
$ATLANAN_ISTEK = @('connection', 'keep-alive', 'proxy-connection', 'transfer-encoding', 'te', 'trailer', 'upgrade', 'host',
                   'content-length', 'expect', 'x-forwarded-for', 'x-forwarded-proto', 'x-forwarded-host', 'x-forwarded-port',
                   'forwarded', 'x-real-ip')
$ATLANAN_YANIT = @('connection', 'keep-alive', 'transfer-encoding', 'te', 'trailer', 'upgrade', 'content-length', 'server')

function Yaz($mesaj) {
    $an = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Host "$an tls_vekili: $mesaj"
}

# --- Hedefe giden istemci -----------------------------------------------------
Add-Type -AssemblyName System.Net.Http
$tutucu = New-Object Net.Http.HttpClientHandler
# 302/308 OLDUGU GIBI gecmeli: yonlendirmeyi uygulama yapar, vekil takip ederse tarayici gormez.
$tutucu.AllowAutoRedirect = $false
$tutucu.AutomaticDecompression = [Net.DecompressionMethods]::None
$tutucu.UseCookies = $false
$istemci = New-Object Net.Http.HttpClient($tutucu)
$istemci.Timeout = [TimeSpan]::FromMinutes(10)

if ($Sema -eq 'http') { Yaz 'UYARI: -Sema http yalnizca testlik; TLS yok demektir.' }
$onek = "${Sema}://${Ad}:${Port}/"
$dinleyici = New-Object Net.HttpListener
$dinleyici.Prefixes.Add($onek)
try {
    $dinleyici.Start()
} catch {
    $hata = $_.Exception.Message
    Yaz "$onek dinlenemedi: $hata"
    if ($hata -match 'conflicts with an existing registration') {
        # Ya bu betigin baska bir kopyasi calisiyor ya da baska bir surec ayni oneki tutuyor.
        Yaz 'Ayni onek baska bir surecte kayitli. YONETICI PowerShell-de, bu betigin eski kopyasini bulup durdurun:'
        Yaz '  Get-CimInstance Win32_Process -Filter "Name=''powershell.exe''" | Where-Object { $_.CommandLine -like "*tls_vekili.ps1*" } | Select-Object ProcessId, CommandLine'
        Yaz '  (ESKI PANELIN vekili https://+:443/ dinler, o ayri bir onektir ve bu hatayi vermez; onu durdurmayin.)'
    } elseif ($hata -match 'Access is denied|denied') {
        Yaz 'Yetki yok: YONETICI (yukseltilmis) PowerShell gerekli.'
    } else {
        Yaz "Sertifika baglanmis mi: netsh http show sslcert ipport=0.0.0.0:$Port"
    }
    exit 2
}
Yaz "dinleniyor $onek  ->  http://127.0.0.1:$HedefPort/"

# --- Istek isleme: ISCI_SAYISI isci ayni dinleyiciden paralel GetContext alir; gunluk satirlari kuyruga yazilir -------------
$ISCI_SAYISI = 16

$ISLE = {
    param($baglam, $ortak)
    # Isci runspace'i varsayilan 'Continue' ile acilir: .Result hatalari susup $cevap'i $null birakirdi. Hatalar catch'e dussun.
    $ErrorActionPreference = 'Stop'
    $basladi = $false
    try {
        $istek = $baglam.Request
        $yanit = $baglam.Response
        $hedef = "http://127.0.0.1:$($ortak.HedefPort)$($istek.RawUrl)"
        $ileti = New-Object Net.Http.HttpRequestMessage((New-Object Net.Http.HttpMethod($istek.HttpMethod)), $hedef)
        if ($istek.HasEntityBody) {
            $ileti.Content = New-Object Net.Http.StreamContent($istek.InputStream)
        }
        foreach ($ad in $istek.Headers.AllKeys) {
            if ($ortak.AtlananIstek -contains $ad.ToLowerInvariant()) { continue }
            $deger = $istek.Headers[$ad]
            if (-not $ileti.Headers.TryAddWithoutValidation($ad, $deger) -and $ileti.Content) {
                [void]$ileti.Content.Headers.TryAddWithoutValidation($ad, $deger)
            }
        }
        # Host hedefe degil ASIL isteme gore gitmeli: panel izinli ad (ALLOWED_HOSTS) ve Origin denetimini bu baslikla yapar.
        [void]$ileti.Headers.TryAddWithoutValidation('Host', $istek.UserHostName)
        [void]$ileti.Headers.TryAddWithoutValidation('X-Forwarded-For', $istek.RemoteEndPoint.Address.ToString())
        [void]$ileti.Headers.TryAddWithoutValidation('X-Forwarded-Proto', $ortak.Sema)

        $cevap = $ortak.Istemci.SendAsync($ileti, [Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        $kod = [int]$cevap.StatusCode
        if ($kod -lt 100 -or $kod -gt 999) { $kod = 502 }   # HttpListener yalniz 3 haneli kod kabul eder
        $yanit.StatusCode = $kod
        if ($cevap.ReasonPhrase) { $yanit.StatusDescription = $cevap.ReasonPhrase }
        foreach ($b in $cevap.Headers)         { if ($ortak.AtlananYanit -notcontains $b.Key.ToLowerInvariant()) { foreach ($d in $b.Value) { $yanit.Headers.Add($b.Key, $d) } } }
        foreach ($b in $cevap.Content.Headers) { if ($ortak.AtlananYanit -notcontains $b.Key.ToLowerInvariant()) { foreach ($d in $b.Value) { $yanit.Headers.Add($b.Key, $d) } } }
        $basladi = $true
        $akis = $null
        try {
            $akis = $cevap.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            $akis.CopyTo($yanit.OutputStream, $ortak.Tampon)
        } finally {
            if ($null -ne $akis) { $akis.Dispose() }   # akis hic acilamadiysa asil hata null hatasiyla gizlenmesin
            $cevap.Dispose()
        }
    } catch {
        $mesaj = $_.Exception.Message
        if ($basladi) {
            # Yanit basladiktan sonra: cogunlukla istemci sayfadan ayrildi. 502 yazilamaz.
            if ($mesaj -match 'nonexistent network connection|forcibly closed|aborted') {
                $ortak.Kuyruk.Enqueue("istemci baglantiyi kapatti: $($istek.HttpMethod) $($istek.Url.AbsolutePath)")
            } else {
                $ortak.Kuyruk.Enqueue("yanit aktarilamadi: $mesaj")
            }
        } else {
            $ortak.Kuyruk.Enqueue("istek iletilemedi: $mesaj")
            try {
                $baglam.Response.StatusCode = 502
                $g = [Text.Encoding]::UTF8.GetBytes('Panel su an yanit vermiyor (502).')
                $baglam.Response.OutputStream.Write($g, 0, $g.Length)
            } catch { }
        }
    } finally {
        try { $baglam.Response.Close() } catch { }
    }
}

$ISCI = {
    param($ortak)
    $isle = [scriptblock]::Create($ortak.IsleMetni)
    while ($ortak.Dinleyici.IsListening) {
        try {
            $baglam = $ortak.Dinleyici.GetContext()
        } catch {
            if (-not $ortak.Dinleyici.IsListening) { break }
            $ortak.Kuyruk.Enqueue("baglanti kabul edilemedi: $($_.Exception.Message)")
            continue
        }
        & $isle $baglam $ortak
    }
}

$ortak = [hashtable]::Synchronized(@{
    Dinleyici = $dinleyici; Istemci = $istemci; HedefPort = $HedefPort; Sema = $Sema
    AtlananIstek = $ATLANAN_ISTEK; AtlananYanit = $ATLANAN_YANIT; Tampon = $TAMPON
    Kuyruk = (New-Object 'System.Collections.Concurrent.ConcurrentQueue[string]')
    IsleMetni = $ISLE.ToString()
})

function Kuyrugu-Bosalt {
    $satir = $null
    while ($ortak.Kuyruk.TryDequeue([ref]$satir)) { Yaz $satir }
}

if ($Test) {
    # Kurulum dogrulamasi: tek istek, ana is parcaciginda.
    $baglam = $dinleyici.GetContext()
    & ([scriptblock]::Create($ortak.IsleMetni)) $baglam $ortak
    Kuyrugu-Bosalt
    Yaz 'tek istek karsilandi (-Test), cikiliyor'
} else {
    $havuz = [runspacefactory]::CreateRunspacePool(1, $ISCI_SAYISI)
    $havuz.Open()
    $isciler = @()
    function Isci-Baslat {
        $ps = [powershell]::Create()
        $ps.RunspacePool = $havuz
        [void]$ps.AddScript($ISCI.ToString()).AddArgument($ortak)
        return @{ PS = $ps; Sonuc = $ps.BeginInvoke() }
    }
    for ($i = 0; $i -lt $ISCI_SAYISI; $i++) { $isciler += Isci-Baslat }
    Yaz "$ISCI_SAYISI isci paralel istek karsiliyor"
    try {
        while ($dinleyici.IsListening) {
            Kuyrugu-Bosalt
            for ($i = 0; $i -lt $isciler.Count; $i++) {
                if ($isciler[$i].Sonuc.IsCompleted -and $dinleyici.IsListening) {
                    # Beklenmedik cikis: hatayi yaz, isciyi yenile (kapasite dusmesin).
                    foreach ($h in $isciler[$i].PS.Streams.Error) { Yaz "isci hatasi: $h" }
                    $isciler[$i].PS.Dispose()
                    $isciler[$i] = Isci-Baslat
                    Yaz 'isci yeniden baslatildi'
                }
            }
            Start-Sleep -Milliseconds 500
        }
    } finally {
        Kuyrugu-Bosalt
        foreach ($c in $isciler) { try { $c.PS.Stop(); $c.PS.Dispose() } catch { } }
        $havuz.Close()
    }
}

$dinleyici.Stop()
$dinleyici.Close()
$istemci.Dispose()