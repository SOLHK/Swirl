$ErrorActionPreference='Stop'
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$copyScript=Join-Path $repo 'scripts/Copy-VerifiedChinaRules.ps1'
$rules=Join-Path $repo 'src/Swirl.Quick/packaging/rules'
$tempBase=if($env:GITHUB_ACTIONS -eq 'true' -and $env:RUNNER_TEMP) {
    $env:RUNNER_TEMP
} else {
    'D:\Codex\tmp'
}
if(-not (Test-Path -LiteralPath $tempBase -PathType Container)) {
    throw "Required test directory missing: $tempBase"
}
$testRoot=Join-Path $tempBase ('swirl-rule-package-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot -ErrorAction Stop | Out-Null

function Assert-Fails([scriptblock]$action, [string]$message) {
    try {
        & $action
    } catch {
        if($_.Exception.Message -notlike "*$message*") { throw }
        return
    }
    throw "Expected failure did not occur: $message"
}

try {
    $stage=Join-Path $testRoot 'stage'
    $elsewhere=Join-Path $testRoot 'elsewhere'
    New-Item -ItemType Directory -Path $stage,$elsewhere -ErrorAction Stop | Out-Null
    Push-Location -LiteralPath $elsewhere
    try {
        & $copyScript -SourceDirectory $rules -ApplicationDirectory $stage
    } finally {
        Pop-Location
    }
    foreach($name in @('cn-domain.mrs','cn-ip.mrs')) {
        $source=Join-Path $rules $name
        $packaged=Join-Path (Join-Path $stage 'rules') $name
        if(-not (Test-Path -LiteralPath $packaged -PathType Leaf) -or
           (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne
           (Get-FileHash -LiteralPath $packaged -Algorithm SHA256).Hash) {
            throw "Rule not copied beside application: $name"
        }
    }

    foreach($name in @('cn-domain.mrs','cn-ip.mrs')) {
        $missing=Join-Path $testRoot ("missing-$name")
        $missingStage=Join-Path $testRoot ("missing-stage-$name")
        Copy-Item -LiteralPath $rules -Destination $missing -Recurse -ErrorAction Stop
        New-Item -ItemType Directory -Path $missingStage -ErrorAction Stop | Out-Null
        Remove-Item -LiteralPath (Join-Path $missing $name) -ErrorAction Stop
        Assert-Fails { & $copyScript -SourceDirectory $missing -ApplicationDirectory $missingStage } "Required China rule missing: $name"
        if(Test-Path -LiteralPath (Join-Path $missingStage 'rules')) { throw 'Missing source produced a partial package' }

        $corrupt=Join-Path $testRoot ("corrupt-$name")
        $corruptStage=Join-Path $testRoot ("corrupt-stage-$name")
        Copy-Item -LiteralPath $rules -Destination $corrupt -Recurse -ErrorAction Stop
        New-Item -ItemType Directory -Path $corruptStage -ErrorAction Stop | Out-Null
        [IO.File]::AppendAllText((Join-Path $corrupt $name),'changed')
        Assert-Fails { & $copyScript -SourceDirectory $corrupt -ApplicationDirectory $corruptStage } "China rule checksum mismatch: $name"
        if(Test-Path -LiteralPath (Join-Path $corruptStage 'rules')) { throw 'Corrupt source produced a partial package' }
    }
    Write-Output 'Windows Rust rule package copy: PASS (different working directory, both assets, missing and corrupt files rejected)'
} finally {
    $full=[IO.Path]::GetFullPath($testRoot)
    $prefix=[IO.Path]::GetFullPath($tempBase).TrimEnd('\')+'\swirl-rule-package-test-'
    if(-not $full.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove unexpected test path: $full"
    }
    Remove-Item -LiteralPath $full -Recurse -Force -ErrorAction Stop
}
