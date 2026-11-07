#Requires -Version 7.4
param(
    [Parameter(Mandatory)][string]$OfficialReceipt,
    [Parameter(Mandatory)][string]$EvidenceDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $IsWindows -or $env:GITHUB_ACTIONS -cne 'true' -or
    $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or $env:GITHUB_REPOSITORY -cne 'SOLHK/Swirl') {
    throw 'Qt product SDK selection requires this repository hosted Windows build.'
}
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'Assert-BuildSource.ps1')
. (Join-Path $PSScriptRoot 'RustProductPackagePolicy.ps1')
Assert-SwirlBuildSource -RepositoryRoot $repo -ExpectedSourceSha $env:GITHUB_SHA
$officialPath = (Resolve-Path -LiteralPath $OfficialReceipt).Path
Assert-SwirlPathWithoutLinks $officialPath
$official = Get-Content -LiteralPath $officialPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($official.version -cne '6.12.0' -or $official.qmake_version -cne '6.12.0' -or
    $official.arch -cne 'win64_msvc2022_64') { throw 'The original official Qt SDK receipt is invalid.' }
$stock = (Resolve-Path -LiteralPath $official.kit_root).Path
$selected = Join-Path $env:RUNNER_TEMP 'swirl-qt-6.12.0-product'
$evidence = [IO.Path]::GetFullPath($EvidenceDirectory)
foreach ($path in @($stock,$selected,$evidence)) { Assert-SwirlPathWithoutLinks $path }
if (Test-Path -LiteralPath $selected) { throw 'Qt product SDK composition requires a fresh selected kit.' }
if (Test-Path -LiteralPath $evidence) { throw 'Existing Qt product SDK evidence will not be replaced.' }
if ([string]::IsNullOrWhiteSpace($env:pythonLocation) -or -not [IO.Path]::IsPathFullyQualified($env:pythonLocation)) {
    throw 'The prepared Python installation location is unavailable.'
}
$python = Join-Path $env:pythonLocation 'python.exe'
Assert-SwirlPathWithoutLinks $python
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'The prepared Python executable is unavailable.' }
& $python (Join-Path $repo 'tools/Compose-Qt612ProductSdk.py') compose `
    --stock-kit $stock --selected-kit $selected --evidence $evidence
if ($LASTEXITCODE -ne 0) { throw 'The pinned complete Qt product SDK could not be composed.' }
$receiptPath = Join-Path $evidence 'selected-sdk.json'
$receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($receipt.schema -ne 1 -or $receipt.kind -cne 'swirl-selected-qt612-product-sdk' -or
    $receipt.success -ne $true -or $receipt.consumer.source_sha -cne $env:GITHUB_SHA -or
    $receipt.qt_version -cne '6.12.0' -or $receipt.stock_unchanged -ne $true -or
    $receipt.kit_root -cne $selected -or $receipt.stock_kit_root -cne $stock -or
    $receipt.selected_content_id -cnotmatch '^[0-9a-f]{64}$') {
    throw 'The selected Qt SDK receipt does not describe this exact composition.'
}
$hook = Join-Path $evidence 'selected-qt.cmake'
if ($receipt.cmake_capture_hook.path -cne $hook -or
    (Get-FileHash -LiteralPath $hook -Algorithm SHA256).Hash.ToLowerInvariant() -cne $receipt.cmake_capture_hook.sha256) {
    throw 'The selected Qt CMake capture hook changed.'
}
# Keep the original official receipt and kit intact. Downstream configure and
# deployment use the complete derived kit, and verify its actual target/file
# identities again; the PATH entry is not the SDK identity proof.
$values = [ordered]@{
    QT_ROOT_DIR=$selected
    CMAKE_PREFIX_PATH=$selected
    SWIRL_QT_STOCK_ROOT=$stock
    SWIRL_QT_SELECTED_RECEIPT=$receiptPath
    SWIRL_QT_SELECTED_CMAKE=$hook
    SWIRL_QT_SELECTED_CONTENT_ID=$receipt.selected_content_id
}
foreach ($entry in $values.GetEnumerator()) {
    if ([string]$entry.Value -match '[\r\n]') { throw 'Invalid selected Qt environment value.' }
    [Environment]::SetEnvironmentVariable($entry.Key,[string]$entry.Value,'Process')
    ($entry.Key+'='+[string]$entry.Value) >> $env:GITHUB_ENV
}
(Join-Path $selected 'bin') >> $env:GITHUB_PATH
Write-Host ('Selected complete Qt 6.12 SDK content '+$receipt.selected_content_id)
