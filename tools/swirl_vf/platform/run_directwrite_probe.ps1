[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Font,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [switch]$AllGlyphs,
    [switch]$Render,
    [string]$Binary
)
$ErrorActionPreference = 'Stop'
$resultDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $resultDirectory | Out-Null
$reportPath = Join-Path $resultDirectory 'directwrite-run.json'
if (Test-Path -LiteralPath $reportPath) { throw 'Choose a new output directory; an earlier report will not be overwritten.' }
$report = [ordered]@{
    schema = 1
    status = 'NOT_RUN'
    started_utc = [DateTime]::UtcNow.ToString('o')
    platform = [System.Environment]::OSVersion.VersionString
    powershell_version = $PSVersionTable.PSVersion.ToString()
    input_path = $Font
    input_sha256 = $null
    input_bytes = $null
    source_sha256 = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'directwrite_probe.cpp') -Algorithm SHA256).Hash.ToLowerInvariant()
    build = 'NOT_RUN'
    native_runtime = 'NOT_RUN'
    original_outline_equality = 'NOT_EVALUATED'
    system_installation = 'NOT_TESTED'
    real_swirl_ui = 'NOT_TESTED'
    clarity_review = 'NOT_EVALUATED'
    requested = @{ all_glyphs = $AllGlyphs.IsPresent; render = $Render.IsPresent }
}
$returnCode = 77
$resolvedFont = $null
try {
    if ($env:OS -ne 'Windows_NT') {
        $report.reason = 'Windows DirectWrite runtime is unavailable on this operating system.'
    } elseif (-not (Test-Path -LiteralPath $Font -PathType Leaf)) {
        $report.reason = 'Candidate font does not exist; no replacement or renamed source was generated.'
    } else {
        # Kernel version alone cannot distinguish Windows 11 from a Server CI
        # runner. Retain the actual product name without turning WMI availability
        # into a requirement for the DirectWrite test itself.
        try {
            $operatingSystem = Get-CimInstance -ClassName Win32_OperatingSystem
            $report.windows_product = $operatingSystem.Caption
            $report.windows_version = $operatingSystem.Version
            $report.windows_build = $operatingSystem.BuildNumber
            $report.os_architecture = $operatingSystem.OSArchitecture
        } catch {
            $report.windows_product = 'UNRESOLVED'
            $report.os_query_error = $_.Exception.Message
        }
        $resolvedFont = (Resolve-Path -LiteralPath $Font).Path
        $report.input_path = $resolvedFont
        $report.input_sha256 = (Get-FileHash -LiteralPath $resolvedFont -Algorithm SHA256).Hash.ToLowerInvariant()
        $report.input_bytes = (Get-Item -LiteralPath $resolvedFont).Length
        $ready = $false
        if ($Binary) {
            $exe = (Resolve-Path -LiteralPath $Binary).Path
            $report.build = 'PREBUILT_BINARY'
            $ready = $true
        } elseif (Get-Command cmake -ErrorAction SilentlyContinue) {
            $buildDirectory = Join-Path $resultDirectory 'build'
            $configureArgs = @('-S', $PSScriptRoot, '-B', $buildDirectory, '-A', 'x64')
            $report.configure_command = @('cmake') + $configureArgs
            & cmake @configureArgs *> (Join-Path $resultDirectory 'cmake-configure.log')
            $configureCode = $LASTEXITCODE
            $report.configure_exit_code = $configureCode
            if ($configureCode -eq 0) {
                $buildArgs = @('--build', $buildDirectory, '--config', 'Release', '--target', 'directwrite_probe')
                $report.build_command = @('cmake') + $buildArgs
                & cmake @buildArgs *> (Join-Path $resultDirectory 'cmake-build.log')
                $buildCode = $LASTEXITCODE
                $report.build_exit_code = $buildCode
                if ($buildCode -eq 0) {
                    $exe = Join-Path $buildDirectory 'Release\directwrite_probe.exe'
                    if (-not (Test-Path -LiteralPath $exe)) { $exe = Join-Path $buildDirectory 'directwrite_probe.exe' }
                    if (-not (Test-Path -LiteralPath $exe)) { throw 'CMake reported success but the executable was not found.' }
                    $report.build = 'COMPILED'
                    $ready = $true
                }
            }
            if (-not $ready) {
                $report.status = 'BUILD_FAILED'
                $report.reason = 'Actual Windows C++/SDK build failed. See the CMake logs.'
                $returnCode = 1
            }
        } else {
            $report.reason = 'CMake/Visual Studio C++ build tools are unavailable. Supply -Binary or install the documented build prerequisites.'
        }
        if ($ready) {
            $report.binary_sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
            $nativeArgs = @($resolvedFont, $resultDirectory)
            if ($AllGlyphs) { $nativeArgs += '--all-glyphs' }
            if ($Render) { $nativeArgs += '--render' }
            $report.run_command = @($exe) + $nativeArgs
            & $exe @nativeArgs 1> (Join-Path $resultDirectory 'native.stdout.log') 2> (Join-Path $resultDirectory 'native.stderr.log')
            $returnCode = $LASTEXITCODE
            $report.native_exit_code = $returnCode
            $report.native_runtime = 'RAN'
            $nativeLog = Join-Path $resultDirectory 'directwrite.jsonl'
            # Font axis tags are case-sensitive. DirectWrite may expose both
            # the physical custom WDTH and a synthesized registered wdth axis.
            # PSCustomObject cannot retain these distinct JSON keys.
            $rows = @(Get-Content -LiteralPath $nativeLog -Encoding UTF8 | ForEach-Object { $_ | ConvertFrom-Json -AsHashtable })
            $headers = @($rows | Where-Object { $_.record -eq 'header' })
            $summaries = @($rows | Where-Object { $_.record -eq 'summary' })
            $failures = @($rows | Where-Object { $_.record -eq 'face_result' -and $_.status -eq 'FAILED' })
            $report.native_log_sha256 = (Get-FileHash -LiteralPath $nativeLog -Algorithm SHA256).Hash.ToLowerInvariant()
            $report.native_summary = $summaries
            if ($returnCode -eq 0 -and $headers.Count -eq 1 -and $summaries.Count -eq 1 -and
                $failures.Count -eq 0 -and $summaries[0].status -eq 'PASS_NATIVE_PROBE' -and
                $headers[0].input_sha256 -eq $report.input_sha256 -and
                $summaries[0].faces_passed -eq $headers[0].physical_face_count) {
                $report.status = 'PASS_NATIVE_PROBE'
            } else {
                $report.status = 'FAILED'
                if ($returnCode -eq 0) { $returnCode = 1 }
            }
            $report.rasters = @(Get-ChildItem -LiteralPath $resultDirectory -Filter '*.png' | ForEach-Object {
                @{ file = $_.Name; bytes = $_.Length; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
            })
        }
    }
} catch {
    $report.status = 'FAILED'
    $report.error = $_.Exception.Message
    $returnCode = 1
} finally {
    if ($resolvedFont) {
        $report.input_sha256_after = (Get-FileHash -LiteralPath $resolvedFont -Algorithm SHA256).Hash.ToLowerInvariant()
        $report.input_unchanged = $report.input_sha256_after -eq $report.input_sha256
        if (-not $report.input_unchanged) { $report.status = 'FAILED_INPUT_CHANGED'; $returnCode = 1 }
    }
    $report.ended_utc = [DateTime]::UtcNow.ToString('o')
    $report | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Output ('Status: ' + $report.status)
    Write-Output ('Report: ' + $reportPath)
}
exit $returnCode
