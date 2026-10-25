# Windows calisma kimligi. Uygulama kullanicilarini / DB parolasini degistirmez.
$TamlifeCalismaHesabi = 'TURKCELL\TAMLIFEADLOG'

function Tamlife-KimlikDogrula {
    $mevcut = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    if ($mevcut -ine $TamlifeCalismaHesabi) {
        throw "Bu islem $TamlifeCalismaHesabi ile calismali. Su an: $mevcut"
    }
}

function Tamlife-GorevKimligi {
    New-ScheduledTaskPrincipal -UserId $TamlifeCalismaHesabi -LogonType Password -RunLevel Highest
}

function Tamlife-GorevKimlikBilgisi {
    $bilgi = Get-Credential -UserName $TamlifeCalismaHesabi -Message 'TAMLIFE Windows gorevleri icin hesap parolasini girin. DB parolasi degildir.'
    if ($null -eq $bilgi) { throw 'Parola penceresi iptal edildi (ya da kapatildi). Gorevler degistirilmedi.' }
    # Kullanici adi TURKCELL\TAMLIFEADLOG, TAMLIFEADLOG ya da TAMLIFEADLOG@... yazilabilir; hepsi ayni hesap.
    $girilen = $bilgi.UserName.Trim()
    if ($girilen.Contains('\')) { $girilen = $girilen.Split('\')[1] }
    if ($girilen.Contains('@')) { $girilen = $girilen.Split('@')[0] }
    if ($girilen -ine $TamlifeCalismaHesabi.Split('\')[1]) {
        throw ('Hesap farkli: ' + $bilgi.UserName + ' girildi, ' + $TamlifeCalismaHesabi + ' bekleniyor. Gorevler degistirilmedi.')
    }
    # 2026-10-23: eskimis parola gorev kaydina yazilinca acilista 0x8007052E (oturum acilamadi) ile hicbir gorev baslamiyordu.
    # Kayittan ONCE etki alaninda dogrulanir; yanlissa hicbir gorev degismez.
    Add-Type -AssemblyName System.DirectoryServices.AccountManagement
    $alan, $ad = $TamlifeCalismaHesabi.Split('\')
    $baglam = New-Object System.DirectoryServices.AccountManagement.PrincipalContext('Domain', $alan)
    try {
        if (-not $baglam.ValidateCredentials($ad, $bilgi.GetNetworkCredential().Password)) {
            throw 'Parola etki alaninda dogrulanamadi. Gorevler degistirilmedi.'
        }
    } finally { $baglam.Dispose() }
    return $bilgi
}
