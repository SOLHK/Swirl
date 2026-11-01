#Requires -Version 7.4
param(
    [Parameter(Mandatory)][string]$RepositoryRoot,
    [Parameter(Mandatory)][string]$RuntimeDirectory,
    [Parameter(Mandatory)][string]$ReferenceExecutable,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [Parameter(Mandatory)][string]$ScratchRoot,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$WorkflowSha,
    [string]$PullRequestHeadSha = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Diagnostic only. Each unchanged --appearance-test runs once, with a fresh
# app directory, working directory and storage/cache root. Neither result can
# replace the original critical test. The native-process deadline stays 90s.
function Write-LatencyJson($Path, $Value) {
    [IO.File]::WriteAllText($Path, (ConvertTo-Json -InputObject $Value -Depth 30), [Text.UTF8Encoding]::new($false))
}
function Get-LatencyHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Test-LatencyChildPath([string]$Path, [string]$Parent) {
    return $Path.Equals($Parent, [StringComparison]::OrdinalIgnoreCase) -or
        $Path.StartsWith($Parent.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
}
function Assert-LatencyPlainPath([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked diagnostic path: $current" }
        }
        $parent = [IO.Path]::GetDirectoryName($current.TrimEnd('\', '/'))
        if ($parent -eq $current) { break }
        $current = $parent
    }
}
function Get-LatencyTree([string]$Root, [string]$Exclude = '', [switch]$TopLevelOnly) {
    $entries = [Collections.Generic.List[object]]::new()
    if (-not (Test-Path -LiteralPath $Root)) {
        $entries.Add([ordered]@{ path='.'; kind='missing' })
        return $entries.ToArray()
    }
    Assert-LatencyPlainPath $Root
    $entries.Add([ordered]@{ path='.'; kind='directory' })
    $pending = [Collections.Generic.Queue[string]]::new()
    $pending.Enqueue($Root)
    while ($pending.Count) {
        foreach ($item in (Get-ChildItem -LiteralPath $pending.Dequeue() -Force | Sort-Object Name)) {
            if ($Exclude -and (Test-LatencyChildPath $item.FullName $Exclude)) { continue }
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked diagnostic entry: $($item.FullName)" }
            if ($TopLevelOnly -and $item.PSIsContainer) { continue }
            $relative = [IO.Path]::GetRelativePath($Root, $item.FullName).Replace('\', '/')
            if ($item.PSIsContainer) {
                $entries.Add([ordered]@{ path=$relative; kind='directory' })
                $pending.Enqueue($item.FullName)
            } else {
                $entries.Add([ordered]@{ path=$relative; kind='file'; bytes=$item.Length;
                    sha256=(Get-LatencyHash $item.FullName); modifiedUtc=$item.LastWriteTimeUtc.ToString('o') })
            }
        }
    }
    return @($entries | Sort-Object path)
}
function Get-LatencyProtectedSnapshot($Scopes, [string]$Exclude) {
    $snapshot = [ordered]@{}
    foreach ($scope in $Scopes.GetEnumerator()) {
        $snapshot[$scope.Key] = @(Get-LatencyTree -Root $scope.Value.path -Exclude $Exclude -TopLevelOnly:$scope.Value.topLevel)
    }
    return $snapshot
}
function Compare-LatencySnapshots($Before, $After) {
    foreach ($name in $Before.Keys) {
        $left = @{}; $right = @{}
        foreach ($entry in $Before[$name]) { $left[$entry.path] = $entry | ConvertTo-Json -Compress }
        foreach ($entry in $After[$name]) { $right[$entry.path] = $entry | ConvertTo-Json -Compress }
        foreach ($path in @(@($left.Keys) + @($right.Keys) | Sort-Object -Unique)) {
            if (-not $left.ContainsKey($path) -or -not $right.ContainsKey($path) -or $left[$path] -cne $right[$path]) {
                [ordered]@{ scope=$name; path=$path; before=$left[$path]; after=$right[$path] }
            }
        }
    }
}
function Get-LatencyQtEnvironment($Environment) {
    $values = [ordered]@{}
    foreach ($name in @('QT_QPA_PLATFORM','QT_QUICK_BACKEND','QSG_RHI_BACKEND','QSG_RENDER_LOOP','QSG_INFO',
        'QT_D3D_MAX_FRAME_LATENCY','QSG_NO_VSYNC','QT_D3D_NO_FLIP','QT_D3D_USE_WARP','QT_D3D_ADAPTER_INDEX',
        'QT_D3D_ADAPTER_LUID','QSG_RHI_PREFER_SOFTWARE_RENDERER','QT_SCALE_FACTOR','QT_SCREEN_SCALE_FACTORS',
        'QT_SCALE_FACTOR_ROUNDING_POLICY','QT_ENABLE_HIGHDPI_SCALING','SWIRL_EXPECTED_DPR','SWIRL_TEST_ROOT',
        'QML_DISK_CACHE_PATH','QML_DISABLE_DISK_CACHE','QSG_RHI_DISABLE_DISK_CACHE','QSG_RHI_PIPELINE_CACHE_LOAD',
        'QSG_RHI_PIPELINE_CACHE_SAVE','QT_QPA_FONTDIR','QT_PLUGIN_PATH','QML_IMPORT_PATH','QML2_IMPORT_PATH','TEMP','TMP','TMPDIR')) {
        $values[$name] = $Environment[$name]
    }
    return $values
}
function Write-LatencyJUnit([string]$Path, $Result) {
    $settings = [Xml.XmlWriterSettings]::new()
    $settings.Indent = $true; $settings.Encoding = [Text.UTF8Encoding]::new($false)
    $writer = [Xml.XmlWriter]::Create($Path, $settings)
    try {
        $failed = $Result.status -ne 'passed'
        $writer.WriteStartDocument(); $writer.WriteStartElement('testsuite')
        $writer.WriteAttributeString('name', 'isolated-d3d11-frame-latency-diagnostic')
        $writer.WriteAttributeString('tests', '1'); $writer.WriteAttributeString('failures', $(if ($failed) { '1' } else { '0' }))
        $writer.WriteAttributeString('time', ([double]$Result.elapsedMs / 1000).ToString('R', [Globalization.CultureInfo]::InvariantCulture))
        $writer.WriteStartElement('testcase')
        $writer.WriteAttributeString('name', "appearance-maximum-frame-latency-$($Result.requestedMaximumFrameLatency)")
        $writer.WriteAttributeString('classname', 'diagnostic.appearance')
        $writer.WriteStartElement('properties')
        foreach ($name in @('requestedMaximumFrameLatency','nativeExitCode','timedOut','deadlineMs')) {
            $writer.WriteStartElement('property'); $writer.WriteAttributeString('name', $name)
            $writer.WriteAttributeString('value', [string]$Result[$name]); $writer.WriteEndElement()
        }
        $writer.WriteEndElement()
        if ($failed) {
            $writer.WriteStartElement('failure')
            $writer.WriteAttributeString('type', $(if ($Result.timedOut) { 'Timeout' } else { 'NativeExitOrEvidenceFailure' }))
            $writer.WriteAttributeString('message', 'See result.json and the unchanged native Appearance diagnostics.')
            $writer.WriteString(($Result.errors -join "`n")); $writer.WriteEndElement()
        }
        $writer.WriteEndElement(); $writer.WriteEndElement(); $writer.WriteEndDocument()
    } finally { $writer.Dispose() }
}
function Invoke-LatencyCase([int]$Maximum, [string]$Session, [string]$Runtime, $RuntimeManifest, [string]$Evidence) {
    $caseRoot = Join-Path $Session "maximum-$Maximum"
    $app = Join-Path $caseRoot 'app'; $store = Join-Path $caseRoot 'store'; $cwd = Join-Path $caseRoot 'cwd'
    $caseEvidence = Join-Path $Evidence "maximum-$Maximum"
    $errors = [Collections.Generic.List[string]]::new()
    $result = [ordered]@{ requestedMaximumFrameLatency=$Maximum; status='failed'; deadlineMs=90000;
        appDirectory=$app; storageRoot=$store; workingDirectory=$cwd; coldCache=$true; initialStoreFiles=$null;
        startedUtc=$null; finishedUtc=$null; elapsedMs=0; processId=$null; nativeExitCode=$null;
        timedOut=$false; exitCodeAfterTermination=$null; environment=$null; normalFrameProbes=@(); errors=@() }
    $process = $null; $stdoutTask = $null; $stderrTask = $null; $clock = $null
    try {
        foreach ($directory in @($app,$store,$cwd,$caseEvidence)) { New-Item -ItemType Directory -Path $directory | Out-Null }
        # Copy the complete deployed tree, including plugins and QML imports.
        Get-ChildItem -LiteralPath $Runtime -Force | Copy-Item -Destination $app -Recurse -Force
        $copied = @(Get-LatencyTree $app)
        $copyDifferences = @(Compare-LatencySnapshots @{ runtime=$RuntimeManifest } @{ runtime=$copied })
        if ($copyDifferences.Count) { throw 'The runtime copy differs from the deployed source, including file timestamps.' }
        # Only files in our new copy are removed. The source diagnostics remain
        # protected, and no copied old output can qualify as this run's evidence.
        $discarded = @(Get-ChildItem -LiteralPath $app -Filter 'Swirl-*.txt' -File)
        $result.copiedDiagnosticsRemoved = @($discarded | ForEach-Object Name)
        foreach ($file in $discarded) { Remove-Item -LiteralPath $file.FullName }
        $result.executableSha256 = Get-LatencyHash (Join-Path $app 'Swirl.exe')
        $result.initialStoreFiles = @(Get-ChildItem -LiteralPath $store -Recurse -File -Force).Count
        if ($result.initialStoreFiles -ne 0) { throw 'The isolated store is not cold.' }
        New-Item -ItemType Directory -Path (Join-Path $store 'tmp') | Out-Null
        $start = [Diagnostics.ProcessStartInfo]::new()
        $start.FileName = Join-Path $app 'Swirl.exe'; $start.WorkingDirectory = $cwd
        $start.UseShellExecute = $false; $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
        $start.ArgumentList.Add('--appearance-test')
        $start.Environment['QT_QPA_PLATFORM'] = 'windows'; $start.Environment['QSG_RHI_BACKEND'] = 'd3d11'
        $start.Environment['QSG_INFO'] = '1'; $start.Environment['QT_D3D_MAX_FRAME_LATENCY'] = [string]$Maximum
        $null = $start.Environment.Remove('QT_QUICK_BACKEND')
        $start.Environment['SWIRL_TEST_ROOT'] = $store
        foreach ($name in @('TEMP','TMP','TMPDIR')) { $start.Environment[$name] = Join-Path $store 'tmp' }
        $start.Environment['QML_DISK_CACHE_PATH'] = Join-Path $store 'cache/qml'
        $start.Environment['QSG_RHI_DISABLE_DISK_CACHE'] = '1'
        $null = $start.Environment.Remove('QSG_RHI_PIPELINE_CACHE_LOAD')
        $start.Environment['QSG_RHI_PIPELINE_CACHE_SAVE'] = Join-Path $store 'cache/pipeline.bin'
        # No swap-interval, render-loop, adapter, scale or animation overrides.
        $result.environment = Get-LatencyQtEnvironment $start.Environment
        $process = [Diagnostics.Process]::new(); $process.StartInfo = $start
        $result.startedUtc = [DateTime]::UtcNow.ToString('o'); $clock = [Diagnostics.Stopwatch]::StartNew()
        if (-not $process.Start()) { throw 'Native Appearance process did not start.' }
        $result.processId = $process.Id
        $stdoutTask = $process.StandardOutput.ReadToEndAsync(); $stderrTask = $process.StandardError.ReadToEndAsync()
        $remaining = [Math]::Max(0, 90000 - [int]$clock.ElapsedMilliseconds)
        if ($process.WaitForExit($remaining)) {
            $result.nativeExitCode = $process.ExitCode
            if ($process.ExitCode -ne 0) { $errors.Add("Native Appearance exited $($process.ExitCode).") }
        } else {
            $result.timedOut = $true; $errors.Add('Native Appearance exceeded the unchanged 90000 ms deadline.')
            $process.Kill($true)
            if ($process.WaitForExit(5000)) { $result.exitCodeAfterTermination = $process.ExitCode }
            else { $errors.Add('Timed-out process tree did not retire within the cleanup bound.') }
        }
        $result.elapsedMs = $clock.Elapsed.TotalMilliseconds
    } catch { $errors.Add($_.Exception.Message) }
    finally {
        if ($process) {
            try {
                if ($result.processId -and -not $process.HasExited) {
                    $process.Kill($true)
                    if (-not $process.WaitForExit(5000)) { $errors.Add('Native process remained alive after cleanup.') }
                }
            } catch { $errors.Add("Process cleanup: $($_.Exception.Message)") }
        }
        if ($clock) { $clock.Stop(); $result.elapsedMs = $clock.Elapsed.TotalMilliseconds }
        $result.finishedUtc = [DateTime]::UtcNow.ToString('o')
        foreach ($capture in @(@{name='stdout';task=$stdoutTask}, @{name='stderr';task=$stderrTask})) {
            try {
                if ($capture.task -and $capture.task.Wait(5000)) {
                    [IO.File]::WriteAllText((Join-Path $caseEvidence "$($capture.name).txt"), $capture.task.Result, [Text.UTF8Encoding]::new($false))
                } elseif ($capture.task) { $errors.Add("$($capture.name) did not close after process termination.") }
            } catch { $errors.Add("$($capture.name) capture: $($_.Exception.Message)") }
        }
        if ($process) { $process.Dispose() }
        try {
            foreach ($name in @('Swirl-appearance.txt','Swirl-appearance-restore.txt','Swirl-diagnostics.txt')) {
                $file = Join-Path $app $name
                if (Test-Path -LiteralPath $file -PathType Leaf) { Copy-Item -LiteralPath $file -Destination $caseEvidence }
            }
            $log = Join-Path $caseEvidence 'Swirl-appearance.txt'
            if (-not (Test-Path -LiteralPath $log -PathType Leaf)) { throw 'The new native Appearance log is missing.' }
            $text = [IO.File]::ReadAllText($log)
            $probes = [Collections.Generic.List[object]]::new()
            foreach ($match in [regex]::Matches($text, '(?m)^\d+: CONTROL_PRESS_NORMAL_FRAME (\S+) (\S+) (\{[^\r\n]*\})\r?$')) {
                try { $sample = $match.Groups[3].Value | ConvertFrom-Json -AsHashtable }
                catch { $errors.Add("Malformed native probe JSON: $($_.Exception.Message)"); continue }
                $probes.Add([ordered]@{ theme=$match.Groups[1].Value; control=$match.Groups[2].Value; sample=$sample })
                if (-not $sample.ContainsKey('swapchainProbe') -or $sample.swapchainProbe -isnot [Collections.IDictionary]) {
                    $errors.Add('Native DXGI probe is absent.'); continue
                }
                $native = $sample.swapchainProbe
                $latency = if ($native.ContainsKey('getMaximumFrameLatency')) { $native.getMaximumFrameLatency } else { $null }
                $confirmed = $native.ContainsKey('d3d11') -and $native.d3d11 -eq $true -and
                    $native.ContainsKey('qtSwapInterval') -and $native.qtSwapInterval -eq 1 -and
                    $latency -is [Collections.IDictionary] -and $latency.ContainsKey('succeeded') -and
                    $latency.succeeded -eq $true -and $latency.ContainsKey('frames') -and $latency.frames -eq $Maximum
                if (-not $confirmed) {
                    $errors.Add("The actual D3D11/vsync/maximum-latency probe did not confirm the requested case: $($match.Groups[1].Value) $($match.Groups[2].Value).")
                }
            }
            $result.normalFrameProbes = $probes.ToArray()
            if ($probes.Count -ne 8) { $errors.Add("Expected all eight unchanged press probes; found $($probes.Count).") }
            $result.qtNativeConfiguration = @($text -split '\r?\n' | Where-Object { $_ -match 'threaded render loop|Creating QRhi|Adapter \d+:|using this adapter|max frame latency|Animation Driver: using vsync' })
            $result.nativeSummary = @($text -split '\r?\n' | Where-Object { $_ -match 'APPEARANCE_CHECKS failures|APPEARANCE_RESTORE_RESULT' })
            if ($text -notmatch 'APPEARANCE_CHECKS failures \d+ totalMs \d+') { $errors.Add('Native Appearance did not write its completion summary.') }
            Write-LatencyJson (Join-Path $caseEvidence 'store-after.json') @(Get-LatencyTree $store)
        } catch { $errors.Add("Evidence collection: $($_.Exception.Message)") }
        $result.errors = $errors.ToArray()
        if ($errors.Count -eq 0 -and $result.nativeExitCode -eq 0 -and -not $result.timedOut) { $result.status = 'passed' }
        Write-LatencyJson (Join-Path $caseEvidence 'result.json') $result
        [IO.File]::WriteAllText((Join-Path $caseEvidence 'LastTest.log'),
            "Isolated diagnostic harness; not the canonical CTest log.`nCommand: $app/Swirl.exe --appearance-test`n" +
            "Requested maximum latency: $Maximum`nNative exit: $($result.nativeExitCode)`nTimeout: $($result.timedOut)`n" +
            "Deadline: 90000 ms`nStarted: $($result.startedUtc)`nFinished: $($result.finishedUtc)`n" + ($errors -join "`n"), [Text.UTF8Encoding]::new($false))
        Write-LatencyJUnit (Join-Path $caseEvidence 'junit.xml') $result
    }
    return $result
}

if (-not $IsWindows) { throw 'This diagnostic requires native Windows and the deployed Windows Qt runtime.' }
if ($PullRequestHeadSha -and $PullRequestHeadSha -notmatch '^[0-9a-fA-F]{40}$') { throw 'Invalid PR head SHA.' }
$repo = (Resolve-Path -LiteralPath $RepositoryRoot).Path.TrimEnd('\', '/')
$runtime = (Resolve-Path -LiteralPath $RuntimeDirectory).Path.TrimEnd('\', '/')
$reference = (Resolve-Path -LiteralPath $ReferenceExecutable).Path
$scratch = (Resolve-Path -LiteralPath $ScratchRoot).Path.TrimEnd('\', '/')
$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\', '/')
foreach ($path in @($repo,$runtime,$reference,$scratch,$output)) { Assert-LatencyPlainPath $path }
if (-not (Test-LatencyChildPath $output (Join-Path $repo 'build-evidence')) -or
    (Test-LatencyChildPath $output $runtime) -or (Test-LatencyChildPath $runtime $output) -or
    (Test-LatencyChildPath $scratch $repo) -or (Test-LatencyChildPath $output $scratch)) {
    throw 'Use a dedicated build-evidence output and an external temporary scratch root.'
}
if (Test-Path -LiteralPath $output) {
    if (-not (Test-Path -LiteralPath $output -PathType Container) -or @(Get-ChildItem -LiteralPath $output -Force).Count) {
        throw 'Diagnostic output already contains evidence; it will not be overwritten.'
    }
} else { New-Item -ItemType Directory -Path $output | Out-Null }
$failures = [Collections.Generic.List[string]]::new(); $cases = [Collections.Generic.List[object]]::new()
$protectedBefore = $null; $scopes = [ordered]@{}
$receipt = [ordered]@{ schema=1; diagnosticOnly=$true; replacesCriticalResult=$false; sourceSha=$null;
    workflowSha=$WorkflowSha.ToLowerInvariant(); pullRequestHeadSha=$PullRequestHeadSha; runId=$env:GITHUB_RUN_ID;
    runAttempt=$env:GITHUB_RUN_ATTEMPT; sourceDirectory=$repo; deployedRuntime=$runtime; referenceExecutable=$reference;
    startedUtc=[DateTime]::UtcNow.ToString('o'); status='failed'; caseOrder=@(2,1); executionsPerCase=1;
    cacheMethod='Two separate initially empty stores; comparison is between these cold cases, not a claim that the earlier critical run had the same cache state.';
    timingScope='Unchanged native Appearance 40 ms submission checks; Qt frameSwapped is not physical display completion.';
    initialQtEnvironment=(Get-LatencyQtEnvironment ([Environment]::GetEnvironmentVariables('Process')));
    originalEvidenceUnchanged=$false; errors=@(); cases=@() }
try {
    $sourceSha = (& git -C $repo rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $sourceSha -cne $WorkflowSha.ToLowerInvariant()) { throw 'Checkout HEAD differs from the declared workflow SHA.' }
    $receipt.sourceSha = $sourceSha
    . (Join-Path $repo 'scripts/Assert-BuildSource.ps1')
    Assert-SwirlBuildSource -RepositoryRoot $repo -ExpectedSourceSha $sourceSha
    foreach ($name in @('Swirl.exe','swirl_api.dll','swirl-rust-build.json','Qt6Core.dll','Qt6Gui.dll','Qt6Network.dll',
        'Qt6Qml.dll','Qt6Quick.dll','platforms/qwindows.dll')) {
        if (-not (Test-Path -LiteralPath (Join-Path $runtime $name) -PathType Leaf)) { throw "Deployed runtime is incomplete: $name" }
    }
    $receipt.executableSha256 = Get-LatencyHash (Join-Path $runtime 'Swirl.exe')
    $receipt.referenceExecutableSha256 = Get-LatencyHash $reference
    if ($receipt.executableSha256 -cne $receipt.referenceExecutableSha256) { throw 'Deployed EXE differs from the original critical-test EXE.' }
    $qtVersion = [Diagnostics.FileVersionInfo]::GetVersionInfo((Join-Path $runtime 'Qt6Core.dll'))
    $receipt.qtCoreVersion = $qtVersion.FileVersion
    if ($qtVersion.FileMajorPart -ne 6 -or $qtVersion.FileMinorPart -ne 12 -or $qtVersion.FileBuildPart -ne 0) { throw 'The deployed Qt runtime is not 6.12.0.' }
    $sourceFiles = [ordered]@{}
    foreach ($relative in @('scripts/Test-QtD3D11FrameLatency.ps1','src/Swirl.Quick/main.cpp','src/Swirl.Quick/tests/AppearanceChecks.cpp',
        'src/Swirl.Quick/app/StoragePaths.h','src/Swirl.Quick/app/SwirlPressClock.cpp','src/Swirl.Quick/app/SwirlPressClock.h')) {
        $sourceFiles[$relative] = Get-LatencyHash (Join-Path $repo $relative)
    }
    $receipt.sourceFileSha256 = $sourceFiles
    $build = Join-Path $repo 'build/swirl-quick'
    $scopes['deployed-runtime'] = @{ path=$runtime; topLevel=$false }
    $scopes['original-app-directory'] = @{ path=(Split-Path -Parent $reference); topLevel=$false }
    $scopes['original-build-files'] = @{ path=$build; topLevel=$true }
    foreach ($name in @('Testing','navigation-evidence','hero-evidence','activity-layout','policy-evidence','liquid-glass-evidence','settings-material-evidence')) {
        $scopes["original-$name"] = @{ path=(Join-Path $build $name); topLevel=$false }
    }
    $scopes['original-build-evidence'] = @{ path=(Join-Path $repo 'build-evidence'); topLevel=$false }
    if ($env:SWIRL_TEST_ROOT) { $scopes['original-test-storage'] = @{ path=$env:SWIRL_TEST_ROOT; topLevel=$false } }
    $protectedBefore = Get-LatencyProtectedSnapshot $scopes $output
    Write-LatencyJson (Join-Path $output 'protected-before.json') $protectedBefore
    $runtimeManifest = $protectedBefore['deployed-runtime']
    Write-LatencyJson (Join-Path $output 'runtime-manifest.json') $runtimeManifest
    $session = Join-Path $scratch ('swirl-d3d11-latency-' + [guid]::NewGuid().ToString('N'))
    $receipt.scratchSession = $session
    New-Item -ItemType Directory -Path $session | Out-Null
    foreach ($maximum in @(2,1)) {
        # A failed or timed-out case never prevents the other case from running.
        try { $case = Invoke-LatencyCase $maximum $session $runtime $runtimeManifest $output }
        catch { $case = [ordered]@{ requestedMaximumFrameLatency=$maximum; status='failed'; errors=@($_.Exception.Message) } }
        $cases.Add($case)
        if ($case.status -ne 'passed') { $failures.Add("Maximum-frame-latency $maximum diagnostic failed: $($case.errors -join ' ')") }
    }
} catch { $failures.Add($_.Exception.Message) }
finally {
    if ($protectedBefore) {
        try {
            $protectedAfter = Get-LatencyProtectedSnapshot $scopes $output
            Write-LatencyJson (Join-Path $output 'protected-after.json') $protectedAfter
            $changes = @(Compare-LatencySnapshots $protectedBefore $protectedAfter)
            Write-LatencyJson (Join-Path $output 'protected-changes.json') $changes
            $receipt.originalEvidenceUnchanged = $changes.Count -eq 0
            if ($changes.Count) { $failures.Add('Original runtime, test storage or formal evidence changed during the isolated diagnostic; see protected-changes.json.') }
            Assert-SwirlBuildSource -RepositoryRoot $repo -ExpectedSourceSha $WorkflowSha.ToLowerInvariant()
        } catch { $failures.Add("Final isolation/source verification: $($_.Exception.Message)") }
    }
    if ($cases.Count -ne 2) { $failures.Add('Both cold diagnostic cases did not complete; no A/B conclusion is valid.') }
    $receipt.finishedUtc = [DateTime]::UtcNow.ToString('o'); $receipt.cases = $cases.ToArray(); $receipt.errors = $failures.ToArray()
    if ($failures.Count -eq 0) { $receipt.status = 'passed' }
    Write-LatencyJson (Join-Path $output 'receipt.json') $receipt
}
if ($failures.Count) { throw ($failures -join "`n") }
Write-Host 'Both isolated native diagnostics passed; the original critical result has not been changed.'
