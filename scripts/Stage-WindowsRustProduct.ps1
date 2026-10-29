param(
    [Parameter(Mandatory=$true)][string]$BuildDirectory,
    [Parameter(Mandatory=$true)][string]$Destination,
    [string]$Configuration = 'Release',
    [string]$Python = 'python'
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
if (Test-Path -LiteralPath $stage) { throw 'Packaging requires a fresh destination.' }
$sourceSha = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceSha -notmatch '^[0-9a-f]{40}$') { throw 'Source identity is missing.' }
$files = @('Swirl.exe','swirl_api.dll','swirl-rust-build.json','SwirlProxyGuard.exe',
    'SwirlGatewayGuard.exe','SwirlScriptRunner.exe','SwirlCodexLauncher.exe',
    'SwirlCodexManage.py','SubscriptionCapture.py')
foreach ($name in $files) {
    if (-not (Test-Path -LiteralPath (Join-Path $bin $name) -PathType Leaf)) { throw "Missing build output: $name" }
}
$expected = Get-Content -LiteralPath (Join-Path $bin 'swirl-rust-build.json') -Raw | ConvertFrom-Json
if ($expected.source_sha -ne $sourceSha -or $expected.target -ne 'x86_64-pc-windows-msvc' -or
    $expected.build_id -ne $buildId) {
    throw 'Release packaging requires current source and Windows x64 MSVC.'
}
if ((Get-FileHash -LiteralPath $rustLibrary -Algorithm SHA256).Hash -ne
    (Get-FileHash -LiteralPath (Join-Path $bin 'swirl_api.dll') -Algorithm SHA256).Hash) { throw 'Deployed Rust DLL is stale.' }
New-Item -ItemType Directory -Path $stage | Out-Null
foreach ($name in $files) { Copy-Item -LiteralPath (Join-Path $bin $name) -Destination $stage }
& (Join-Path $PSScriptRoot 'Copy-VerifiedChinaRules.ps1') `
    -SourceDirectory (Join-Path $repo 'src/Swirl.Quick/packaging/rules') -ApplicationDirectory $stage
Copy-Item -LiteralPath (Join-Path $repo 'src/Swirl.Quick/packaging/licenses') -Destination $stage -Recurse
Copy-Item -LiteralPath (Join-Path $repo 'src/Swirl.Quick/packaging/THIRD_PARTY_NOTICES.txt') -Destination $stage
Copy-Item -LiteralPath (Join-Path $repo 'src/Swirl.Quick/packaging/README-RustProductPreview.txt') -Destination (Join-Path $stage 'README.txt')
foreach ($name in @('Swirl-brand-phase3.ico','Swirl-brand-0217-canonical.ico')) {
    Copy-Item -LiteralPath (Join-Path $build 'brand/Swirl.ico') -Destination (Join-Path $stage $name)
}
& windeployqt --release --compiler-runtime --qmldir (Join-Path $repo 'src/Swirl.Quick/qml') (Join-Path $stage 'Swirl.exe')
if ($LASTEXITCODE -ne 0) { throw 'Qt deployment failed.' }
foreach ($name in @('Qt6Core.dll','Qt6Gui.dll','Qt6Qml.dll','Qt6Quick.dll','platforms/qwindows.dll','swirl_api.dll')) {
    if (-not (Test-Path -LiteralPath (Join-Path $stage $name) -PathType Leaf)) { throw "Missing packaged dependency: $name" }
}
$forbidden = @(Get-SwirlForbiddenProductFiles -ApplicationDirectory $stage)
if ($forbidden.Count) { throw ('Forbidden package entries: ' + ($forbidden -join ', ')) }
# Run the real EXE/DLL from a clean working directory, not the development tree.
# Preserve the report in the evidence path even when the executable fails.
$scratch = Join-Path ([IO.Path]::GetTempPath()) ('swirl-package-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch | Out-Null
$reportPath = Join-Path $stage 'rust-self-test.json'
$process = Start-Process -FilePath (Join-Path $stage 'Swirl.exe') `
    -ArgumentList @('--rust-core-self-test', ('"' + $reportPath + '"')) -WorkingDirectory $scratch -PassThru
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
$manifest = [ordered]@{ schema=1; source_sha=$sourceSha; rust=$expected; files=@() }
foreach ($file in (Get-ChildItem -LiteralPath $stage -Recurse -File | Sort-Object FullName)) {
    # Windows PowerShell 5.1 lacks Path.GetRelativePath. All entries were
    # enumerated inside this stage, so the canonical directory prefix suffices.
    $relativePath = $file.FullName.Substring($stage.TrimEnd('\','/').Length + 1).Replace('\','/')
    $manifest.files += [ordered]@{ path=$relativePath;
        sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $stage 'package-manifest.json') -Encoding utf8
Write-Host "Verified Rust product package: $sourceSha"
