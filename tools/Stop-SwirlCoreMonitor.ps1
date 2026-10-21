param(
    [string]$DataDirectory = 'D:\Codex\SwirlCoreMonitorData',
    [switch]$KeepAutostart
)
$ErrorActionPreference='Stop'
if(-not $KeepAutostart) {
    Remove-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'SwirlCoreMonitor' -ErrorAction SilentlyContinue
}
$pidPath=Join-Path $DataDirectory 'monitor.pid'
if(-not (Test-Path -LiteralPath $pidPath -PathType Leaf)) {
    [pscustomobject]@{status='NOT_RUNNING'} | ConvertTo-Json
    exit 0
}
$monitorId=0
if(-not [int]::TryParse(([IO.File]::ReadAllText($pidPath)).Trim(),[ref]$monitorId) -or $monitorId -lt 1) {
    throw 'Invalid monitor.pid; no process was stopped.'
}
$process=Get-CimInstance Win32_Process -Filter "ProcessId=$monitorId" -ErrorAction SilentlyContinue
if(-not $process) {
    [pscustomobject]@{status='NOT_RUNNING'} | ConvertTo-Json
    exit 0
}
if($process.Name -ine 'powershell.exe' -or $process.CommandLine -notlike '*Monitor-SwirlCore.ps1*') {
    throw 'PID is not the Swirl Core monitor; it was not stopped.'
}
[IO.File]::WriteAllText((Join-Path $DataDirectory 'stop.request'),'stop',[Text.Encoding]::ASCII)
for($i=0;$i -lt 120;$i++) {
    if(-not (Get-Process -Id $monitorId -ErrorAction SilentlyContinue)) {
        [pscustomobject]@{status='STOPPED';pid=$monitorId} | ConvertTo-Json
        exit 0
    }
    Start-Sleep -Seconds 1
}
throw 'Monitor did not stop within 120 seconds; no process was force-killed.'
