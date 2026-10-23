$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot '../RustProductPackagePolicy.ps1')
$allowed = @('licenses/LGPL-3.0-only.txt','Swirl.exe','swirl_api.dll','Qt6Core.dll',
    'rules/cn-domain.mrs','rules/cn-ip.mrs','THIRD_PARTY_NOTICES.txt')
$denied = @('mihomo.exe','engine/mihomo-windows-amd64.exe','licenses/mihomo.exe',
    'licenses/mihomo-GPL-3.0.txt','licenses\mihomo-GPL-3.0.txt','LICENSES/MIHOMO-GPL-3.0.TXT',
    'licenses/mihomo-GPL-3.0.txt.exe','mihomo-GPL-3.0.txt','other/licenses/mihomo-GPL-3.0.txt',
    'Mihomo.dll','clash.exe','xray.exe','sing-box.exe','mihomo-manifest.json',
    'SwirlRustCoreTests.exe','SwirlEngineFixture.exe','swirl_loader_fixture_1.dll',
    'swirl_loader_fixture_10.dll','nodes.dpapi','subscriptions.private')
foreach ($path in $allowed) {
    if (Test-SwirlForbiddenProductPath $path) { throw "Allowed package entry was rejected: $path" }
}
foreach ($path in $denied) {
    if (-not (Test-SwirlForbiddenProductPath $path)) { throw "Forbidden package entry was accepted: $path" }
}
$root = Join-Path ([IO.Path]::GetTempPath()) ('swirl-package-policy-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $root 'licenses') -Force | Out-Null
try {
    [IO.File]::WriteAllText((Join-Path $root 'licenses/LGPL-3.0-only.txt'), 'retained Qt license fixture')
    [IO.File]::WriteAllText((Join-Path $root 'Swirl.exe'), 'product fixture')
    if (@(Get-SwirlForbiddenProductFiles $root).Count -ne 0) { throw 'Retained Qt license poisoned clean package.' }
    [IO.File]::WriteAllText((Join-Path $root 'licenses/mihomo.exe'), 'forbidden runtime fixture')
    $actual = @(Get-SwirlForbiddenProductFiles $root)
    if ($actual.Count -ne 1 -or $actual[0] -ne 'licenses/mihomo.exe') { throw 'Runtime hidden in licenses escaped enumeration.' }
} finally {
    if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($root)) -ne [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\','/')) { throw 'Unexpected test cleanup path.' }
    Remove-Item -LiteralPath $root -Recurse -Force
}
Write-Host "Package policy: $($allowed.Count + $denied.Count + 2) assertions passed."

# Exercise the real staging entry point. Valid caches must reach the later
# missing-product guard; no executable, Qt installation or output stage exists.
# Visual Studio writes CRLF caches, while Ninja and Unix commonly write LF.
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$staging = Join-Path $repo 'scripts/Stage-WindowsRustProduct.ps1'
$cacheRoot = Join-Path ([IO.Path]::GetTempPath()) ('swirl-release-cache-' + [guid]::NewGuid().ToString('N'))
$build = Join-Path $cacheRoot 'build'
$destination = Join-Path $cacheRoot 'unused-stage'
New-Item -ItemType Directory -Path $build -Force | Out-Null
$cacheCases = @(
    @{ Line='CMAKE_BUILD_TYPE:STRING=Release'; Accepted=$true },
    @{ Line='CMAKE_CONFIGURATION_TYPES:STRING=Debug;Release;MinSizeRel;RelWithDebInfo'; Accepted=$true },
    @{ Line='CMAKE_CONFIGURATION_TYPES:STRING=Release;Debug'; Accepted=$true },
    @{ Line='CMAKE_CONFIGURATION_TYPES:STRING=Debug;Release'; Accepted=$true },
    @{ Line='CMAKE_CONFIGURATION_TYPES:STRING=Debug;RelWithDebInfo'; Accepted=$false },
    @{ Line='CMAKE_CONFIGURATION_TYPES:STRING=Debug;PreRelease'; Accepted=$false },
    @{ Line='CMAKE_CONFIGURATION_TYPES:STRING=Debug;ReleaseCandidate'; Accepted=$false }
)
$caseCount = 0
try {
    foreach ($ending in @("`n", "`r`n")) {
        foreach ($case in $cacheCases) {
            $lines = @('SWIRL_BUILD_UI_TESTS:BOOL=OFF', $case.Line,
                ('CMAKE_HOME_DIRECTORY:INTERNAL=' + (Join-Path $repo 'src/Swirl.Quick')),
                'SWIRL_USE_RUST_CORE:BOOL=ON',
                ('SWIRL_RUST_LIBRARY:INTERNAL=' + (Join-Path $build 'unused.dll')),
                'SWIRL_RUST_BUILD_ID:INTERNAL=cache-policy-fixture')
            [IO.File]::WriteAllText((Join-Path $build 'CMakeCache.txt'), (($lines -join $ending) + $ending))
            $failure = $null
            try {
                & $staging -BuildDirectory $build -Destination $destination
            } catch {
                $failure = $_.Exception.Message
            }
            $expected = if ($case.Accepted) { 'Missing build output: Swirl.exe' } else {
                'The CMake build does not include a Release configuration.'
            }
            if ($failure -cne $expected) {
                throw "Staging cache gate mismatch for $($case.Line), newline length $($ending.Length): $failure"
            }
            if (Test-Path -LiteralPath $destination) { throw 'Cache regression created a product stage.' }
            $caseCount++
        }
    }
} finally {
    if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($cacheRoot)) -ne [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\','/')) { throw 'Unexpected test cleanup path.' }
    Remove-Item -LiteralPath $cacheRoot -Recurse -Force
}
Write-Host "Release cache policy: $caseCount staging cases passed."
