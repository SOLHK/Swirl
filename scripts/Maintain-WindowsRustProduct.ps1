param(
    [Parameter(Mandatory=$true)][ValidateSet('Upgrade','Verify','Uninstall')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$ApplicationDirectory,
    [Parameter(Mandatory=$true)][string]$ExpectedManifest,
    [string]$PreviousManifest,
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'RustProductPackagePolicy.ps1')

function Get-PayloadHash([string]$Path) {
    # Use the framework primitive directly: a 32-bit installer can inherit a
    # 64-bit PowerShell module path where Get-FileHash is unavailable.
    $stream = [IO.File]::OpenRead($Path)
    $digest = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($digest.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $digest.Dispose(); $stream.Dispose() }
}

function Read-OwnedManifest([string]$Path) {
    Assert-SwirlPathWithoutLinks $Path
    if ((Get-Item -LiteralPath $Path).Length -gt 16777216) { throw 'Package manifest exceeds the bounded size.' }
    $manifest = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($manifest.schema -ne 1 -or $manifest.source_sha -notmatch '^[0-9a-f]{40}$' -or
        $manifest.rust.source_sha -cne $manifest.source_sha -or
        @($manifest.files).Count -eq 0 -or @($manifest.files).Count -gt 50000) {
        throw 'Package ownership manifest has invalid identity or file count.'
    }
    $paths = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $manifest.files) {
        $relative = [string]$entry.path
        if (-not $relative -or $relative.Length -gt 900 -or
            $relative -match '[:\\\x00-\x1f"$*?<>|]' -or $relative.StartsWith('/') -or
            @($relative.Split('/') | Where-Object { $_ -in @('','.', '..') -or $_.EndsWith('.') -or $_.EndsWith(' ') }).Count -or
            $relative -in @('package-manifest.json','.swirl-install-owned','.swirl-isolated-install','卸载 Swirl.exe') -or
            (Test-SwirlForbiddenProductPath $relative) -or $paths.ContainsKey($relative) -or
            [string]$entry.sha256 -notmatch '^[0-9a-fA-F]{64}$') {
            throw 'Unsafe package ownership manifest entry.'
        }
        $paths.Add($relative, $entry)
    }
    return $paths
}

Assert-SwirlPathWithoutLinks $ApplicationDirectory
Assert-SwirlPathWithoutLinks $ExpectedManifest
$root = [IO.Path]::GetFullPath($ApplicationDirectory).TrimEnd('\','/')
if ($root.Length -lt 4 -or $root -eq [IO.Path]::GetPathRoot($root).TrimEnd('\','/')) {
    throw 'A drive root is not an application installation.'
}
$expected = Read-OwnedManifest $ExpectedManifest
if ($PrepareOnly -and ($Mode -ne 'Upgrade' -or -not $PreviousManifest)) { throw 'Invalid upgrade preparation arguments.' }
if ($PreviousManifest) {
    Assert-SwirlPathWithoutLinks $PreviousManifest
    $previousFullPath = [IO.Path]::GetFullPath($PreviousManifest)
    if ($previousFullPath.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Saved upgrade ownership must be outside the installation.'
    }
}
foreach ($relative in $expected.Keys) { Assert-SwirlPathWithoutLinks (Join-Path $root $relative) }
$installedManifest = Join-Path $root 'package-manifest.json'
# A saved older uninstaller must never act on a newer installation. Validate
# version ownership before constructing any deletion plan, including files
# whose bytes happen to be unchanged across both builds.
if ($Mode -eq 'Uninstall') {
    Assert-SwirlPathWithoutLinks $installedManifest
    if (-not (Test-Path -LiteralPath $installedManifest -PathType Leaf) -or
        (Get-PayloadHash $installedManifest) -cne (Get-PayloadHash $ExpectedManifest)) {
        throw 'Installed package identity does not match this uninstaller.'
    }
}
$plan = New-Object 'System.Collections.Generic.List[string]'
$preserved = 0
$legacy = $false

if ($Mode -eq 'Verify') {
    foreach ($relative in $expected.Keys) {
        $file = Join-Path $root $relative
        if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or
            (Get-PayloadHash $file) -ine $expected[$relative].sha256) {
            throw 'Installed vendor payload hash verification failed.'
        }
    }
    Assert-SwirlPathWithoutLinks $installedManifest
    if ((Get-PayloadHash $installedManifest) -cne (Get-PayloadHash $ExpectedManifest)) {
        throw 'Installed package manifest differs from the embedded manifest.'
    }
} else {
    $owned = $expected
    if ($Mode -eq 'Upgrade') {
        $oldManifest = if ($PreviousManifest -and -not $PrepareOnly) { $PreviousManifest } else { $installedManifest }
        if (-not (Test-Path -LiteralPath (Join-Path $root '.swirl-install-owned') -PathType Leaf) -or
            -not (Test-Path -LiteralPath $oldManifest -PathType Leaf)) {
            # Legacy ownership is unknown. Keep every extra file; never invoke
            # a legacy recursive uninstaller or infer ownership from extension.
            $legacy = $true
            $owned = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([StringComparer]::OrdinalIgnoreCase)
        } else {
            $owned = Read-OwnedManifest $oldManifest
        }
    }
    # Validate the entire candidate set before the first deletion. Paths are
    # literal and all ancestors are checked, including user-added junctions.
    foreach ($relative in $owned.Keys) {
        $file = Join-Path $root $relative
        Assert-SwirlPathWithoutLinks $file
        if ($Mode -eq 'Upgrade' -and $expected.ContainsKey($relative)) { continue }
        if (-not (Test-Path -LiteralPath $file)) { continue }
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw 'Owned package file became a directory.' }
        if ((Get-PayloadHash $file) -ieq $owned[$relative].sha256) {
            $plan.Add($file)
        } else {
            $preserved++
        }
    }
    if ($Mode -eq 'Uninstall') { $plan.Add($installedManifest) }
    if ($PrepareOnly) {
        if (-not $legacy) {
            if (Test-Path -LiteralPath $PreviousManifest) { throw 'Saved upgrade ownership already exists.' }
            Copy-Item -LiteralPath $installedManifest -Destination $PreviousManifest
        }
        @{mode='PrepareUpgrade'; planned_obsolete_files=$plan.Count; success=$true} | ConvertTo-Json -Compress | Write-Output
        return
    }
    foreach ($file in $plan) {
        Assert-SwirlPathWithoutLinks $file
        Remove-Item -LiteralPath $file -Force
        $parent = [IO.Path]::GetDirectoryName($file)
        while ($parent -ne $root -and $parent.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
            Assert-SwirlPathWithoutLinks $parent
            if (@(Get-ChildItem -LiteralPath $parent -Force).Count) { break }
            Remove-Item -LiteralPath $parent
            $parent = [IO.Path]::GetDirectoryName($parent)
        }
    }
}
@{mode=$Mode; removed=$plan.Count; modified_files_preserved=$preserved; legacy_extra_files_preserved=$legacy;
  success=$true} | ConvertTo-Json -Compress | Write-Output
