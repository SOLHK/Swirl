[CmdletBinding()]
param([string]$Font = (Join-Path $PSScriptRoot '..\SwirlVF.ttc'),
      [string]$OutputDirectory = (Join-Path $PSScriptRoot ('results-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))))
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Actual Windows is required' }
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Choose a fresh output directory' }
$plan = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'plan.json') -Raw | ConvertFrom-Json
$fontPath = (Resolve-Path -LiteralPath $Font).Path
$before = (Get-FileHash -LiteralPath $fontPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($before -ne $plan.candidate_sha256) { throw 'Candidate SHA256 mismatch' }
$requestsHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'requests.txt') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($requestsHash -ne $plan.requests_sha256) { throw 'Request file SHA256 mismatch' }
foreach ($binary in $plan.binaries) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $binary.file) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $binary.sha256) { throw 'Diagnostic binary SHA256 mismatch' }
}
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$os = Get-CimInstance Win32_OperatingSystem
$report = [ordered]@{ input_sha256 = $before; windows_product = $os.Caption; windows_version = $os.Version;
    os_architecture = $os.OSArchitecture; desktop_visual = 'NOT_RUN'; persistent_installation = 'NOT_RUN';
    production_accepted = $false; requested_outlines = $plan.requests; source_upload = $false }
try {
    $writer = [System.IO.StreamWriter]::new((Join-Path $OutputDirectory 'outline-coordinates.jsonl'), $false, [Text.UTF8Encoding]::new($false))
    try {
        Get-Content -LiteralPath (Join-Path $PSScriptRoot 'requests.txt') |
            & (Join-Path $PSScriptRoot 'observe.exe') $fontPath 2> (Join-Path $OutputDirectory 'observer.stderr.log') |
            ForEach-Object { $writer.WriteLine($_) }
        $report.observer_exit_code = $LASTEXITCODE
    } finally { $writer.Dispose() }
    $header = Get-Content -LiteralPath (Join-Path $OutputDirectory 'outline-coordinates.jsonl') -TotalCount 1 | ConvertFrom-Json
    $summary = Get-Content -LiteralPath (Join-Path $OutputDirectory 'outline-coordinates.jsonl') -Tail 1 | ConvertFrom-Json
    if ($header.faces -ne 4 -or $summary.requests -ne $plan.requests) { throw 'Incomplete native observation' }
    $report.observed_outlines = $summary.requests
    $report.axis_readback_mismatches = $summary.axis_readback_mismatches
    $report.exact_axis_gate_passed = $summary.exact_axis_gate_passed
    $report.private_GDI_registered_fonts = $header.private_GDI_registered_fonts
    & (Join-Path $PSScriptRoot 'medium.exe') $fontPath > (Join-Path $OutputDirectory 'medium.json') 2> (Join-Path $OutputDirectory 'medium.stderr.log')
    $report.medium_exit_code = $LASTEXITCODE
    $medium = Get-Content -LiteralPath (Join-Path $OutputDirectory 'medium.json') -Raw | ConvertFrom-Json
    if ($medium.status -ne 'PASS' -or $medium.families -ne 4) { throw 'Native Medium selection failed' }
    # Preserve the original strict readback/precision failure, independently of
    # the complete requested-position capture above. The probe also records
    # Unicode mapping, font metadata and actual Windows raster observations.
    & (Join-Path $PSScriptRoot 'directwrite_probe.exe') $fontPath (Join-Path $OutputDirectory 'strict') --render --outline-coordinates > (Join-Path $OutputDirectory 'strict.stdout.log') 2> (Join-Path $OutputDirectory 'strict.stderr.log')
    $report.strict_exit_code = $LASTEXITCODE
    $report.status = 'CAPTURED_REQUIRES_GEOMETRY_AND_VISUAL_REVIEW'
} catch {
    $report.status = 'FAILED'
    $report.error = $_.Exception.Message
} finally {
    $after = (Get-FileHash -LiteralPath $fontPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $report.input_unchanged = ($after -eq $before)
    if (-not $report.input_unchanged) { $report.status = 'FAILED_INPUT_CHANGED' }
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'windows-run.json') -Encoding UTF8
    Write-Output ('Report: ' + (Join-Path $OutputDirectory 'windows-run.json'))
}
if ($report.status -like 'FAILED*' -or $report.observer_exit_code -ne 0 -or $report.medium_exit_code -ne 0) { exit 1 }
exit 0
