param(
    [Parameter(Mandatory)][string]$QtDir,
    [string]$BuildDir='D:\Codex\build\current-portable',
    [string]$DistDir='D:\Codex\outputs\current-portable\app',
    [string]$OutDir='D:\Codex\outputs\current-portable',
    [ValidateRange(1,64)][int]$Parallel=4
)
$ErrorActionPreference='Stop'
# One verified production build/staging implementation; no obsolete branch
# restriction, engine archive parameter, or reuse of a test-enabled product.
& (Join-Path $PSScriptRoot 'build-quick-windows.ps1') -QtDir $QtDir `
    -BuildDir $BuildDir -DistDir $DistDir -OutDir $OutDir -Parallel $Parallel `
    -InputTests -PortableOnly
