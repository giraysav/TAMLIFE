# ASCII. Cacti LDAP only; does not change Windows task credentials.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'calisma_kimligi.ps1')
Tamlife-KimlikDogrula
$projeKoku = Split-Path $PSScriptRoot -Parent
$pythonYolu = Join-Path $projeKoku '.venv\Scripts\python.exe'
$aracYolu = Join-Path $projeKoku 'backend\araclar\cacti_kimlik_koru.py'
$bilgi = Get-Credential -Message 'Cacti / Lookouteyes LDAP hesabi. Windows gorev veya DB parolasi degildir.'
if ($null -eq $bilgi) { return }
$ptr = [IntPtr]::Zero
$parolaBaytlari = $null
$kullaniciBaytlari = $null
try {
    Add-Type -AssemblyName System.Security
    $kapsam = [Security.Cryptography.DataProtectionScope]::CurrentUser
    $kullaniciBaytlari = [Text.Encoding]::UTF8.GetBytes($bilgi.UserName)
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($bilgi.Password)
    $parolaBaytlari = [Text.Encoding]::UTF8.GetBytes([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr))
    $sifreli = @{
        TAMLIFE_CACTI_USERNAME_DPAPI = [Convert]::ToBase64String([Security.Cryptography.ProtectedData]::Protect($kullaniciBaytlari, $null, $kapsam))
        TAMLIFE_CACTI_PASSWORD_DPAPI = [Convert]::ToBase64String([Security.Cryptography.ProtectedData]::Protect($parolaBaytlari, $null, $kapsam))
    }
    # Only ciphertext travels through the pipe; no plaintext file or arguments.
    $sifreli | ConvertTo-Json -Compress | & $pythonYolu $aracYolu --sifreli-girdi
    if ($LASTEXITCODE -ne 0) { throw 'Kimlik kaydi tamamlanamadi.' }
} catch {
    throw 'Cacti kimlik kaydi basarisiz. Hesabi, DPAPI profilini ve dosya erisimini kontrol edin.'
} finally {
    if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    if ($null -ne $parolaBaytlari) { [Array]::Clear($parolaBaytlari, 0, $parolaBaytlari.Length) }
    if ($null -ne $kullaniciBaytlari) { [Array]::Clear($kullaniciBaytlari, 0, $kullaniciBaytlari.Length) }
    $bilgi = $null
    $sifreli = $null
}
