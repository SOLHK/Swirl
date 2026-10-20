# Starts the bounded worker as a separate Windows process so Codex may disconnect.
# The user must pause and later resume Mihomo manually; this launcher does neither.
param(
    [Parameter(Mandatory=$true)][string]$SwirlExe,
    [Parameter(Mandatory=$true)][string]$EncryptedStore,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$ExpectedSourceSha,
    [Parameter(Mandatory=$true)][ValidateRange(1,2147483647)][int]$MihomoPid,
    [ValidateRange(1,65535)][int]$MihomoProxyPort = 7898,
    [ValidateRange(5,1800)][int]$WaitForPauseSeconds = 600,
    [string]$WorkRoot = 'D:\Codex\Swirl-acceptance-private-20261020'
)
$ErrorActionPreference='Stop'
$worker=Join-Path $PSScriptRoot 'Invoke-WindowsRustIndependentAcceptance.ps1'
if(-not(Test-Path -LiteralPath $worker -PathType Leaf)) { throw 'Worker script missing.' }
if(-not(Test-Path -LiteralPath $WorkRoot -PathType Container)) { throw 'Private D: work root missing.' }
$workDir=Join-Path $WorkRoot ('independent-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8))
$preflightText=& $worker -SwirlExe $SwirlExe -EncryptedStore $EncryptedStore -WorkDirectory $workDir -ExpectedSourceSha $ExpectedSourceSha -MihomoPid $MihomoPid -MihomoProxyPort $MihomoProxyPort -WaitForPauseSeconds $WaitForPauseSeconds -PreflightOnly
$preflight=$preflightText | ConvertFrom-Json
if($preflight.status -ne 'PASS') {
    [pscustomobject]@{status='BLOCKED';reasonCode=$preflight.reasonCode;workerStarted=$false} | ConvertTo-Json
    return
}
$pwsh=(Get-Command pwsh -ErrorAction Stop).Source
# Windows paths cannot contain a quote. Quote every path because Start-Process
# joins ArgumentList into a single command line.
$args=@(
    '-NoProfile','-File',('"' + $worker + '"'),
    '-SwirlExe',('"' + $SwirlExe + '"'),
    '-EncryptedStore',('"' + $EncryptedStore + '"'),
    '-WorkDirectory',('"' + $workDir + '"'),
    '-ExpectedSourceSha',$ExpectedSourceSha,
    '-ExpectedExeSha256',$preflight.swirlExeSha256,
    '-ExpectedRustDllSha256',$preflight.rustDllSha256,
    '-MihomoPid',"$MihomoPid",
    '-MihomoProxyPort',"$MihomoProxyPort",
    '-WaitForPauseSeconds',"$WaitForPauseSeconds"
)
$process=Start-Process -FilePath $pwsh -ArgumentList $args -PassThru -WindowStyle Hidden
$statusPath=Join-Path $workDir 'status.json'
$deadline=[DateTime]::UtcNow.AddSeconds(30)
$state='STARTING'
while([DateTime]::UtcNow -lt $deadline) {
    if(Test-Path -LiteralPath $statusPath) {
        try {
            $status=Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
            $state=$status.state
            if($state -in @('WAITING_FOR_MIHOMO_SUSPEND','COMPLETE')) { break }
        } catch { }
    }
    if($process.HasExited) { $state='WORKER_EXITED_EARLY'; break }
    Start-Sleep -Milliseconds 250
}
if($state -eq 'WAITING_FOR_MIHOMO_SUSPEND') {
    try {
        $latest=Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
        if($process.HasExited -or $latest.state -ne 'WAITING_FOR_MIHOMO_SUSPEND') { $state='WORKER_STATE_CHANGED' }
    } catch { $state='WORKER_STATE_UNREADABLE' }
}
[pscustomobject]@{
    status=if($state -eq 'WAITING_FOR_MIHOMO_SUSPEND'){'ARMED'}elseif($state -eq 'COMPLETE' -or $state -eq 'WORKER_EXITED_EARLY'){'BLOCKED'}else{'UNKNOWN_RUNNING'}
    workerPid=$process.Id
    state=$state
    workDirectory=$workDir
    statusFile=$statusPath
    completeMarker=(Join-Path $workDir 'complete.marker')
    resultFile=(Join-Path $workDir 'result.json')
    note=if($state -eq 'WAITING_FOR_MIHOMO_SUSPEND') {
        'Recheck status.json is WAITING and worker PID is alive immediately before pausing Mihomo. Resume it manually after COMPLETE or timeout.'
    } else {
        'Do not pause Mihomo unless state is WAITING_FOR_MIHOMO_SUSPEND; inspect the worker PID and status file.'
    }
} | ConvertTo-Json
