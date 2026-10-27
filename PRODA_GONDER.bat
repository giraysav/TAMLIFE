@echo off
rem TAMLIFE - CITRIX makinede: gelistirmeyi PROD'a gonderim paketi hazirlar (saf ASCII). Cift tiklayin; yonetici GEREKMEZ.
rem Once tum degisiklikleri commit edin. Paket Masaustu\TAMLIFE_GONDER klasorune yazilir; sonra prod sunucuda PROD_GUNCELLE.bat.
rem Asil is: kurulum\gonder_prod.ps1
title TAMLIFE - Proda gonder
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0kurulum\gonder_prod.ps1"
exit /b %errorLevel%
