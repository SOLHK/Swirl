param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'RustProductPackagePolicy.ps1')
$root=[IO.Path]::GetFullPath($OutputDirectory)
Assert-SwirlPathWithoutLinks $root
New-Item -ItemType Directory -Force -Path $root | Out-Null
# Pins were computed from the exact official HTTPS distribution. The upstream
# Windows index does not publish a separate checksum/signature; none is claimed.
$url='https://www.nasm.us/pub/nasm/releasebuilds/3.02/win64/nasm-3.02-win64.zip'
$archive=Join-Path $root 'nasm-3.02-win64.zip'
$archiveSha='161d0bfaff53c2f9e9f3e69fd0672323ebabafd1268976a5cec11be92a19aee7'
Assert-SwirlPathWithoutLinks $archive
if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
    $download=$archive+'.part'
    Assert-SwirlPathWithoutLinks $download
    Invoke-WebRequest -Uri $url -OutFile $download -MaximumRedirection 0 -TimeoutSec 120
    if ((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLowerInvariant() -cne $archiveSha) { throw 'Official NASM ZIP differs from the pinned distribution.' }
    Move-Item -LiteralPath $download -Destination $archive
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -cne $archiveSha) { throw 'Cached NASM ZIP differs from the pin.' }
$files=[ordered]@{
    'nasm.exe'='04ec2385879f7e1c45dbe76c4020970555de48eeb97c23f59620ede061328f51'
    'LICENSE'='222b65a5fab7ba8ade645970ad21bd5c2e2e6533897d59d1ca0914681c1f9da6'
}
$zip=[IO.Compression.ZipFile]::OpenRead($archive)
try {
    foreach ($name in $files.Keys) {
        $path=Join-Path $root $name
        Assert-SwirlPathWithoutLinks $path
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            # Copy only fixed entries, never expand arbitrary archive paths.
            $entry=$zip.GetEntry('nasm-3.02/'+$name)
            if (-not $entry -or $entry.Length -gt 4194304) { throw 'Pinned NASM ZIP entry is absent or oversized.' }
            $incoming=$entry.Open()
            try {
                $outgoing=[IO.File]::Open($path,[IO.FileMode]::CreateNew)
                try { $incoming.CopyTo($outgoing) } finally { $outgoing.Dispose() }
            } finally { $incoming.Dispose() }
        }
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $files[$name]) { throw "NASM executable/license hash mismatch: $name" }
    }
} finally { $zip.Dispose() }
$exe=Join-Path $root 'nasm.exe'
$version=(& $exe --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $version -cne 'NASM version 3.02 compiled on Jun 28 2026') { throw 'Pinned native NASM version verification failed.' }
Write-Host "Verified $version"
Write-Output $exe
