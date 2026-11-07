param(
    [Parameter(Mandatory=$true)][string]$BuildDirectory,
    [Parameter(Mandatory=$true)][string]$Destination,
    [string]$OpenSslRoot,
    [string]$Configuration = 'Release',
    [string]$Python = 'python',
    [string]$QtSdkReceipt = $env:SWIRL_QT_SELECTED_RECEIPT,
    [string]$QtEvidenceDirectory,
    [string]$QtSourceDirectory,
    [string]$QtSourceCacheDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'RustProductPackagePolicy.ps1')
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$build = (Resolve-Path -LiteralPath $BuildDirectory).Path
$cache = Get-Content -LiteralPath (Join-Path $build 'CMakeCache.txt') -Raw
if ($Configuration -cne 'Release') { throw 'Product packaging requires the Release configuration.' }
if ($cache -notmatch '(?m)^SWIRL_BUILD_UI_TESTS:BOOL=OFF\s*$') { throw 'Never package an executable with UI test entry points enabled.' }
if ($cache -notmatch '(?m)^CMAKE_BUILD_TYPE:STRING=Release\s*$' -and
    $cache -notmatch '(?m)^CMAKE_CONFIGURATION_TYPES:STRING=[^\r\n]*\bRelease\b[^\r\n]*\r?$') {
    throw 'The CMake build does not include a Release configuration.'
}
if ($cache -notmatch '(?m)^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$' -or
    [IO.Path]::GetFullPath($Matches[1].Trim()).TrimEnd('\','/') -ne
    [IO.Path]::GetFullPath((Join-Path $repo 'src/Swirl.Quick')).TrimEnd('\','/')) {
    throw 'The build belongs to a different source tree.'
}
if ($cache -notmatch '(?m)^SWIRL_RUNTIME:INTERNAL=rust\s*$') { throw 'Rust Core must be the only configured product runtime.' }
if ($cache -notmatch '(?m)^SWIRL_RUST_LIBRARY:INTERNAL=(.+)$') { throw 'Exact Cargo library path is missing.' }
$rustLibrary = $Matches[1].Trim()
if ($cache -notmatch '(?m)^SWIRL_RUST_BUILD_ID:INTERNAL=(.+)$') { throw 'Paired Rust build identity is missing.' }
$buildId = $Matches[1].Trim()
$bin = Join-Path $build $Configuration
if (-not (Test-Path -LiteralPath (Join-Path $bin 'Swirl.exe'))) { $bin = $build }
$stage = [IO.Path]::GetFullPath($Destination)
Assert-SwirlPathWithoutLinks $stage
if (Test-Path -LiteralPath $stage) { throw 'Packaging requires a fresh destination.' }
$sourceSha = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceSha -notmatch '^[0-9a-f]{40}$') { throw 'Source identity is missing.' }
$files = @('Swirl.exe','swirl_api.dll','swirl-rust-build.json','swirl-tun-broker.exe','swirl-tun-helper.exe','SwirlProxyGuard.exe',
    'SwirlGatewayGuard.exe','SwirlScriptRunner.exe','SwirlCodexLauncher.exe',
    'SwirlCodexManage.py','SubscriptionCapture.py')
foreach ($name in $files) {
    if (-not (Test-Path -LiteralPath (Join-Path $bin $name) -PathType Leaf)) { throw "Missing build output: $name" }
}
# Bind deployment tools to the kit which CMake actually resolved. This also
# keeps non-CI callers from silently borrowing windeployqt/qtpaths from PATH.
if ($cache -notmatch '(?m)^Qt6_DIR:PATH=(.+)$') { throw 'Configured Qt SDK location is missing.' }
$qtConfig = (Resolve-Path -LiteralPath $Matches[1].Trim()).Path
$qtRoot = (Resolve-Path -LiteralPath (Join-Path $qtConfig '../../..')).Path
$windeployqt = Join-Path $qtRoot 'bin/windeployqt.exe'
$qtpaths = Join-Path $qtRoot 'bin/qtpaths.exe'
foreach ($path in @($qtRoot,$windeployqt,$qtpaths)) { Assert-SwirlPathWithoutLinks $path }
if (-not (Test-Path -LiteralPath $windeployqt -PathType Leaf) -or
    -not (Test-Path -LiteralPath $qtpaths -PathType Leaf)) { throw 'Configured Qt deployment tools are unavailable.' }
if ($QtSdkReceipt) {
    if (-not $QtEvidenceDirectory -or -not $QtSourceDirectory -or -not $QtSourceCacheDirectory) {
        throw 'Selected Qt packaging requires verification evidence and a corresponding source output/cache.'
    }
    Assert-SwirlPathWithoutLinks $QtSdkReceipt
    $selectedQt = Get-Content -LiteralPath $QtSdkReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $qtRoot.Equals([IO.Path]::GetFullPath($selectedQt.kit_root),[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Packaging would use a Qt kit different from the selected SDK.'
    }
    & $Python (Join-Path $repo 'tools/Compose-Qt612ProductSdk.py') verify --receipt $QtSdkReceipt `
        --build-dir $build --phase pre-deploy --evidence (Join-Path $QtEvidenceDirectory 'pre-deploy')
    if ($LASTEXITCODE -ne 0) { throw 'Selected Qt SDK or actual product linkage changed before deployment.' }
}
$expected = Get-Content -LiteralPath (Join-Path $bin 'swirl-rust-build.json') -Raw | ConvertFrom-Json
if ($expected.source_sha -ne $sourceSha -or $expected.target -ne 'x86_64-pc-windows-msvc' -or
    $expected.build_id -ne $buildId) {
    throw 'Release packaging requires current source and Windows x64 MSVC.'
}
if ((Get-FileHash -LiteralPath $rustLibrary -Algorithm SHA256).Hash -ne
    (Get-FileHash -LiteralPath (Join-Path $bin 'swirl_api.dll') -Algorithm SHA256).Hash) { throw 'Deployed Rust DLL is stale.' }
foreach ($artifact in @(@{cache='SWIRL_TUN_BROKER';name='swirl-tun-broker.exe'},@{cache='SWIRL_TUN_HELPER';name='swirl-tun-helper.exe'})) {
    if ($cache -notmatch ('(?m)^'+$artifact.cache+':INTERNAL=(.+)$')) { throw ('Paired Rust executable path is missing: '+$artifact.name) }
    $output = $Matches[1].Trim()
    if ((Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash -ne
        (Get-FileHash -LiteralPath (Join-Path $bin $artifact.name) -Algorithm SHA256).Hash) {
        throw ('Deployed Rust executable is stale: '+$artifact.name)
    }
}
New-Item -ItemType Directory -Path $stage | Out-Null
foreach ($name in $files) { Copy-Item -LiteralPath (Join-Path $bin $name) -Destination $stage }
& (Join-Path $PSScriptRoot 'Copy-VerifiedChinaRules.ps1') `
    -SourceDirectory (Join-Path $repo 'src/Swirl.Quick/packaging/rules') -ApplicationDirectory $stage
Copy-Item -LiteralPath (Join-Path $repo 'src/Swirl.Quick/packaging/licenses') -Destination $stage -Recurse
# Collect notices from the exact locked Rust sources, including reviewed driver
# and supplemental notices that are absent from some published crate archives.
if ($cache -notmatch '(?m)^SWIRL_CARGO:FILEPATH=(.+)$') { throw 'Configured Cargo path is missing for Rust license staging.' }
$licenseCargo = $Matches[1].Trim()
$licenseMetadataPath = Join-Path $build 'rust-license-metadata.json'
& $licenseCargo metadata --locked --format-version 1 --manifest-path (Join-Path $repo 'core/Cargo.toml') |
    Set-Content -LiteralPath $licenseMetadataPath -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Locked Rust dependency metadata collection failed.' }
$licenseDirectory = Join-Path $stage 'licenses/rust'
& $Python (Join-Path $repo 'tools/Collect-RustDependencies.py') `
    --metadata $licenseMetadataPath --inventory (Join-Path $licenseDirectory 'DEPENDENCIES.json') `
    --notices $licenseDirectory --supplemental-inventory (Join-Path $repo 'core/DEPENDENCIES.json')
if ($LASTEXITCODE -ne 0) { throw 'Rust dependency notice staging failed.' }
$wintun = & (Join-Path $PSScriptRoot 'Copy-VerifiedWintunRuntime.ps1') -ArchivePath (Join-Path $build 'dependency-cache/wintun-0.14.1.zip') -ApplicationDirectory $stage
Copy-Item -LiteralPath (Join-Path $repo 'src/Swirl.Quick/packaging/THIRD_PARTY_NOTICES.txt') -Destination $stage
Copy-Item -LiteralPath (Join-Path $repo 'src/Swirl.Quick/packaging/README-RustProductPreview.txt') -Destination (Join-Path $stage 'README.txt')
foreach ($name in @('Swirl-brand-phase3.ico','Swirl-brand-0217-optical.ico')) {
    Copy-Item -LiteralPath (Join-Path $build 'brand/Swirl.ico') -Destination (Join-Path $stage $name)
}
if (-not $OpenSslRoot) { throw 'An explicitly verified OpenSSL runtime root is required.' }
& (Join-Path $PSScriptRoot 'Copy-VerifiedOpenSslRuntime.ps1') -OpenSslRoot $OpenSslRoot `
    -ApplicationDirectory $stage -Target VC-WIN64A -Python $Python
& $windeployqt --qtpaths $qtpaths --release --no-compiler-runtime --openssl-root $OpenSslRoot --include-plugins qopensslbackend --qmldir (Join-Path $repo 'src/Swirl.Quick/qml') (Join-Path $stage 'Swirl.exe')
if ($LASTEXITCODE -ne 0) { throw 'Qt deployment failed.' }
if ($QtSdkReceipt) {
    & $Python (Join-Path $repo 'tools/Compose-Qt612ProductSdk.py') verify --receipt $QtSdkReceipt `
        --build-dir $build --phase post-deploy --runtime-dir $stage `
        --evidence (Join-Path $QtEvidenceDirectory 'post-deploy')
    if ($LASTEXITCODE -ne 0) { throw 'Deployed Qt files differ from the selected SDK.' }
}
& (Join-Path $PSScriptRoot 'Copy-VerifiedMsvcRuntime.ps1') -BuildDirectory $build -ApplicationDirectory $stage
# windeployqt creates empty QML directories that NSIS File /r would own only
# implicitly. Prune this freshly created stage before any real runtime checks;
# installed-product maintenance must preserve unknown user directories.
$removedEmptyDirectories = @(Remove-SwirlEmptyStagingDirectories -StagingDirectory $stage)
foreach ($name in @('Qt6Core.dll','Qt6Gui.dll','Qt6Qml.dll','Qt6Quick.dll','platforms/qwindows.dll','swirl_api.dll')) {
    if (-not (Test-Path -LiteralPath (Join-Path $stage $name) -PathType Leaf)) { throw "Missing packaged dependency: $name" }
}
$forbidden = @(Get-SwirlForbiddenProductFiles -ApplicationDirectory $stage)
if ($forbidden.Count) { throw ('Forbidden package entries: ' + ($forbidden -join ', ')) }
# Run the real EXE/DLL from a clean working directory, not the development tree.
# Preserve the report in the evidence path even when the executable fails.
$scratch = Join-Path ([IO.Path]::GetTempPath()) ('swirl-package-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch | Out-Null
function Read-SwirlTunBuildIdentity([string]$Name,[string]$Role) {
    $file = Join-Path $stage $Name
    Assert-SwirlAmd64Image $file
    $output = Join-Path $scratch ($Role+'-build-info.json')
    $stderr = Join-Path $scratch ($Role+'-build-info.stderr')
    # These commands only report compiled identity. They do not elevate,
    # recover a journal, load Wintun or change host networking.
    $process = Start-Process -FilePath $file -ArgumentList @('--build-info') -WorkingDirectory $scratch -WindowStyle Hidden -PassThru -RedirectStandardOutput $output -RedirectStandardError $stderr
    if (-not $process.WaitForExit(10000)) { $process.Kill(); throw ('TUN build identity timed out: '+$Name) }
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $output -PathType Leaf) -or
        (Get-Item -LiteralPath $output).Length -gt 65536) { throw ('Cannot verify TUN build identity: '+$Name) }
    $identity = Get-Content -LiteralPath $output -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($identity.abi_version -ne 1 -or $identity.role -cne $Role -or $identity.source_sha -cne $sourceSha -or
        $identity.build_id -cne $buildId -or $identity.target -cne $expected.target) {
        throw ('TUN executable was not built from the paired source and target: '+$Name)
    }
    return [ordered]@{sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant();identity=$identity}
}
$tunPayload = [ordered]@{schema=1;kind='windows-native-tun-payload';source_sha=$sourceSha;build_id=$buildId;
    target=$expected.target;driver=$wintun;binaries=[ordered]@{
        'swirl-tun-broker.exe'=(Read-SwirlTunBuildIdentity 'swirl-tun-broker.exe' 'swirl_tun_broker')
        'swirl-tun-helper.exe'=(Read-SwirlTunBuildIdentity 'swirl-tun-helper.exe' 'swirl_tun_helper')
    }}
$tunPayload | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $stage 'tun-runtime.json') -Encoding utf8
$reportPath = Join-Path $stage 'rust-self-test.json'
$process = Start-Process -FilePath (Join-Path $stage 'Swirl.exe') `
    -ArgumentList @('--rust-core-self-test', ('"' + $reportPath + '"')) -WorkingDirectory $scratch -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(30000)) { $process.Kill(); throw 'Packaged EXE timed out.' }
if ($process.ExitCode -ne 0) {
    if (Test-Path -LiteralPath $reportPath) { Get-Content -LiteralPath $reportPath }
    throw "Packaged EXE failed with exit code $($process.ExitCode)."
}
$report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
if (-not $report.success -or -not $report.http_response_verified -or
    -not $report.socks5_response_verified -or -not $report.connect_response_verified -or
    -not $report.listener_released) { throw 'Not all required native roundtrips passed.' }
# Python is an existing build-host dependency; no interpreter is shipped.
& $Python (Join-Path $repo 'tools/Verify-WindowsIconResources.py') `
    --ico (Join-Path $build 'brand/Swirl.ico') --exe (Join-Path $stage 'Swirl.exe') `
    --output (Join-Path $build 'icon-resource-verification.json')
if ($LASTEXITCODE -ne 0) { throw 'Packaged EXE icon resources differ from the generated 18-frame ICO.' }
if ($QtSdkReceipt) {
    # Add the actual source archive identity and original license texts before
    # the first exact payload manifest is created. Finalize remains a strict
    # verifier and never blesses files added after the manifest was recorded.
    & $Python (Join-Path $repo 'tools/Prepare-Qt612ProductSource.py') prepare --runtime-dir $stage `
        --source-sha $sourceSha --sdk-evidence $selectedQt.sdk_evidence_dir `
        --cache-dir $QtSourceCacheDirectory --output-dir $QtSourceDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Matching Qt sources and installation notices could not be prepared.' }
}
$manifest = [ordered]@{ schema=1; source_sha=$sourceSha; rust=$expected;
    staging=[ordered]@{empty_directory_cleanup_scope='fresh-build-stage-only';empty_directories_removed=$removedEmptyDirectories}; files=@() }
foreach ($file in (Get-ChildItem -LiteralPath $stage -Recurse -File | Sort-Object FullName)) {
    # Windows PowerShell 5.1 lacks Path.GetRelativePath. All entries were
    # enumerated inside this stage, so the canonical directory prefix suffices.
    $relativePath = $file.FullName.Substring($stage.TrimEnd('\','/').Length + 1).Replace('\','/')
    $manifest.files += [ordered]@{ path=$relativePath;
        sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $stage 'package-manifest.json') -Encoding utf8
$null=Assert-SwirlTunPayload -ApplicationDirectory $stage -ExpectedSourceSha $sourceSha -ExpectedBuildId $buildId
$tlsLock=Get-Content -LiteralPath (Join-Path $repo 'tools/openssl-runtime.lock.json') -Raw | ConvertFrom-Json
$null=Assert-SwirlTlsPayload -ApplicationDirectory $stage -ExpectedVersion $tlsLock.version -ExpectedSourceSha256 $tlsLock.source.sha256
$tlsReport=Join-Path $build ('tls-runtime-'+$sourceSha+'.json')
$originalPath=$env:PATH
try {
    $env:PATH="$stage;$env:SystemRoot/System32;$env:SystemRoot"
    $process=Start-Process -FilePath (Join-Path $stage 'Swirl.exe') `
        -ArgumentList @('--tls-runtime-self-test',('"'+$tlsReport+'"')) -WorkingDirectory $scratch -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(30000)) { $process.Kill(); throw 'Packaged TLS runtime verification timed out.' }
    if ($process.ExitCode -ne 0) { if(Test-Path -LiteralPath $tlsReport){Get-Content -LiteralPath $tlsReport}; throw 'Packaged Qt TLS backend is incomplete or borrowed from another application.' }
} finally { $env:PATH=$originalPath }
Write-Host "Verified Rust product package: $sourceSha"
