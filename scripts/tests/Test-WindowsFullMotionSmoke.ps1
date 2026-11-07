#Requires -Version 7.4
param(
    [Parameter(Mandatory)][string]$RepositoryRoot,
    [Parameter(Mandatory)][string]$RuntimeDirectory,
    [Parameter(Mandatory)][string]$ReferenceExecutable,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [Parameter(Mandatory)][string]$ScratchRoot,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$WorkflowSha,
    [string]$PullRequestHeadSha = '',
    [ValidateSet('qa','release')][string]$ExpectedFlavor = 'qa'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
function Write-MotionJson($Path, $Value) { [IO.File]::WriteAllText($Path, (ConvertTo-Json -InputObject $Value -Depth 20), [Text.UTF8Encoding]::new($false)) }
function Get-MotionHash($Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Test-MotionChild($Path, $Parent) { $Path.Equals($Parent, [StringComparison]::OrdinalIgnoreCase) -or $Path.StartsWith($Parent.TrimEnd('\','/') + '\', [StringComparison]::OrdinalIgnoreCase) }
function Assert-MotionPath([string]$Path) {
    if ($Path -notmatch '^[a-zA-Z]:[\\/]') { throw 'Use absolute local Windows paths.' }
    for ($p = $Path; $p; $p = [IO.Path]::GetDirectoryName($p.TrimEnd('\','/'))) {
        if ((Test-Path -LiteralPath $p) -and ((Get-Item -LiteralPath $p -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Linked path is not an isolated smoke root: $p" }
    }
}
function Get-MotionTree($Root) {
    foreach ($item in (Get-ChildItem -LiteralPath $Root -Recurse -Force | Sort-Object FullName)) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked deployed runtime entry.' }
        if (-not $item.PSIsContainer) { [ordered]@{path=[IO.Path]::GetRelativePath($Root,$item.FullName).Replace('\','/');bytes=$item.Length;sha256=(Get-MotionHash $item.FullName)} }
    }
}
if (-not $IsWindows) { throw 'Full-motion smoke requires the native Windows Qt runtime.' }
if ($PullRequestHeadSha -and $PullRequestHeadSha -notmatch '^[0-9a-fA-F]{40}$') { throw 'Invalid PR head SHA.' }
$repo = (Resolve-Path -LiteralPath $RepositoryRoot).Path.TrimEnd('\','/')
$runtime = (Resolve-Path -LiteralPath $RuntimeDirectory).Path.TrimEnd('\','/')
$reference = (Resolve-Path -LiteralPath $ReferenceExecutable).Path
$scratch = (Resolve-Path -LiteralPath $ScratchRoot).Path.TrimEnd('\','/')
$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\','/')
foreach ($path in @($repo,$runtime,$reference,$scratch,$output)) { Assert-MotionPath $path }
if (-not (Test-MotionChild $output (Join-Path $repo 'build-evidence')) -or
    (Test-MotionChild $scratch $repo) -or (Test-MotionChild $repo $scratch) -or
    (Test-MotionChild $runtime $output) -or (Test-MotionChild $output $runtime)) { throw 'Use build-evidence output and a separate external scratch root.' }
if (Test-Path -LiteralPath $output) {
    if (@(Get-ChildItem -LiteralPath $output -Force).Count) { throw 'Existing full-motion evidence will not be overwritten.' }
} else { New-Item -ItemType Directory -Path $output | Out-Null }
$errors = [Collections.Generic.List[string]]::new(); $cases = [Collections.Generic.List[object]]::new(); $before = $null
$receipt = [ordered]@{schema=1;status='failed';source_sha=$WorkflowSha;pr_head_sha=$PullRequestHeadSha;run_id=$env:GITHUB_RUN_ID;run_attempt=$env:GITHUB_RUN_ATTEMPT;
    started_utc=[DateTime]::UtcNow.ToString('o');expected_flavor=$ExpectedFlavor;deadline_ms=90000;internal_smoke_deadline_ms=60000;
    scope='Two additional native D3D11 smoke cases using ordinary isolated full-motion preferences. Existing smoke/animation/warning gates remain unchanged; no physical GPU or display-latency claim.';
    original_runtime_unchanged=$false;cases=@();errors=@()}
try {
    . (Join-Path $repo 'scripts/Assert-BuildSource.ps1')
    Assert-SwirlBuildSource -RepositoryRoot $repo -ExpectedSourceSha $WorkflowSha
    $exe = Join-Path $runtime 'Swirl.exe'
    $receipt.exe_sha256 = Get-MotionHash $exe; $receipt.reference_exe_sha256 = Get-MotionHash $reference
    if ($receipt.exe_sha256 -cne $receipt.reference_exe_sha256) { throw 'Deployed EXE differs from the current source build.' }
    $receipt.rust_identity = Get-Content -LiteralPath (Join-Path $runtime 'swirl-rust-build.json') -Raw | ConvertFrom-Json
    if ($receipt.rust_identity.source_sha -cne $WorkflowSha) { throw 'Deployed Rust source is not paired with this workflow.' }
    $receipt.rust_api_sha256 = Get-MotionHash (Join-Path $runtime 'swirl_api.dll')
    $qt = [Diagnostics.FileVersionInfo]::GetVersionInfo((Join-Path $runtime 'Qt6Core.dll'))
    $receipt.qt_version = $qt.FileVersion
    if ($qt.FileMajorPart -ne 6 -or $qt.FileMinorPart -ne 12 -or $qt.FileBuildPart -ne 0) { throw 'Expected Qt 6.12.0.' }
    $before = @(Get-MotionTree $runtime); Write-MotionJson (Join-Path $output 'runtime-before.json') $before
    $session = Join-Path $scratch ('swirl-full-motion-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $session | Out-Null
    foreach ($mode in @('rapid','ready')) {
        $caseErrors = [Collections.Generic.List[string]]::new(); $process = $null; $stdout = $null; $stderr = $null; $clock = $null
        $root = Join-Path $session $mode; $app = Join-Path $root 'app'; $profile = Join-Path $root 'profile'; $evidence = Join-Path $output $mode
        $case = [ordered]@{mode=$mode;status='failed';exit_code=$null;timed_out=$false;kill_tree_requested=$false;process_exit_observed=$false;elapsed_ms=$null;errors=@()}
        try {
            foreach ($dir in @($evidence,$app,$profile,(Join-Path $profile 'config/SOLHK'),(Join-Path $profile 'tmp'))) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
            Get-ChildItem -LiteralPath $runtime -Force | Copy-Item -Destination $app -Recurse -Force
            if ((ConvertTo-Json -InputObject @(Get-MotionTree $app) -Compress -Depth 5) -cne (ConvertTo-Json -InputObject $before -Compress -Depth 5)) { throw 'Copied runtime identity differs.' }
            Get-ChildItem -LiteralPath $app -Filter 'Swirl-*.txt' -File | Remove-Item
            $ini = Join-Path $profile 'config/SOLHK/Swirl.ini'
            [IO.File]::WriteAllText($ini,"[Appearance]`nsavedReduceMotion=false`nsavedFollowSystemMotion=false`n",[Text.UTF8Encoding]::new($false))
            Copy-Item -LiteralPath $ini -Destination (Join-Path $evidence 'settings-before.ini')
            $start = [Diagnostics.ProcessStartInfo]::new(); $start.FileName = Join-Path $app 'Swirl.exe'; $start.WorkingDirectory = $profile
            $start.UseShellExecute = $false; $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
            $start.ArgumentList.Add('--smoke-test'); $start.ArgumentList.Add('--preview-preserve-settings')
            if ($mode -eq 'ready') { $start.ArgumentList.Add('--font-review') }
            $removed = [ordered]@{}
            foreach ($name in @('QT_QUICK_BACKEND','QT_SCALE_FACTOR','QT_SCREEN_SCALE_FACTORS','QSG_RENDER_LOOP','QSG_NO_VSYNC','QT_D3D_MAX_FRAME_LATENCY','QT_D3D_NO_VBLANK_THREAD','QT_QPA_UPDATE_IDLE_TIME','QT_D3D_NO_FLIP','QT_D3D_USE_WARP','QT_D3D_ADAPTER_INDEX','QT_D3D_ADAPTER_LUID','QSG_RHI_PREFER_SOFTWARE_RENDERER','QT_LOGGING_RULES','QML_DISABLE_DISK_CACHE','QSG_RHI_PIPELINE_CACHE_LOAD')) {
                if ($start.Environment.ContainsKey($name)) { $removed[$name] = $start.Environment[$name]; $null = $start.Environment.Remove($name) }
            }
            $childEnvironment = [ordered]@{QT_QPA_PLATFORM='windows';QSG_RHI_BACKEND='d3d11';QSG_INFO='1';SWIRL_TEST_ROOT=$profile;TEMP=(Join-Path $profile 'tmp');TMP=(Join-Path $profile 'tmp');TMPDIR=(Join-Path $profile 'tmp');QML_DISK_CACHE_PATH=(Join-Path $profile 'cache/qml');QSG_RHI_DISABLE_DISK_CACHE='1';QSG_RHI_PIPELINE_CACHE_SAVE=(Join-Path $profile 'cache/pipeline.bin')}
            foreach ($entry in $childEnvironment.GetEnumerator()) { $start.Environment[$entry.Key] = $entry.Value }
            $case.environment = $childEnvironment; $case.removed_child_overrides = $removed; $case.arguments = @($start.ArgumentList); $case.profile = $profile
            $process = [Diagnostics.Process]::new(); $process.StartInfo = $start; $clock = [Diagnostics.Stopwatch]::StartNew()
            $case.started_utc = [DateTime]::UtcNow.ToString('o')
            if (-not $process.Start()) { throw 'Smoke process did not start.' }
            $case.process_id = $process.Id; $stdout = $process.StandardOutput.ReadToEndAsync(); $stderr = $process.StandardError.ReadToEndAsync()
            $case.process_exit_observed = $process.WaitForExit([Math]::Max(0,90000-[int]$clock.ElapsedMilliseconds))
            if (-not $case.process_exit_observed) { $case.timed_out = $true; throw 'Smoke exceeded its unchanged 90000 ms outer deadline.' }
            $case.exit_code = $process.ExitCode
            if ($case.exit_code -ne 0) { throw "Native smoke exited $($case.exit_code)." }
        } catch { $caseErrors.Add($_.Exception.Message) }
        finally {
            if ($process) {
                try { if ($case.Contains('process_id') -and -not $process.HasExited) { $case.kill_tree_requested = $true; $process.Kill($true); $case.process_exit_observed = $process.WaitForExit(5000) }
                    if ($case.Contains('process_id') -and -not $case.process_exit_observed) { $caseErrors.Add('Process exit was not observed after cleanup.') }
                    if ($case.process_exit_observed) { $case.exit_code = $process.ExitCode }
                } catch { $caseErrors.Add("Process cleanup: $($_.Exception.Message)") }
            }
            foreach ($capture in @(@{name='stdout';task=$stdout},@{name='stderr';task=$stderr})) {
                try { if ($capture.task -and $capture.task.Wait(5000)) { [IO.File]::WriteAllText((Join-Path $evidence "$($capture.name).log"),$capture.task.Result,[Text.UTF8Encoding]::new($false)) }
                    elseif ($capture.task) { $caseErrors.Add("$($capture.name) did not close after process exit.") }
                } catch { $caseErrors.Add("Output capture: $($_.Exception.Message)") }
            }
            if ($process) { $process.Dispose() }; if ($clock) { $clock.Stop(); $case.elapsed_ms = $clock.Elapsed.TotalMilliseconds }
            try {
                $log = Join-Path $evidence 'Swirl-diagnostics.txt'; Copy-Item -LiteralPath (Join-Path $app 'Swirl-diagnostics.txt') -Destination $log
                $text = [IO.File]::ReadAllText($log); $case.log_sha256 = Get-MotionHash $log
                Copy-Item -LiteralPath (Join-Path $profile 'config/SOLHK/Swirl.ini') -Destination (Join-Path $evidence 'settings-after.ini')
                $case.vme_context_count = [regex]::Matches($text,'QML_VME_WARNING_CONTEXT').Count
                $case.warning_lines = @($text -split '\r?\n' | Where-Object { $_ -match '^[123]: |Cannot find member data|is not a function' })
                $policies = @([regex]::Matches($text,'(?m)^4: MOTION_POLICY (\{[^\r\n]*\})\r?$'))
                if ($policies.Count -ne 1) { throw 'Expected exactly one motion policy receipt.' }
                $policy = $policies[0].Groups[1].Value | ConvertFrom-Json; $case.motion_policy = $policy
                if ($policy.followSystem -ne $false -or $policy.applicationReduced -ne $false -or $policy.effectiveReduced -ne $false -or $policy.expandDuration -ne 360) { throw 'Ordinary full-motion settings or normal expansion duration were not observed.' }
                $pages = @([regex]::Matches($text,'(?m)^4: SMOKE_PAGES (\d+)\s*$')); $case.smoke_completion_counts = @($pages | ForEach-Object { [int]$_.Groups[1].Value })
                if ($pages.Count -ne 1 -or [int]$pages[0].Groups[1].Value -ne 61) { throw 'Expected one completed61-route traversal.' }
                if ($case.vme_context_count -ne 0 -or $case.warning_lines.Count -ne 0) { throw 'Native full-motion smoke reported a warning.' }
                $case.renderer_lines = @($text -split '\r?\n' | Where-Object { $_ -match 'Creating QRhi|threaded render loop|Adapter \d+:|using this adapter|Animation Driver: using vsync|max frame latency' })
                if ($text -notmatch 'Creating QRhi with backend D3D11') { throw 'The observed renderer is not native D3D11.' }
                $ready = @([regex]::Matches($text,'(?m)^4: FONT_SMOKE_ROUTE_READY (\S+) (\S+)\r?$')); $case.ready_routes = @($ready | ForEach-Object { @{requested=$_.Groups[1].Value;adopted=$_.Groups[2].Value} })
                if ($mode -eq 'ready') {
                    # Main.qml deliberately shares the activity loader for these two routes.
                    $case.canonical_route_aliases = @{dashboard='activity';requestlogs='activity'}
                    $mismatches = @($case.ready_routes | Where-Object { $expected = if ($case.canonical_route_aliases.ContainsKey($_.requested)) { $case.canonical_route_aliases[$_.requested] } else { $_.requested }; $expected -cne $_.adopted })
                    if ($ready.Count -ne 61 -or @($case.ready_routes.requested | Sort-Object -Unique).Count -ne 61 -or $mismatches.Count) { throw 'Expected61distinct ready routes with their exact canonical loader identities.' }
                    $cache = @([regex]::Matches($text,'(?m)^4: QML_CACHE_EVIDENCE (\{[^\r\n]*\})\r?$'))
                    if ($cache.Count -ne 1) { throw 'Missing ready-smoke cache/source flavor receipt.' }
                    $case.qml_cache = $cache[0].Groups[1].Value | ConvertFrom-Json
                    if ($case.qml_cache.flavor -cne $ExpectedFlavor -or $case.qml_cache.qtVersion -cne '6.12.0') { throw 'Observed Qt/cache build flavor differs from the expected payload.' }
                } elseif ($ready.Count -ne 0) { throw 'Rapid smoke unexpectedly used the ready-route driver.' }
            } catch { $caseErrors.Add("Evidence: $($_.Exception.Message)") }
            $case.errors = $caseErrors.ToArray(); $case.finished_utc = [DateTime]::UtcNow.ToString('o')
            if (-not $caseErrors.Count -and $case.exit_code -eq 0 -and $case.process_exit_observed -and -not $case.timed_out) { $case.status = 'passed' }
            Write-MotionJson (Join-Path $evidence 'result.json') $case; $cases.Add($case)
            if ($case.status -ne 'passed') { $errors.Add("$mode full-motion smoke failed: $($case.errors -join ' ')") }
        }
        if ($case.Contains('process_id') -and -not $case.process_exit_observed) { throw 'Refusing another smoke while prior process exit is unproven.' }
    }
} catch { $errors.Add($_.Exception.Message) }
finally {
    if ($null -ne $before) {
        try { $after = @(Get-MotionTree $runtime); Write-MotionJson (Join-Path $output 'runtime-after.json') $after
            $receipt.original_runtime_unchanged = (ConvertTo-Json -InputObject $before -Compress -Depth 5) -ceq (ConvertTo-Json -InputObject $after -Compress -Depth 5)
            if (-not $receipt.original_runtime_unchanged) { $errors.Add('Original deployed runtime or diagnostics changed.') }
            Assert-SwirlBuildSource -RepositoryRoot $repo -ExpectedSourceSha $WorkflowSha
        } catch { $errors.Add("Final isolation/source check: $($_.Exception.Message)") }
    }
    if ($cases.Count -ne 2) { $errors.Add('Both full-motion smoke cases did not complete.') }
    $receipt.cases = $cases.ToArray(); $receipt.errors = $errors.ToArray(); $receipt.finished_utc = [DateTime]::UtcNow.ToString('o')
    if (-not $errors.Count) { $receipt.status = 'passed' }
    Write-MotionJson (Join-Path $output 'receipt.json') $receipt
}
if ($errors.Count) { throw ($errors -join "`n") }
Write-Host 'Both native full-motion61-route smoke cases passed; original smoke evidence is unchanged.'
