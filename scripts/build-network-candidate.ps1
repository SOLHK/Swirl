# Incremental, exact-source Windows network repair candidate. Run in x64 MSVC.
param(
    [Parameter(Mandatory)][string]$QtDir,
    [string]$BuildDir = 'D:/Codex/build/swirl-network-candidate',
    [string]$RustTargetDir = 'D:/Codex/build/swirl-network-rust',
    [Parameter(Mandatory)][string]$OutDir,
    [string]$Nsis = 'D:/Codex/toolchains/nsis-3.11/makensis.exe',
    [ValidateRange(1,64)][int]$Parallel = 4,
    [switch]$DisposableSystemProxyTests
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'BuildInputTimes.ps1')
. (Join-Path $PSScriptRoot 'Assert-BuildSource.ps1')
if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) { throw 'Run in an x64 MSVC developer shell.' }
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$build = [IO.Path]::GetFullPath($BuildDir)
$rustTarget = [IO.Path]::GetFullPath($RustTargetDir)
$out = [IO.Path]::GetFullPath($OutDir)
if (Test-Path -LiteralPath $out) { throw 'Use a fresh OutDir; existing deliverables are preserved.' }
New-Item -ItemType Directory -Path $out | Out-Null
$evidence = Join-Path $out 'evidence'
New-Item -ItemType Directory -Path $evidence | Out-Null
$oldPath = $env:PATH
$oldIncremental = $env:CARGO_INCREMENTAL
$oldProxyTest = $env:SWIRL_SYSTEM_PROXY_TEST
$oldTestRoot = $env:SWIRL_TEST_ROOT
$env:PATH = "$(Join-Path (Resolve-Path -LiteralPath $QtDir).Path 'bin');$env:PATH"
$env:CARGO_INCREMENTAL = '1'
$env:SWIRL_TEST_ROOT = Join-Path $evidence 'isolated-test-data'
New-Item -ItemType Directory -Path $env:SWIRL_TEST_ROOT | Out-Null
if ($DisposableSystemProxyTests) {
    if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
        throw 'System proxy mutation checks require a disposable GitHub-hosted runner.'
    }
    $env:SWIRL_SYSTEM_PROXY_TEST = '1'
} else { Remove-Item Env:SWIRL_SYSTEM_PROXY_TEST -ErrorAction SilentlyContinue }
$report = [ordered]@{schema=1; source_sha=''; status='running'; cargo_incremental=$true;
    product_version=(Get-Content -LiteralPath (Join-Path $repo 'src/Swirl.Quick/PRODUCT_VERSION.txt') -Raw).Trim();
    generator='Ninja'; build_directory=$build; rust_target_directory=$rustTarget;
    restored_cmake_cache=(Test-Path -LiteralPath (Join-Path $build 'CMakeCache.txt'));
    restored_cargo_cache=(Test-Path -LiteralPath $rustTarget); compiler_cache_ready=$false; steps=@();
    system_proxy_mutation_requested=[bool]$DisposableSystemProxyTests;
    private_provider_verified=$false; codex_account_verified=$false; tun_verified=$false;
    dpi_visual_acceptance='user'; broad_ui_regression='not run by this network-only candidate; manual DPI acceptance belongs to the user';
    standalone_core_tests=$true; application_ui_test_entry_points=$false; production_reconfigured=$false}
