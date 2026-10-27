param(
    [Parameter(Mandatory=$true)][string]$ApplicationDirectory,
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory,
    [Parameter(Mandatory=$true)][string]$UninstallList
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'RustProductPackagePolicy.ps1')
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$sha = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot read source identity.' }
foreach ($path in @($ApplicationDirectory, $EvidenceDirectory, $UninstallList)) { Assert-SwirlPathWithoutLinks $path }
$root = (Resolve-Path -LiteralPath $ApplicationDirectory).Path.TrimEnd('\','/')
$evidence = [IO.Path]::GetFullPath($EvidenceDirectory).TrimEnd('\','/')
$list = [IO.Path]::GetFullPath($UninstallList)
foreach ($outside in @($evidence, $list)) {
    if ($outside -ieq $root -or $outside.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Evidence and uninstall include must be outside the payload.'
    }
}
$null = Assert-SwirlProductManifest -ApplicationDirectory $root -ExpectedSourceSha $sha -AllowSmokeDiagnostic
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$diagnostic = Join-Path $root 'Swirl-diagnostics.txt'
if (Test-Path -LiteralPath $diagnostic -PathType Leaf) {
    $saved = Join-Path $evidence 'Swirl-diagnostics.txt'
    if (Test-Path -LiteralPath $saved) { throw 'Smoke evidence already exists; use a fresh evidence directory.' }
    Move-Item -LiteralPath $diagnostic -Destination $saved
}
$manifest = Assert-SwirlProductManifest -ApplicationDirectory $root -ExpectedSourceSha $sha
if (Test-Path -LiteralPath $list) { throw 'Uninstall include already exists.' }
# Runtime cleanup uses the embedded manifest and hash-aware maintenance helper.
# Never generate unconditional Delete instructions for potentially modified files.
$lines = @('; Generated only after exact payload and source verification.',
    ('!define SWIRL_VERIFIED_SOURCE_SHA "' + $sha + '"'),
    ('!define SWIRL_VERIFIED_FILE_COUNT ' + @($manifest.files).Count))
New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($list)) | Out-Null
$lines | Set-Content -LiteralPath $list -Encoding utf8
@{ source_sha=$sha; files=@($manifest.files).Count; exact_inventory=$true; all_hashes_verified=$true } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'final-package-verification.json') -Encoding utf8
Write-Host "Final payload inventory and hashes verified: $sha"
