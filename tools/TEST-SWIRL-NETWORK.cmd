@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where pwsh.exe >nul 2>nul
if errorlevel 1 (
    echo PowerShell 7 ^(pwsh.exe^) is required on this Windows computer.
    echo No test was started. No network settings were changed.
    pause
    exit /b 2
)
pwsh.exe -NoLogo -NoProfile -File "%~dp0tools\Invoke-WindowsRustPortableCheck.ps1"
set "test_code=%errorlevel%"
echo.
echo Press any key to close this window.
pause >nul
exit /b %test_code%