$total = [Diagnostics.Stopwatch]::StartNew()
function Run-Step([string]$Name, [scriptblock]$Body) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $log = Join-Path $evidence ($Name+'.log')
    Write-Host "::group::$Name"
    try {
        & $Body 2>&1 | Tee-Object -FilePath $log
        $report.steps += [ordered]@{name=$Name; seconds=[Math]::Round($timer.Elapsed.TotalSeconds,3); passed=$true; log=($Name+'.log')}
    } catch {
        $report.steps += [ordered]@{name=$Name; seconds=[Math]::Round($timer.Elapsed.TotalSeconds,3); passed=$false; log=($Name+'.log')}
        throw
    } finally { Write-Host '::endgroup::' }
}
function Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
function Engine-Objects {
    $map = @{}
    $directory = Join-Path $build 'CMakeFiles/SwirlEngine.dir'
    if (Test-Path -LiteralPath $directory) {
        foreach ($file in (Get-ChildItem -LiteralPath $directory -Recurse -File -Filter '*.obj')) {
            $map[$file.FullName] = ((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash + ':' + $file.LastWriteTimeUtc.Ticks)
        }
    }
    return $map
}
Push-Location $repo
try {
    $report.source_sha = (& git rev-parse HEAD).Trim()
    Assert-SwirlBuildSource -RepositoryRoot $repo -ExpectedSourceSha $report.source_sha
    Run-Step 'restore-content-verified-input-times' { $report.source_timestamps_restored_by_content = Sync-SwirlBuildInputTimes -RepositoryRoot $repo -BuildDirectory $build -Restore }
    Run-Step 'validate-standalone-production-graph' {
        # This separate configure-only graph may exercise UI test mode without
        # invalidating any generated files in the actual product build cache.
        Checked python @('scripts/tests/Test-CMakeCoreProfile.py','--build-dir',(Join-Path $build 'profile-validation'),
            '--','-DCMAKE_C_COMPILER=cl.exe','-DCMAKE_CXX_COMPILER=cl.exe',
            "-DCMAKE_PREFIX_PATH=$QtDir","-DSWIRL_RUST_TARGET=$rustTarget")
        Copy-Item -LiteralPath (Join-Path $build 'profile-validation/profile-graph-evidence') -Destination (Join-Path $evidence 'standalone-production-graph') -Recurse
    }
    $configure = @('-S','src/Swirl.Quick','-B',$build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_C_COMPILER=cl.exe','-DCMAKE_CXX_COMPILER=cl.exe',"-DCMAKE_PREFIX_PATH=$QtDir",
        "-DSWIRL_RUST_TARGET=$rustTarget",'-DSWIRL_BUILD_CORE_TESTS=ON',
        '-DSWIRL_BUILD_UI_TESTS=OFF','-DSWIRL_XRAY_UI_TESTS=OFF')
    Run-Step 'configure-focused-tests' { Checked cmake $configure }
    $targets = @('SwirlRustCoreTests','SwirlRustCoreLibraryTests','SwirlNodeTests','SwirlImportTests',
        'SwirlSubscriptionFormatTests','SwirlNetworkRegressionTests','SwirlDiagnosticTests',
        'SwirlSystemProxyStateTests','SwirlQtNetworkPolicyTests','SwirlCodexLauncherTests',
        'SwirlTelemetryTests','SwirlNodeViewModelTests','SwirlNodeSectionModelTests')
    if ($DisposableSystemProxyTests) { $targets += 'SwirlSystemProxyTests' }
    Run-Step 'build-focused-tests' { Checked cmake (@('--build',$build,'--target')+$targets+@('--parallel',"$Parallel")) }
    Assert-SwirlBuildSource -RepositoryRoot $repo -ExpectedSourceSha $report.source_sha
    Run-Step 'save-compiled-input-times' { $null = Sync-SwirlBuildInputTimes -RepositoryRoot $repo -BuildDirectory $build }
    $report.compiler_cache_ready = $true
    if ($env:GITHUB_OUTPUT) { 'cache-ready=true' | Out-File -FilePath $env:GITHUB_OUTPUT -Encoding utf8 -Append }
    Run-Step 'deploy-test-runtime' { Checked windeployqt @('--release','--compiler-runtime',(Join-Path $build 'SwirlRustCoreTests.exe')) }
    $pattern = '^swirl-(rust-library-loader|rust-qt-integration|node-real-chain|stream-regression|import-subscription|subscription-formats|diagnostic-export|system-proxy-state|qt-network-policy|codex-proxy-launcher|telemetry-accounting|node-view-model|node-section-model'
    if ($DisposableSystemProxyTests) { $pattern += '|system-proxy-recovery' }
    $pattern += ')$'
    Run-Step 'focused-core-security-network-tests' { Checked ctest @('--test-dir',$build,'-C','Release','-R',$pattern,'--output-on-failure','--no-tests=error','--output-junit',(Join-Path $evidence 'focused-tests.xml')) }
    [xml]$testResults=Get-Content -LiteralPath (Join-Path $evidence 'focused-tests.xml') -Raw
    $report.focused_ctest_suites=[int]$testResults.testsuite.tests
    if([int]$testResults.testsuite.failures -ne 0 -or $report.focused_ctest_suites -ne $targets.Count) { throw 'Focused test report is incomplete or failed.' }
    $testedDllHash = (Get-FileHash -LiteralPath (Join-Path $build 'swirl_api.dll')).Hash
    $testedIdentity = Get-Content -LiteralPath (Join-Path $build 'swirl-rust-build.json') -Raw | ConvertFrom-Json
    $beforeObjects = Engine-Objects
    # Standalone test executables do not change Swirl's production target.
    # Switching UI_TESTS ON/OFF here used to invalidate every QML cache command.
    # Retain one production application graph and the tested shared objects.
    $cache = Get-Content -LiteralPath (Join-Path $build 'CMakeCache.txt') -Raw
    foreach ($setting in @('SWIRL_BUILD_CORE_TESTS:BOOL=ON','SWIRL_BUILD_UI_TESTS:BOOL=OFF','SWIRL_XRAY_UI_TESTS:BOOL=OFF')) {
        if ($cache -notmatch ('(?m)^'+[regex]::Escape($setting)+'\s*$')) { throw 'Application test exposure changed during the candidate build.' }
    }
    Run-Step 'build-production-once' { Checked cmake @('--build',$build,'--target','Swirl','--parallel',"$Parallel") }
    $afterObjects = Engine-Objects
    $reused = @($beforeObjects.Keys | Where-Object { $afterObjects.ContainsKey($_) -and $afterObjects[$_] -ceq $beforeObjects[$_] }).Count
    $report.engine_objects = @{tested=$beforeObjects.Count; reused_in_production=$reused}
    if ($reused -ne $beforeObjects.Count -or $reused -eq 0) { throw 'Production unexpectedly rebuilt or changed tested engine objects.' }
    if ((Get-FileHash -LiteralPath (Join-Path $build 'swirl_api.dll')).Hash -cne $testedDllHash) { throw 'Production Rust DLL differs from the tested DLL.' }
    $identity = Get-Content -LiteralPath (Join-Path $build 'swirl-rust-build.json') -Raw | ConvertFrom-Json
    if ($identity.source_sha -cne $report.source_sha -or $identity.build_id -cne $testedIdentity.build_id) { throw 'Tested and production source identities differ.' }
    Run-Step 'measure-no-change-rebuild' { Checked cmake @('--build',$build,'--target','Swirl','--parallel',"$Parallel") }
    if (Select-String -LiteralPath (Join-Path $evidence 'measure-no-change-rebuild.log') -Pattern 'Building CXX object|Building C object|Linking CXX|Compiling swirl-' -Quiet) { throw 'The no-change rebuild unexpectedly recompiled source.' }
    $report.no_change_recompiled_source = $false
    Run-Step 'stage-and-real-proxy-roundtrips' { & (Join-Path $PSScriptRoot 'Stage-WindowsRustProduct.ps1') -BuildDirectory $build -Destination (Join-Path $out 'app') }
    Run-Step 'production-startup' {
        $process = Start-Process (Join-Path $out 'app/Swirl.exe') -ArgumentList '--smoke-test' -WorkingDirectory $evidence -WindowStyle Hidden -PassThru
        if (-not $process.WaitForExit(75000)) { $process.Kill(); throw 'Production startup timed out.' }
        if ($process.ExitCode -ne 0) { throw 'Production startup failed.' }
    }
    if (-not (Test-Path -LiteralPath $Nsis -PathType Leaf)) { throw 'NSIS is required to create the installer.' }
    Run-Step 'installer-lifecycle-security' {
        & (Join-Path $PSScriptRoot 'tests/Test-S4InstallerLifecycle.ps1') -Nsis $Nsis -Icon (Join-Path $build 'brand/Swirl.ico') -EvidenceRoot (Join-Path $evidence 'installer-lifecycle')
        if ($LASTEXITCODE -ne 0) { throw 'Installer lifecycle and retained-data checks failed.' }
    }
    Run-Step 'verify-manifest-and-build-installer' {
        Assert-SwirlBuildSource -RepositoryRoot $repo -ExpectedSourceSha $report.source_sha
        $uninstall = Join-Path $out 'Swirl-UninstallFiles.nsh'
        & (Join-Path $PSScriptRoot 'Finalize-WindowsRustProduct.ps1') -ApplicationDirectory (Join-Path $out 'app') -EvidenceDirectory (Join-Path $evidence 'package') -UninstallList $uninstall
        $version = (Get-Content -LiteralPath 'src/Swirl.Quick/PRODUCT_VERSION.txt' -Raw).Trim()
        Checked $Nsis @('/INPUTCHARSET','UTF8',"/DAPP_DIST=$(Join-Path $out 'app')","/DOUT_DIR=$out","/DAPP_ICON=$(Join-Path $build 'brand/Swirl.ico')","/DAPP_VERSION=$version","/DUNINSTALL_LIST=$uninstall","/DREPO_ROOT=$repo",'src/Swirl.Quick/packaging/Swirl.nsi')
    }
    $report.installer_sha256 = (Get-FileHash -LiteralPath (Join-Path $out 'Swirl-Setup.exe')).Hash.ToLowerInvariant()
    Run-Step 'save-content-verified-input-times' { $null = Sync-SwirlBuildInputTimes -RepositoryRoot $repo -BuildDirectory $build }
    Assert-SwirlBuildSource -RepositoryRoot $repo -ExpectedSourceSha $report.source_sha
    $report.status = 'passed-controlled-network-candidate'
} catch {
    $report.status = 'failed'
    $report.failure = $_.Exception.Message
    throw
} finally {
    $total.Stop()
    $report.total_seconds = [Math]::Round($total.Elapsed.TotalSeconds,3)
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidence 'build-timings.json') -Encoding utf8
    $env:PATH = $oldPath
    $env:CARGO_INCREMENTAL = $oldIncremental
    $env:SWIRL_SYSTEM_PROXY_TEST = $oldProxyTest
    $env:SWIRL_TEST_ROOT = $oldTestRoot
    Pop-Location
}
