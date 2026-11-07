param(
    [Parameter(Mandatory)][string]$QtRoot,
    [Parameter(Mandatory)][string]$ApplicationDirectory,
    [string]$QtSdkReceipt,
    [string]$EvidenceDirectory,
    [string]$Python
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'RustProductPackagePolicy.ps1')
$kit = (Resolve-Path -LiteralPath $QtRoot).Path
$app = (Resolve-Path -LiteralPath $ApplicationDirectory).Path
Assert-SwirlPathWithoutLinks $kit
Assert-SwirlPathWithoutLinks $app
if ($PSBoundParameters.ContainsKey('QtSdkReceipt')) {
    # This branch delegates the one copy and its compatibility receipt to the
    # source-bound verifier. An explicitly empty receipt must not use fallback.
    foreach ($path in @($QtSdkReceipt,$EvidenceDirectory,$Python)) {
        if ([string]::IsNullOrWhiteSpace($path) -or $path.IndexOf([char]0) -ge 0 -or
            $path -cnotmatch '^(?:[A-Za-z]:[\\/]|[\\/]{2}[^\\/]+[\\/][^\\/]+(?:[\\/]|$))') {
            throw 'Selected Qt shader deployment requires explicit absolute receipt, evidence and Python paths.'
        }
        Assert-SwirlPathWithoutLinks $path
    }
    foreach ($path in @($QtRoot,$ApplicationDirectory)) { Assert-SwirlPathWithoutLinks $path }
    $receiptPath = [IO.Path]::GetFullPath($QtSdkReceipt)
    $evidencePath = [IO.Path]::GetFullPath($EvidenceDirectory)
    $pythonPath = [IO.Path]::GetFullPath($Python)
    $verifier = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../tools/Compose-Qt612ProductSdk.py'))
    foreach ($path in @($receiptPath,$pythonPath,$verifier)) {
        Assert-SwirlPathWithoutLinks $path
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw 'Selected Qt shader deployment input is missing.'
        }
    }
    if ((Get-Item -LiteralPath $receiptPath).Length -gt 16777216 -or
        -not (Test-Path -LiteralPath $kit -PathType Container) -or
        -not (Test-Path -LiteralPath $app -PathType Container)) {
        throw 'Selected Qt shader deployment input has an invalid type or size.'
    }
    $selected = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($selected.kit_root -isnot [string] -or [string]::IsNullOrWhiteSpace($selected.kit_root) -or
        $selected.kit_root -cnotmatch '^(?:[A-Za-z]:[\\/]|[\\/]{2}[^\\/]+[\\/][^\\/]+(?:[\\/]|$))') {
        throw 'Selected Qt receipt has no absolute kit identity.'
    }
    $receiptKit = [IO.Path]::GetFullPath($selected.kit_root)
    Assert-SwirlPathWithoutLinks $receiptKit
    if (-not $kit.TrimEnd('\','/').Equals($receiptKit.TrimEnd('\','/'),[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Qt shader deployment kit differs from the selected receipt.'
    }
    & $pythonPath $verifier copy-d3d --receipt $receiptPath --runtime-dir $app --evidence $evidencePath
    if ($LASTEXITCODE -ne 0) { throw 'Selected Qt shader deployment verification failed.' }
    return
}
if ($PSBoundParameters.ContainsKey('EvidenceDirectory') -or $PSBoundParameters.ContainsKey('Python')) {
    throw 'Selected Qt shader deployment parameters require an explicit receipt.'
}
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
