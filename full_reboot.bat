@echo off
setlocal
rem TAMLIFE v3.5 - elle TAM yeniden baslatma (saf ASCII).
rem Calisan panel, TLS vekili ve donguleri durdurur; panel, vekil ve ReportDB gorevlerini baslatir ve GERCEKTEN
rem basladiklarini dogrular. Gorev hesap parolasi gecersizse (0x8007052E) parolayi yenilemeyi onerir; yenilenmezse
rem paneli ve vekili dogrudan surec olarak acar (bir sonraki sunucu yeniden baslatmasina kadar). Sonda saglik denetimi.
rem Asil is: kurulum\canli_gorev_kur.ps1 -YenidenBaslat (bu dosya depo kokunde, TAMLIFE_v3.5\full_reboot.bat)
rem   full_reboot.bat /oto : sorusuz (pause yok); gece senkronu (kurulum\gece_sync.ps1) panel acilmazsa boyle cagirir.

set "BETIK=%~dp0kurulum\canli_gorev_kur.ps1"
set "OTO="
if /i "%~1"=="/oto" set "OTO=1"

echo ========================================================
echo TAMLIFE v3.5 - Sistem Yeniden Baslatma
echo ========================================================

rem Yonetici denetimi PowerShell ile: net.exe kurumsal politikayla engelli (2026-10-25, 'Executable Blocked').
powershell.exe -NoProfile -Command "exit [int](-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))" >nul 2>&1
if %errorLevel% neq 0 (
    echo [!] HATA: Yonetici yetkisi gerekli. Dosyaya sag tiklayip "Yonetici olarak calistir" secin.
    if not defined OTO pause
    exit /b 1
)

if not exist "%BETIK%" (
    echo [!] HATA: Betik bulunamadi: %BETIK%
    if not defined OTO pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BETIK%" -YenidenBaslat
set "KOD=%errorLevel%"

echo ========================================================
if "%KOD%"=="0" (
    echo [OK] Panel calisiyor ve gorevler acilista otomatik baslayacak.
) else if "%KOD%"=="2" (
    echo [!] Panel ACIK ama gorevlerle degil: sunucu yeniden baslayinca kapanir.
    echo     Kalici cozum: Yonetici PowerShell'de
    echo     "%BETIK%" -Hemen
) else (
    echo [!] Panel acilamadi ^(kod %KOD%^). Ayrinti yukarida.
)
echo Adres: https://tamlife/
echo ========================================================
if not defined OTO pause
exit /b %KOD%
