[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$FixtureDirectory,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [switch]$InstallPerUserFont
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# This script only measures the two fonts authored by the D1 generator. It is
# not an installer for PingFang or a production acceptance certificate.
# Installation model reviewed before implementation:
# https://learn.microsoft.com/en-us/windows/win32/gdi/font-installation-and-deletion
# https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-addfontresourcew
# https://github.com/fontlaborg/fontlift-win-cli (design reference; no code copied)

$resultDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $resultDirectory) {
    throw 'Use a new output directory; D1 evidence must not be overwritten.'
}
New-Item -ItemType Directory -Path $resultDirectory | Out-Null
$reportPath = Join-Path $resultDirectory 'windows-axis-precision-run.json'
$report = [ordered]@{
    schema = 1
    status = 'NOT_RUN'
    started_utc = [DateTime]::UtcNow.ToString('o')
    source_commit = $env:GITHUB_SHA
    source_ref = $env:GITHUB_REF
    run_id = $env:GITHUB_RUN_ID
    run_attempt = $env:GITHUB_RUN_ATTEMPT
    runner_label = $env:D1_RUNNER_LABEL
    platform = [Environment]::OSVersion.VersionString
    powershell_version = $PSVersionTable.PSVersion.ToString()
    original_ttc_acceptance = 'NOT_RUN_NO_QUALIFIED_CANDIDATE'
    original_equality = 'NOT_TESTED'
    real_swirl_ui = 'NOT_TESTED'
    physical_display_dpi = 'NOT_TESTED'
    windows11_acceptance = 'NOT_RUN'
    system_installation_requested = $InstallPerUserFont.IsPresent
    font_installation_reboot = 'NOT_TESTED'
    sources = @{}
    fixtures = @{}
    binaries = @{}
    runs = [Collections.Generic.List[object]]::new()
    installations = [Collections.Generic.List[object]]::new()
    errors = [Collections.Generic.List[string]]::new()
}
$returnCode = 1
$savedQpa = $env:QT_QPA_PLATFORM
$savedPluginPath = $env:QT_QPA_PLATFORM_PLUGIN_PATH

