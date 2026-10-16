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
    return $bilgi
}
