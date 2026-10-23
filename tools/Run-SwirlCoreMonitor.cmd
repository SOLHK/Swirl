@echo off
setlocal
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Monitor-SwirlCore.ps1" %*
set "result=%ERRORLEVEL%"
echo This manual observation does not change proxy settings or install autostart.
pause
exit /b %result%
