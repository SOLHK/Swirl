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
            $lines = @('SWIRL_BUILD_UI_TESTS:BOOL=OFF','SWIRL_BUILD_CORE_TESTS:BOOL=ON', $case.Line,
                ('CMAKE_HOME_DIRECTORY:INTERNAL=' + (Join-Path $repo 'src/Swirl.Quick')),
                'SWIRL_RUNTIME:INTERNAL=rust',
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
        foreach ($runtime in @('', 'SWIRL_RUNTIME:INTERNAL=mihomo')) {
            $runtimeLines = @('SWIRL_BUILD_UI_TESTS:BOOL=OFF','CMAKE_BUILD_TYPE:STRING=Release',
                ('CMAKE_HOME_DIRECTORY:INTERNAL=' + (Join-Path $repo 'src/Swirl.Quick')),
                ('SWIRL_RUST_LIBRARY:INTERNAL=' + (Join-Path $build 'unused.dll')),
                'SWIRL_RUST_BUILD_ID:INTERNAL=cache-policy-fixture')
            if ($runtime) { $runtimeLines += $runtime }
            [IO.File]::WriteAllText((Join-Path $build 'CMakeCache.txt'), (($runtimeLines -join $ending) + $ending))
            $failure = $null
            try { & $staging -BuildDirectory $build -Destination $destination } catch { $failure=$_.Exception.Message }
            if ($failure -cne 'Rust Core must be the only configured product runtime.') {
                throw 'A missing or foreign runtime identity reached product staging.'
            }
            if (Test-Path -LiteralPath $destination) { throw 'Runtime identity regression created a product stage.' }
            $caseCount++
        }
        $uiLines = @('SWIRL_BUILD_UI_TESTS:BOOL=ON','SWIRL_BUILD_CORE_TESTS:BOOL=ON','CMAKE_BUILD_TYPE:STRING=Release')
        [IO.File]::WriteAllText((Join-Path $build 'CMakeCache.txt'), (($uiLines -join $ending) + $ending))
        $failure = $null
        try { & $staging -BuildDirectory $build -Destination $destination } catch { $failure = $_.Exception.Message }
        if ($failure -cne 'Never package an executable with UI test entry points enabled.') {
            throw 'Standalone core tests must not permit packaging an application with UI test entry points.'
        }
        if (Test-Path -LiteralPath $destination) { throw 'UI test cache regression created a product stage.' }
        $caseCount++
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

# The current product must carry its own complete Qt/OpenSSL TLS closure. These
# PE headers are synthetic and are never loaded or executed by this test.
$tlsTestRoot = Join-Path ([IO.Path]::GetTempPath()) ('swirl-tls-policy-' + [guid]::NewGuid().ToString('N'))
$tlsSourceSha = '603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a'
$tlsApplicationSha = '0123456789abcdef0123456789abcdef01234567'
$tlsMap = [ordered]@{
    'bin/libssl-3-x64.dll'='libssl-3-x64.dll'
    'bin/libcrypto-3-x64.dll'='libcrypto-3-x64.dll'
    'licenses/LICENSE.txt'='licenses/OpenSSL-LICENSE.txt'
    'licenses/NOTICE.txt'='licenses/OpenSSL-NOTICE.txt'
}
$tlsRequired = @('Qt6Network.dll','tls/qopensslbackend.dll','openssl-runtime.json') + @($tlsMap.Values)
$script:tlsFixtureCounter = 0
$script:tlsAssertions = 0
New-Item -ItemType Directory -Path $tlsTestRoot | Out-Null

function Write-TlsFixturePe {
    param([string]$Path, [uint16]$Machine = 0x8664)
    $bytes = New-Object byte[] 128
    $bytes[0]=0x4d; $bytes[1]=0x5a
    [BitConverter]::GetBytes([uint32]64).CopyTo($bytes,60)
    [BitConverter]::GetBytes([uint32]0x4550).CopyTo($bytes,64)
    [BitConverter]::GetBytes($Machine).CopyTo($bytes,68)
    [IO.File]::WriteAllBytes($Path,$bytes)
}

function Write-TlsFixtureManifest {
    param([hashtable]$Fixture)
    $files = @()
    foreach ($file in (Get-ChildItem -LiteralPath $Fixture.Root -File -Recurse | Sort-Object FullName)) {
        $relative = $file.FullName.Substring($Fixture.Root.Length+1).Replace('\','/')
        if ($relative -eq 'package-manifest.json') { continue }
        $files += @{path=$relative;sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    $Fixture.Manifest.files=$files
    $Fixture.Manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $Fixture.Root 'package-manifest.json') -Encoding utf8
}

function Write-TlsFixtureReceipt {
    param([hashtable]$Fixture)
    $Fixture.Receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $Fixture.Root 'openssl-runtime.json') -Encoding utf8
    Write-TlsFixtureManifest $Fixture
}

function New-TlsFixture {
    param([string]$RustTarget = 'x86_64-pc-windows-msvc')
    $script:tlsFixtureCounter++
    $directory = Join-Path $tlsTestRoot ('case-' + $script:tlsFixtureCounter)
    New-Item -ItemType Directory -Path (Join-Path $directory 'tls'),(Join-Path $directory 'licenses') -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $directory 'Swirl.exe'),'synthetic product bytes')
    foreach ($name in @('Qt6Network.dll','tls/qopensslbackend.dll','libssl-3-x64.dll','libcrypto-3-x64.dll')) {
        Write-TlsFixturePe (Join-Path $directory $name)
    }
    [IO.File]::WriteAllText((Join-Path $directory 'licenses/OpenSSL-LICENSE.txt'),'controlled license fixture')
    [IO.File]::WriteAllText((Join-Path $directory 'licenses/OpenSSL-NOTICE.txt'),'controlled Swirl provenance notice')
    $records = [ordered]@{}
    foreach ($entry in $tlsMap.GetEnumerator()) {
        $file = Join-Path $directory $entry.Value
        $records[$entry.Key]=@{sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant();size=(Get-Item -LiteralPath $file).Length}
    }
    $runtimeTarget = if ($RustTarget -eq 'x86_64-pc-windows-msvc') { 'VC-WIN64A' } else { 'mingw64' }
    $fixture = @{Root=$directory;Manifest=@{schema=1;source_sha=$tlsApplicationSha;rust=@{source_sha=$tlsApplicationSha;target=$RustTarget};files=@()};
        Receipt=@{schema_version=1;status='success';version='3.5.9';source=@{sha256=$tlsSourceSha};target=$runtimeTarget;files=$records}}
    Write-TlsFixtureReceipt $fixture
    return $fixture
}

