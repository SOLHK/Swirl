param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$geoManifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'geodata.json') -Raw | ConvertFrom-Json
$geoDestination = [IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Path $geoDestination -Force | Out-Null
foreach ($geoAsset in $geoManifest.assets) {
    $geoFile = Join-Path $geoDestination $geoAsset.file
    $geoUrl = 'https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/' + $geoManifest.revision + '/' + $geoAsset.source
    if (-not (Test-Path -LiteralPath $geoFile) -or (Get-FileHash -LiteralPath $geoFile -Algorithm SHA256).Hash -ne $geoAsset.sha256) {
        Invoke-WebRequest $geoUrl -OutFile $geoFile -TimeoutSec 180
    }
    if ((Get-FileHash -LiteralPath $geoFile -Algorithm SHA256).Hash -ne $geoAsset.sha256) { throw ('GEO database checksum mismatch: ' + $geoAsset.file) }
}
$geoLicenseUrl = 'https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/' + $geoManifest.licenseRevision + '/LICENSE'
Invoke-WebRequest $geoLicenseUrl -OutFile (Join-Path $geoDestination 'LICENSE-GeoData.txt') -TimeoutSec 30
@"
GEO databases from MetaCubeX/meta-rules-dat, unchanged.
Source snapshot: https://github.com/MetaCubeX/meta-rules-dat/tree/$($geoManifest.revision)
SHA256 values: scripts/geodata.json in Swirl source.
License: GPL-3.0; see LICENSE-GeoData.txt.
Upstream datasets and attribution: https://github.com/MetaCubeX/meta-rules-dat#readme
GeoLite2 data created by MaxMind, available from https://www.maxmind.com/ .
Swirl seeds missing default databases into its core data directory before validation.
Existing databases and explicitly customized GEO download sources are preserved.
"@ | Set-Content -LiteralPath (Join-Path $geoDestination 'NOTICE-GeoData.txt') -Encoding utf8
Get-ChildItem -LiteralPath $geoDestination | Select-Object Name,Length
