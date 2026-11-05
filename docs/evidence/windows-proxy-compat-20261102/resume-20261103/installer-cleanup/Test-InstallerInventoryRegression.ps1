param(
    [Parameter(Mandatory=$true)][string]$RepositoryRoot,
    [string]$OutputDirectory=$PSScriptRoot
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$repo=(Resolve-Path -LiteralPath $RepositoryRoot).Path
$source=Join-Path $repo 'scripts/tests/Test-WindowsProductionInstaller.ps1'
$priorCommit='ae083d7f0dc73c5d34802d872d124a34fb4e465d'
$priorObject=$priorCommit + ':scripts/tests/Test-WindowsProductionInstaller.ps1'
$priorSource=(& git -C $repo show $priorObject) -join "`n"
if ($LASTEXITCODE -ne 0) { throw 'Cannot read the fixed pre-fix validator.' }
$priorBlob=(& git -C $repo rev-parse $priorObject).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify the pre-fix validator blob.' }
$tokens=$null;$errors=$null
$priorAst=[Management.Automation.Language.Parser]::ParseInput($priorSource,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Pre-fix source AST failed.' }
$currentAst=[Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Current source AST failed.' }
. (Join-Path $repo 'scripts/RustProductPackagePolicy.ps1')
foreach ($name in @('Assert-FixturePath','Assert-InstalledPayload')) {
    $definition=$currentAst.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
    . ([scriptblock]::Create($definition.Extent.Text))
}
$previous=$priorAst.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Assert-InstalledPayload'},$true)
. ([scriptblock]::Create($previous.Extent.Text.Replace('function Assert-InstalledPayload','function Assert-InstalledPayloadBefore')))
$base=Join-Path ([IO.Path]::GetTempPath()) ('swirl-inventory-regression-'+[guid]::NewGuid().ToString('N'))
$package=Join-Path $base 'package';$target=Join-Path $base 'install';$root=$target
New-Item -ItemType Directory -Path $package,(Join-Path $target 'qml/Owned') -Force | Out-Null
$vendor=Join-Path $target 'Swirl.exe'
[IO.File]::WriteAllText($vendor,'controlled runtime fixture')
[IO.File]::WriteAllText((Join-Path $target 'qml/Owned/qmldir'),'controlled QML fixture')
$manifest=[pscustomobject]@{files=@('Swirl.exe','qml/Owned/qmldir') | ForEach-Object {
    [pscustomobject]@{path=$_;sha256=(Get-FileHash -LiteralPath (Join-Path $target $_)).Hash.ToLowerInvariant()}
}}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $package 'package-manifest.json') -Encoding utf8
Copy-Item -LiteralPath (Join-Path $package 'package-manifest.json') -Destination $target
foreach ($name in @('.swirl-install-owned','.swirl-isolated-install','卸载 Swirl.exe')) {
    [IO.File]::WriteAllText((Join-Path $target $name),'controlled ownership fixture')
}
$checks=New-Object 'System.Collections.Generic.List[object]'
function Record([string]$Name) { $checks.Add([ordered]@{name=$Name;passed=$true}) }
function Must-Reject([string]$Name) {
    $rejected=$false
    try { Assert-InstalledPayload } catch { $rejected=$true }
    if (-not $rejected) { throw "Validator accepted invalid payload: $Name" }
    Record $Name
}
try {
    Assert-InstalledPayload;Record 'exact-manifest-files-and-ancestor-directories'
    New-Item -ItemType Directory -Path (Join-Path $target 'qml/QtQuick/VectorImage/Helpers') -Force | Out-Null
    Assert-InstalledPayloadBefore;Record 'negative-control-old-validator-misses-real-empty-directory-shape'
    Must-Reject 'current-validator-rejects-unowned-empty-directory-tree'
    Remove-Item -LiteralPath (Join-Path $target 'qml/QtQuick') -Recurse
    Assert-InstalledPayload;Record 'normalized-fixture-retains-valid-owned-qml-tree'
    $empty=Join-Path $target 'empty-root-child';New-Item -ItemType Directory -Path $empty | Out-Null
    Must-Reject 'unowned-root-empty-directory';Remove-Item -LiteralPath $empty
    [IO.File]::WriteAllText($vendor,'tampered');Must-Reject 'tampered-runtime'
    [IO.File]::WriteAllText($vendor,'controlled runtime fixture')
    $extra=Join-Path $target 'unexpected.dll';[IO.File]::WriteAllText($extra,'unexpected')
    Must-Reject 'unlisted-runtime';Remove-Item -LiteralPath $extra
    Remove-Item -LiteralPath $vendor;Must-Reject 'missing-runtime'
    [IO.File]::WriteAllText($vendor,'controlled runtime fixture')
    $marker=Join-Path $target '.swirl-isolated-install'
    Remove-Item -LiteralPath $marker -Force;Must-Reject 'missing-isolation-marker'
    [IO.File]::WriteAllText($marker,'controlled ownership fixture')
    [IO.File]::WriteAllText((Join-Path $target 'package-manifest.json'),'different')
    Must-Reject 'mismatching-installed-manifest'
    Copy-Item -LiteralPath (Join-Path $package 'package-manifest.json') -Destination $target -Force
    Remove-Item -LiteralPath $vendor
    New-Item -ItemType SymbolicLink -Path $vendor -Target (Join-Path $package 'package-manifest.json') | Out-Null
    Must-Reject 'linked-installed-entry'
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $report=[ordered]@{
        schema=1; scope='Exact validator functions with controlled files; no Windows installer is executed.'
        previous_commit=$priorCommit; previous_script_git_blob=$priorBlob
        current_script_sha256=(Get-FileHash -LiteralPath $source).Hash.ToLowerInvariant()
        checks=$checks.ToArray();success=$true
    }
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'inventory-regression.json') -Encoding utf8
    Write-Host "Installer inventory regression: $($checks.Count) checks passed, including the fixed historical negative control."
} finally {
    if (Test-Path -LiteralPath $base) { Remove-Item -LiteralPath $base -Recurse -Force }
}
