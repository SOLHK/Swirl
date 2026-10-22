param(
    [Parameter(Mandatory=$true)][string]$QtDir,
    [string]$Nsis='D:\Codex\toolchains\nsis-3.11\makensis.exe',
    [string]$BuildDir='D:\Codex\build\rust-product',
    [string]$OutRoot='D:\Codex\outputs',
    [ValidateRange(1,64)][int]$Parallel=4
)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$dirty=& git -C $repo status --porcelain
if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Commit source changes before packaging an exact SHA.' }
$sha=(& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sha -notmatch '^[0-9a-f]{40}$') { throw 'Source SHA unavailable.' }
$out=Join-Path $OutRoot ('Swirl-Rust-'+$sha.Substring(0,12)+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
& (Join-Path $PSScriptRoot 'build-quick-windows.ps1') -QtDir $QtDir `
    -BuildDir $BuildDir -DistDir (Join-Path $out 'app') -OutDir $out -Nsis $Nsis -Parallel $Parallel
