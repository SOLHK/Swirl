# Read-only package identity helpers, shared by the live Windows checker and
# portable fixture tests. Loading this file does not load a DLL or start a core.
# A local manifest establishes consistency, not publisher authenticity.
function Get-SwirlFileSha256 {
    param([Parameter(Mandatory=$true)][string]$Path)
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}

function Read-SwirlIdentityJson {
    param([string]$Path,[int]$MaximumBytes)
    if (-not [IO.File]::Exists($Path)) { throw 'IDENTITY_METADATA_MISSING' }
    $length = ([IO.FileInfo]$Path).Length
    if ($length -lt 2 -or $length -gt $MaximumBytes) { throw 'IDENTITY_METADATA_SIZE' }
    try { $document = [IO.File]::ReadAllText($Path) | ConvertFrom-Json -ErrorAction Stop }
    catch { throw 'IDENTITY_METADATA_JSON' }
    if ($null -eq $document -or $document -isnot [pscustomobject]) { throw 'IDENTITY_METADATA_OBJECT' }
    return $document
}

function Assert-SwirlIdentityHash {
    param([string]$Directory,[string]$Name,$Expected)
    if ($Expected -isnot [string] -or $Expected -notmatch '^[0-9a-fA-F]{64}$') { throw 'IDENTITY_FILE_HASH_INVALID' }
    $path = Join-Path $Directory $Name
    if (-not [IO.File]::Exists($path)) { throw 'IDENTITY_FILE_MISSING' }
    if ((Get-SwirlFileSha256 $path) -cne $Expected.ToLowerInvariant()) { throw 'IDENTITY_FILE_HASH_MISMATCH' }
}

