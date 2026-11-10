param(
    [Parameter(Mandatory=$true)][string]$BuildDirectory,
    [Parameter(Mandatory=$true)][string]$UiRuntimeDirectory,
    [Parameter(Mandatory=$true)][string]$WintunArchivePath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'RustProductPackagePolicy.ps1')
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$build = (Resolve-Path -LiteralPath $BuildDirectory).Path.TrimEnd('\','/')
$runtime = (Resolve-Path -LiteralPath $UiRuntimeDirectory).Path
foreach ($path in @($build,$runtime)) { Assert-SwirlPathWithoutLinks $path }
$cache = Get-Content -LiteralPath (Join-Path $build 'CMakeCache.txt') -Raw
$expectedHome = [IO.Path]::GetFullPath((Join-Path $repo 'src/Swirl.Quick')).TrimEnd('\','/')
if ($cache -notmatch '(?m)^SWIRL_BUILD_UI_TESTS:BOOL=ON\s*$' -or
    $cache -notmatch '(?m)^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$' -or
    [IO.Path]::GetFullPath($Matches[1].Trim()).TrimEnd('\','/') -ne $expectedHome) {
    throw 'Broker control checks require the current UI-hooks-ON build, separate from production.'
}
$bin = Join-Path $build 'Release'
$sha = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sha -notmatch '^[0-9a-f]{40}$') { throw 'Broker fixture source identity is unavailable.' }
$identity = Get-Content -LiteralPath (Join-Path $bin 'swirl-rust-build.json') -Raw | ConvertFrom-Json
if ($identity.source_sha -cne $sha -or $identity.target -cne 'x86_64-pc-windows-msvc' -or
    $identity.build_id -cnotmatch '^[0-9a-f]{64}$') { throw 'Broker control fixture requires the exact paired Windows MSVC build.' }
foreach ($name in @('Swirl.exe','swirl_api.dll')) {
    if ((Get-FileHash -LiteralPath (Join-Path $runtime $name) -Algorithm SHA256).Hash -cne
        (Get-FileHash -LiteralPath (Join-Path $bin $name) -Algorithm SHA256).Hash) {
        throw ('UI runtime differs from the test build: '+$name)
    }
}
$fixture = [IO.Path]::GetFullPath((Join-Path $build 'native-tun-broker-control'))
$app = Join-Path $fixture 'app'
Assert-SwirlPathWithoutLinks $fixture
if (-not $fixture.StartsWith($build+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or
    [IO.Path]::GetFileName($fixture) -cne 'native-tun-broker-control') { throw 'Unsafe broker fixture destination.' }
if (Test-Path -LiteralPath $fixture) {
    $marker = Get-Content -LiteralPath (Join-Path $fixture 'fixture.json') -Raw | ConvertFrom-Json
    if ($marker.kind -cne 'native-tun-broker-control-test-fixture' -or $marker.source_root -cne $repo) {
        throw 'Refusing to replace a directory without the matching test-fixture ownership marker.'
    }
    foreach ($entry in Get-ChildItem -LiteralPath $fixture -Recurse -Force) { Assert-SwirlPathWithoutLinks $entry.FullName }
    # The checked absolute target is only this owned, disposable build fixture.
    Remove-Item -LiteralPath $fixture -Recurse -Force
}
New-Item -ItemType Directory -Path $app -Force | Out-Null
foreach ($entry in Get-ChildItem -LiteralPath $runtime -Recurse -Force) { Assert-SwirlPathWithoutLinks $entry.FullName }
foreach ($entry in Get-ChildItem -LiteralPath $runtime -Force) {
    Assert-SwirlPathWithoutLinks $entry.FullName
    if ($entry.Name -ieq 'wintun.dll') { continue }
    Copy-Item -LiteralPath $entry.FullName -Destination $app -Recurse
}
foreach ($name in @('swirl-tun-broker.exe','swirl-tun-helper.exe')) {
    Copy-Item -LiteralPath (Join-Path $bin $name) -Destination (Join-Path $app $name)
}
$driver = & (Join-Path $PSScriptRoot 'Copy-VerifiedWintunRuntime.ps1') -ArchivePath $WintunArchivePath -ApplicationDirectory $app
$manifest = [ordered]@{schema=1;kind='native-tun-broker-control-test-fixture';ui_test_hooks=$true;source_sha=$sha;rust=$identity;files=@()}
foreach ($file in Get-ChildItem -LiteralPath $app -Recurse -File -Force | Sort-Object FullName) {
    Assert-SwirlPathWithoutLinks $file.FullName
    $relative = $file.FullName.Substring($app.Length+1).Replace('\','/')
    if ($relative -ceq 'package-manifest.json') { throw 'An existing production manifest must not enter a UI test fixture.' }
    $manifest.files += [ordered]@{path=$relative;sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $app 'package-manifest.json') -Encoding utf8
[ordered]@{schema=1;kind=$manifest.kind;source_root=$repo;source_sha=$sha;build_id=$identity.build_id;ui_test_hooks=$true;
    scope='authenticated broker and loopback Core control only; no native_tun_start or adapter traffic';wintun=$driver} |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $fixture 'fixture.json') -Encoding utf8
Write-Host ('Prepared independent UI-hooks-ON broker-control fixture: '+$sha)
