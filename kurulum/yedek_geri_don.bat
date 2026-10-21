@echo off
rem TAMLIFE geri donus baslaticisi (ROLLBACK\GERI_DON.bat). Yonetici ister, geri_don.ps1'i sifre sorarak calistirir. Saf ASCII.
net session >nul 2>&1
if errorlevel 1 (
  echo Yonetici yetkisi gerekiyor, yukseltiliyor...
  powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0geri_don.ps1" %*
echo.
pause
