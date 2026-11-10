@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Test-SwirlMihomoPath.ps1"
set "result=%ERRORLEVEL%"
echo.
if "%result%"=="0" echo SWIRL NATIVE EGRESS OBSERVED. See JSON for limits.
if "%result%"=="1" echo A LOCAL MIHOMO PATH WAS OBSERVED. See JSON.
if "%result%"=="2" echo INCONCLUSIVE. See JSON diagnostics.
echo This test does not stop Mihomo or change network settings.
pause
exit /b %result%
