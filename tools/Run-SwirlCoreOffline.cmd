@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Test-SwirlCoreOffline.ps1"
set "result=%ERRORLEVEL%"
echo.
if "%result%"=="0" echo PASS: The active local proxy is the Swirl Rust build.
if "%result%"=="1" echo FAIL: Check the JSON diagnostics above.
if "%result%"=="2" echo BLOCKED: Check the JSON diagnostics above.
echo Public Shadowsocks egress was not tested; no internet request was made.
pause
exit /b %result%
