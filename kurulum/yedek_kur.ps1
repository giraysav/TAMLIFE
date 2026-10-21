# TAMLIFE v3.5 yedek klasoru kurulumu (bir kez / sifre degisince). Betik saf ASCII (PS 5.1). YONETICI PowerShell gerekir.
#   .\yedek_kur.ps1                    : klasoru olusturur, erisimi kisitlar, geri donus betiklerini koyar (sifre.hash yoksa sorar)
#   .\yedek_kur.ps1 -SifreDegistir     : geri donus sifresini degistirir (sifre.hash yeniden yazilir)
# NEDEN: panelden "Yedek al" tam yedegi <Dizin> altina yazar; geri donus <Dizin>\ROLLBACK\GERI_DON.bat ile, SIFRE sorularak yapilir.
# Windows klasore parola koyamaz: koruma (1) NTFS erisim kisiti (yalniz Administrators, SYSTEM ve panel hesabi), (2) geri donus
# betiginin PBKDF2 sifre ozeti ile calismasi. Parola dosyada DUZ METIN olarak TUTULMAZ, yalniz ozeti (sifre.hash) tutulur.
# Panelin bu klasore yazmasi icin canli_baslat.ps1 surece TAMLIFE_BACKUP_DIR yazar (.env'de ayni anahtar varsa o gecerli).
param([string]$Dizin = 'E:\TAMLIFE_YEDEK_KRITIK',
      [switch]$SifreDegistir)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'calisma_kimligi.ps1')
$yonetici = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $yonetici) { throw 'YONETICI (yukseltilmis) PowerShell gerekli.' }

$Geri = Join-Path $Dizin 'ROLLBACK'
New-Item -ItemType Directory -Force -Path $Geri | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot 'yedek_geri_don.ps1') (Join-Path $Geri 'geri_don.ps1')
Copy-Item -Force (Join-Path $PSScriptRoot 'yedek_geri_don.bat') (Join-Path $Geri 'GERI_DON.bat')

# Erisim: miras kapali; Administrators + SYSTEM tam, panel hesabi degistirme (yedek yazar/budar). Digerleri (Users dahil) giremez.
& icacls $Dizin /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' "${TamlifeCalismaHesabi}:(OI)(CI)M" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'icacls basarisiz.' }

$SifreDosyasi = Join-Path $Geri 'sifre.hash'
if ($SifreDegistir -or -not (Test-Path $SifreDosyasi)) {
    $bir = Read-Host 'Geri donus sifresi' -AsSecureString
    $iki = Read-Host 'Geri donus sifresi (tekrar)' -AsSecureString
    $cevir = { param($g) $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($g); try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) } }
    $p1 = & $cevir $bir; $p2 = & $cevir $iki
    if ($p1 -cne $p2 -or $p1.Length -lt 12) { throw 'Sifreler uyusmuyor ya da 12 karakterden kisa.' }
    $tuz = New-Object byte[] 16
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($tuz)
    $tur = 600000
    $kdf = New-Object Security.Cryptography.Rfc2898DeriveBytes($p1, $tuz, $tur, [Security.Cryptography.HashAlgorithmName]::SHA256)
    $ozet = $kdf.GetBytes(32)
    Set-Content -Path $SifreDosyasi -Encoding ASCII -Value ('pbkdf2-sha256${0}${1}${2}' -f $tur, [Convert]::ToBase64String($tuz), [Convert]::ToBase64String($ozet))
    $p1 = $null; $p2 = $null
    Write-Host '[+] Sifre ozeti yazildi: ' $SifreDosyasi
}
Write-Host "[+] Tamam: $Dizin (geri donus: $Geri\GERI_DON.bat)"