function File-Identity([string]$Path) {
    $file = Get-Item -LiteralPath $Path
    return @{ file = $file.Name; bytes = $file.Length;
              sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
}

function Invoke-D1Probe {
    param([string]$Executable, [string]$Font, [string]$Label, [string]$ReportName,
          [string]$ExpectedStatus, [string[]]$ExtraArguments = @(), [string]$Platform = '')
    $directory = Join-Path $resultDirectory $Label
    New-Item -ItemType Directory -Path $directory | Out-Null
    $entry = [ordered]@{ label = $Label; status = 'FAILED'; platform_requested = $Platform;
        output = $Label; exit_code = $null; timeout = $false; summary = $null }
    $report.runs.Add($entry)
    $process = $null
    try {
        if ($Platform) { $env:QT_QPA_PLATFORM = $Platform }
        else { $env:QT_QPA_PLATFORM = $savedQpa }
        $start = [Diagnostics.ProcessStartInfo]::new()
        $start.FileName = $Executable
        $start.WorkingDirectory = $directory
        $start.UseShellExecute = $false
        $start.RedirectStandardOutput = $true
        $start.RedirectStandardError = $true
        $start.ArgumentList.Add($Font)
        $start.ArgumentList.Add($directory)
        foreach ($argument in $ExtraArguments) { $start.ArgumentList.Add($argument) }
        $entry.command = @($Executable, $Font, $directory) + $ExtraArguments
        $process = [Diagnostics.Process]::new()
        $process.StartInfo = $start
        if (-not $process.Start()) { throw 'Could not start native probe.' }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(180000)) {
            $entry.timeout = $true
            $process.Kill($true)
            $process.WaitForExit()
        }
        $entry.exit_code = $process.ExitCode
        $stdoutTask.Result | Set-Content -LiteralPath (Join-Path $directory 'stdout.log') -Encoding utf8
        $stderrTask.Result | Set-Content -LiteralPath (Join-Path $directory 'stderr.log') -Encoding utf8
        if ($entry.timeout) { throw 'Probe exceeded its 180 second process limit.' }
        $nativeLog = Join-Path $directory $ReportName
        $rows = @(Get-Content -LiteralPath $nativeLog -Encoding UTF8 | ForEach-Object {
            if (-not [string]::IsNullOrWhiteSpace($_)) { $_ | ConvertFrom-Json -AsHashtable }
        })
        $headers = @($rows | Where-Object { $_.Contains('record') -and $_.record -eq 'header' })
        $summaries = @($rows | Where-Object { $_.Contains('record') -and $_.record -eq 'summary' })
        $errors = @($rows | Where-Object { $_.Contains('record') -and $_.record -eq 'error' })
        if ($headers.Count -ne 1 -or $summaries.Count -ne 1 -or $errors.Count -ne 0) {
            throw 'Native evidence has missing/ambiguous header or footer, or an error row.'
        }
        $entry.header = $headers[0]
        $entry.summary = $summaries[0]
        $entry.native_log = File-Identity $nativeLog
        $expectedHash = (File-Identity $Font).sha256
        if ($headers[0].input_sha256 -cne $expectedHash) { throw 'Probe input identity does not match authored fixture.' }
        if ($entry.exit_code -ne 0 -or $summaries[0].status -cne $ExpectedStatus) {
            throw 'Native probe did not complete its exact required successful summary.'
        }
        if ($rows[-1].record -cne 'summary') { throw 'Final JSONL row is not the completed summary.' }
        $entry.status = 'PASS'
        Write-Output ('D1_HEADER ' + $Label + ' ' + ($headers[0] | ConvertTo-Json -Compress -Depth 30))
        # Full paths and all repeated observations stay in the JSONL artifact.
        # The first pair observations also appear in job logs for direct review.
        $printed = @{}
        foreach ($row in $rows) {
            $id = ''
            foreach ($key in @('case_id', 'request_id', 'id', 'case')) {
                if ($row.Contains($key) -and $row[$key] -is [string]) { $id = [string]$row[$key]; break }
            }
            if ($id -in @('pair_lo', 'pair_hi') -and -not $printed.ContainsKey($id)) {
                Write-Output ('D1_PAIR ' + $Label + ' ' + ($row | ConvertTo-Json -Compress -Depth 30))
                $printed[$id] = $true
            }
        }
        Write-Output ('D1_SUMMARY ' + $Label + ' ' + ($summaries[0] | ConvertTo-Json -Compress -Depth 30))
    } catch {
        $entry.error = $_.Exception.Message
        $report.errors.Add($Label + ': ' + $_.Exception.Message)
        Write-Output ('D1_FAILED ' + $Label + ': ' + $_.Exception.Message)
        foreach ($logName in @('stdout.log', 'stderr.log')) {
            $logPath = Join-Path $directory $logName
            if (Test-Path -LiteralPath $logPath) { Get-Content -LiteralPath $logPath }
        }
    } finally {
        if ($null -ne $process) { $process.Dispose() }
        $env:QT_QPA_PLATFORM = $savedQpa
    }
}

function Invoke-FixtureModes([string]$Font, [string]$FixtureName, [bool]$Installed) {
    $mode = if ($Installed) { 'installed' } else { 'private' }
    foreach ($order in @('forward', 'reverse')) {
        $arguments = @('--cases', $casesPath)
        if ($Installed) { $arguments += '--installed' }
        if ($order -eq 'reverse') { $arguments += '--reverse' }
        Invoke-D1Probe -Executable $nativeExe -Font $Font -Label "$FixtureName-dwrite-$mode-$order" -ReportName 'directwrite-axis-precision.jsonl' -ExpectedStatus 'PASS_DWRITE_SYNTHETIC' -ExtraArguments $arguments
        if ($FixtureName -eq 'ordinary') {
            foreach ($backend in @('native', 'freetype')) {
                $qtArguments = @()
                if ($Installed) { $qtArguments += '--installed' }
                if ($order -eq 'reverse') { $qtArguments += '--reverse' }
                # Qt 6.10.3 accepts native/freetype/gdi. "directwrite" is not
                # a recognized fontengine value and would silently use default.
                Invoke-D1Probe -Executable $qtExe -Font $Font -Label "$FixtureName-qt-$backend-$mode-$order" -ReportName 'qt-axis-precision.jsonl' -ExpectedStatus 'PASS_QT_SYNTHETIC' -ExtraArguments $qtArguments -Platform "windows:fontengine=$backend"
            }
        }
    }
}

