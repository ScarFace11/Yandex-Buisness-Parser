@echo off
rem ══════════════════════════════════════════════════════════════
rem  Build the Windows installer (Inno Setup) from the PyInstaller
rem  output in dist\YandexBusinessParser\.
rem
rem  Prerequisites:
rem    - build.bat has produced dist\YandexBusinessParser\
rem    - Inno Setup 6 is installed (winget install JRSoftware.InnoSetup)
rem
rem  Result: dist\YandexBusinessParser-windows-x64-setup.exe
rem ══════════════════════════════════════════════════════════════
setlocal

if not exist "dist\YandexBusinessParser\YandexBusinessParser.exe" (
    echo [!] dist\YandexBusinessParser\YandexBusinessParser.exe not found.
    echo     Run build.bat first.
    exit /b 1
)

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo [!] Inno Setup 6 not found.
    echo     Install it with: winget install JRSoftware.InnoSetup
    exit /b 1
)

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
for /f "usebackq delims=" %%v in (`%PY% -c "import config; print(config.APP_VERSION)"`) do set "VERSION=%%v"
if "%VERSION%"=="" (
    echo [!] Could not read APP_VERSION from config.py
    exit /b 1
)

echo [1/2] Building installer for v%VERSION%...
"%ISCC%" "/DMyAppVersion=%VERSION%" "installer\windows.iss" || exit /b 1

echo [2/2] Done: dist\YandexBusinessParser-windows-x64-setup.exe
endlocal
