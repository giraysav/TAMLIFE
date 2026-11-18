# Windows calisma kimligi. Uygulama kullanicilarini / DB parolasini degistirmez.
$TamlifeCalismaHesabi = 'TURKCELL\TAMLIFEADLOG'

function Tamlife-KimlikDogrula {
    $mevcut = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    # 2026-11-18: sunucu acilisinda oturumsuz kalkan TAMLIFE_Servis_Acilis gorevi SYSTEM olarak calisir (S4U kurum politikasiyla reddedilmisti).
    if ($mevcut -ieq 'NT AUTHORITY\SYSTEM') { return }
    if ($mevcut -ine $TamlifeCalismaHesabi) {
        throw "Bu islem $TamlifeCalismaHesabi ile calismali. Su an: $mevcut"
    }
}

function Tamlife-GorevKimligi {
    New-ScheduledTaskPrincipal -UserId $TamlifeCalismaHesabi -LogonType Password -RunLevel Highest
}

# 2026-10-25: hesap parolasi kurum PAM'i ile 24 saatte bir donduruluyor; parolali (Password) gorev her donusten sonra 0x8007052E ile
# baslamaz. Canli gorevler bu kimlikle kaydedilir: parola saklanmaz, hesabin acik oturumunda (RDP koparilsa da) yuksek yetkiyle kosar.
function Tamlife-OturumKimligi {
    New-ScheduledTaskPrincipal -UserId $TamlifeCalismaHesabi -LogonType Interactive -RunLevel Highest
}

function Tamlife-GorevKimlikBilgisi {
    # 2026-10-25: Get-Credential penceresi uzak masaustu / yukseltilmis oturumda acilmadan $null donuyordu; parola konsoldan sorulur.
    Write-Host ('TAMLIFE Windows gorevleri icin ' + $TamlifeCalismaHesabi + ' etki alani parolasi (DB parolasi degildir; bos = iptal).')
    $gizli = Read-Host -AsSecureString -Prompt 'Parola'
    if ($null -eq $gizli -or $gizli.Length -eq 0) { throw 'Parola girilmedi. Gorevler degistirilmedi.' }
    $bilgi = New-Object System.Management.Automation.PSCredential($TamlifeCalismaHesabi, $gizli)
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
