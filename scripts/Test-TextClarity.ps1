param(
    [Parameter(Mandatory=$true)][string]$Executable,
    [string]$OutputDirectory='text-clarity-evidence'
)
$ErrorActionPreference='Stop'
$exe=(Resolve-Path -LiteralPath $Executable).Path
$dest=[IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$previousFactor=$env:QT_SCALE_FACTOR
try {
    # Measure Qt's actual native DPR; QT_SCALE_FACTOR is a multiplier of it.
    Remove-Item Env:QT_SCALE_FACTOR -ErrorAction SilentlyContinue
    $native=Join-Path $dest 'native-probe'
    $p=Start-Process -FilePath $exe -ArgumentList @('--ui-quality-test',"--ui-quality-output=$native") -WindowStyle Hidden -Wait -PassThru
    if($p.ExitCode -ne 0){throw "Native DPR probe failed: $($p.ExitCode)"}
    $baseDpr=(Get-Content -LiteralPath (Join-Path $native 'quality-report.json') -Raw | ConvertFrom-Json).dpr
    if($baseDpr -le 0){throw 'Qt did not report a valid DPR'}
    foreach($target in @(1.0,1.25,1.5,2.0)) {
        $env:QT_SCALE_FACTOR=($target/$baseDpr).ToString('R',[cultureinfo]::InvariantCulture)
        $folder=Join-Path $dest ([string][int]($target*100))
        $p=Start-Process -FilePath $exe -ArgumentList @('--ui-quality-test',"--ui-quality-output=$folder") -WindowStyle Hidden -Wait -PassThru
        if($p.ExitCode -ne 0){throw "DPR $target checks failed: $($p.ExitCode)"}
        $report=Get-Content -LiteralPath (Join-Path $folder 'quality-report.json') -Raw | ConvertFrom-Json
        if($report.failures -ne 0 -or [math]::Abs($report.dpr-$target) -gt 0.01){throw "Actual Qt DPR differs from $target or checks failed"}
        Write-Output "DPR $($report.dpr): $($report.checks.Count) checks passed"
    }
} finally {
    if($null -eq $previousFactor){Remove-Item Env:QT_SCALE_FACTOR -ErrorAction SilentlyContinue}
    else {$env:QT_SCALE_FACTOR=$previousFactor}
}
