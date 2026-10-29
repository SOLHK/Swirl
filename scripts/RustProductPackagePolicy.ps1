# Shared by production staging and independent package-policy regression tests.
# The retired runtime and its unused migration assets do not belong in a product.
function Assert-SwirlPathWithoutLinks {
    param([Parameter(Mandatory=$true)][string]$Path)
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Linked package or output path is forbidden.'
            }
        }
        $parent = [IO.Path]::GetDirectoryName($current.TrimEnd('\','/'))
        if ($parent -eq $current) { break }
        $current = $parent
    }
}

function Test-SwirlForbiddenProductPath {
    param([Parameter(Mandatory=$true)][string]$RelativePath)
    $path = $RelativePath.Replace('\','/')
    $name = ($path -split '/')[-1]
    return ($name -match '^(mihomo|clash|xray|sing-box)([.-]|$)' -or
        $name -match '(Tests|Fixture)\.(exe|dll)$' -or
        $name -match '^swirl_loader_fixture_[0-9]+\.(dll|so|dylib)$' -or
        $name -match '^Swirl(?:-[a-z0-9-]+)?-diagnostics\.txt$' -or
        $name -match '\.(private|dpapi)$')
}

# Validate the final payload, including files created after initial staging.
# A successful smoke launch does not authorize new or modified package files.
function Assert-SwirlProductManifest {
    param(
        [Parameter(Mandatory=$true)][string]$ApplicationDirectory,
        [Parameter(Mandatory=$true)][string]$ExpectedSourceSha,
        [switch]$AllowSmokeDiagnostic
    )
    Assert-SwirlPathWithoutLinks $ApplicationDirectory
    $root = (Resolve-Path -LiteralPath $ApplicationDirectory -ErrorAction Stop).Path.TrimEnd('\','/')
    # Inspect links before reading even the manifest, which can itself be linked.
    foreach ($item in (Get-ChildItem -LiteralPath $root -Recurse -Force -ErrorAction Stop)) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Linked package entry is forbidden.' }
    }
    $manifest = Get-Content -LiteralPath (Join-Path $root 'package-manifest.json') -Raw | ConvertFrom-Json
    if ($ExpectedSourceSha -notmatch '^[0-9a-f]{40}$' -or $manifest.schema -ne 1 -or
        $manifest.source_sha -cne $ExpectedSourceSha -or $manifest.rust.source_sha -cne $ExpectedSourceSha) {
        throw 'Package manifest source identity mismatch.'
    }
    $paths = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $manifest.files) {
        $relative = [string]$entry.path
        if (-not $relative -or $relative -match '[:\\\x00-\x1f"$]' -or $relative.StartsWith('/') -or
            @($relative.Split('/') | Where-Object { $_ -in @('','.', '..') }).Count -or
            $relative -ieq 'package-manifest.json' -or -not $paths.Add($relative)) {
            throw 'Unsafe or duplicate package manifest path.'
        }
        if (Test-SwirlForbiddenProductPath $relative) { throw "Forbidden manifest entry: $relative" }
        if ([string]$entry.sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw "Invalid package digest: $relative" }
    }
    # Check reparse points before opening files named by the manifest.
    foreach ($item in (Get-ChildItem -LiteralPath $root -Recurse -Force -ErrorAction Stop)) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Linked package entry is forbidden.' }
        if ($item.PSIsContainer) { continue }
        $relative = $item.FullName.Substring($root.Length + 1).Replace('\','/')
        if ($relative -ieq 'package-manifest.json') { continue }
        if ($AllowSmokeDiagnostic -and $relative -ceq 'Swirl-diagnostics.txt') { continue }
        if (-not $paths.Contains($relative)) { throw "Unlisted package entry: $relative" }
    }
    foreach ($entry in $manifest.files) {
        $file = Join-Path $root $entry.path
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing package entry: $($entry.path)" }
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ine $entry.sha256) {
            throw "Package digest mismatch: $($entry.path)"
        }
    }
    if ($paths.Count -eq 0) { throw 'Package manifest is empty.' }
    return $manifest
}

