param(
    [Parameter(Mandatory=$true)][string]$ArchivePath,
    [Parameter(Mandatory=$true)][string]$ApplicationDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'RustProductPackagePolicy.ps1')
$driver = Get-SwirlWintunArtifact
$archive = [IO.Path]::GetFullPath($ArchivePath)
$root = (Resolve-Path -LiteralPath $ApplicationDirectory).Path
foreach ($path in @($archive,$root)) { Assert-SwirlPathWithoutLinks $path }
if ((Test-Path -LiteralPath $archive) -and -not (Test-Path -LiteralPath $archive -PathType Leaf)) {
    throw 'The Wintun cache path must name a ZIP file.'
}
if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
    $directory = [IO.Path]::GetDirectoryName($archive)
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $partial = Join-Path $directory ('wintun-download-'+[guid]::NewGuid().ToString('N')+'.zip')
    try {
        # The reviewed official URL is fixed by the checked-in dependency
        # inventory. Do not follow redirects to another download source.
        Invoke-WebRequest -Uri $driver.url -MaximumRedirection 0 -OutFile $partial
        if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ine $driver.archive_sha256) {
            throw 'Official Wintun archive SHA256 mismatch.'
        }
        Move-Item -LiteralPath $partial -Destination $archive
    } finally {
        if (Test-Path -LiteralPath $partial -PathType Leaf) { Remove-Item -LiteralPath $partial }
    }
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ine $driver.archive_sha256) {
    throw 'Cached Wintun archive differs from the pinned official release.'
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($archive)
try {
    $image = $zip.GetEntry($driver.archive_path)
    $license = $zip.GetEntry('wintun/LICENSE.txt')
    if (-not $image -or -not $license) { throw 'Official Wintun archive is missing its AMD64 binary or license.' }
    $dll = Join-Path $root 'wintun.dll'
    $notice = Join-Path $root 'licenses/rust/crates/swirl-platform/licenses/WINTUN-0.14.1.txt'
    foreach ($path in @($dll,$notice)) { Assert-SwirlPathWithoutLinks $path }
    New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($notice)) | Out-Null
    [IO.Compression.ZipFileExtensions]::ExtractToFile($image,$dll,$false)
    [IO.Compression.ZipFileExtensions]::ExtractToFile($license,$notice,$true)
} finally { $zip.Dispose() }
if ((Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash -ine $driver.sha256) {
    throw 'The Wintun AMD64 DLL differs from the pinned archive entry.'
}
Assert-SwirlAmd64Image $dll
if (([IO.File]::ReadAllText($notice).Replace([string][char]13,'')) -cne
    ([IO.File]::ReadAllText($driver.notice).Replace([string][char]13,''))) {
    throw 'The reviewed Wintun prebuilt-binaries license differs from the official archive.'
}
return [pscustomobject]@{version=$driver.version;source=$driver.url;archive_sha256=$driver.archive_sha256;
    sha256=$driver.sha256;architecture='amd64';license_path='licenses/rust/crates/swirl-platform/licenses/WINTUN-0.14.1.txt'}