try {
    if ($env:OS -ne 'Windows_NT') { throw 'D1 requires actual Windows; no Linux replacement result is accepted.' }
    if ($InstallPerUserFont -and ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted')) {
        throw 'Per-user installation is scoped to a disposable GitHub-hosted runner. Omit -InstallPerUserFont for local file/private tests.'
    }
    $fixtures = (Resolve-Path -LiteralPath $FixtureDirectory).Path
    $casesPath = Join-Path $fixtures 'requests.tsv'
    if (-not (Test-Path -LiteralPath $casesPath)) { throw 'Original fixture requests.tsv is missing.' }
    $manifest = Get-Content -LiteralPath (Join-Path $fixtures 'manifest.json') -Raw | ConvertFrom-Json -AsHashtable
    if ($manifest.original_synthetic -isnot [bool] -or -not $manifest.original_synthetic) { throw 'This harness accepts only the authored D1 fixture manifest.' }
    if ($manifest.fonts.Count -ne 2 -or $manifest.requests_sha256 -cne (File-Identity $casesPath).sha256) { throw 'Fixture manifest or request stream identity mismatch.' }
    Copy-Item -LiteralPath (Join-Path $fixtures 'manifest.json') -Destination (Join-Path $resultDirectory 'fixture-manifest.json')
    Copy-Item -LiteralPath $casesPath -Destination (Join-Path $resultDirectory 'requests.tsv')
    foreach ($name in @('ordinary', 'gain')) {
        $report.fixtures[$name] = File-Identity (Join-Path $fixtures "$name.ttf")
        $binding = @($manifest.fonts | Where-Object { $_.kind -ceq $name -and $_.file -ceq "$name.ttf" })
        if ($binding.Count -ne 1 -or $binding[0].sha256 -cne $report.fixtures[$name].sha256) { throw "Fixture manifest hash mismatch: $name" }
    }
    foreach ($name in @('win_axis_precision_directwrite.cpp', 'win_axis_precision_qt.cpp', 'make_win_axis_precision_fixture.py', 'run_win_axis_precision.ps1')) {
        $report.sources[$name] = File-Identity (Join-Path $PSScriptRoot $name)
    }
    $report.sources['CMakeLists.txt'] = File-Identity (Join-Path $PSScriptRoot 'win_axis_precision/CMakeLists.txt')
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $report.windows_product = $os.Caption
    $report.windows_version = $os.Version
    $report.windows_build = $os.BuildNumber
    $report.os_architecture = $os.OSArchitecture
    $report.product_type = $os.ProductType
    # Even a matching kernel build is not proof that a Server VM is Windows 11.
    if ($os.ProductType -eq 1 -and $os.Caption -match 'Windows 11') { $report.windows11_acceptance = 'SYNTHETIC_RUNTIME_ONLY' }
    $dwrite = Get-Item -LiteralPath (Join-Path $env:SystemRoot 'System32/dwrite.dll')
    $report.dwrite_version = $dwrite.VersionInfo.FileVersion
    $report.dwrite_identity = File-Identity $dwrite.FullName
    if ($env:GITHUB_SHA) {
        $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
        $checkedOut = (& git -C $repoRoot rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0 -or $checkedOut -cne $env:GITHUB_SHA) { throw 'Checked-out source does not match the triggering commit.' }
    }
    $qtVersion = (& qmake -query QT_VERSION).Trim()
    if ($LASTEXITCODE -ne 0 -or $qtVersion -cne '6.10.3') { throw "Unexpected Qt SDK: $qtVersion" }
    $report.qt_sdk = $qtVersion
    $qtSpec = (& qmake -query QMAKE_XSPEC).Trim()
    if ($LASTEXITCODE -ne 0 -or $qtSpec -cne 'win32-msvc') { throw "Unexpected Qt compiler ABI: $qtSpec" }
    $qtPlugins = (& qmake -query QT_INSTALL_PLUGINS).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Qt plugin directory is unavailable.' }
    $env:QT_QPA_PLATFORM_PLUGIN_PATH = Join-Path $qtPlugins 'platforms'
    $buildDirectory = Join-Path $resultDirectory 'build'
    & cmake -S (Join-Path $PSScriptRoot 'win_axis_precision') -B $buildDirectory -G 'Visual Studio 17 2022' -A x64 *> (Join-Path $resultDirectory 'cmake-configure.log')
    if ($LASTEXITCODE -ne 0) {
        Get-Content -LiteralPath (Join-Path $resultDirectory 'cmake-configure.log')
        throw 'Windows CMake configure failed.'
    }
    Copy-Item -LiteralPath (Join-Path $buildDirectory 'd1-toolchain.txt') -Destination $resultDirectory
    $toolchain = Get-Content -LiteralPath (Join-Path $buildDirectory 'd1-toolchain.txt') -Raw
    if ($toolchain -notmatch '(?m)^Qt=6\.10\.3\r?$' -or $toolchain -notmatch '(?m)^Compiler=MSVC\r?$' -or $toolchain -notmatch '(?m)^PointerSize=8\r?$') {
        throw 'Qt/compiler ABI toolchain evidence mismatch.'
    }
    & cmake --build $buildDirectory --config Release --parallel 2 *> (Join-Path $resultDirectory 'cmake-build.log')
    if ($LASTEXITCODE -ne 0) {
        Get-Content -LiteralPath (Join-Path $resultDirectory 'cmake-build.log')
        throw 'Actual Windows native compilation failed.'
    }
    $nativeExe = (Resolve-Path -LiteralPath (Join-Path $buildDirectory 'Release/win_axis_precision_directwrite.exe')).Path
    $qtExe = (Resolve-Path -LiteralPath (Join-Path $buildDirectory 'Release/win_axis_precision_qt.exe')).Path
    $report.binaries.directwrite = File-Identity $nativeExe
    $report.binaries.qt = File-Identity $qtExe
    foreach ($name in @('ordinary', 'gain')) {
        Invoke-FixtureModes (Join-Path $fixtures "$name.ttf") $name $false
    }
    if ($InstallPerUserFont) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class SwirlD1FontRegistration {
    [DllImport("gdi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
    public static extern int AddFontResourceW(string path);
    [DllImport("gdi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool RemoveFontResourceW(string path);
    [DllImport("user32.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
    public static extern IntPtr SendMessageTimeoutW(IntPtr window, uint message, UIntPtr wparam, IntPtr lparam, uint flags, uint timeout, out UIntPtr result);
    public static bool Notify() {
        UIntPtr result;
        return SendMessageTimeoutW(new IntPtr(0xffff), 0x001d, UIntPtr.Zero, IntPtr.Zero, 2, 5000, out result) != IntPtr.Zero;
    }
}
'@
        $fontDirectory = Join-Path $env:LOCALAPPDATA 'Microsoft/Windows/Fonts'
        New-Item -ItemType Directory -Force -Path $fontDirectory | Out-Null
        $registryPath = 'Software\Microsoft\Windows NT\CurrentVersion\Fonts'
        foreach ($name in @('ordinary', 'gain')) {
            $family = if ($name -eq 'ordinary') { 'Swirl D1 Precision' } else { 'Swirl D1 Precision Gain' }
            $valueName = "$family (TrueType)"
            $destination = Join-Path $fontDirectory ('SwirlD1-' + [guid]::NewGuid().ToString('N') + '.ttf')
            $lifecycle = [ordered]@{ fixture = $name; family = $family; registry_hive = 'HKCU';
                registry_value = $valueName; installed_copy = $destination; status = 'FAILED';
                cleanup = 'NOT_RUN'; resource_added = $false; registry_added = $false; file_copied = $false }
            $report.installations.Add($lifecycle)
            $key = $null
            try {
                $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($registryPath)
                if ($key.GetValueNames() -contains $valueName) { throw 'Authored fixture registry name already exists; refusing to replace it.' }
                Copy-Item -LiteralPath (Join-Path $fixtures "$name.ttf") -Destination $destination -ErrorAction Stop
                $lifecycle.file_copied = $true
                $copyHash = (File-Identity $destination).sha256
                if ($copyHash -cne $report.fixtures[$name].sha256) { throw 'Installed copy hash mismatch.' }
                $key.SetValue($valueName, $destination, [Microsoft.Win32.RegistryValueKind]::String)
                $lifecycle.registry_added = $true
                $count = [SwirlD1FontRegistration]::AddFontResourceW($destination)
                if ($count -le 0) { throw 'AddFontResourceW did not register the authored fixture.' }
                $lifecycle.resource_added = $true
                $lifecycle.registered_faces = $count
                $lifecycle.broadcast_after_add = [SwirlD1FontRegistration]::Notify()
                if (-not $lifecycle.broadcast_after_add) { throw 'Font addition WM_FONTCHANGE broadcast failed.' }
                $lifecycle.status = 'REGISTERED'
                # Discovery is verified in a fresh process through the actual
                # system collection. Registration alone is never a PASS.
                Invoke-FixtureModes (Join-Path $fixtures "$name.ttf") $name $true
            } catch {
                $lifecycle.error = $_.Exception.Message
                $report.errors.Add('Install ' + $name + ': ' + $_.Exception.Message)
            } finally {
                $cleanupErrors = [Collections.Generic.List[string]]::new()
                try {
                    if ($lifecycle.resource_added) {
                        $lifecycle.resource_removed = [SwirlD1FontRegistration]::RemoveFontResourceW($destination)
                        if (-not $lifecycle.resource_removed) { throw 'RemoveFontResourceW failed for owned fixture registration.' }
                    }
                } catch { $cleanupErrors.Add($_.Exception.Message) }
                try {
                    if ($lifecycle.registry_added -and $null -ne $key) {
                        if ($key.GetValue($valueName) -cne $destination) { throw 'Owned registry value changed unexpectedly; refusing to remove another value.' }
                        $key.DeleteValue($valueName, $true)
                    }
                } catch { $cleanupErrors.Add($_.Exception.Message) }
                try {
                    if ($lifecycle.file_copied) { Remove-Item -LiteralPath $destination -ErrorAction Stop }
                } catch { $cleanupErrors.Add($_.Exception.Message) }
                try {
                    if ($lifecycle.resource_added) {
                        $lifecycle.broadcast_after_remove = [SwirlD1FontRegistration]::Notify()
                        if (-not $lifecycle.broadcast_after_remove) { throw 'Font removal WM_FONTCHANGE broadcast failed.' }
                    }
                    if (Test-Path -LiteralPath $destination) { throw 'Owned installed copy still exists after cleanup.' }
                    if ($lifecycle.registry_added -and ($key.GetValueNames() -contains $valueName)) { throw 'Owned registry value still exists after cleanup.' }
                } catch { $cleanupErrors.Add($_.Exception.Message) }
                if ($null -ne $key) { $key.Dispose() }
                $lifecycle.cleanup = if ($cleanupErrors.Count -eq 0) { 'PASS' } else { 'FAILED' }
                $lifecycle.cleanup_errors = @($cleanupErrors)
                foreach ($cleanupError in $cleanupErrors) { $report.errors.Add('Cleanup ' + $name + ': ' + $cleanupError) }
                Write-Output ('D1_INSTALLATION ' + ($lifecycle | ConvertTo-Json -Compress -Depth 15))
            }
        }
    }
    $expectedRuns = if ($InstallPerUserFont) { 16 } else { 8 }
    if ($report.runs.Count -ne $expectedRuns) { $report.errors.Add("Incomplete native matrix: $($report.runs.Count)/$expectedRuns") }
    if (@($report.runs | Where-Object { $_.status -ne 'PASS' }).Count -gt 0) { $report.errors.Add('One or more native observations failed.') }
    foreach ($name in @('ordinary', 'gain')) {
        if ((File-Identity (Join-Path $fixtures "$name.ttf")).sha256 -cne $report.fixtures[$name].sha256) { $report.errors.Add('Fixture changed: ' + $name) }
    }
    if ($report.errors.Count -eq 0) { $report.status = 'PASS_SYNTHETIC_WINDOWS_EXPERIMENT'; $returnCode = 0 }
    else { $report.status = 'FAILED' }
} catch {
    $report.status = 'FAILED'
    $report.errors.Add($_.Exception.Message)
} finally {
    $env:QT_QPA_PLATFORM = $savedQpa
    $env:QT_QPA_PLATFORM_PLUGIN_PATH = $savedPluginPath
    $report.ended_utc = [DateTime]::UtcNow.ToString('o')
    $report | ConvertTo-Json -Depth 60 | Set-Content -LiteralPath $reportPath -Encoding utf8
    Write-Output ('D1_RUN ' + ($report | ConvertTo-Json -Compress -Depth 60))
    if ($env:GITHUB_STEP_SUMMARY) {
        "D1 runtime: $($report.platform); status: $($report.status). Original TTC and physical Windows 11 display acceptance remain unexecuted." | Add-Content -LiteralPath $env:GITHUB_STEP_SUMMARY
    }
}
exit $returnCode
