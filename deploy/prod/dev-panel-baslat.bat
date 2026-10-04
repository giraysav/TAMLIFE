@echo off
rem Yeni panel (TAMLIFE v3.5) sureci: /admin/dev arkasinda, yalniz 127.0.0.1 uzerinde.
rem Once dev-panel.env.bat dosyasini dev-panel.env.bat.ornek'ten olusturun.
setlocal
cd /d "%~dp0"
if not exist "dev-panel.env.bat" (
  echo HATA: dev-panel.env.bat yok. dev-panel.env.bat.ornek dosyasini kopyalayip doldurun.
  exit /b 1
)
call "dev-panel.env.bat"
if not defined PYTHON_EXE (
  echo HATA: dev-panel.env.bat icinde PYTHON_EXE tanimli degil.
  exit /b 1
)
if not defined TAMLIFE_SSO_SECRET (
  echo HATA: TAMLIFE_SSO_SECRET tanimli degil.
  exit /b 1
)
if not defined DEV_PANEL_PORT set DEV_PANEL_PORT=8117
cd /d "%~dp0..\..\backend"
if not exist "var" mkdir "var"
"%PYTHON_EXE%" -m alembic upgrade head
if errorlevel 1 (
  echo HATA: veritabani semasi guncellenemedi.
  exit /b 1
)
rem Oturumlar bellekte tutulur: tek surec (--workers 1). Vekil basliklari uygulama icinde dogrulanir (--no-proxy-headers).
"%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %DEV_PANEL_PORT% --workers 1 --no-proxy-headers
