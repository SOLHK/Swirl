param(
    [Parameter(Mandatory)][string]$Destination,
    [string]$Archive,
    [string]$Proxy
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$manifestPath = Join-Path $repo 'src/Swirl.Quick/packaging/mihomo-manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$scratch = Join-Path ([IO.Path]::GetTempPath()) ('swirl-mihomo-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch | Out-Null
try {
    if (!$Archive) {
        $Archive = Join-Path $scratch $manifest.asset
        $download = @{ Uri = $manifest.url; OutFile = $Archive; ErrorAction = 'Stop' }
        if ($Proxy) { $download.Proxy = $Proxy }
        Invoke-WebRequest @download
    }
    if ((Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.archiveSha256) {
        throw 'Mihomo archive SHA-256 mismatch; refusing to extract or execute.'
    }
    $expanded = Join-Path $scratch 'expanded'
    Expand-Archive -LiteralPath $Archive -DestinationPath $expanded
    $programs = @(Get-ChildItem -LiteralPath $expanded -Filter '*.exe' -File)
    if ($programs.Count -ne 1) { throw 'Expected exactly one Mihomo executable.' }
    if ((Get-FileHash -LiteralPath $programs[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.executableSha256) {
        throw 'Mihomo executable SHA-256 mismatch; refusing to stage or execute.'
    }
    $core = Join-Path $Destination 'core'
    New-Item -ItemType Directory -Force -Path $core | Out-Null
    Copy-Item -LiteralPath $programs[0].FullName -Destination (Join-Path $core 'mihomo.exe')
    Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $core 'mihomo-manifest.json')
    Write-Host ('Verified and staged Mihomo ' + $manifest.version)
} finally {
    # Only remove the exact temporary directory created by this invocation.
    $resolvedScratch = [IO.Path]::GetFullPath($scratch)
    $temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (!$resolvedScratch.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe cleanup target.' }
    Remove-Item -LiteralPath $resolvedScratch -Recurse -Force
}
