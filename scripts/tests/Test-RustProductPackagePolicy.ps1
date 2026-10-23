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
    'swirl_loader_fixture_10.dll','nodes.dpapi','subscriptions.private',
    'Swirl-diagnostics.txt','Swirl-motion-diagnostics.txt')
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

# Reproduce post-smoke contamination and payload changes, not only filename rules.
$manifestRoot = Join-Path ([IO.Path]::GetTempPath()) ('swirl-manifest-' + [guid]::NewGuid().ToString('N'))
$manifestSha = '0123456789abcdef0123456789abcdef01234567'
New-Item -ItemType Directory -Path $manifestRoot | Out-Null
try {
    $payload = Join-Path $manifestRoot 'Swirl.exe'
    [IO.File]::WriteAllText($payload, 'synthetic product bytes')
    $manifestData = @{ schema=1; source_sha=$manifestSha; rust=@{source_sha=$manifestSha}; files=@(
        @{path='Swirl.exe'; sha256=(Get-FileHash -LiteralPath $payload -Algorithm SHA256).Hash}) }
    $manifestFile = Join-Path $manifestRoot 'package-manifest.json'
    $manifestData | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestFile -Encoding utf8
    $null = Assert-SwirlProductManifest $manifestRoot $manifestSha
    $diagnostic = Join-Path $manifestRoot 'Swirl-diagnostics.txt'
    [IO.File]::WriteAllText($diagnostic, 'synthetic smoke diagnostic')
    $failure = $null
    try { $null = Assert-SwirlProductManifest $manifestRoot $manifestSha } catch { $failure=$_.Exception.Message }
    if ($failure -notlike 'Unlisted package entry:*') { throw 'Post-smoke unlisted diagnostics were accepted.' }
    $null = Assert-SwirlProductManifest $manifestRoot $manifestSha -AllowSmokeDiagnostic
    [IO.File]::WriteAllText((Join-Path $manifestRoot 'unexpected.txt'), 'unlisted bytes')
    $failure = $null
    try { $null = Assert-SwirlProductManifest $manifestRoot $manifestSha -AllowSmokeDiagnostic } catch { $failure=$_.Exception.Message }
    if ($failure -notlike 'Unlisted package entry:*') { throw 'Smoke exception accepted unrelated payload.' }
    Remove-Item -LiteralPath (Join-Path $manifestRoot 'unexpected.txt')
    Remove-Item -LiteralPath $diagnostic
    [IO.File]::WriteAllText($payload, 'modified bytes after manifest')
    $failure = $null
    try { $null = Assert-SwirlProductManifest $manifestRoot $manifestSha } catch { $failure=$_.Exception.Message }
    if ($failure -notlike 'Package digest mismatch:*') { throw 'Changed payload hash was accepted.' }
    Remove-Item -LiteralPath $payload
    $failure = $null
    try { $null = Assert-SwirlProductManifest $manifestRoot $manifestSha } catch { $failure=$_.Exception.Message }
    if ($failure -notlike 'Missing package entry:*') { throw 'Missing payload was accepted.' }
    foreach ($unsafePath in @('../outside.exe','/absolute.exe','C:/outside.exe','folder/../outside.exe','folder//file.exe','folder\file.exe','inject$INSTDIR.exe')) {
        $manifestData.files[0].path=$unsafePath
        $manifestData | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestFile -Encoding utf8
        $failure = $null
        try { $null = Assert-SwirlProductManifest $manifestRoot $manifestSha } catch { $failure=$_.Exception.Message }
        if ($failure -ne 'Unsafe or duplicate package manifest path.') { throw "Unsafe manifest path accepted: $unsafePath" }
    }
    $manifestData.files=@(@{path='Swirl.exe';sha256=('a'*64)},@{path='SWIRL.EXE';sha256=('a'*64)})
    $manifestData | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestFile -Encoding utf8
    $failure=$null
    try { $null=Assert-SwirlProductManifest $manifestRoot $manifestSha } catch { $failure=$_.Exception.Message }
    if ($failure -ne 'Unsafe or duplicate package manifest path.') { throw 'Windows case-colliding manifest paths accepted.' }
} finally {
    if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($manifestRoot)) -ne [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\','/')) { throw 'Unexpected manifest cleanup path.' }
    Remove-Item -LiteralPath $manifestRoot -Recurse -Force
}
Write-Host 'Final manifest regression: 14 scenarios passed.'
