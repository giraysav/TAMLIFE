@echo off
rem TAMLIFE geri donus baslaticisi (ROLLBACK\GERI_DON.bat). Yonetici ister, geri_don.ps1'i sifre sorarak calistirir. Saf ASCII.
rem Yonetici denetimi PowerShell ile: net.exe kurumsal politikayla engelli (2026-10-25, 'Executable Blocked').
powershell.exe -NoProfile -Command "exit [int](-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))" >nul 2>&1
if errorlevel 1 (
  echo Yonetici yetkisi gerekiyor, yukseltiliyor...
  powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0geri_don.ps1" %*
echo.
pause
