@echo off
setlocal
set "report=D:\Codex\SwirlCoreMonitorData\report.html"
if not exist "%report%" (
  echo No report yet. Start the monitor first.
  pause
  exit /b 2
)
start "" "%report%"
