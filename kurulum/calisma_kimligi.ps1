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
    if ($null -eq $bilgi -or $bilgi.UserName -ine $TamlifeCalismaHesabi) {
        throw 'Kimlik bilgisi iptal edildi veya hesap farkli. Gorevler degistirilmedi.'
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