# Current production staging/finalization calls this unconditionally. The
# generic schema-1 ownership reader above remains compatible with old packages.
function Assert-SwirlTlsPayload {
    param(
        [Parameter(Mandatory=$true)][string]$ApplicationDirectory,
        [Parameter(Mandatory=$true)][string]$ExpectedVersion,
        [Parameter(Mandatory=$true)][string]$ExpectedSourceSha256
    )
    Assert-SwirlPathWithoutLinks $ApplicationDirectory
    $root = (Resolve-Path -LiteralPath $ApplicationDirectory -ErrorAction Stop).Path.TrimEnd('\','/')
    $manifestFile = Join-Path $root 'package-manifest.json'
    Assert-SwirlPathWithoutLinks $manifestFile
    $manifest = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
    $paths = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $manifest.files) { $null = $paths.Add([string]$entry.path) }
    $mapped = [ordered]@{
        'bin/libssl-3-x64.dll'='libssl-3-x64.dll'
        'bin/libcrypto-3-x64.dll'='libcrypto-3-x64.dll'
        'licenses/LICENSE.txt'='licenses/OpenSSL-LICENSE.txt'
        'licenses/NOTICE.txt'='licenses/OpenSSL-NOTICE.txt'
    }
    $required = @('Qt6Network.dll','tls/qopensslbackend.dll','openssl-runtime.json') + @($mapped.Values)
    foreach ($relative in $required) {
        $file = Join-Path $root $relative
        Assert-SwirlPathWithoutLinks $file
        if (-not $paths.Contains($relative) -or -not (Test-Path -LiteralPath $file -PathType Leaf)) {
            throw "Incomplete Qt TLS payload: $relative"
        }
        if ($relative.EndsWith('.dll')) {
            $stream = [IO.File]::OpenRead($file)
            $reader = New-Object IO.BinaryReader($stream)
            try {
                if ($stream.Length -lt 64 -or $reader.ReadUInt16() -ne 0x5a4d) { throw 'TLS dependency is not a PE image.' }
                $stream.Position=60; $offset=$reader.ReadUInt32()
                if ($offset -gt $stream.Length-6) { throw 'Invalid TLS PE header.' }
                $stream.Position=$offset
                if ($reader.ReadUInt32() -ne 0x4550 -or $reader.ReadUInt16() -ne 0x8664) { throw 'TLS dependency must be Windows x64.' }
            } finally { $reader.Dispose(); $stream.Dispose() }
        }
    }
    $receiptFile = Join-Path $root 'openssl-runtime.json'
    if ((Get-Item -LiteralPath $receiptFile).Length -gt 65536) { throw 'TLS receipt exceeds the bounded size.' }
    $receipt = Get-Content -LiteralPath $receiptFile -Raw | ConvertFrom-Json
    $target = switch ($manifest.rust.target) {
        'x86_64-pc-windows-msvc' { 'VC-WIN64A' }
        'x86_64-pc-windows-gnu' { 'mingw64' }
        default { throw 'Unsupported TLS package target.' }
    }
    if ($receipt.schema_version -ne 1 -or $receipt.status -cne 'success' -or
        $receipt.version -cne $ExpectedVersion -or $receipt.source.sha256 -cne $ExpectedSourceSha256 -or
        $receipt.target -cne $target -or @($receipt.files.PSObject.Properties).Count -ne 4) {
        throw 'TLS runtime receipt identity mismatch.'
    }
    foreach ($entry in $mapped.GetEnumerator()) {
        $record = $receipt.files.PSObject.Properties[$entry.Key].Value
        $file = Join-Path $root $entry.Value
        if ([string]$record.sha256 -notmatch '^[0-9a-f]{64}$' -or
            $record.size -ne (Get-Item -LiteralPath $file).Length -or
            (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ine $record.sha256) {
            throw "TLS runtime receipt digest mismatch: $($entry.Value)"
        }
    }
    return $receipt
}

function Get-SwirlForbiddenProductFiles {
    param([Parameter(Mandatory=$true)][string]$ApplicationDirectory)
    $root = (Resolve-Path -LiteralPath $ApplicationDirectory -ErrorAction Stop).Path.TrimEnd('\','/')
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw 'Product directory is not a directory.' }
    foreach ($file in (Get-ChildItem -LiteralPath $root -Recurse -File -Force -ErrorAction Stop)) {
        $relative = $file.FullName.Substring($root.Length + 1).Replace('\','/')
        if (Test-SwirlForbiddenProductPath -RelativePath $relative) { $relative }
    }
}
