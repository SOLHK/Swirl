@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "SWIRL_PWSH=%~dp0runtime\powershell\pwsh.exe"
if not exist "%SWIRL_PWSH%" (
    echo The bundled PowerShell runtime is missing. This package is incomplete.
    echo No test was started. No network settings were changed.
    pause
    exit /b 2
)
set "PATH=%~dp0runtime\powershell;%PATH%"
"%SWIRL_PWSH%" -NoLogo -NoProfile -File "%~dp0tools\Invoke-WindowsRustPortableCheck.ps1"
set "test_code=%errorlevel%"
echo.
echo Press any key to close this window.
pause >nul
exit /b %test_code%
