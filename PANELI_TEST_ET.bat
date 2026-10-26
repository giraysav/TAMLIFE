@echo off
setlocal
rem TAMLIFE v3.5 - PANELI TEST ET (saf ASCII). Cift tiklayin; yonetici olmaniz GEREKMEZ.
rem 1) Paneli uctan uca test eder (canli sistem, veritabani, baglantilar, tum arka uc ve arayuz testleri; ~10 dk). Canli veriye dokunmaz.
rem 2) Rapor Not Defteri'nde acilir. HATA varsa Claude Code'a analiz [A] ya da analiz + duzeltme [D] yaptirmayi sorar.
rem 3) Sonda "yeniden baslatayim mi?" diye sorar. Evet derseniz veritabani yedegi alinir, Windows onay penceresi cikar
rem    (yonetici), panel + TLS vekili + ReportDB iscisi yeniden baslar ve tekrar denetlenir.
rem Asil is: kurulum\panel_testi.ps1. Raporlar: var\log\panel_testi\<zaman>\

title TAMLIFE - Panel testi
set "BETIK=%~dp0kurulum\panel_testi.ps1"
if not exist "%BETIK%" (
    echo [!] Betik bulunamadi: %BETIK%
    pause
    exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BETIK%"
exit /b %errorLevel%
