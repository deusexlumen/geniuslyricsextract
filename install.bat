@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

call :find_python
if defined PYEXE goto ready

echo Python 3.10 oder neuer wurde nicht gefunden.
echo Python 3.12 wird jetzt über winget installiert.
where winget >nul 2>&1
if errorlevel 1 goto manual
winget install -e --id Python.Python.3.12 --scope user --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
if not errorlevel 1 goto refresh_path
winget install -e --id Python.Python.3.12 --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto manual

:refresh_path
set "MACHINE_PATH="
set "USER_PATH="
for /f "tokens=2,*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do if /i "%%A"=="REG_EXPAND_SZ" set "MACHINE_PATH=%%B"
for /f "tokens=2,*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do if /i "%%A"=="REG_SZ" set "MACHINE_PATH=%%B"
for /f "tokens=2,*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do if /i "%%A"=="REG_EXPAND_SZ" set "USER_PATH=%%B"
for /f "tokens=2,*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do if /i "%%A"=="REG_SZ" set "USER_PATH=%%B"
set "PATH=!MACHINE_PATH!;!USER_PATH!;!PATH!"
call :find_python
if defined PYEXE goto ready
echo Python ist in diesem Fenster noch nicht sichtbar.
echo Bitte das Fenster schließen und install.bat erneut starten.
pause
exit /b 1

:ready
echo Abhängigkeiten werden eingerichtet...
%PYEXE% -m pip install -r requirements.txt
if errorlevel 1 (
  echo Die Einrichtung der Abhängigkeiten ist fehlgeschlagen.
  pause
  exit /b 1
)
%PYEXE% web2txt.py ui
if errorlevel 1 (
  echo Der Start ist fehlgeschlagen.
  pause
  exit /b 1
)
exit /b 0

:manual
echo Die automatische Python-Installation ist nicht verfügbar oder fehlgeschlagen.
echo Bitte Python 3.10 oder neuer von https://www.python.org/downloads/ installieren
echo und dabei "Add python.exe to PATH" aktivieren.
echo Danach install.bat erneut starten.
pause
exit /b 1

:find_python
set "PYEXE="
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "PYEXE=py -3"
  exit /b 0
)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "PYEXE=python"
  exit /b 0
)
py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "PYEXE=py -3.12"
  exit /b 0
)
for %%P in ("%LocalAppData%\Programs\Python\Python312\python.exe" "%ProgramFiles%\Python312\python.exe") do (
  if exist "%%~P" (
    "%%~P" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 (
      set PYEXE="%%~P"
      exit /b 0
    )
  )
)
exit /b 1
