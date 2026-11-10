#Requires -Version 7.4
param(
    [Parameter(Mandatory)][string]$RepositoryRoot,
    [Parameter(Mandatory)][string]$RuntimeDirectory,
    [Parameter(Mandatory)][string]$ReferenceExecutable,
    [Parameter(Mandatory)][string]$OriginalReceipt,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [Parameter(Mandatory)][string]$ScratchRoot,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$ExecutingWorkflowSha,
    [string]$ExecutingPrHeadSha = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $IsWindows) { throw 'This pinned diagnostic requires Windows.' }
$sourceSha = 'c30304a9946b95de2563a978d1ce9538b6d61485'
$developmentSha = '88cd225c6c7284e3701ac67c547e574be259c2b0'
$caseScriptHash = '096e52980f6bb1eb6c60ca240fd9d76e0684591640cb081861d6344b1106d396'
$exeHash = 'befabbed6b8879228067a695cfe67350878aea40197ebb3ef2a7ed81f3103a37'
$scratch = (Resolve-Path -LiteralPath $ScratchRoot).Path.TrimEnd('\','/')
$stage = Join-Path $scratch ('swirl-pinned-d3d-etw-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
$profileName = 'SwirlD3D88cd' + [guid]::NewGuid().ToString('N')
$report = [ordered]@{
    schema=1; scope='One pinned old-source diagnostic; never replaces the original failure or current-source gates.'
    executing_workflow_sha=$ExecutingWorkflowSha; executing_pr_head_sha=$ExecutingPrHeadSha
    tested_source_sha=$sourceSha; tested_development_sha=$developmentSha
    original_run_id=42277110326; original_job_id=128096155298; original_failure_retained=$true
    replaces_critical_result=$false; planned_original_script_invocations=1; native_case_order=@(2,1)
    collection_status='not-started'; native_status='not-run'; native_exit_code=$null
    native_stop_request_elapsed_ms=$null; native_exit_observed_elapsed_ms=$null
    trace_coverage_status='unverified'; publication_status='not-published'; root_cause_status='not-established'
    xml_export_complete=$false; filter_complete=$false; filter=$null
    trace_stop_request_target_ms=55000; native_wrapper_limit_ms=210000; original_case_deadline_ms=90000
    configured_trace_memory_bytes=268435456; xml_limit_bytes=536870912; xml_deadline_ms=60000
    process_thread_provider_enabled=$false; process_start_coverage_claimed=$false
    trace_start_attempted=$false; trace_started=$false; trace_retirement_confirmed=$false
    staging_directory=$stage; profile_name=$profileName; started_utc=[DateTime]::UtcNow.ToString('o')
    tools=[Collections.Generic.List[object]]::new(); errors=[Collections.Generic.List[string]]::new()
    trace_stop_attempts=[Collections.Generic.List[object]]::new()
}
$child=$null; $childOut=$null; $childErr=$null; $childClock=$null; $nativeOutput=$null; $output=$null
$childExited=$true; $wpr=$null; $traceClock=$null; $traceStopAttempted=$false
$etl=Join-Path $stage 'pinned-88cd.etl'; $xml=Join-Path $stage 'events.private.xml'
$public=Join-Path $stage 'public'; New-Item -ItemType Directory -Path $public | Out-Null

function Write-EtwJson([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path, (ConvertTo-Json -InputObject $Value -Depth 40), [Text.UTF8Encoding]::new($false))
}
function Etw-Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Assert-EtwPlainPath([string]$Path) {
    $current=[IO.Path]::GetFullPath($Path)
    while ($current) {
        if ((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Linked diagnostic paths are not admitted.' }
        $parent=[IO.Path]::GetDirectoryName($current.TrimEnd('\','/'))
        if ($parent -eq $current) { break }; $current=$parent
    }
}
function Invoke-EtwTool([string]$Name,[string]$File,[string[]]$Arguments,[int]$DeadlineMs=15000,[string]$GrowthPath='',[long]$GrowthLimit=0) {
    $prefix=('{0:000}-{1}' -f ($report.tools.Count+1),$Name)
    $row=[ordered]@{name=$Name;file=$File;arguments=$Arguments;stdout_file=($prefix+'.stdout.log');stderr_file=($prefix+'.stderr.log');started_utc=[DateTime]::UtcNow.ToString('o');exit_code=$null;timed_out=$false;growth_limit_reached=$false;exit_confirmed=$false;errors=@();elapsed_ms=0}
    $report.tools.Add($row); $process=$null; $outTask=$null; $errTask=$null; $clock=[Diagnostics.Stopwatch]::StartNew()
    $errors=[Collections.Generic.List[string]]::new(); $textOut=''; $textErr=''
    try {
        $info=[Diagnostics.ProcessStartInfo]::new(); $info.FileName=$File; $info.UseShellExecute=$false
        $info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true; $info.WorkingDirectory=$stage
        foreach ($arg in $Arguments) { $info.ArgumentList.Add($arg) }
        $process=[Diagnostics.Process]::new(); $process.StartInfo=$info
        if (-not $process.Start()) { throw 'Native diagnostic tool did not start.' }
        $outTask=$process.StandardOutput.ReadToEndAsync(); $errTask=$process.StandardError.ReadToEndAsync()
        while (-not $process.WaitForExit(100)) {
            if ($GrowthPath -and (Test-Path -LiteralPath $GrowthPath) -and (Get-Item -LiteralPath $GrowthPath).Length -ge $GrowthLimit) { $row.growth_limit_reached=$true; break }
            if ($clock.ElapsedMilliseconds -ge $DeadlineMs) { $row.timed_out=$true; break }
        }
    } catch { $errors.Add('execute:' + $_.Exception.GetType().Name) }
    finally {
        if ($process) {
            try { if (-not $process.HasExited) { $process.Kill($true) }; $row.exit_confirmed=$process.WaitForExit(5000); if ($row.exit_confirmed) { $row.exit_code=$process.ExitCode } }
            catch { $errors.Add('cleanup:' + $_.Exception.GetType().Name); $row.exit_confirmed=$false }
        }
        foreach ($item in @(@{task=$outTask;kind='stdout'},@{task=$errTask;kind='stderr'})) {
            try {
                if ($item.task -and $item.task.Wait(1000)) {
                    $value=$item.task.Result
                    [IO.File]::WriteAllText((Join-Path $stage ($prefix + '.' + $item.kind + '.log')),$value,[Text.UTF8Encoding]::new($false))
                    if ($item.kind -eq 'stdout') { $textOut=$value } else { $textErr=$value }
                }
            } catch { $errors.Add('capture-' + $item.kind + ':' + $_.Exception.GetType().Name) }
        }
        if ($process) { $process.Dispose() }; $clock.Stop(); $row.elapsed_ms=$clock.Elapsed.TotalMilliseconds
        $row.errors=$errors.ToArray(); Write-EtwJson (Join-Path $stage 'receipt.private.json') $report
    }
    return @{record=$row;stdout=$textOut;stderr=$textErr;ok=($row.exit_confirmed -and $row.exit_code -eq 0 -and -not $row.timed_out -and -not $row.growth_limit_reached -and $errors.Count -eq 0)}
}
function Get-EtwState([string]$Name) {
    $state=Invoke-EtwTool $Name $wpr @('-status','profiles')
    $text=$state.stdout + $state.stderr
    # Microsoft's documented -status profiles format is "Profile : CPU.Verbose.Memory".
    # Never infer ownership from an arbitrary occurrence of our name in the output.
    $profileLines=@($text -split '\r?\n' | Where-Object { $_ -match '^\s*Profile\s*:' })
    $profiles=[Collections.Generic.List[string]]::new(); $unrecognized=$false
    foreach ($line in $profileLines) {
        if ($line -cmatch '^\s*Profile\s*:\s*(\S+\.(?:Light|Verbose)\.(?:Memory|File))\s*$') { $profiles.Add($Matches[1]) }
        else { $unrecognized=$true }
    }
    return @{inactive=($text -match '(?i)WPR is not recording' -and $state.ok -and $profileLines.Count -eq 0); owned=($state.ok -and -not $unrecognized -and $profiles.Count -eq 1 -and $profiles[0] -ceq ($profileName + '.Verbose.Memory')); raw=$state}
}
function Stop-OwnedEtw {
    $script:traceStopAttempted=$true
    $attempt=[ordered]@{decision_elapsed_ms=$traceClock.Elapsed.TotalMilliseconds;stop_command_elapsed_ms=$null;retirement_observed_elapsed_ms=$null;owned=$false}
    $report.trace_stop_attempts.Add($attempt)
    $state=Get-EtwState 'trace-state-before-stop'
    if ($state.inactive) { $report.trace_retirement_confirmed=$true; $attempt.retirement_observed_elapsed_ms=$traceClock.Elapsed.TotalMilliseconds; return }
    if (-not $state.owned) { $report.errors.Add('Trace ownership is unconfirmed; no stop/cancel was sent.'); return }
    $attempt.owned=$true
    $null=Invoke-EtwTool 'trace-final-collectors' $wpr @('-status','collectors','-details')
    $attempt.stop_command_elapsed_ms=$traceClock.Elapsed.TotalMilliseconds
    $stop=Invoke-EtwTool 'trace-stop' $wpr @('-stop',$etl,'Pinned88cd unchanged D3D diagnostic','-skipPdbGen','-compress') 30000
    $after=Get-EtwState 'trace-state-after-stop'
    $report.trace_retirement_confirmed=$after.inactive
    if ($after.inactive) { $attempt.retirement_observed_elapsed_ms=$traceClock.Elapsed.TotalMilliseconds }
    if ($stop.ok -and $after.inactive -and (Test-Path -LiteralPath $etl) -and (Get-Item -LiteralPath $etl).Length -gt 0) { $report.collection_status=if ($report.trace_started) { 'collected' } else { 'failed-start-retired' } }
    else {
        $report.collection_status='failed-or-partial'
        if ($after.owned) {
            $null=Invoke-EtwTool 'trace-cancel-owned-after-failed-stop' $wpr @('-cancel')
            $report.trace_retirement_confirmed=(Get-EtwState 'trace-state-after-owned-cancel').inactive
            if ($report.trace_retirement_confirmed) { $attempt.retirement_observed_elapsed_ms=$traceClock.Elapsed.TotalMilliseconds }
        }
    }
}

try {
    if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or $env:GITHUB_REPOSITORY -cne 'SOLHK/Swirl' -or $env:SWIRL_PINNED_D3D_ETW -cne '1') { throw 'This diagnostic requires the explicit isolated GitHub-hosted SOLHK/Swirl opt-in.' }
    $repo=(Resolve-Path -LiteralPath $RepositoryRoot).Path.TrimEnd('\','/')
    $runtime=(Resolve-Path -LiteralPath $RuntimeDirectory).Path.TrimEnd('\','/')
    $reference=(Resolve-Path -LiteralPath $ReferenceExecutable).Path
    $original=(Resolve-Path -LiteralPath $OriginalReceipt).Path
    $output=[IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\','/')
    foreach ($path in @($repo,$runtime,$reference,$original,$output,$scratch,$stage)) { Assert-EtwPlainPath $path }
    if (-not $output.StartsWith((Join-Path $repo 'build-evidence') + '\',[StringComparison]::OrdinalIgnoreCase) -or $scratch.StartsWith($repo + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Use build-evidence output and external temporary staging.' }
    $nativeOutput=Join-Path $output 'native'
    if ((Test-Path -LiteralPath $nativeOutput) -or (Test-Path -LiteralPath (Join-Path $output 'trace'))) { throw 'Existing diagnostic evidence will not be overwritten.' }
    New-Item -ItemType Directory -Path $output -Force | Out-Null
    if ((Etw-Hash $original) -cne 'c2c4784c5e4d69185d22be325943b5a7fdf5bdc8997eb41ca24794ddbd4aa073') { throw 'Original failed-run receipt hash differs.' }
    $baseline=Get-Content -LiteralPath $original -Raw -Encoding utf8 | ConvertFrom-Json
    if ($baseline.sourceSha -cne $sourceSha -or $baseline.pullRequestHeadSha -cne $developmentSha -or $baseline.status -cne 'failed') { throw 'Original receipt identifies a different source or verdict.' }
    . (Join-Path $repo 'scripts/Assert-BuildSource.ps1')
    Assert-SwirlBuildSource -RepositoryRoot $repo -ExpectedSourceSha $sourceSha
    $caseScript=Join-Path $repo 'scripts/Test-QtD3D11FrameLatency.ps1'
    if ((Etw-Hash $caseScript) -cne $caseScriptHash) { throw 'The original native diagnostic script changed.' }
    foreach ($entry in $baseline.sourceFileSha256.PSObject.Properties) {
        if ((Etw-Hash (Join-Path $repo $entry.Name)) -cne [string]$entry.Value) { throw 'Pinned source file differs from the original receipt.' }
    }
    $critical=@{'Swirl.exe'=$exeHash;'swirl_api.dll'='91e10ef45f20e85530ad4723da50e79a59037dab05883c2fd398333514f9eace';'swirl-rust-build.json'='8ef2c892856a8f9a7f23ea3c740128c80c407a2e7acc73855b4ef76af43e03b7';'Qt6Gui.dll'='37c79b48b9cc2d9a03d21410c26fea683d236f9280f5c9aaab85d980759f2835';'Qt6Quick.dll'='6d9b5639e8cad3b01083fc7c8c838b09d9f2d04a38cc4c339ddc3973123d5fa8'}
    foreach ($entry in $critical.GetEnumerator()) { if ((Etw-Hash (Join-Path $runtime $entry.Key)) -cne $entry.Value) { throw 'Admitted runtime critical hash changed.' } }
    if ((Etw-Hash $reference) -cne $exeHash -or [Diagnostics.FileVersionInfo]::GetVersionInfo((Join-Path $runtime 'Qt6Core.dll')).FileVersion -cne '6.12.0.0') { throw 'Original EXE or Qt version differs.' }
    $report.critical_runtime_sha256=$critical; $report.original_receipt_sha256=Etw-Hash $original
    $report.original_script_sha256=$caseScriptHash
    $filterScript=Join-Path $PSScriptRoot 'Test-PinnedD3D11EtwFilter.ps1'
    if (-not (Test-Path -LiteralPath $filterScript -PathType Leaf)) { throw 'The bounded trace publication filter is missing.' }
    $report.collector_script_sha256=Etw-Hash $PSCommandPath; $report.filter_script_sha256=Etw-Hash $filterScript
    # Exercise publication refusal with synthetic input before any system trace.
    $cleanEvents='<Event><System><Provider Name="Microsoft-Windows-DXGI"/><Execution ProcessID="101" ThreadID="202"/><EventID>1</EventID><TimeCreated RawTime="1"/></System><EventData><Data Name="SwapChain">0x123</Data></EventData></Event><Event><System><Provider Name="Windows Kernel Trace"/><Execution ProcessID="0" ThreadID="0"/><EventID>2</EventID></System><EventData><Data Name="OldThreadId">202</Data><Data Name="NewThreadId">303</Data></EventData></Event><Event><System><Provider Name="Windows Kernel Trace"/><Execution ProcessID="0" ThreadID="0"/><EventID>3</EventID></System><EventData><Data Name="TThreadId">202</Data></EventData></Event><Event><System><Provider Name="Windows Kernel Trace"/><Execution ProcessID="0" ThreadID="0"/><EventID>4</EventID></System><EventData><Data Name="StackProcess">101</Data><Data Name="StackThread">202</Data><Data Name="EventTimeStamp">1</Data></EventData></Event>'
    $unsafeEvents='<Event><System><Provider Name="SyntheticTarget"/><Execution ProcessID="101" ThreadID="202"/></System><EventData><Data Name="CommandLine">SYNTHETIC_ONLY_CMDLINE</Data></EventData></Event><Event><System><Provider Name="SyntheticTarget"/><Execution ProcessID="101" ThreadID="202"/></System><EventData><Binary>0a</Binary></EventData></Event>'
    $filterChecks=[Collections.Generic.List[object]]::new()
    foreach ($kind in @('clean','refuse')) {
        $fixture=Join-Path $stage ('filter-' + $kind + '.xml'); $testOutput=Join-Path $stage ('filter-' + $kind)
        $body=if ($kind -eq 'clean') { $cleanEvents } else { $cleanEvents+$unsafeEvents }
        [IO.File]::WriteAllText($fixture,('<Events>'+$body+'</Events>'),[Text.UTF8Encoding]::new($false))
        $check=& $filterScript -XmlPath $fixture -OutputDirectory $testOutput -ProcessIds @(101)
        $expected=$check.complete -and $check.retained_events -eq 4 -and $check.target_threads.Count -eq 1
        if ($kind -eq 'clean') { $expected=$expected -and $check.command_line_fields -eq 0 -and $check.opaque_events -eq 0 }
        else { $expected=$expected -and $check.command_line_fields -gt 0 -and $check.opaque_events -eq 1 -and -not ([IO.File]::ReadAllText((Join-Path $testOutput 'target-events.jsonl')).Contains('SYNTHETIC_ONLY_CMDLINE')) }
        $filterChecks.Add([ordered]@{kind=$kind;passed=$expected;result=$check})
        if (-not $expected) { throw 'The actual trace publication filter failed its synthetic positive or negative control.' }
    }
    Write-EtwJson (Join-Path $public 'filter-self-check.json') $filterChecks.ToArray()
    $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'ETW requires this disposable runner elevated token.' }
    $wpt=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\Windows Performance Toolkit'
    $wpr=Join-Path $wpt 'wpr.exe'; if (-not (Test-Path -LiteralPath $wpr -PathType Leaf)) { $wpr=(Get-Command wpr.exe -ErrorAction Stop).Source }
    $logman=(Get-Command logman.exe -ErrorAction Stop).Source; $tracerpt=(Get-Command tracerpt.exe -ErrorAction Stop).Source
    $pwsh=(Get-Process -Id $PID).Path
    $report.tool_identity=@($wpr,$logman,$tracerpt,$pwsh | ForEach-Object { [ordered]@{path=$_;sha256=(Etw-Hash $_);version=[Diagnostics.FileVersionInfo]::GetVersionInfo($_).FileVersion;signature=[string](Get-AuthenticodeSignature -LiteralPath $_).Status} })
    $before=Get-EtwState 'preflight-wpr-state'
    if (-not $before.inactive) { throw 'An existing or unidentifiable WPR recording blocks this diagnostic.' }
    $sessions=Invoke-EtwTool 'preflight-etw-sessions' $logman @('query','-ets')
    if (-not $sessions.ok -or $sessions.stdout -match '(?im)^\s*NT Kernel Logger\s') { throw 'A conflicting or unidentifiable kernel trace blocks this diagnostic.' }
    # Circular Kernel Context Logger is a system session, not owned by this script.
    foreach ($provider in @('Microsoft-Windows-DXGI','Microsoft-Windows-DxgKrnl')) {
        $query=Invoke-EtwTool ('provider-' + $provider) $logman @('query','providers',$provider)
        if (-not $query.ok) { throw 'A required ETW provider is unavailable.' }
    }
    $captureProfilePath=Join-Path $stage 'capture.wprp'
    $profileText=@'
<?xml version="1.0" encoding="utf-8"?>
<WindowsPerformanceRecorder Version="1.0" Author="Swirl"><Profiles>
<SystemCollector Id="SystemCollector" Name="NT Kernel Logger"><BufferSize Value="128"/><Buffers Value="1024"/></SystemCollector>
<EventCollector Id="EventCollector" Name="PROFILEEvents"><BufferSize Value="128"/><Buffers Value="1024"/></EventCollector>
<SystemProvider Id="SystemProvider"><Keywords><Keyword Value="Loader"/><Keyword Value="CSwitch"/><Keyword Value="ReadyThread"/></Keywords><Stacks><Stack Value="CSwitch"/><Stack Value="ReadyThread"/></Stacks></SystemProvider>
<EventProvider Id="DXGI" Name="Microsoft-Windows-DXGI" Level="5" Strict="true" ProcessExeFilter="Swirl.exe"><Keywords><Keyword Value="0xffffffffffffffff"/></Keywords></EventProvider>
<EventProvider Id="DxgKrnl" Name="Microsoft-Windows-DxgKrnl" Level="5" Strict="true"><Keywords><Keyword Value="0xffffffffffffffff"/></Keywords></EventProvider>
<Profile Id="PROFILE.Verbose.Memory" Name="PROFILE" Description="Pinned old-source D3D submission diagnosis" LoggingMode="Memory" DetailLevel="Verbose"><Collectors>
<SystemCollectorId Value="SystemCollector"><SystemProviderId Value="SystemProvider"/></SystemCollectorId>
<EventCollectorId Value="EventCollector"><EventProviders><EventProviderId Value="DXGI"/><EventProviderId Value="DxgKrnl"/></EventProviders></EventCollectorId>
</Collectors></Profile></Profiles></WindowsPerformanceRecorder>
'@
    [IO.File]::WriteAllText($captureProfilePath,$profileText.Replace('PROFILE',$profileName),[Text.UTF8Encoding]::new($false))
    $validation=Invoke-EtwTool 'preflight-custom-profile' $wpr @('-profiles',$captureProfilePath)
    if (-not $validation.ok -or -not $validation.stdout.Contains($profileName)) { throw 'Installed WPR did not validate the bounded custom profile.' }
    $report.profile_sha256=Etw-Hash $captureProfilePath
    $report.trace_start_attempted=$true; $traceClock=[Diagnostics.Stopwatch]::StartNew()
    $start=Invoke-EtwTool 'trace-start' $wpr @('-start',($captureProfilePath + '!' + $profileName))
    # A start timeout can leave a recording active. Always query ownership before cleanup.
    $startedState=Get-EtwState 'trace-state-after-start'
    if (-not $start.ok -or -not $startedState.owned) { throw 'Trace start or unique recording ownership was not confirmed.' }
    $report.trace_started=$true; $report.collection_status='recording'
    $info=[Diagnostics.ProcessStartInfo]::new(); $info.FileName=$pwsh; $info.UseShellExecute=$false; $info.WorkingDirectory=$repo
    $info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true
    foreach ($arg in @('-NoProfile','-NonInteractive','-File',$caseScript,'-RepositoryRoot',$repo,'-RuntimeDirectory',$runtime,'-ReferenceExecutable',$reference,'-OutputDirectory',$nativeOutput,'-ScratchRoot',$scratch,'-WorkflowSha',$sourceSha,'-PullRequestHeadSha',$developmentSha)) { $info.ArgumentList.Add($arg) }
    $child=[Diagnostics.Process]::new(); $child.StartInfo=$info
    $report.native_status='running'; $report.native_launch_qpc=[Diagnostics.Stopwatch]::GetTimestamp(); $report.qpc_frequency=[Diagnostics.Stopwatch]::Frequency
    if (-not $child.Start()) { throw 'The original native driver did not start.' }; $childExited=$false
    $childOut=$child.StandardOutput.ReadToEndAsync(); $childErr=$child.StandardError.ReadToEndAsync()
    $childClock=[Diagnostics.Stopwatch]::StartNew()
    while (-not $child.WaitForExit(200)) {
        if (-not $traceStopAttempted -and $traceClock.ElapsedMilliseconds -ge 55000) { $report.trace_coverage_status='stop-request-target-reached; actual retirement and per-case event coverage must be verified'; Stop-OwnedEtw }
        if ($childClock.ElapsedMilliseconds -ge 210000) { $report.native_status='wrapper-timeout'; throw 'The original two-case driver exceeded the wrapper bound.' }
    }
    $childExited=$true; $report.native_exit_code=$child.ExitCode; $report.native_exit_observed_elapsed_ms=$childClock.Elapsed.TotalMilliseconds
    if (-not $traceStopAttempted) { $report.trace_coverage_status='driver-completed-during-capture; event-loss and frame coverage unverified'; Stop-OwnedEtw }
    $nativeReceipt=Join-Path $nativeOutput 'receipt.json'
    if (-not (Test-Path -LiteralPath $nativeReceipt -PathType Leaf)) { throw 'The original driver receipt is missing.' }
    $native=Get-Content -LiteralPath $nativeReceipt -Raw -Encoding utf8 | ConvertFrom-Json
    $report.native_receipt_sha256=Etw-Hash $nativeReceipt
    if ($native.sourceSha -cne $sourceSha -or $native.executableSha256 -cne $exeHash -or @($native.cases).Count -ne 2 -or -not $native.originalEvidenceUnchanged) { throw 'The original native identity, two-case scope, or protected evidence check failed.' }
    $report.native_status=[string]$native.status
    $report.native_cases=@($native.cases | ForEach-Object { [ordered]@{maximum_frame_latency=$_.requestedMaximumFrameLatency;status=$_.status;process_id=$_.processId;native_exit_code=$_.nativeExitCode;timed_out=$_.timedOut;started_utc=$_.startedUtc;finished_utc=$_.finishedUtc} })
    $report.alignment='No absolute input-arm QPC anchor in the unchanged EXE. Only explicit unique sequence matching may support a labelled alignment inference.'
    if ((Test-Path -LiteralPath $etl) -and $report.trace_retirement_confirmed) {
        $report.etl_sha256=Etw-Hash $etl; $report.etl_bytes=(Get-Item -LiteralPath $etl).Length
        $export=Invoke-EtwTool 'trace-export' $tracerpt @($etl,'-o',$xml,'-of','XML','-rts','-export',(Join-Path $stage 'events-schema.private.man'),'-y') 60000 $xml 536870912
        $report.xml_export_complete=$export.ok
        $report.xml_bytes=if (Test-Path -LiteralPath $xml) { (Get-Item -LiteralPath $xml).Length } else { 0 }
        # ETL is not automatically public: compression does not remove command lines.
        # The read-only filter is invoked after the original snapshots have finished.
        if ($export.ok) {
            $filterResult=& $filterScript -XmlPath $xml -OutputDirectory $public -ProcessIds @($native.cases | ForEach-Object { [int]$_.processId })
            $report.filter=$filterResult; $report.filter_complete=($filterResult.complete -eq $true)
            if ($filterResult.complete -and $filterResult.command_line_fields -eq 0 -and $filterResult.opaque_events -eq 0) {
                Copy-Item -LiteralPath $etl -Destination (Join-Path $public 'pinned-88cd.etl')
                $report.publication_status='compressed-etl-and-target-events; no-command-line-fields-in-complete-export'
            } else { $report.publication_status='raw-etl-withheld; filtered-events-and-receipt-only' }
        } else { $report.publication_status='raw-etl-withheld; export-incomplete' }
    }
} catch {
    $report.errors.Add($_.Exception.Message)
    if ($report.collection_status -eq 'not-started') { $report.collection_status='blocked' }
} finally {
    # A failed/overdue native driver is stopped before any potentially slow WPR
    # control calls. Trace cleanup must not extend that driver's timeout.
    if ($child) {
        try {
            if (-not $child.HasExited) {
                if ($childClock) { $report.native_stop_request_elapsed_ms=$childClock.Elapsed.TotalMilliseconds }
                $child.Kill($true)
            }
            $childExited=$child.WaitForExit(5000)
            if ($childExited) {
                $report.native_exit_code=$child.ExitCode
                if ($childClock -and $null -eq $report.native_exit_observed_elapsed_ms) { $report.native_exit_observed_elapsed_ms=$childClock.Elapsed.TotalMilliseconds }
            }
        } catch { $childExited=$false; $report.errors.Add('Native cleanup:' + $_.Exception.GetType().Name) }
        foreach ($item in @(@{task=$childOut;name='native-driver.stdout.log'},@{task=$childErr;name='native-driver.stderr.log'})) {
            try { if ($item.task -and $item.task.Wait(1000)) { [IO.File]::WriteAllText((Join-Path $public $item.name),$item.task.Result,[Text.UTF8Encoding]::new($false)) } }
            catch { $report.errors.Add('Native output capture:' + $_.Exception.GetType().Name) }
        }
        $child.Dispose()
    }
    if ($report.trace_start_attempted -and -not $report.trace_retirement_confirmed -and $wpr) {
        try { Stop-OwnedEtw } catch { $report.errors.Add('Trace cleanup:' + $_.Exception.GetType().Name) }
    }
    $report.native_driver_exit_confirmed=$childExited
    if ($report.native_status -eq 'running') { $report.native_status='incomplete' }
    $report.finished_utc=[DateTime]::UtcNow.ToString('o')
    # Raw ETL/XML remain in owned temporary staging if publication is refused.
    # These are only the capability/provider/control commands above. Event XML,
    # schemas and unapproved ETL are deliberately not part of this publication.
    foreach ($file in (Get-ChildItem -LiteralPath $stage -Filter '*.log' -File)) { Copy-Item -LiteralPath $file.FullName -Destination $public }
    if (Test-Path -LiteralPath (Join-Path $stage 'capture.wprp')) { Copy-Item -LiteralPath (Join-Path $stage 'capture.wprp') -Destination $public }
    Write-EtwJson (Join-Path $public 'receipt.json') $report
    if ($output -and $childExited -and -not (Test-Path -LiteralPath (Join-Path $output 'trace'))) {
        Copy-Item -LiteralPath $public -Destination (Join-Path $output 'trace') -Recurse
    } else { Write-Host ('Evidence retained only in owned temporary publication directory: ' + $public) }
}
Write-Host ('Pinned diagnostic: collection=' + $report.collection_status + '; native=' + $report.native_status + '; publication=' + $report.publication_status)
if ($report.collection_status -ne 'collected' -or -not $report.trace_started -or -not $report.trace_retirement_confirmed -or -not $childExited -or $report.native_status -notin @('passed','failed') -or $report.errors.Count -ne 0 -or -not $report.xml_export_complete -or -not $report.filter_complete) { throw 'Pinned trace collection, retirement, export, or filtering is incomplete; see the separate unchanged native verdict.' }
