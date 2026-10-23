param(
    [Parameter(Mandatory=$true)][string]$Executable,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [double[]]$Scales = @(1, 1.25, 1.5, 1.75, 2)
)
$ErrorActionPreference = 'Stop'
$Executable = (Resolve-Path -LiteralPath $Executable).Path
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$OutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$names = @('QT_SCALE_FACTOR','QT_SCREEN_SCALE_FACTORS','QT_QUICK_BACKEND','QSG_RHI_BACKEND','SWIRL_LIQUID_GLASS_CHECKS','SWIRL_GLASS_ALL_PAGES')
$saved = @{}
foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name,'Process') }
$results = @()
try {
    $env:QT_SCALE_FACTOR='1'
    $env:QT_QUICK_BACKEND=$null
    $env:QSG_RHI_BACKEND='d3d11'
    $env:SWIRL_LIQUID_GLASS_CHECKS='1'
    foreach ($scale in $Scales) {
        $env:QT_SCREEN_SCALE_FACTORS=$scale.ToString([Globalization.CultureInfo]::InvariantCulture)
        $env:SWIRL_GLASS_ALL_PAGES=if ($scale -eq 1.5) {'1'} else {$null}
        $target=Join-Path $OutputDirectory ('dpi-'+[int]($scale*100))
        $process=Start-Process -FilePath $Executable -ArgumentList @('--motion-test',('--motion-output="'+$target+'"')) -WindowStyle Hidden -PassThru -Wait
        $report=Get-Content -LiteralPath (Join-Path $target 'report.json') -Raw | ConvertFrom-Json
        $passed=$process.ExitCode -eq 0 -and $report.failures -eq 0 -and [Math]::Abs($report.dpr-$scale) -lt 0.01
        $results += [PSCustomObject]@{scale=$scale;dpr=$report.dpr;exitCode=$process.ExitCode;checks=$report.checks.Count;captures=$report.captures.Count;passed=$passed}
        Write-Output $results[-1]
    }
    $results | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'dpi-summary.json') -Encoding utf8
    if ($results.passed -contains $false) { throw 'Liquid Glass checks failed. Inspect each report.json and screenshots.' }
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name,$saved[$name],'Process') }
}
