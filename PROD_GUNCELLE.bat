@echo off
rem TAMLIFE - PROD sunucuda: Citrix'teki gelistirmeyi 1:1 alir (saf ASCII). Cift tiklayin; uygulama adiminda Windows onay penceresi cikar.
rem Paket: Citrix masaustundeki TAMLIFE_GONDER (Citrix'te PRODA_GONDER.bat hazirlar), \\tsclient uzerinden okunur.
rem Once dogrular ve yeni surumu canlidan ayri bir kopyada test eder; onayinizla uygular, sorun olursa geri almayi onerir.
rem Asil is: kurulum\prod_guncelle.ps1
title TAMLIFE - Prod guncelleme
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0kurulum\prod_guncelle.ps1"
exit /b %errorLevel%
