#Requires -Version 7.4
param(
    [Parameter(Mandatory)][string]$OutputDirectory,
    [Parameter(Mandatory)][string]$ScratchRoot,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExecutingWorkflowSha,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExecutingPrHeadSha
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$runClock = [Diagnostics.Stopwatch]::StartNew()
$stage = $null; $output = $null; $wpr = $null; $logman = $null; $pwsh = $null
$baselineSessions = @(); $queryHelper = $null
$providerGuids=@{'Microsoft-Windows-DXGI'='ca11c036-0102-4a2d-a6ad-f03cfed5d3c9';'Microsoft-Windows-DxgKrnl'='802ec45a-1e99-4b83-9920-87c98277ba9d'}
$report = [ordered]@{
    schema=1; scope='Provider enablement controls only; no Swirl launch, event export, or native acceptance.'
    executing_workflow_sha=$ExecutingWorkflowSha; executing_pr_head_sha=$ExecutingPrHeadSha
    original_run_id=42292503809; original_hresult='0xc558300c'; original_failure_retained=$true
    original_profile_sha256='a90c2d50fa7270545c7c37f48eca83fed5d8b7aaa4445f2f1d6ba0b9cde221aa'
    status='not-started'; native_acceptance_status='not-run'; root_cause_status='not-established'
    swirl_launch_count=0; event_data_saved=$false; etl_export_attempted=$false
    required_base_cases=@('G0','D0','K0'); maximum_cases=7; case_admission_limit_ms=360000
    tool_wait_limit_ms=5000; query_tool_wait_limit_ms=8000; tool_exit_confirmation_limit_ms=2000
    retirement_deadline_claimed=$false; native_tool_exit_unconfirmed=$false
    started_utc=[DateTime]::UtcNow.ToString('o'); finished_utc=$null
    tools=[Collections.Generic.List[object]]::new(); cases=[Collections.Generic.List[object]]::new()
    errors=[Collections.Generic.List[string]]::new()
}

function Write-ProbeJson([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path,(ConvertTo-Json -InputObject $Value -Depth 40),[Text.UTF8Encoding]::new($false))
}
function Probe-Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Assert-ProbePlainPath([string]$Path) {
    $current=[IO.Path]::GetFullPath($Path)
    while ($current) {
        if ((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Linked probe paths are not admitted.' }
        $parent=[IO.Path]::GetDirectoryName($current.TrimEnd('\','/'))
        if ($parent -eq $current) { break }; $current=$parent
    }
}
function Invoke-ProbeTool([string]$Name,[string]$File,[string[]]$Arguments,[int]$DeadlineMs=5000) {
    $prefix=('{0:000}-{1}' -f ($report.tools.Count+1),$Name)
    $row=[ordered]@{name=$Name;file=$File;arguments=$Arguments;stdout_file=($prefix+'.stdout.log');stderr_file=($prefix+'.stderr.log');started_utc=[DateTime]::UtcNow.ToString('o');started=$false;exit_code=$null;timed_out=$false;exit_confirmed=$false;errors=@();elapsed_ms=0}
    $report.tools.Add($row); $process=$null; $outTask=$null; $errTask=$null
    $clock=[Diagnostics.Stopwatch]::StartNew(); $errors=[Collections.Generic.List[string]]::new(); $textOut=''; $textErr=''
    try {
        $info=[Diagnostics.ProcessStartInfo]::new(); $info.FileName=$File; $info.UseShellExecute=$false
        $info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true; $info.WorkingDirectory=$stage
        foreach ($arg in $Arguments) { $info.ArgumentList.Add($arg) }
        $process=[Diagnostics.Process]::new(); $process.StartInfo=$info
        if (-not $process.Start()) { throw 'Native probe tool did not start.' }; $row.started=$true
        $outTask=$process.StandardOutput.ReadToEndAsync(); $errTask=$process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($DeadlineMs)) { $row.timed_out=$true }
    } catch { $errors.Add('execute:' + $_.Exception.GetType().Name) }
    finally {
        if ($process -and $row.started) {
            try {
                if (-not $process.HasExited) { $process.Kill($true) }
                $row.exit_confirmed=$process.WaitForExit(2000)
                if ($row.exit_confirmed) { $row.exit_code=$process.ExitCode }
            } catch { $errors.Add('cleanup:' + $_.Exception.GetType().Name); $row.exit_confirmed=$false }
        } else { $row.exit_confirmed=$true }
        foreach ($item in @(@{task=$outTask;kind='stdout'},@{task=$errTask;kind='stderr'})) {
            $value=''
            try {
                if ($item.task) {
                    if ($item.task.Wait(1000)) { $value=$item.task.Result }
                    else { $errors.Add('capture-' + $item.kind + ':Timeout') }
                }
            } catch { $errors.Add('capture-' + $item.kind + ':' + $_.Exception.GetType().Name) }
            [IO.File]::WriteAllText((Join-Path $stage ($prefix+'.'+$item.kind+'.log')),$value,[Text.UTF8Encoding]::new($false))
            if ($item.kind -eq 'stdout') { $textOut=$value } else { $textErr=$value }
        }
        if ($process) { $process.Dispose() }
        if (-not $row.exit_confirmed) { $report.native_tool_exit_unconfirmed=$true }
        $clock.Stop(); $row.elapsed_ms=$clock.Elapsed.TotalMilliseconds; $row.errors=$errors.ToArray()
        Write-ProbeJson (Join-Path $stage 'receipt.json') $report
    }
    return @{record=$row;stdout=$textOut;stderr=$textErr;ok=($row.started -and $row.exit_confirmed -and $row.exit_code -eq 0 -and -not $row.timed_out -and $errors.Count -eq 0)}
}
function Get-ProbeState([string]$Name,[string]$Instance='', [string]$Profile='') {
    $arguments=@('-status','profiles')
    if ($Instance) { $arguments+=@('-instancename',$Instance) }
    $tool=Invoke-ProbeTool $Name $wpr $arguments
    $text=$tool.stdout+$tool.stderr
    $lines=@($text -split '\r?\n' | Where-Object { $_ -match '^\s*Profile\s*:' })
    $profiles=[Collections.Generic.List[string]]::new(); $unknown=$false
    foreach ($line in $lines) {
        if ($line -cmatch '^\s*Profile\s*:\s*(\S+\.(?:Light|Verbose)\.(?:Memory|File))\s*$') { $profiles.Add($Matches[1]) }
        else { $unknown=$true }
    }
    return @{inactive=($tool.ok -and $text -match '(?i)WPR is not recording' -and $lines.Count -eq 0);owned=($tool.ok -and -not $unknown -and $profiles.Count -eq 1 -and $profiles[0] -ceq ($Profile+'.Verbose.Memory'));tool=$tool}
}
function Get-ProbeSessions([string]$Name) {
    $tool=Invoke-ProbeTool $Name $logman @('query','-ets')
    $names=[Collections.Generic.List[string]]::new(); $unknown=$false
    foreach ($line in ($tool.stdout -split '\r?\n')) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line -match '^Data Collector Set\s+Type\s+Status\s*$' -or $line -match '^-+\s*$' -or $line -eq 'The command completed successfully.') { continue }
        if ($line -cmatch '^\s*(.+?)\s+Trace\s+(?:Running|Stopped)\s*$') { $names.Add($Matches[1].Trim()) }
        else { $unknown=$true }
    }
    $sorted=[string[]]$names.ToArray(); [Array]::Sort($sorted,[StringComparer]::Ordinal)
    return @{ok=($tool.ok -and -not $unknown -and $tool.stdout.Contains('The command completed successfully.'));names=$sorted;tool=$tool}
}
function Test-ProbeSameSessions([string[]]$First,[string[]]$Second) { return (($First -join "`n") -ceq ($Second -join "`n")) }
function Read-ProbeSession($Case,[string]$Name,[string]$Phase) {
    $tool=Invoke-ProbeTool ($Case.id+'-'+$Phase+'-query-session') $pwsh @('-NoProfile','-NonInteractive','-File',$queryHelper,'-SessionName',$Name) 8000
    $entry=[ordered]@{phase=$Phase;session_name=$Name;query_tool_ok=$tool.ok;mode_observed=$false;session_absent=$false;properties=$null;error=$null}
    if ($tool.ok) {
        try {
            $entry.properties=ConvertFrom-Json -InputObject $tool.stdout
            if ($entry.properties.session_name -cne $Name) { throw 'Session query identity mismatch.' }
            $entry.mode_observed=($entry.properties.error_code -eq 0)
            $entry.session_absent=($entry.properties.error_code -eq 4201) # ERROR_WMI_INSTANCE_NOT_FOUND.
            if (-not $entry.mode_observed -and -not $entry.session_absent) { $entry.error='ControlTraceW-query-failed' }
        } catch { $entry.error='decode:'+$_.Exception.GetType().Name; $entry.properties=$null }
    } else { $entry.error='query-tool-failed' }
    $Case.session_queries.Add($entry)
    return $entry
}
function Test-ProbeCollector($Case,[string]$Text) {
    $collectors=[Collections.Generic.List[string]]::new()
    $keywords=[Collections.Generic.List[string]]::new(); $stacks=[Collections.Generic.List[string]]::new()
    $providers=[Collections.Generic.List[object]]::new(); $section=''
    foreach ($line in ($Text -split '\r?\n')) {
        if ($line -cmatch '^\s*Collector Name\s*:\s*(.+?)\s*$') { $collectors.Add($Matches[1]); $section=''; continue }
        if ($line -cmatch '^\s*(System Keywords|System Stacks|Providers)\s*:?\s*$') { $section=$Matches[1]; continue }
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($section -in @('System Keywords','System Stacks') -and $line -cmatch '^\s*([A-Za-z][A-Za-z0-9]*)\s*$') {
            if ($section -eq 'System Keywords') { $keywords.Add($Matches[1]) } else { $stacks.Add($Matches[1]) }
        }
        elseif ($section -eq 'Providers' -and $line -cmatch '^\s*([^:]+?)\s*:\s*0x([0-9a-fA-F]+)\s*:\s*0x([0-9a-fA-F]+)(?:\s*:\s*(.+))?\s*$') {
            $extra=if ($Matches.ContainsKey(4)) { $Matches[4].Trim() } else {''}
            $providers.Add(@{display=$Matches[1].Trim();keywords=[Convert]::ToUInt64($Matches[2],16);level=[Convert]::ToUInt32($Matches[3],16);extra=$extra})
        }
        else { $section='' }
    }
    if ($collectors.Count -ne 1) { return $false }
    $name=$collectors[0]
    $Case.actual_system_keywords=$keywords.ToArray(); $Case.actual_system_stacks=$stacks.ToArray()
    if ($Case.component -eq 'System') {
        if ($name -cne 'NT Kernel Logger' -and -not $name.Contains($Case.instance_name)) { return $false }
        if ($keywords.Count -ne 3 -or @($keywords | Where-Object { $_ -cnotin @('Loader','CSwitch','ReadyThread') }).Count -or $providers.Count) { return $false }
        foreach ($expected in @('Loader','CSwitch','ReadyThread')) { if ($keywords -cnotcontains $expected) { return $false } }
        [string[]]$expectedStacks=@()
        if ($Case.stacks) { $expectedStacks=@('CSwitch','ReadyThread') }
        if ($stacks.Count -ne $expectedStacks.Count -or @($stacks | Where-Object { $_ -cnotin $expectedStacks }).Count) { return $false }
        foreach ($expected in $expectedStacks) { if ($stacks -cnotcontains $expected) { return $false } }
    } else {
        if (-not $name.Contains($Case.collector_token)) { return $false }
        $provider='Microsoft-Windows-'+$Case.component
        if ($providers.Count -ne 1) { return $false }
        $actual=$providers[0]; $resolvedGuid=[guid]::Empty; $identityMode='unknown'
        if ($actual.display -ceq $provider) { $resolvedGuid=[guid]$providerGuids[$provider]; $identityMode='name-resolved-by-preflight-logman-guid' }
        elseif ([guid]::TryParse($actual.display,[ref]$resolvedGuid)) { $identityMode='guid-in-collector-status' }
        $Case.actual_provider=[ordered]@{display=$actual.display;resolved_guid=$resolvedGuid.ToString();identity_mode=$identityMode;keywords=('0x'+$actual.keywords.ToString('x16'));level=$actual.level;extra=$actual.extra}
        if ($resolvedGuid -ne [guid]$providerGuids[$provider] -or $actual.level -ne 5 -or $actual.keywords -ne [Convert]::ToUInt64($Case.keywords.Substring(2),16) -or $actual.extra -or $keywords.Count -or $stacks.Count) { return $false }
    }
    $Case.collector_names=@($name)
    return $true
}
function Invoke-EnablementProbe([string]$Id,[string]$Component,[bool]$NonPaged,[string]$Keywords,[bool]$ExeFilter,[bool]$Stacks,[string]$Control='') {
    if ($runClock.ElapsedMilliseconds -ge 360000 -or $report.cases.Count -ge 7) { throw 'The bounded probe admission limit was reached.' }
    $nonce=[guid]::NewGuid().ToString('N')
    $case=[ordered]@{
        id=$Id;component=$Component;control_case=$Control;non_paged_memory=if ($NonPaged) {'true'} else {'omitted'}
        keywords=$Keywords;exe_filter=if ($ExeFilter) {'Swirl.exe'} else {''};stacks=$Stacks
        profile_name=('SwirlEtwProbe'+$nonce);instance_name=('SwirlEtwInstance'+$nonce);collector_token=('SwirlEtwCollector'+$nonce)
        profile_sha256=$null;start_attempted=$false;start_exit_code=$null;enablement_status='not-run'
        ownership_confirmed=$false;collector_details_verified=$false;collector_names=@();retirement_confirmed=$false
        actual_provider=$null;actual_system_keywords=@();actual_system_stacks=@()
        cancel_requested=$false;cancel_request_elapsed_ms=$null;retirement_observed_elapsed_ms=$null
        before_sessions=@();after_sessions=@();session_queries=[Collections.Generic.List[object]]::new();errors=[Collections.Generic.List[string]]::new()
    }
    $report.cases.Add($case); $clock=[Diagnostics.Stopwatch]::StartNew(); $before=$null
    try {
        $before=Get-ProbeSessions ($Id+'-sessions-before')
        if (-not $before.ok -or -not (Test-ProbeSameSessions $baselineSessions $before.names)) { throw 'Existing ETW sessions changed or cannot be identified; no probe is admitted.' }
        $case.before_sessions=$before.names
        if (@($before.names | Where-Object { $_.Contains($nonce) }).Count) { throw 'A generated probe session identity already exists.' }
        if ($Component -eq 'System' -and $before.names -contains 'NT Kernel Logger') { throw 'An existing NT Kernel Logger blocks the kernel probe.' }
        $state=Get-ProbeState ($Id+'-state-before') $case.instance_name $case.profile_name
        if (-not $state.inactive) { throw 'The unique probe instance is not confirmed inactive.' }
        $collectorId='Collector'+$nonce; $providerId='Provider'+$nonce
        if ($Component -eq 'System') {
            # WPR permits only these fixed system collector names. Never use the system CKCL.
            $collector='<SystemCollector Id="'+$collectorId+'" Name="NT Kernel Logger"><BufferSize Value="128"/><Buffers Value="1024"/></SystemCollector>'
            $stackText=if ($Stacks) {'<Stacks><Stack Value="CSwitch"/><Stack Value="ReadyThread"/></Stacks>'} else {''}
            $provider='<SystemProvider Id="'+$providerId+'"><Keywords><Keyword Value="Loader"/><Keyword Value="CSwitch"/><Keyword Value="ReadyThread"/></Keywords>'+$stackText+'</SystemProvider>'
            $reference='<SystemCollectorId Value="'+$collectorId+'"><SystemProviderId Value="'+$providerId+'"/></SystemCollectorId>'
        } else {
            $collector='<EventCollector Id="'+$collectorId+'" Name="'+$case.collector_token+'"><BufferSize Value="128"/><Buffers Value="1024"/></EventCollector>'
            $memory=if ($NonPaged) {' NonPagedMemory="true"'} else {''}
            $filter=if ($ExeFilter) {' ProcessExeFilter="Swirl.exe"'} else {''}
            $provider='<EventProvider Id="'+$providerId+'" Name="Microsoft-Windows-'+$Component+'" Level="5" Strict="true"'+$memory+$filter+'><Keywords><Keyword Value="'+$Keywords+'"/></Keywords></EventProvider>'
            $reference='<EventCollectorId Value="'+$collectorId+'"><EventProviders><EventProviderId Value="'+$providerId+'"/></EventProviders></EventCollectorId>'
        }
        $profilePath=Join-Path $stage ($Id+'.wprp')
        $profileText='<?xml version="1.0" encoding="utf-8"?><WindowsPerformanceRecorder Version="1.0" Author="Swirl"><Profiles>'+$collector+$provider+'<Profile Id="'+$case.profile_name+'.Verbose.Memory" Name="'+$case.profile_name+'" Description="Provider enablement only; no application acceptance" LoggingMode="Memory" DetailLevel="Verbose"><Collectors>'+$reference+'</Collectors></Profile></Profiles></WindowsPerformanceRecorder>'
        [IO.File]::WriteAllText($profilePath,$profileText,[Text.UTF8Encoding]::new($false)); $case.profile_sha256=Probe-Hash $profilePath
        $parse=Invoke-ProbeTool ($Id+'-profile-parse') $wpr @('-profiles',$profilePath)
        if (-not $parse.ok -or -not $parse.stdout.Contains($case.profile_name)) { throw 'Installed WPR did not parse the single-component profile.' }
        $case.start_attempted=$true
        $start=Invoke-ProbeTool ($Id+'-start') $wpr @('-start',($profilePath+'!'+$case.profile_name),'-instancename',$case.instance_name)
        $case.start_exit_code=$start.record.exit_code
        $state=Get-ProbeState ($Id+'-state-after-start') $case.instance_name $case.profile_name
        $case.ownership_confirmed=$state.owned
        if (-not $state.owned -and -not $state.inactive) { throw 'Probe ownership is unknown after the start attempt.' }
        if ($start.record.timed_out -or -not $start.record.exit_confirmed -or $start.record.errors.Count) { throw 'The start control process failed or timed out; enablement is inconclusive.' }
        if (-not $start.ok) { $case.enablement_status='enable-failed' }
        elseif (-not $state.owned) { throw 'WPR returned success without the uniquely owned recording.' }
        else {
            $details=Invoke-ProbeTool ($Id+'-collectors') $wpr @('-status','collectors','-details','-instancename',$case.instance_name)
            if (-not $details.ok -or -not (Test-ProbeCollector $case $details.stdout)) { $case.enablement_status='unknown'; throw 'The actual collector configuration could not be matched to this probe.' }
            $case.collector_details_verified=$true; $case.enablement_status='enabled'
            foreach ($name in $case.collector_names) { $null=Read-ProbeSession $case $name 'active' }
        }
    } catch { $case.errors.Add($_.Exception.Message); throw }
    finally {
        if ($case.start_attempted) {
            try {
                $state=Get-ProbeState ($Id+'-state-before-cancel') $case.instance_name $case.profile_name
                if ($state.owned) {
                    $case.cancel_requested=$true; $case.cancel_request_elapsed_ms=$clock.Elapsed.TotalMilliseconds
                    $cancel=Invoke-ProbeTool ($Id+'-cancel-owned') $wpr @('-cancel','-instancename',$case.instance_name)
                    $state=Get-ProbeState ($Id+'-state-after-cancel') $case.instance_name $case.profile_name
                    if (-not $cancel.ok) { $case.errors.Add('The owned cancel command did not complete successfully.') }
                }
                elseif (-not $state.inactive) { $case.errors.Add('Recording ownership is unknown; no cancel was sent.') }
                foreach ($name in $case.collector_names) { $null=Read-ProbeSession $case $name 'after-cancel' }
                $stillQueryable=@($case.session_queries | Where-Object { $_.phase -eq 'after-cancel' -and $_.mode_observed }).Count -gt 0
                $after=Get-ProbeSessions ($Id+'-sessions-after'); $case.after_sessions=$after.names
                $case.retirement_confirmed=($state.inactive -and $after.ok -and $before -and $before.ok -and (Test-ProbeSameSessions $before.names $after.names) -and -not $stillQueryable -and -not $report.native_tool_exit_unconfirmed)
                if ($case.retirement_confirmed) { $case.retirement_observed_elapsed_ms=$clock.Elapsed.TotalMilliseconds }
                else { $case.errors.Add('Retirement or the unchanged pre-existing session set was not confirmed.') }
            } catch { $case.errors.Add('retirement:'+$_.Exception.GetType().Name); $case.retirement_confirmed=$false }
        }
        else { $case.retirement_confirmed=$false }
        $clock.Stop(); $case.elapsed_ms=$clock.Elapsed.TotalMilliseconds
        Write-ProbeJson (Join-Path $stage ($Id+'.json')) $case
        Write-ProbeJson (Join-Path $stage 'receipt.json') $report
    }
    if (-not $case.retirement_confirmed -or $case.errors.Count -or $report.native_tool_exit_unconfirmed) { throw 'Probe cleanup or control evidence is incomplete; later probes are stopped.' }
    return $case
}

try {
    if (-not $IsWindows -or [IntPtr]::Size -ne 8) { throw 'This probe requires 64-bit Windows.' }
    if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or $env:GITHUB_REPOSITORY -cne 'SOLHK/Swirl' -or $env:SWIRL_ETW_PROVIDER_PROBE -cne '1' -or $env:GITHUB_EVENT_NAME -cne 'pull_request') { throw 'The isolated hosted-runner opt-in is missing.' }
    $event=Get-Content -LiteralPath $env:GITHUB_EVENT_PATH -Raw -Encoding utf8 | ConvertFrom-Json
    if ($event.action -cne 'labeled' -or $event.label.name -cne 'qa-etw-provider-probe' -or $event.number -ne 61 -or $event.repository.full_name -cne 'SOLHK/Swirl' -or $event.pull_request.head.repo.full_name -cne 'SOLHK/Swirl' -or $event.pull_request.head.ref -cne 'work/node-probe-render-20261105' -or $event.pull_request.base.ref -cne 'test' -or $event.pull_request.head.sha -cne $ExecutingPrHeadSha -or $env:GITHUB_SHA -cne $ExecutingWorkflowSha) { throw 'This probe is restricted to the explicitly labeled same-repository PR 61.' }
    $scratch=(Resolve-Path -LiteralPath $ScratchRoot).Path.TrimEnd('\','/'); Assert-ProbePlainPath $scratch
    $output=[IO.Path]::GetFullPath($OutputDirectory); Assert-ProbePlainPath $output
    $workspace=(Resolve-Path -LiteralPath $env:GITHUB_WORKSPACE).Path.TrimEnd('\','/')
    if (-not $output.StartsWith((Join-Path $workspace 'build-evidence')+'\',[StringComparison]::OrdinalIgnoreCase) -or $scratch.StartsWith($workspace+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Use fresh build-evidence output and external temporary staging.' }
    if (Test-Path -LiteralPath $output) { throw 'Existing probe evidence will not be overwritten.' }
    New-Item -ItemType Directory -Path $output | Out-Null
    $stage=Join-Path $scratch ('swirl-etw-enablement-'+[guid]::NewGuid().ToString('N')); New-Item -ItemType Directory -Path $stage | Out-Null
    $report.script_sha256=Probe-Hash $PSCommandPath; $report.staging_directory=$stage
    $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'The disposable runner elevated token is required.' }
    if (@(Get-Process -Name Swirl -ErrorAction SilentlyContinue).Count) { throw 'An existing Swirl process blocks this no-application probe.' }
    $wpr=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\Windows Performance Toolkit\wpr.exe'
    if (-not (Test-Path -LiteralPath $wpr -PathType Leaf)) { $wpr=(Get-Command wpr.exe -ErrorAction Stop).Source }
    $logman=(Get-Command logman.exe -ErrorAction Stop).Source; $pwsh=(Get-Process -Id $PID).Path
    $report.tool_identity=@($wpr,$logman,$pwsh | ForEach-Object { [ordered]@{path=$_;sha256=(Probe-Hash $_);version=[Diagnostics.FileVersionInfo]::GetVersionInfo($_).FileVersion;signature=[string](Get-AuthenticodeSignature -LiteralPath $_).Status} })
    if (@($report.tool_identity | Where-Object { $_.signature -cne 'Valid' }).Count) { throw 'A required native tool signature is not valid.' }
    $defaultState=Get-ProbeState 'preflight-default-wpr'
    if (-not $defaultState.inactive) { throw 'An existing or unidentified default WPR recording blocks the probe.' }
    $sessions=Get-ProbeSessions 'preflight-sessions'
    if (-not $sessions.ok) { throw 'The existing ETW session set cannot be parsed.' }
    $baselineSessions=$sessions.names; $report.baseline_sessions=$baselineSessions
    foreach ($provider in @('Microsoft-Windows-DXGI','Microsoft-Windows-DxgKrnl')) {
        $capability=Invoke-ProbeTool ('capability-'+$provider) $logman @('query','providers',$provider)
        if (-not $capability.ok -or $capability.stdout -cnotmatch ('(?m)^\s*'+[regex]::Escape($provider)+'\s+\{([0-9a-fA-F-]{36})\}\s*$') -or [guid]$Matches[1] -ne [guid]$providerGuids[$provider]) { throw 'A required provider metadata query or GUID binding failed.' }
    }
    $report.verified_provider_guids=$providerGuids
    # This isolated helper exposes only QUERY (control code 0), never START/STOP/UPDATE.
    # Run it in a bounded child so metadata inspection cannot indefinitely delay cancellation.
    $queryHelper=Join-Path $stage 'query-session.ps1'
    $querySource=@'
param([Parameter(Mandatory)][string]$SessionName)
$ErrorActionPreference='Stop'
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class SwirlEtwReadOnlyQuery {
    [StructLayout(LayoutKind.Sequential)] struct Wnode {
        public uint BufferSize, ProviderId;
        public ulong HistoricalContext;
        public long TimeStamp;
        public Guid Guid;
        public uint ClientContext, Flags;
    }
    [StructLayout(LayoutKind.Sequential)] struct Properties {
        public Wnode Header;
        public uint BufferSize, MinimumBuffers, MaximumBuffers, MaximumFileSize, LogFileMode, FlushTimer, EnableFlags;
        public int AgeLimit;
        public uint NumberOfBuffers, FreeBuffers, EventsLost, BuffersWritten, LogBuffersLost, RealTimeBuffersLost;
        public IntPtr LoggerThreadId;
        public uint LogFileNameOffset, LoggerNameOffset;
    }
    [DllImport("sechost.dll", EntryPoint="ControlTraceW", CharSet=CharSet.Unicode, ExactSpelling=true)]
    static extern uint QueryNative(ulong traceId, string name, IntPtr properties, uint controlCode);
    public static object Query(string name) {
        int size=Marshal.SizeOf<Properties>();
        if (IntPtr.Size!=8 || size!=120 || Marshal.OffsetOf<Properties>("LogFileMode").ToInt32()!=64)
            throw new InvalidOperationException("Unexpected x64 EVENT_TRACE_PROPERTIES layout.");
        int bytes=size+4096;
        IntPtr memory=Marshal.AllocHGlobal(bytes);
        try {
            Marshal.Copy(new byte[bytes],0,memory,bytes);
            var value=new Properties();
            value.Header.BufferSize=(uint)bytes;
            value.LoggerNameOffset=(uint)size;
            value.LogFileNameOffset=(uint)(size+2048);
            Marshal.StructureToPtr(value,memory,false);
            uint code=QueryNative(0,name,memory,0); // EVENT_TRACE_CONTROL_QUERY only.
            value=Marshal.PtrToStructure<Properties>(memory);
            return new { session_name=name, error_code=code, session_guid=code==0 ? value.Header.Guid.ToString() : null,
                log_file_mode=code==0 ? (uint?)value.LogFileMode : null,
                log_file_mode_hex=code==0 ? "0x"+value.LogFileMode.ToString("x8") : null,
                paged_buffers=code==0 ? (bool?)((value.LogFileMode & 0x01000000)!=0) : null,
                buffering_mode=code==0 ? (bool?)((value.LogFileMode & 0x400)!=0) : null,
                buffer_size_kib=code==0 ? (uint?)value.BufferSize : null,
                number_of_buffers=code==0 ? (uint?)value.NumberOfBuffers : null,
                enable_flags=code==0 ? (uint?)value.EnableFlags : null,
                events_lost=code==0 ? (uint?)value.EventsLost : null };
        } finally { Marshal.FreeHGlobal(memory); }
    }
}
"@
[SwirlEtwReadOnlyQuery]::Query($SessionName) | ConvertTo-Json -Depth 4 -Compress
'@
    [IO.File]::WriteAllText($queryHelper,$querySource,[Text.UTF8Encoding]::new($false)); $report.query_helper_sha256=Probe-Hash $queryHelper
    $report.status='running'
    $g0=Invoke-EnablementProbe 'G0' 'DxgKrnl' $false '0xffffffffffffffff' $false $false
    if ($g0.enablement_status -eq 'enable-failed') {
        $g1=Invoke-EnablementProbe 'G1' 'DxgKrnl' $true '0xffffffffffffffff' $false $false 'G0'
        if ($g1.enablement_status -eq 'enable-failed') { $null=Invoke-EnablementProbe 'G2' 'DxgKrnl' $true '0x08000001' $false $false 'G1' }
    }
    $d0=Invoke-EnablementProbe 'D0' 'DXGI' $false '0xffffffffffffffff' $true $false
    if ($d0.enablement_status -eq 'enable-failed') { $null=Invoke-EnablementProbe 'D1' 'DXGI' $false '0xffffffffffffffff' $false $false 'D0' }
    $k0=Invoke-EnablementProbe 'K0' 'System' $false 'Loader,CSwitch,ReadyThread' $false $true
    if ($k0.enablement_status -eq 'enable-failed') { $null=Invoke-EnablementProbe 'K1' 'System' $false 'Loader,CSwitch,ReadyThread' $false $false 'K0' }
    $report.status='completed'
} catch { $report.status='blocked-or-incomplete'; $report.errors.Add($_.Exception.Message) }
finally {
    $report.finished_utc=[DateTime]::UtcNow.ToString('o'); $report.elapsed_ms=$runClock.Elapsed.TotalMilliseconds
    $report.enablement_failures=@($report.cases | Where-Object { $_.enablement_status -eq 'enable-failed' } | ForEach-Object { $_.id })
    if ($stage) {
        Write-ProbeJson (Join-Path $stage 'receipt.json') $report
        if ($output) {
            $publish=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
            $null=$publish.Add('receipt.json'); $null=$publish.Add('query-session.ps1')
            foreach ($tool in $report.tools) { $null=$publish.Add($tool.stdout_file); $null=$publish.Add($tool.stderr_file) }
            foreach ($case in $report.cases) { $null=$publish.Add($case.id+'.json'); $null=$publish.Add($case.id+'.wprp') }
            foreach ($name in $publish) {
                $path=Join-Path $stage $name
                if (Test-Path -LiteralPath $path -PathType Leaf) { Copy-Item -LiteralPath $path -Destination (Join-Path $output $name) }
            }
            $files=@(Get-ChildItem -LiteralPath $output -File | Sort-Object Name | ForEach-Object { [ordered]@{path=$_.Name;bytes=$_.Length;sha256=(Probe-Hash $_.FullName)} })
            Write-ProbeJson (Join-Path $output 'files.json') $files
        }
    }
}
Write-Host ('ETW provider probe: status={0}; enable-failed={1}; native acceptance=not-run; event export=none' -f $report.status,($report.enablement_failures -join ','))
if ($report.status -ne 'completed' -or $report.errors.Count -or $report.native_tool_exit_unconfirmed) { throw 'The provider-only experiment is incomplete; inspect preserved control evidence.' }
