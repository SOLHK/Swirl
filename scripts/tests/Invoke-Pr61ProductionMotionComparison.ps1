#Requires -Version 7.4
param(
    [Parameter(Mandatory)][string]$RepositoryRoot,
    [Parameter(Mandatory)][string]$RuntimeDirectory,
    [Parameter(Mandatory)][string]$ReferenceExecutable,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [Parameter(Mandatory)][string]$ScratchRoot,
    [Parameter(Mandatory)][string]$SourceSha,
    [Parameter(Mandatory)][string]$PullRequestHeadSha
)

$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or -not $IsWindows) {
    throw 'Run the recovered Release comparison only on an isolated hosted Windows runner.'
}
$original = Join-Path $RepositoryRoot 'scripts/tests/Test-WindowsFullMotionSmoke.ps1'
$source = [IO.File]::ReadAllText($original)
$anchor = '            $case.environment = $childEnvironment;'
if ([regex]::Matches($source,[regex]::Escape($anchor)).Count -ne 1) {
    throw 'The exact historical harness no longer has the expected child environment boundary.'
}
$settings = @'
            foreach ($name in @('QML_DISK_CACHE','QML_FORCE_DISK_CACHE','QV4_FORCE_INTERPRETER','QV4_SKIP_AOT_VALIDATION','QV4_FAIL_ON_INVALID_AOT')) {
                if ($start.Environment.ContainsKey($name)) { $removed[$name] = $start.Environment[$name]; $null = $start.Environment.Remove($name) }
            }
            switch ($env:SWIRL_PR61_COMPARISON_MODE) {
                'default' { }
                'aot' { $childEnvironment['QML_DISK_CACHE'] = 'aot' }
                'bytecode' { $childEnvironment['QML_DISK_CACHE'] = 'aot-bytecode' }
                'runtime' { $childEnvironment['QML_DISABLE_DISK_CACHE'] = '1' }
                'policies-first' { $start.ArgumentList.Add('--preview-page=policies') }
                default { throw 'Unknown diagnostic mode.' }
            }
            foreach ($entry in $childEnvironment.GetEnumerator()) { $start.Environment[$entry.Key] = $entry.Value }
'@
$settings += "`n"
$comparisonHarness = Join-Path $ScratchRoot ('swirl-pr61-comparison-' + [guid]::NewGuid().ToString('N') + '.ps1')
[IO.File]::WriteAllText($comparisonHarness, $source.Replace($anchor, $settings + $anchor))
$null = New-Item -ItemType Directory -Path $OutputDirectory
$rows = [Collections.Generic.List[object]]::new()
$failures = [Collections.Generic.List[string]]::new()

# AOT permits validated native functions with bytecode fallback. Both AOT modes
# omit disk read/write. The policies-first case keeps the default cache and makes
# policies the initial synchronous route before the unchanged 61-route driver.
foreach ($trial in 1..2) {
    foreach ($variant in @('default','aot','bytecode','runtime','policies-first')) {
        $env:SWIRL_PR61_COMPARISON_MODE = $variant
        $casePath = Join-Path $OutputDirectory "$trial-$variant"
        $harnessFailure = $null
        try {
            & $comparisonHarness -RepositoryRoot $RepositoryRoot -RuntimeDirectory $RuntimeDirectory `
                -ReferenceExecutable $ReferenceExecutable -OutputDirectory $casePath -ScratchRoot $ScratchRoot `
                -WorkflowSha $SourceSha -PullRequestHeadSha $PullRequestHeadSha -ExpectedFlavor release
        } catch {
            $harnessFailure = $_.Exception.Message
        }
        $receiptPath = Join-Path $casePath 'receipt.json'
        if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
            $failures.Add("$trial/$variant has no receipt. $harnessFailure")
            continue
        }
        $receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
        if ($receipt.source_sha -cne $SourceSha -or $receipt.pr_head_sha -cne $PullRequestHeadSha -or
            -not $receipt.original_runtime_unchanged -or @($receipt.cases).Count -ne 2) {
            $failures.Add("$trial/$variant could not attest the same source and runtime.")
        }
        foreach ($case in $receipt.cases) {
            $warnings = @($case.warning_lines | Where-Object { $_ -match '^[123]: ' })
            $rows.Add([ordered]@{
                trial = $trial
                variant = $variant
                driver = $case.mode
                exit_code = $case.exit_code
                routes = $case.smoke_completion_counts
                warnings = $warnings.Count
                member_storage_warnings = @($warnings | Where-Object { $_ -match 'Cannot find member data' }).Count
                first_warning = $warnings | Select-Object -First 1
                vme_contexts = $case.vme_context_count
                executable_sha256 = $receipt.exe_sha256
                log_sha256 = $case.log_sha256
                errors = $case.errors
            })
            if (-not $case.process_exit_observed -or $case.timed_out -or
                ($case.smoke_completion_counts -join ' ') -cne '61' -or
                ($case.exit_code -ne 0 -and ($case.exit_code -ne 2 -or $warnings.Count -eq 0))) {
                $failures.Add("$trial/$variant/$($case.mode) did not complete a comparable traversal.")
            }
        }
    }
}
Remove-Item Env:SWIRL_PR61_COMPARISON_MODE
$report = [ordered]@{source_sha=$SourceSha; pr_head_sha=$PullRequestHeadSha; rows=$rows.ToArray(); incomplete=$failures.ToArray()}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'comparison.json') -Encoding utf8
if ($failures.Count -ne 0) { throw ($failures -join "`n") }
