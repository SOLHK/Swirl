@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Stop-SwirlCoreMonitor.ps1"
if errorlevel 1 (
  echo Monitor did not stop. See the error above.
  pause
  exit /b 1
)
echo.
pause
