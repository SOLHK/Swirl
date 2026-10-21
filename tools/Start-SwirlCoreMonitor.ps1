param(
    [string]$DataDirectory = 'D:\Codex\SwirlCoreMonitorData',
    [switch]$NoAutostart
)
$ErrorActionPreference='Stop'
$runner=Join-Path $PSScriptRoot 'Monitor-SwirlCore.ps1'
$powershell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if(-not (Test-Path -LiteralPath $runner -PathType Leaf)) { throw 'Monitor script is missing.' }
if(-not (Test-Path -LiteralPath $DataDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $DataDirectory -Force | Out-Null
}
$pidPath=Join-Path $DataDirectory 'monitor.pid'
if(Test-Path -LiteralPath $pidPath) {
    $existingId=0
    [void][int]::TryParse(([IO.File]::ReadAllText($pidPath)).Trim(),[ref]$existingId)
    if($existingId -gt 0) {
        $existing=Get-CimInstance Win32_Process -Filter "ProcessId=$existingId" -ErrorAction SilentlyContinue
        if($existing -and $existing.CommandLine -like '*Monitor-SwirlCore.ps1*') {
            [pscustomobject]@{status='ALREADY_RUNNING';pid=$existingId;dataDirectory=$DataDirectory} | ConvertTo-Json
            exit 0
        }
    }
}
$arguments="-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runner`" -DataDirectory `"$DataDirectory`""
if(-not $NoAutostart) {
    $run='HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    New-ItemProperty -Path $run -Name 'SwirlCoreMonitor' -Value "`"$powershell`" $arguments" -PropertyType String -Force | Out-Null
}
$started=Start-Process -FilePath $powershell -ArgumentList $arguments -PassThru -WindowStyle Hidden
$ready=$false
for($i=0;$i -lt 20;$i++) {
    if($started.HasExited) { break }
    if(Test-Path -LiteralPath $pidPath) {
        $read=([IO.File]::ReadAllText($pidPath)).Trim()
        if($read -eq [string]$started.Id) { $ready=$true;break }
    }
    Start-Sleep -Milliseconds 200
}
if(-not $ready) {
    if(-not $NoAutostart) {
        Remove-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'SwirlCoreMonitor' -ErrorAction SilentlyContinue
    }
    throw 'Monitor did not become ready.'
}
[pscustomobject]@{status='RUNNING';pid=$started.Id;dataDirectory=$DataDirectory;autostart=(-not $NoAutostart)} | ConvertTo-Json