function Assert-TlsFixtureAccepted {
    param([hashtable]$Fixture)
    $null=Assert-SwirlTlsPayload -ApplicationDirectory $Fixture.Root -ExpectedVersion '3.5.9' -ExpectedSourceSha256 $tlsSourceSha
    $null=Assert-SwirlProductManifest -ApplicationDirectory $Fixture.Root -ExpectedSourceSha $tlsApplicationSha
    $script:tlsAssertions++
}

function Assert-TlsFixtureRejected {
    param([hashtable]$Fixture,[string]$Label,[string]$Expected = '*')
    $failure=$null
    try { Assert-TlsFixtureAccepted $Fixture } catch { $failure=$_.Exception.Message }
    if (-not $failure -or $failure -notlike $Expected) { throw "TLS package policy accepted $Label or failed for another reason: $failure" }
    $script:tlsAssertions++
}

try {
    Assert-TlsFixtureAccepted (New-TlsFixture)
    Assert-TlsFixtureAccepted (New-TlsFixture 'x86_64-pc-windows-gnu')
    foreach ($relative in $tlsRequired) {
        $fixture=New-TlsFixture
        Remove-Item -LiteralPath (Join-Path $fixture.Root $relative)
        Write-TlsFixtureManifest $fixture
        Assert-TlsFixtureRejected $fixture "missing dependency and matching manifest entry: $relative" 'Incomplete Qt TLS payload:*'
        $fixture=New-TlsFixture
        $fixture.Manifest.files=@($fixture.Manifest.files | Where-Object { $_.path -ne $relative })
        $fixture.Manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $fixture.Root 'package-manifest.json') -Encoding utf8
        Assert-TlsFixtureRejected $fixture "unmanifested required dependency: $relative" 'Incomplete Qt TLS payload:*'
    }
    foreach ($relative in @('Qt6Network.dll','tls/qopensslbackend.dll','libssl-3-x64.dll','libcrypto-3-x64.dll')) {
        foreach ($kind in @('x86','non-PE')) {
            $fixture=New-TlsFixture
            $path=Join-Path $fixture.Root $relative
            if ($kind -eq 'x86') { Write-TlsFixturePe $path 0x14c } else { [IO.File]::WriteAllText($path,'not a PE') }
            Write-TlsFixtureManifest $fixture
            Assert-TlsFixtureRejected $fixture "$kind dependency: $relative" 'TLS dependency*'
        }
    }
    foreach ($field in @('schema_version','status','version','source','target')) {
        $fixture=New-TlsFixture
        $fixture.Receipt[$field]=switch ($field) {
            'schema_version' { 2 }; 'status' { 'partial' }; 'version' { '3.0.16' }
            'source' { @{sha256=('0'*64)} }; 'target' { 'mingw64' }
        }
        Write-TlsFixtureReceipt $fixture
        Assert-TlsFixtureRejected $fixture "changed receipt identity $field" 'TLS runtime receipt identity mismatch.'
    }
    foreach ($relative in $tlsMap.Values) {
        $fixture=New-TlsFixture
        [IO.File]::AppendAllText((Join-Path $fixture.Root $relative),'changed after runtime receipt')
        Write-TlsFixtureManifest $fixture
        Assert-TlsFixtureRejected $fixture "changed mapped runtime/license: $relative" 'TLS runtime receipt digest mismatch:*'
    }
    foreach ($key in @('../outside.dll','bin/libssl-3-x64.dll:stream','licenses/OpenSSL-LICENSE.txt')) {
        $fixture=New-TlsFixture
        $record=$fixture.Receipt.files['bin/libssl-3-x64.dll']
        $fixture.Receipt.files.Remove('bin/libssl-3-x64.dll')
        $fixture.Receipt.files[$key]=$record
        Write-TlsFixtureReceipt $fixture
        Assert-TlsFixtureRejected $fixture "unsafe or unmapped runtime receipt key $key"
    }
    $fixture=New-TlsFixture 'aarch64-pc-windows-msvc'
    Assert-TlsFixtureRejected $fixture 'unsupported Rust/TLS package architecture' 'Unsupported TLS package target.'
    $fixture=New-TlsFixture
    $fixture.Receipt.files.Remove('licenses/NOTICE.txt')
    Write-TlsFixtureReceipt $fixture
    Assert-TlsFixtureRejected $fixture 'missing mandatory receipt map' 'TLS runtime receipt identity mismatch.'
    $fixture=New-TlsFixture
    $fixture.Receipt['padding']='x'*65536
    Write-TlsFixtureReceipt $fixture
    Assert-TlsFixtureRejected $fixture 'oversized runtime receipt' 'TLS receipt exceeds the bounded size.'
    $fixture=New-TlsFixture
    [IO.File]::AppendAllText((Join-Path $fixture.Root 'Qt6Network.dll'),'changed without manifest update')
    Assert-TlsFixtureRejected $fixture 'modified Qt dependency after manifest' 'Package digest mismatch:*'
    $fixture=New-TlsFixture
    [IO.File]::WriteAllText((Join-Path $fixture.Root 'private.dpapi'),'must not ship')
    Assert-TlsFixtureRejected $fixture 'unlisted private payload' 'Unlisted package entry:*'
    $fixture=New-TlsFixture
    $outside=Join-Path $tlsTestRoot 'outside-tls'
    $tlsDirectory=(Resolve-Path -LiteralPath (Join-Path $fixture.Root 'tls')).Path
    if (-not $tlsDirectory.StartsWith([IO.Path]::GetFullPath($tlsTestRoot).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($outside)) -ne [IO.Path]::GetFullPath($tlsTestRoot)) { throw 'Unexpected TLS link fixture move path.' }
    Move-Item -LiteralPath $tlsDirectory -Destination $outside
    $link=Join-Path $fixture.Root 'tls'
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        New-Item -ItemType Junction -Path $link -Target $outside | Out-Null
    } else {
        New-Item -ItemType SymbolicLink -Path $link -Target $outside | Out-Null
    }
    try {
        Assert-TlsFixtureRejected $fixture 'linked TLS directory' 'Linked package or output path is forbidden.'
    } finally { [IO.Directory]::Delete($link) }
} finally {
    if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($tlsTestRoot)) -ne [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\','/')) { throw 'Unexpected TLS fixture cleanup path.' }
    Remove-Item -LiteralPath $tlsTestRoot -Recurse -Force
}
Write-Host "TLS package policy: $script:tlsAssertions scenarios passed."
