param(
    [Parameter(Mandatory=$true)][string]$BuildDirectory,
    [Parameter(Mandatory=$true)][string]$Destination,
    [string]$Configuration = 'Release'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$build = (Resolve-Path -LiteralPath $BuildDirectory).Path
$cache = Get-Content -LiteralPath (Join-Path $build 'CMakeCache.txt') -Raw
if ($cache -notmatch '(?m)^SWIRL_USE_RUST_CORE:BOOL=ON\s*$') { throw 'Rust Core must be the only configured product runtime.' }
if ($cache -notmatch '(?m)^SWIRL_RUST_LIBRARY:INTERNAL=(.+)$') { throw 'Exact Cargo library path is missing.' }
$rustLibrary = $Matches[1].Trim()
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
if ($expected.source_sha -ne $sourceSha -or $expected.target -ne 'x86_64-pc-windows-msvc') {
    throw 'Release packaging requires current source and Windows x64 MSVC.'
}
if ((Get-FileHash -LiteralPath $rustLibrary -Algorithm SHA256).Hash -ne
    (Get-FileHash -LiteralPath (Join-Path $bin 'swirl_api.dll') -Algorithm SHA256).Hash) { throw 'Deployed Rust DLL is stale.' }
New-Item -ItemType Directory -Path $stage | Out-Null
foreach ($name in $files) { Copy-Item -LiteralPath (Join-Path $bin $name) -Destination $stage }
& (Join-Path $PSScriptRoot 'Copy-VerifiedChinaRules.ps1') `
    -SourceDirectory (Join-Path $repo 'src/Swirl.Quick/packaging/rules') -ApplicationDirectory $stage
Copy-Item -LiteralPath (Join-Path $repo 'src/Swirl.Quick/packaging/licenses') -Destination $stage -Recurse
Copy-Item -LiteralPath (Join-Path $repo 'src/Swirl.Quick/packaging/README-RustProductPreview.txt') -Destination (Join-Path $stage 'README.txt')
foreach ($name in @('Swirl-brand-phase3.ico','Swirl-brand-phase3-v2.ico')) {
    Copy-Item -LiteralPath (Join-Path $build 'brand/Swirl.ico') -Destination (Join-Path $stage $name)
}
& windeployqt --release --compiler-runtime --qmldir (Join-Path $repo 'src/Swirl.Quick/qml') (Join-Path $stage 'Swirl.exe')
if ($LASTEXITCODE -ne 0) { throw 'Qt deployment failed.' }
foreach ($name in @('Qt6Core.dll','Qt6Gui.dll','Qt6Qml.dll','Qt6Quick.dll','platforms/qwindows.dll','swirl_api.dll')) {
    if (-not (Test-Path -LiteralPath (Join-Path $stage $name) -PathType Leaf)) { throw "Missing packaged dependency: $name" }
}
$forbidden = Get-ChildItem -LiteralPath $stage -Recurse -File | Where-Object {
    $_.Name -match '^(mihomo|clash|xray|sing-box)([.-]|$)|Tests\.exe$|Fixture\.dll$|\.private$|\.dpapi$'
}
if ($forbidden) { throw 'External core, test fixture or private data entered the package.' }
# Run the real EXE/DLL from a clean working directory, not the development tree.
$scratch = Join-Path ([IO.Path]::GetTempPath()) ('swirl-package-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch | Out-Null
$reportPath = Join-Path $scratch 'self-test.json'
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
Copy-Item -LiteralPath $reportPath -Destination (Join-Path $stage 'rust-self-test.json')
$manifest = [ordered]@{ schema=1; source_sha=$sourceSha; rust=$expected; files=@() }
foreach ($file in (Get-ChildItem -LiteralPath $stage -Recurse -File | Sort-Object FullName)) {
    $manifest.files += [ordered]@{ path=[IO.Path]::GetRelativePath($stage,$file.FullName).Replace('\','/');
        sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $stage 'package-manifest.json') -Encoding utf8
Write-Host "Verified Rust product package: $sourceSha"
