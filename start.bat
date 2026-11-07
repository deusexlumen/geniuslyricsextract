@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "PYEXE="

where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
  if not errorlevel 1 set "PYEXE=py -3"
)

if not defined PYEXE (
  where python >nul 2>&1
  if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYEXE=python"
  )
)

if not defined PYEXE (
  echo Python 3.10 oder neuer wurde nicht gefunden.
  echo Bitte zuerst install.bat doppelklicken. Das richtet Python bei Bedarf automatisch ein.
  echo Oder Python von https://www.python.org/downloads/ installieren
  echo und dabei "Add python.exe to PATH" aktivieren.
  echo.
  pause
  exit /b 1
)

%PYEXE% -c "import requests, bs4" >nul 2>&1
if errorlevel 1 (
  echo Abhängigkeiten werden eingerichtet...
  %PYEXE% -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Die Einrichtung ist fehlgeschlagen.
    pause
    exit /b 1
  )
)

%PYEXE% web2txt.py ui
if errorlevel 1 (
  echo Der Start ist fehlgeschlagen.
  pause
  exit /b 1
)
