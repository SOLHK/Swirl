param(
    [Parameter(Mandatory)][string]$QtRoot,
    [Parameter(Mandatory)][string]$ApplicationDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'RustProductPackagePolicy.ps1')
$kit = (Resolve-Path -LiteralPath $QtRoot).Path
$app = (Resolve-Path -LiteralPath $ApplicationDirectory).Path
Assert-SwirlPathWithoutLinks $kit
Assert-SwirlPathWithoutLinks $app
$files = [ordered]@{}
foreach ($name in @('d3dcompiler_47.dll','dxcompiler.dll','dxil.dll')) {
    $source = Join-Path $kit ('bin/' + $name)
    if (!(Test-Path -LiteralPath $source -PathType Leaf)) {
        if ($name -eq 'd3dcompiler_47.dll') { throw 'The selected Qt SDK lacks its D3D compiler runtime.' }
        continue
    }
    $target = Join-Path $app $name
    Assert-SwirlPathWithoutLinks $source
    Assert-SwirlPathWithoutLinks $target
    $before = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    Copy-Item -LiteralPath $source -Destination $target -Force
    $after = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    $deployed = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($before -cne $after -or $before -cne $deployed) { throw 'Deployed shader runtime differs from the selected Qt SDK.' }
    $files[$name] = [ordered]@{sha256=$deployed;bytes=(Get-Item -LiteralPath $target).Length}
}
[ordered]@{schema=1;source='selected-qt-sdk';files=$files} | ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath (Join-Path $app 'qt-shader-runtime.json') -Encoding utf8
