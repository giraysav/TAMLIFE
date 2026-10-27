@echo off
rem TAMLIFE - Citrix gelistirme kurulumu (saf ASCII). Masaustu\TAMLIFE_PAKET icinde cift tiklayin; yonetici GEREKMEZ.
rem Paketi dogrular, yerelde acar, Masaustu\TAMLIFE\TAMLIFE_v3.5 klasorunu gunceller. Asil is: kur_citrix.ps1 (ayni klasorde).
title TAMLIFE - Citrix kurulumu
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0kur_citrix.ps1"
exit /b %errorLevel%
