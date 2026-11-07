param([Parameter(Mandatory=$true)][string]$EvidenceDirectory)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($env:OS -ne 'Windows_NT' -or $env:GITHUB_ACTIONS -ne 'true' -or
   $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or -not [Environment]::Is64BitProcess -or
   $PSVersionTable.PSVersion.Major -ne 7) {
    throw 'Native cleanup controls require an isolated hosted Windows runner and PowerShell 7 x64.'
}
$source=Join-Path $PSScriptRoot 'OwnedWindowsProfileCleanup.ps1'
. $source
$evidence=[IO.Path]::GetFullPath($EvidenceDirectory)
if(Test-Path -LiteralPath $evidence){throw 'Refusing to replace existing cleanup-control evidence.'}
$null=[IO.Directory]::CreateDirectory($evidence)
$fixture=Join-Path $env:RUNNER_TEMP ('swirl-cleanup-controls-'+[Guid]::NewGuid().ToString('N'))
$receipt=[ordered]@{schema=1;source_sha=$env:GITHUB_SHA
    helper_sha256=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    controls_script_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    powershell_version=$PSVersionTable.PSVersion.ToString();process_bits=64
    controls=$null;error=$null;success=$false}
try {
    $receipt.controls=[SwirlOwnedProfileCleanup.Native]::RunNativeControls($fixture)
    $receipt.success=$receipt.controls.success -and $receipt.controls.total -eq 12 -and $receipt.controls.passed -eq 12
}catch {$receipt.error=$_.Exception.ToString()}
finally {$receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $evidence 'receipt.json') -Encoding UTF8}
if(-not $receipt.success){throw 'The actual Win32 disposable-profile cleanup controls failed; see receipt.json.'}
Write-Host '12 actual Win32 scoped-cleanup controls passed; this is synthetic filesystem evidence only.'
