@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-SwirlCoreMonitor.ps1"
if errorlevel 1 (
  echo Monitor did not start. See the error above.
  pause
  exit /b 1
)
echo.
echo Monitor runs in the background. Open the report shortcut to view results.
pause
