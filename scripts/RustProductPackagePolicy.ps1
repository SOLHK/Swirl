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

# Only Stage-WindowsRustProduct may call this for the destination it just
# created. Installed-product maintenance never calls it. No files or root
# directory are removed; a nonempty directory is always preserved.
function Remove-SwirlEmptyStagingDirectories {
    param(
        [Parameter(Mandatory=$true)][string]$StagingDirectory
    )
    $fullRoot = [IO.Path]::GetFullPath($StagingDirectory)
    $root = $fullRoot.TrimEnd('\','/')
    if (-not $root -or $root -eq [IO.Path]::GetPathRoot($fullRoot).TrimEnd('\','/')) {
        throw 'A filesystem root is not a build staging directory.'
    }
    Assert-SwirlPathWithoutLinks $root
    $stageItem = Get-Item -LiteralPath $root -Force -ErrorAction Stop
    if (-not $stageItem.PSIsContainer) { throw 'Empty-directory pruning requires a build staging directory.' }
    foreach ($marker in @('.swirl-install-owned','.swirl-isolated-install')) {
        if (Test-Path -LiteralPath (Join-Path $root $marker)) {
            throw 'Empty-directory pruning never modifies an installed product.'
        }
    }
    $comparison = if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        [StringComparison]::OrdinalIgnoreCase
    } else { [StringComparison]::Ordinal }
    $prefix = $root + [IO.Path]::DirectorySeparatorChar
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $directories = New-Object 'System.Collections.Generic.List[string]'
    $pending.Push($root)
    # Inspect the entire tree before mutation, enumerating each directory
    # without recursion so a junction/symlink is rejected before traversal.
    while ($pending.Count) {
        $directory = $pending.Pop()
        Assert-SwirlPathWithoutLinks $directory
        foreach ($entry in (Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
            if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Linked package or output path is forbidden.'
            }
            $full = [IO.Path]::GetFullPath($entry.FullName)
            if (-not $full.StartsWith($prefix,$comparison)) { throw 'Staging directory inventory escaped its root.' }
            if ($entry.PSIsContainer) { $directories.Add($full); $pending.Push($full) }
        }
    }
    $removed = New-Object 'System.Collections.Generic.List[string]'
    foreach ($directory in ($directories | Sort-Object { $_.Length } -Descending)) {
        Assert-SwirlPathWithoutLinks $directory
        if (@(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop).Count -eq 0) {
            # Non-recursive deletion also refuses a file created after the
            # emptiness check. Never replace this with recursive cleanup.
            [IO.Directory]::Delete($directory,$false)
            $removed.Add($directory.Substring($root.Length + 1).Replace('\','/'))
        }
    }
    return $removed.ToArray()
}

function Test-SwirlForbiddenProductPath {
    param([Parameter(Mandatory=$true)][string]$RelativePath)
    $path = $RelativePath.Replace('\','/')
    $name = ($path -split '/')[-1]
    return ($name -match '^(mihomo|clash|xray|sing-box)([.-]|$)' -or
        $name -match '^(swirl-tun-packet-worker|windows-tun-smoke|windows-gateway-forward-smoke)([.-]|$)' -or
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

function Get-SwirlWintunArtifact {
    $repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
    $inventory = Get-Content -LiteralPath (Join-Path $repo 'core/DEPENDENCIES.json') -Raw | ConvertFrom-Json
    $drivers = @($inventory.runtime_artifacts | Where-Object { $_.name -ceq 'Wintun official signed DLL' })
    if ($drivers.Count -ne 1) { throw 'Expected one reviewed Wintun runtime artifact.' }
    $driver = $drivers[0]
    $images = @($driver.artifacts | Where-Object { $_.target -ceq 'x86_64-pc-windows' })
    if ($driver.version -cne '0.14.1' -or $driver.source -cne 'https://www.wintun.net/builds/wintun-0.14.1.zip' -or
        $driver.archive_sha256 -cnotmatch '^[0-9a-f]{64}$' -or $images.Count -ne 1 -or
        $images[0].archive_path -cne 'wintun/bin/amd64/wintun.dll' -or $images[0].sha256 -cnotmatch '^[0-9a-f]{64}$') {
        throw 'Unreviewed Wintun version, source or AMD64 identity.'
    }
    return [pscustomobject]@{version=$driver.version;url=$driver.source;archive_sha256=$driver.archive_sha256;
        archive_path=$images[0].archive_path;sha256=$images[0].sha256;
        notice=(Join-Path $repo 'core/crates/swirl-platform/licenses/WINTUN-0.14.1.txt')}
}

function Assert-SwirlAmd64Image {
    param([Parameter(Mandatory=$true)][string]$Path)
    Assert-SwirlPathWithoutLinks $Path
    $stream = [IO.File]::OpenRead($Path)
    $reader = New-Object IO.BinaryReader $stream
    try {
        if ($stream.Length -lt 64 -or $reader.ReadUInt16() -ne 0x5a4d) { throw 'Invalid deployable DOS header.' }
        $stream.Position = 60
        $offset = $reader.ReadInt32()
        if ($offset -lt 64 -or $offset -gt $stream.Length - 26) { throw 'Invalid deployable PE header offset.' }
        $stream.Position = $offset
        if ($reader.ReadUInt32() -ne 0x4550 -or $reader.ReadUInt16() -ne 0x8664) { throw 'Product TUN requires an AMD64 PE image.' }
        $stream.Position = $offset + 24
        if ($reader.ReadUInt16() -ne 0x20b) { throw 'Product TUN requires a PE32+ image.' }
    } finally { $reader.Dispose(); $stream.Dispose() }
}

# Called by current staging/finalization, separately from the historical manifest
# ownership reader used to maintain older installed products.
function Assert-SwirlTunPayload {
    param(
        [Parameter(Mandatory=$true)][string]$ApplicationDirectory,
        [Parameter(Mandatory=$true)][string]$ExpectedSourceSha,
        [Parameter(Mandatory=$true)][string]$ExpectedBuildId,
        [string]$ExpectedTarget = 'x86_64-pc-windows-msvc'
    )
    $root = (Resolve-Path -LiteralPath $ApplicationDirectory).Path
    $manifest = Get-Content -LiteralPath (Join-Path $root 'package-manifest.json') -Raw | ConvertFrom-Json
    $required = @('swirl-tun-broker.exe','swirl-tun-helper.exe','wintun.dll','tun-runtime.json',
        'licenses/rust/crates/swirl-platform/licenses/WINTUN-0.14.1.txt')
    foreach ($name in $required) {
        $file = Join-Path $root $name
        Assert-SwirlPathWithoutLinks $file
        if ($name -cnotin @($manifest.files.path) -or -not (Test-Path -LiteralPath $file -PathType Leaf)) {
            throw "Missing product TUN payload entry: $name"
        }
    }
    $receipt = Get-Content -LiteralPath (Join-Path $root 'tun-runtime.json') -Raw | ConvertFrom-Json
    if ($receipt.schema -ne 1 -or $receipt.kind -cne 'windows-native-tun-payload' -or
        $receipt.source_sha -cne $ExpectedSourceSha -or $receipt.build_id -cne $ExpectedBuildId -or
        $receipt.target -cne $ExpectedTarget) { throw 'Product TUN payload identity mismatch.' }
    foreach ($entry in @(@{name='swirl-tun-broker.exe';role='swirl_tun_broker'},@{name='swirl-tun-helper.exe';role='swirl_tun_helper'})) {
        $file = Join-Path $root $entry.name
        $record = $receipt.binaries.PSObject.Properties[$entry.name].Value
        $identity = $record.identity
        if ($record.sha256 -cnotmatch '^[0-9a-f]{64}$' -or
            (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ine $record.sha256 -or
            $identity.abi_version -ne 1 -or $identity.role -cne $entry.role -or
            $identity.source_sha -cne $ExpectedSourceSha -or $identity.build_id -cne $ExpectedBuildId -or
            $identity.target -cne $ExpectedTarget) { throw ('Product TUN executable pairing mismatch: '+$entry.name) }
        Assert-SwirlAmd64Image $file
    }
    $driver = Get-SwirlWintunArtifact
    if ($receipt.driver.version -cne $driver.version -or $receipt.driver.source -cne $driver.url -or
        $receipt.driver.archive_sha256 -cne $driver.archive_sha256 -or $receipt.driver.sha256 -cne $driver.sha256 -or
        (Get-FileHash -LiteralPath (Join-Path $root 'wintun.dll') -Algorithm SHA256).Hash -ine $driver.sha256) {
        throw 'Product Wintun payload differs from the reviewed official binary.'
    }
    Assert-SwirlAmd64Image (Join-Path $root 'wintun.dll')
    $notice = Join-Path $root $required[-1]
    if (([IO.File]::ReadAllText($notice).Replace([string][char]13,'')) -cne
        ([IO.File]::ReadAllText($driver.notice).Replace([string][char]13,''))) {
        throw 'The complete official Wintun prebuilt-binaries license is required.'
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
