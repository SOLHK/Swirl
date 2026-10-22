param(
    [Parameter(Mandatory=$true)][string]$Destination,
    [string]$Archive
)
$ErrorActionPreference = 'Stop'
$coreVersion = 'v1.19.32'
$coreArchiveName = "mihomo-windows-amd64-v1-$coreVersion.zip"
$coreExpectedHash = '00549b347d8e124600e46cac67d59293358454f465e9d86d2511567da56b7029'
$coreSourceUrl = "https://github.com/MetaCubeX/mihomo/releases/download/$coreVersion/$coreArchiveName"
$coreDestination = [IO.Path]::GetFullPath($Destination)
$coreDownloadedHere = $false
& (Join-Path $PSScriptRoot 'prepare-geodata.ps1') -Destination (Join-Path $coreDestination 'geodata')
New-Item -ItemType Directory -Path $coreDestination -Force | Out-Null
if (-not $Archive) {
    $Archive = Join-Path $coreDestination $coreArchiveName
    $coreDownloadedHere = $true
    Invoke-WebRequest $coreSourceUrl -OutFile $Archive -TimeoutSec 180
}
if ((Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash -ne $coreExpectedHash) { throw 'Mihomo archive checksum mismatch' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$coreZip = [IO.Compression.ZipFile]::OpenRead([IO.Path]::GetFullPath($Archive))
try {
    $coreEntries = @($coreZip.Entries | Where-Object { $_.Name -match '^mihomo.*\.exe$' })
    if ($coreEntries.Count -ne 1) { throw 'Expected one Mihomo executable in official archive' }
    [IO.Compression.ZipFileExtensions]::ExtractToFile($coreEntries[0], (Join-Path $coreDestination 'mihomo.exe'), $true)
} finally { $coreZip.Dispose() }
if ($coreDownloadedHere) { Remove-Item -LiteralPath $Archive }
Invoke-WebRequest "https://raw.githubusercontent.com/MetaCubeX/mihomo/$coreVersion/LICENSE" -OutFile (Join-Path $coreDestination 'LICENSE-Mihomo.txt') -TimeoutSec 30
$wintunArchive = Join-Path $coreDestination 'wintun-0.14.1.zip'
Invoke-WebRequest 'https://www.wintun.net/builds/wintun-0.14.1.zip' -OutFile $wintunArchive -TimeoutSec 60
if ((Get-FileHash -LiteralPath $wintunArchive -Algorithm SHA256).Hash -ne '07c256185d6ee3652e09fa55c0b673e2624b565e02c4b9091c79ca7d2f24ef51') { throw 'Wintun archive checksum mismatch' }
$wintunZip = [IO.Compression.ZipFile]::OpenRead($wintunArchive)
try {
    $wintunEntry = $wintunZip.GetEntry('wintun/bin/amd64/wintun.dll')
    $wintunLicense = $wintunZip.GetEntry('wintun/LICENSE.txt')
    if ($null -eq $wintunEntry -or $null -eq $wintunLicense) { throw 'Expected Wintun x64 DLL or license missing' }
    [IO.Compression.ZipFileExtensions]::ExtractToFile($wintunEntry, (Join-Path $coreDestination 'wintun.dll'), $true)
    [IO.Compression.ZipFileExtensions]::ExtractToFile($wintunLicense, (Join-Path $coreDestination 'LICENSE-Wintun.txt'), $true)
} finally { $wintunZip.Dispose() }
Remove-Item -LiteralPath $wintunArchive
$jqUrl = 'https://github.com/jqlang/jq/releases/download/jq-1.8.1/jq-win64.exe'
$jqFile = Join-Path $coreDestination 'jq.exe'
Invoke-WebRequest $jqUrl -OutFile $jqFile -TimeoutSec 60
if ((Get-FileHash -LiteralPath $jqFile -Algorithm SHA256).Hash -ne '23cb60a1354eed6bcc8d9b9735e8c7b388cd1fdcb75726b93bc299ef22dd9334') { throw 'jq checksum mismatch' }
Invoke-WebRequest 'https://raw.githubusercontent.com/jqlang/jq/jq-1.8.1/COPYING' -OutFile (Join-Path $coreDestination 'LICENSE-jq.txt') -TimeoutSec 30
@"
Mihomo $coreVersion, distributed as a separate unmodified executable.
Source: https://github.com/MetaCubeX/mihomo/tree/$coreVersion
Release: $coreSourceUrl
Official archive SHA256: $coreExpectedHash
License: GNU General Public License version 3; see LICENSE-Mihomo.txt.
Swirl launches the core as a separate process and talks to its loopback API.
Loon is a separate product; Swirl is not affiliated with Loon or MetaCubeX.
Third-party Loon plugins are not bundled or publicly redistributed.
Wintun 0.14.1 x64 from https://www.wintun.net/ ; see LICENSE-Wintun.txt.
jq 1.8.1 unmodified Windows x64 binary: $jqUrl ; see LICENSE-jq.txt.
jq source: https://github.com/jqlang/jq/tree/jq-1.8.1
"@ | Set-Content -LiteralPath (Join-Path $coreDestination 'NOTICE.txt') -Encoding utf8
Get-Item -LiteralPath (Join-Path $coreDestination 'mihomo.exe') | Select-Object Name,Length
