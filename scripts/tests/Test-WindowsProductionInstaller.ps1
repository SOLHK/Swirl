param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$PackageDirectory,
    [Parameter(Mandatory=$true)][string]$ExpectedSourceSha,
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT' -or $env:GITHUB_ACTIONS -ne 'true' -or
    $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:SWIRL_DISPOSABLE_INSTALL_TEST -ne '1') {
    throw 'Production installer execution requires an explicitly opted-in disposable GitHub Windows runner.'
}
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $repo 'scripts/RustProductPackagePolicy.ps1')
$source = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $source -cne $ExpectedSourceSha) { throw 'Installer test checkout identity mismatch.' }
$manifest = Assert-SwirlProductManifest -ApplicationDirectory $PackageDirectory -ExpectedSourceSha $source
$package = (Resolve-Path -LiteralPath $PackageDirectory).Path
Assert-SwirlPathWithoutLinks $Installer
$setup = (Resolve-Path -LiteralPath $Installer).Path
Assert-SwirlPathWithoutLinks $EvidenceDirectory
$evidence = [IO.Path]::GetFullPath($EvidenceDirectory)
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
# This is the installer's existing, explicitly isolated namespace. Do not
# generalize its production path policy just to make a CI test convenient.
$root = Join-Path 'D:\Codex\tmp\s4' ('production-installer-' + [guid]::NewGuid().ToString('N'))
$target = Join-Path $root 'install'
Assert-SwirlPathWithoutLinks $root
New-Item -ItemType Directory -Path $root | Out-Null
$processes = New-Object 'System.Collections.Generic.List[object]'
$result = [ordered]@{
    schema=1; source_sha=$source; installer_sha256=(Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
    scope='Actual production NSIS isolated install, installed runtime and uninstall on a disposable Windows runner.'
    windows11_codex_desktop='NOT_RUN'; normal_user_installation='NOT_RUN'; isolated=$true
    installed_files=0; all_installed_hashes_verified=$false; exact_installed_inventory=$false
    installed_exe_sha256=$null; installed_rust_dll_sha256=$null; installed_manifest_sha256=$null
    rust_roundtrips_verified=$false; tls_runtime_verified=$false; installed_ui_pages=0; runtime_storage_isolated=$false
    installer_exit_code=$null; uninstaller_exit_code=$null; install_directory_removed=$false
    user_integration_unchanged=$false; remaining_owned_processes=$null; fixture_removed=$false
    failure_diagnostics_preserved=$false
    forced_termination=$false; processes=$processes; success=$false; error=$null
}
$savedEnvironment = @{}
foreach ($name in @('SWIRL_ISOLATED_INSTALL_ROOT','SWIRL_TEST_ROOT','QT_QPA_PLATFORM','QSG_RHI_BACKEND',
    'QT_QUICK_BACKEND','QT_SCALE_FACTOR','QT_SCREEN_SCALE_FACTORS','QT_PLUGIN_PATH','QML_IMPORT_PATH','QML2_IMPORT_PATH','PATH')) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name,'Process')
}
function Assert-FixturePath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\','/')
    if ($full -cne $root -and -not $full.StartsWith($root + '\',[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing an installer lifecycle operation outside its unique fixture.'
    }
    Assert-SwirlPathWithoutLinks $full
}
function Snapshot-UserIntegration {
    # Keep raw registry/shortcut state in memory only. The public evidence
    # records equality, never another application's user configuration.
    $data = [ordered]@{}
    foreach ($key in @('HKCU:\Software\Swirl','HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Swirl')) {
        $values = $null
        if (Test-Path -LiteralPath $key) {
            $item = Get-Item -LiteralPath $key
            $values = [ordered]@{}
            foreach ($name in @($item.GetValueNames() | Sort-Object)) {
                $values[$name] = [ordered]@{kind=$item.GetValueKind($name).ToString()
                    value=$item.GetValue($name,$null,[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)}
            }
        }
        $data[$key] = $values
    }
    foreach ($path in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Swirl.lnk'),
        (Join-Path ([Environment]::GetFolderPath('Programs')) 'Swirl'))) {
        $data[$path] = if (Test-Path -LiteralPath $path) {
            @(Get-ChildItem -LiteralPath $path -File -Recurse -Force | Sort-Object FullName | ForEach-Object {
                [ordered]@{path=$_.FullName; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}
            })
        } else { $null }
    }
    return ($data | ConvertTo-Json -Depth 8 -Compress)
}
function Get-OwnedProcesses {
    return @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
        $_.ExecutablePath -and ([string]$_.ExecutablePath).StartsWith($root + '\',[StringComparison]::OrdinalIgnoreCase)
    })
}
function Run-InstalledProcess([string]$Name,[string]$Executable,[string]$Arguments,[int]$TimeoutSeconds) {
    $entry = [ordered]@{name=$Name; started_utc=[DateTime]::UtcNow.ToString('o'); elapsed_ms=$null; exited=$false; exit_code=$null}
    $processes.Add($entry)
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $process = $null
    try {
        $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $root -PassThru `
            -RedirectStandardOutput (Join-Path $evidence "$Name.stdout.log") -RedirectStandardError (Join-Path $evidence "$Name.stderr.log")
        $entry.exited = $process.WaitForExit($TimeoutSeconds * 1000)
        if (-not $entry.exited) { throw "Production installer lifecycle phase timed out: $Name" }
        $entry.exit_code = $process.ExitCode
        if ($process.ExitCode -ne 0) { throw "Production installer lifecycle phase failed: $Name (exit $($process.ExitCode))." }
        return $entry.exit_code
    } finally {
        $watch.Stop(); $entry.elapsed_ms = $watch.Elapsed.TotalMilliseconds
        if ($null -ne $process) {
            if (-not $process.HasExited) {
                $result.forced_termination = $true
                $process.Kill($true); $null = $process.WaitForExit(5000)
            }
            $process.Dispose()
        }
    }
}
function Assert-InstalledPayload {
    Assert-FixturePath $target
    $expected = @($manifest.files | ForEach-Object { [string]$_.path }) +
        @('package-manifest.json','.swirl-install-owned','.swirl-isolated-install','卸载 Swirl.exe')
    $actual = @(Get-ChildItem -LiteralPath $target -Recurse -Force -ErrorAction Stop | ForEach-Object {
        if (($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Installed payload contains a linked entry.' }
        if (-not $_.PSIsContainer) { $_.FullName.Substring($target.Length + 1).Replace('\','/') }
    })
    if (@(Compare-Object ($expected | Sort-Object) ($actual | Sort-Object)).Count -ne 0) {
        throw 'Installed payload inventory differs from the manifest and known installer ownership files.'
    }
    foreach ($entry in $manifest.files) {
        $file = Join-Path $target $entry.path
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ine $entry.sha256) { throw "Installed payload hash mismatch: $($entry.path)" }
    }
    if ((Get-FileHash -LiteralPath (Join-Path $target 'package-manifest.json')).Hash -cne
        (Get-FileHash -LiteralPath (Join-Path $package 'package-manifest.json')).Hash) { throw 'Installed manifest differs from the verified source package.' }
}
$before = $null
try {
    $before = Snapshot-UserIntegration
    $env:SWIRL_ISOLATED_INSTALL_ROOT = $root
    $env:SWIRL_TEST_ROOT = Join-Path $root 'runtime-state'
    New-Item -ItemType Directory -Path $env:SWIRL_TEST_ROOT | Out-Null
    $result.installer_exit_code = Run-InstalledProcess 'install' $setup "/S /ISOLATED /D=$target" 120
    Assert-InstalledPayload
    $result.installed_files = @($manifest.files).Count
    $result.all_installed_hashes_verified = $true; $result.exact_installed_inventory = $true
    $exe = Join-Path $target 'Swirl.exe'
    $result.installed_exe_sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    $result.installed_rust_dll_sha256 = (Get-FileHash -LiteralPath (Join-Path $target 'swirl_api.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
    $result.installed_manifest_sha256 = (Get-FileHash -LiteralPath (Join-Path $target 'package-manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    $env:QT_QPA_PLATFORM = 'windows'; $env:QSG_RHI_BACKEND = 'd3d11'
    foreach ($name in @('QT_QUICK_BACKEND','QT_SCALE_FACTOR','QT_SCREEN_SCALE_FACTORS','QT_PLUGIN_PATH','QML_IMPORT_PATH','QML2_IMPORT_PATH')) {
        [Environment]::SetEnvironmentVariable($name,$null,'Process')
    }
    $env:PATH = "$target;$env:SystemRoot\System32;$env:SystemRoot"
    $rustPath = Join-Path $evidence 'installed-rust-self-test.json'
    $null = Run-InstalledProcess 'installed-rust' $exe ('--rust-core-self-test "' + $rustPath + '"') 30
    $rust = Get-Content -LiteralPath $rustPath -Raw | ConvertFrom-Json
    if (-not $rust.success -or -not $rust.http_response_verified -or -not $rust.connect_response_verified -or
        -not $rust.socks5_response_verified -or -not $rust.listener_released -or $rust.origin_requests -ne 3 -or
        $rust.library.source_sha -cne $source -or $rust.library.build_id -cne $manifest.rust.build_id) {
        throw 'Installed executable did not verify its source-paired Rust data path and cleanup.'
    }
    $result.rust_roundtrips_verified = $true
    $tlsPath = Join-Path $evidence 'installed-tls-runtime.json'
    $null = Run-InstalledProcess 'installed-tls' $exe ('--tls-runtime-self-test "' + $tlsPath + '"') 30
    $tls = Get-Content -LiteralPath $tlsPath -Raw | ConvertFrom-Json
    if (-not $tls.success) { throw 'Installed Qt/OpenSSL runtime self-test did not pass.' }
    $result.tls_runtime_verified = $true
    $null = Run-InstalledProcess 'installed-ui' $exe '--smoke-test --font-review' 60
    $diagnostic = Join-Path $target 'Swirl-diagnostics.txt'
    if (-not (Test-Path -LiteralPath $diagnostic -PathType Leaf)) { throw 'Installed UI emitted no diagnostics.' }
    Copy-Item -LiteralPath $diagnostic -Destination (Join-Path $evidence 'installed-ui.log')
    if (Select-String -LiteralPath $diagnostic -Pattern '^[123]:' -Quiet) { throw 'Installed UI emitted Qt warnings or errors.' }
    $cache = @(Select-String -LiteralPath $diagnostic -Pattern '^4:\s+QML_CACHE_EVIDENCE\s+(\{.*\})\s*$')
    if ($cache.Count -ne 1) { throw 'Installed UI did not report its actual isolated cache identity.' }
    $cacheIdentity = $cache[0].Matches[0].Groups[1].Value | ConvertFrom-Json
    $cacheRoot = [IO.Path]::GetFullPath((Join-Path $env:SWIRL_TEST_ROOT 'cache/qmlcache')).TrimEnd('\','/')
    if (-not ([IO.Path]::GetFullPath([string]$cacheIdentity.path)).StartsWith($cacheRoot + '\',[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Installed UI cache escaped the disposable runtime directory.'
    }
    $result.runtime_storage_isolated = $true
    $completed = @(Select-String -LiteralPath $diagnostic -Pattern '^4:\s+SMOKE_PAGES\s+(\d+)\s*$')
    $ready = @(Select-String -LiteralPath $diagnostic -Pattern '^4:\s+FONT_SMOKE_ROUTE_READY\s+(\S+)\s+(\S+)\s*$')
    if ($completed.Count -ne 1 -or [int]$completed[0].Matches[0].Groups[1].Value -le 0 -or
        $ready.Count -ne [int]$completed[0].Matches[0].Groups[1].Value) { throw 'Installed UI did not complete every ready route.' }
    foreach ($route in $ready) {
        $requested = $route.Matches[0].Groups[1].Value.Trim('"'); $actual = $route.Matches[0].Groups[2].Value.Trim('"')
        $expected = if ($requested -in @('requestlogs','dashboard')) { 'activity' } else { $requested }
        if ($actual -cne $expected) { throw 'Installed UI confirmed an incorrect route.' }
    }
    $result.installed_ui_pages = $ready.Count
    Remove-Item -LiteralPath $diagnostic
    Assert-InstalledPayload
    if (@(Get-OwnedProcesses).Count) { throw 'Installed product left a process running after normal exit.' }
    $uninstaller = Join-Path $root 'uninstall-runner.exe'
    Copy-Item -LiteralPath (Join-Path $target '卸载 Swirl.exe') -Destination $uninstaller
    $result.uninstaller_exit_code = Run-InstalledProcess 'uninstall' $uninstaller "/S _?=$target" 120
    $result.install_directory_removed = -not (Test-Path -LiteralPath $target)
    if (-not $result.install_directory_removed) { throw 'The actual production uninstaller left owned installation files behind.' }
    $result.success = $true
} catch {
    $result.error = $_.Exception.Message; $result.success = $false
} finally {
    # Preserve the actual installed application's last diagnostics even when
    # its process fails before the normal report-copy step. Evidence collection
    # must not prevent the separately guarded fixture/process cleanup below.
    try {
        $lastDiagnostic = Join-Path $target 'Swirl-diagnostics.txt'
        if (Test-Path -LiteralPath $lastDiagnostic -PathType Leaf) {
            Assert-FixturePath $lastDiagnostic
            Copy-Item -LiteralPath $lastDiagnostic -Destination (Join-Path $evidence 'installed-last-diagnostics.log')
            $result.failure_diagnostics_preserved = $true
        }
    } catch {
        $result.success = $false
        $result.error = [string]$result.error + ' Installed diagnostics preservation failed: ' + $_.Exception.Message
    }
    try {
        $remaining = @(Get-OwnedProcesses)
        $result.remaining_owned_processes = $remaining.Count
        if ($remaining.Count) {
            $result.success = $false; $result.forced_termination = $true
            if (-not $result.error) { $result.error = 'Owned installer or product processes remained after the normal lifecycle.' }
            foreach ($entry in $remaining) {
                $owned = [Diagnostics.Process]::GetProcessById([int]$entry.ProcessId)
                try { if (-not $owned.HasExited) { $owned.Kill($true); $null = $owned.WaitForExit(5000) } } finally { $owned.Dispose() }
            }
        }
        if ($null -ne $before) {
            $result.user_integration_unchanged = (Snapshot-UserIntegration) -ceq $before
            if (-not $result.user_integration_unchanged) { $result.success = $false; $result.error = 'Isolated installation changed user registry or shortcuts.' }
        }
        Assert-FixturePath $root
        foreach ($entry in (Get-ChildItem -LiteralPath $root -Recurse -Force)) {
            if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Refusing to clean a linked installer fixture.' }
        }
        Remove-Item -LiteralPath $root -Recurse -Force
        $result.fixture_removed = -not (Test-Path -LiteralPath $root)
        if (-not $result.fixture_removed) { $result.success = $false; $result.error = 'The unique installer fixture could not be removed.' }
    } catch {
        $result.success = $false; $result.error = 'Installer lifecycle cleanup failed: ' + $_.Exception.Message
    } finally {
        foreach ($name in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($name,$savedEnvironment[$name],'Process') }
        $result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $evidence 'lifecycle.json') -Encoding utf8
    }
}
if (-not $result.success) { throw ('Production installer lifecycle verification failed: ' + $result.error) }
Write-Host "Production installer lifecycle verified for $source; $($result.installed_files) payload files and $($result.installed_ui_pages) ready UI routes."
