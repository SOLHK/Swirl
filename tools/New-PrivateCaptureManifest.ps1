param(
    [Parameter(Mandatory=$true)][string]$PrivateDirectory
)
$ErrorActionPreference = 'Stop'
$captureDirectory = [System.IO.Path]::GetFullPath($PrivateDirectory)
$captureManifest = Join-Path $captureDirectory 'subscriptions.private'
if (Test-Path -LiteralPath $captureManifest) { throw 'Manifest already exists; it was not changed.' }
$captureAncestor = $captureDirectory
while ($captureAncestor) {
    if (Test-Path -LiteralPath (Join-Path $captureAncestor '.git')) { throw 'Private data must be outside Git checkouts.' }
    $captureAncestor = Split-Path -Parent $captureAncestor
}
New-Item -ItemType Directory -Path $captureDirectory -Force | Out-Null
$captureSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $captureDirectory '/inheritance:r' '/grant:r' "*${captureSid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Private directory ACL setup failed.' }
$captureClients = @('Clash-Mihomo','sing-box','Hiddify','v2rayN','v2rayNG','V2Ray-Xray','NekoBox-NekoRay','Surge','Shadowrocket','Quantumult-X','Loon','Stash','Surfboard','Egern','Karing','Streisand','V2Box','Other','Related-resource')
$captureEntries = @()
for ($captureIndex=0; $captureIndex -lt $captureClients.Count; $captureIndex++) {
    $captureEntries += [ordered]@{
        id=('e{0:d2}' -f ($captureIndex+1)); client=$captureClients[$captureIndex]; version='unknown'
        kind=$(if ($captureClients[$captureIndex] -eq 'Related-resource') {'resource'} else {'root'})
        group='g1'; url=''; headers=@{}; exportOf=''; protocols=@(); transports=@()
    }
}
$captureTemplate = [ordered]@{
    schema=1; concurrency=4; localFixtures=$false; proxy=@{mode='direct'}
    groups=@{g1=@{windowSeconds=600}}
    authorization=@{download=$true; offlineAnalysis=$true; nodeConnections=$false; throughputTests=$false; systemProxyChange=$false; tun=$false}
    entries=$captureEntries
}
$captureTemplate | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $captureManifest -Encoding utf8
[ordered]@{confirmed=$false; groups=@{g1=@{openedAt=''}}} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $captureDirectory 'opening.json') -Encoding utf8
Write-Output "Private manifest created: $captureManifest"
Write-Output 'Fill links locally; leave unavailable exports blank. Keep website update switches OFF.'
