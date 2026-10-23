param(
    [Parameter(Mandatory=$true)][string]$BaselineExecutable,
    [Parameter(Mandatory=$true)][string]$CandidateExecutable,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [ValidateRange(3,30)][int]$Samples=10
)
$ErrorActionPreference='Stop'
$BaselineExecutable=(Resolve-Path -LiteralPath $BaselineExecutable).Path
$CandidateExecutable=(Resolve-Path -LiteralPath $CandidateExecutable).Path
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$OutputDirectory=(Resolve-Path -LiteralPath $OutputDirectory).Path
$results=@()
for($sample=0;$sample -lt $Samples;$sample++) {
    foreach($entry in @(@{label='baseline';exe=$BaselineExecutable},@{label='candidate';exe=$CandidateExecutable})) {
        $capture=Join-Path $OutputDirectory ($entry.label+'-'+$sample+'.png')
        $clock=[Diagnostics.Stopwatch]::StartNew()
        $process=Start-Process -FilePath $entry.exe -ArgumentList @('--preview-page=activity',('--capture-preview="'+$capture+'"')) -WindowStyle Hidden -PassThru
        $ready=$process.WaitForInputIdle(15000)
        $readyMs=$clock.Elapsed.TotalMilliseconds
        if(-not $process.WaitForExit(20000)) {
            Stop-Process -Id $process.Id
            throw 'Owned isolated preview did not exit within its timeout.'
        }
        $results += [pscustomobject]@{variant=$entry.label;sample=$sample;inputIdleMs=$readyMs;inputIdle=$ready;exitCode=$process.ExitCode;captureExists=(Test-Path -LiteralPath $capture)}
    }
}
$summary=@()
foreach($label in @('baseline','candidate')) {
    $rows=@($results | Where-Object variant -eq $label)
    $times=@($rows.inputIdleMs | Sort-Object)
    $summary += [pscustomobject]@{variant=$label;samples=$rows.Count;p50InputIdleMs=$times[[Math]::Floor($times.Count*.5)];p95InputIdleMs=$times[[Math]::Min($times.Count-1,[Math]::Floor($times.Count*.95))];passed=(@($rows|Where-Object {-not $_.inputIdle -or $_.exitCode -ne 0 -or -not $_.captureExists}).Count -eq 0)}
}
[pscustomobject]@{note='Fresh isolated GUI processes, interleaved. WaitForInputIdle is message-loop readiness, not cold boot, cold disk cache, first rendered frame, or input-to-photon latency. Each process self-exits via the existing capture-preview path.';summary=$summary;samples=$results}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $OutputDirectory 'startup.json') -Encoding utf8
$summary
if($summary.passed -contains $false){throw 'One or more fresh-process readiness samples failed.'}