function Get-SwirlInstalledIdentity {
    param(
        [Parameter(Mandatory=$true)][string]$Directory,
        [string]$ExpectedSourceSha = ''
    )
    $directoryPath = [IO.Path]::GetFullPath($Directory)
    $packagePath = Join-Path $directoryPath 'package-manifest.json'
    $rustPath = Join-Path $directoryPath 'swirl-rust-build.json'
    $legacyPath = Join-Path $directoryPath 'PRODUCT.json'
    $legacyBuildPath = Join-Path $directoryPath 'BUILD.txt'
    $hasPackage = [IO.File]::Exists($packagePath)
    $hasRust = [IO.File]::Exists($rustPath)
    $hasLegacy = [IO.File]::Exists($legacyPath)
    $hasLegacyBuild = [IO.File]::Exists($legacyBuildPath)
    if (($hasPackage -or $hasRust) -and ($hasLegacy -or $hasLegacyBuild)) {
        # Never prefer a good-looking old manifest over an incomplete/new one.
        throw 'IDENTITY_MIXED_PACKAGE_FORMATS'
    }
    $result = [ordered]@{
        sourceSha = ''; format = ''; buildId = ''; rulesHashesVerified = $false
        executableHashMatchesManifest = $false; rustDllHashMatchesManifest = $false
        rustBuildFlagEnabled = $false; productDeclaresRustCore = $false
        publisherAuthenticity = 'NOT_VERIFIED'
    }
    if ($hasPackage -or $hasRust) {
        if (-not ($hasPackage -and $hasRust)) { throw 'IDENTITY_CURRENT_PAIR_INCOMPLETE' }
        $package = Read-SwirlIdentityJson $packagePath (8 * 1024 * 1024)
        $rust = Read-SwirlIdentityJson $rustPath (64 * 1024)
        if (($package.schema -isnot [int] -and $package.schema -isnot [long]) -or $package.schema -ne 1 -or $package.source_sha -isnot [string] -or
            $package.source_sha -notmatch '^[0-9a-f]{40}$' -or $package.rust -isnot [pscustomobject] -or
            $package.files -isnot [array] -or $package.files.Count -lt 5 -or $package.files.Count -gt 20000) {
            throw 'IDENTITY_CURRENT_MANIFEST_INVALID'
        }
        foreach ($metadata in @($rust,$package.rust)) {
            if (($metadata.abi_version -isnot [int] -and $metadata.abi_version -isnot [long]) -or $metadata.abi_version -ne 1 -or $metadata.target -cne 'x86_64-pc-windows-msvc' -or
                $metadata.source_sha -cne $package.source_sha -or $metadata.build_id -isnot [string] -or
                $metadata.build_id -notmatch '^[0-9a-f]{64}$') { throw 'IDENTITY_RUST_METADATA_MISMATCH' }
        }
        if ($rust.build_id -cne $package.rust.build_id) { throw 'IDENTITY_RUST_BUILD_MISMATCH' }
        $hashes = @{}
        foreach ($entry in $package.files) {
            if ($entry -isnot [pscustomobject] -or $entry.path -isnot [string] -or
                $entry.path.Length -gt 1024 -or $entry.path -notmatch '^[^/\\:\x00-\x1f<>"|?*]+(?:/[^/\\:\x00-\x1f<>"|?*]+)*$' -or
                @($entry.path.Split('/') | Where-Object { $_ -in @('.','..') -or $_.EndsWith('.') -or $_.EndsWith(' ') }).Count -gt 0 -or
                $entry.sha256 -isnot [string] -or $entry.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or
                $hashes.ContainsKey($entry.path)) { throw 'IDENTITY_MANIFEST_ENTRY_INVALID' }
            $hashes[$entry.path] = $entry.sha256
        }
        # Verify the actual pair and its metadata. Rule files are mandatory in
        # the current product; this also detects incomplete installation copies.
        foreach ($name in @('Swirl.exe','swirl_api.dll','swirl-rust-build.json','rules/cn-domain.mrs','rules/cn-ip.mrs')) {
            if (-not $hashes.ContainsKey($name)) { throw 'IDENTITY_REQUIRED_FILE_UNLISTED' }
            Assert-SwirlIdentityHash $directoryPath $name $hashes[$name]
        }
        $result.sourceSha = $package.source_sha
        $result.buildId = $rust.build_id
        $result.format = 'r1-paired-package-v1'
        $result.rulesHashesVerified = $true
    } elseif ($hasLegacy -or $hasLegacyBuild) {
        if (-not ($hasLegacy -and $hasLegacyBuild)) { throw 'IDENTITY_LEGACY_PAIR_INCOMPLETE' }
        $legacy = Read-SwirlIdentityJson $legacyPath (128 * 1024)
        if ($legacy.sourceSha -isnot [string] -or $legacy.sourceSha -notmatch '^[0-9a-fA-F]{40}$' -or
            $legacy.rustCore -isnot [bool] -or -not $legacy.rustCore -or
            $legacy.mihomoBundled -isnot [bool] -or $legacy.mihomoBundled -or
            $legacy.kind -cne 'windows-rust-product-preview') { throw 'IDENTITY_LEGACY_MANIFEST_INVALID' }
        if (([IO.FileInfo]$legacyBuildPath).Length -gt 65536) { throw 'IDENTITY_METADATA_SIZE' }
        $build = [IO.File]::ReadAllText($legacyBuildPath)
        if ($build -notmatch '(?<![A-Za-z0-9_])SWIRL_USE_RUST_CORE=ON(?![A-Za-z0-9_])' -or
            $build -notmatch ('(?<![0-9a-fA-F])' + [regex]::Escape($legacy.sourceSha) + '(?![0-9a-fA-F])')) {
            throw 'IDENTITY_LEGACY_BUILD_MISMATCH'
        }
        Assert-SwirlIdentityHash $directoryPath 'Swirl.exe' $legacy.exeSha256
        Assert-SwirlIdentityHash $directoryPath 'swirl_api.dll' $legacy.rustDllSha256
        $result.sourceSha = $legacy.sourceSha.ToLowerInvariant()
        $result.format = 'legacy-product-preview'
    } else { throw 'IDENTITY_METADATA_MISSING' }
    if ($ExpectedSourceSha -and ($ExpectedSourceSha -notmatch '^[0-9a-fA-F]{40}$' -or
        $result.sourceSha -cne $ExpectedSourceSha.ToLowerInvariant())) { throw 'IDENTITY_EXPECTED_SOURCE_MISMATCH' }
    $result.executableHashMatchesManifest = $true
    $result.rustDllHashMatchesManifest = $true
    $result.rustBuildFlagEnabled = $true
    $result.productDeclaresRustCore = $true
    return [pscustomobject]$result
}
