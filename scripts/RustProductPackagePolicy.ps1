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

function Get-SwirlForbiddenProductFiles {
    param([Parameter(Mandatory=$true)][string]$ApplicationDirectory)
    $root = (Resolve-Path -LiteralPath $ApplicationDirectory -ErrorAction Stop).Path.TrimEnd('\','/')
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw 'Product directory is not a directory.' }
    foreach ($file in (Get-ChildItem -LiteralPath $root -Recurse -File -Force -ErrorAction Stop)) {
        $relative = $file.FullName.Substring($root.Length + 1).Replace('\','/')
        if (Test-SwirlForbiddenProductPath -RelativePath $relative) { $relative }
    }
}
