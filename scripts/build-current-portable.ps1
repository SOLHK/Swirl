param(
    [Parameter(Mandatory)][string]$QtDir,
    [string]$BuildDir='build/current-portable',
    [string]$DistDir='dist/current-portable',
    [string]$OutDir='out/current-portable',
    [int]$Parallel=6,
    [string]$MihomoArchive
)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
$previousPath=$env:PATH
$previousPlatform=$env:QT_QPA_PLATFORM
$previousHelpMode=$env:QT_COMMAND_LINE_PARSER_NO_GUI_MESSAGE_BOXES
Push-Location $repo
try {
    if((git branch --show-current) -ne 'test'){throw 'Build the integrated source from test.'}
    if(git status --porcelain){throw 'Commit or preserve source changes before packaging.'}
    if((git rev-parse 0ae36d6) -eq ''){throw 'The current UI baseline is missing.'}
    git merge-base --is-ancestor 0ae36d6 HEAD
    if($LASTEXITCODE){throw 'Current source must preserve the 0ae36d6 UI baseline.'}
    $qt=(Resolve-Path -LiteralPath $QtDir).Path
    $env:PATH="$qt/bin;$env:PATH"
    $env:QT_QPA_PLATFORM='offscreen'
    $env:QT_COMMAND_LINE_PARSER_NO_GUI_MESSAGE_BOXES='1'
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    cmake -S src/Swirl.Quick -B $BuildDir -G Ninja -DCMAKE_BUILD_TYPE=Release "-DCMAKE_PREFIX_PATH=$qt" -DSWIRL_BUILD_UI_TESTS=ON
    if($LASTEXITCODE){throw 'Configure failed.'}
    cmake --build $BuildDir --parallel $Parallel
    if($LASTEXITCODE){throw 'Build failed.'}
    # Only in-memory accounting/diagnostic-file tests. The user performs all
    # real node, proxy, Codex, graphical and visual acceptance testing.
    & (Join-Path $BuildDir 'SwirlTelemetryTests.exe') closedSnapshotsAreNotActiveAndControlFailureIsNotClosure internetFailureClassificationAndRouteChanges continuingMeasurementFailureIsOneIncident dailyBucketsPreserveGapsAndProxyFilter processAndDeviceRates accounting resetsAndNewProcess idleAndUncollected timestampedHistory ranges -o "$(Join-Path $OutDir 'telemetry-memory.txt'),txt"
    if($LASTEXITCODE){throw 'Telemetry accounting checks failed.'}
    & (Join-Path $BuildDir 'SwirlDiagnosticTests.exe') -o "$(Join-Path $OutDir 'diagnostic-files.txt'),txt"
    if($LASTEXITCODE){throw 'Diagnostic file checks failed.'}
    cmake -S src/Swirl.Quick -B $BuildDir -DSWIRL_BUILD_UI_TESTS=OFF
    if($LASTEXITCODE){throw 'Production configure failed.'}
    cmake --build $BuildDir --parallel $Parallel
    if($LASTEXITCODE){throw 'Production build failed.'}
    if(Test-Path -LiteralPath (Join-Path $DistDir 'Swirl.exe')){throw 'Use a fresh distribution directory.'}
    New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
    foreach($name in 'Swirl.exe','SwirlProxyGuard.exe','SwirlGatewayGuard.exe','SwirlScriptRunner.exe'){
        Copy-Item -LiteralPath (Join-Path $BuildDir $name) -Destination $DistDir
    }
    & (Join-Path $PSScriptRoot 'stage-mihomo.ps1') -Destination $DistDir -Archive $MihomoArchive
    Copy-Item -LiteralPath 'src/Swirl.Quick/packaging/rules' -Destination (Join-Path $DistDir 'rules') -Recurse
    Copy-Item -LiteralPath (Join-Path $BuildDir 'brand/Swirl.ico') -Destination (Join-Path $DistDir 'Swirl-brand-phase3-v2.ico')
    & "$qt/bin/windeployqt.exe" --release --qmldir src/Swirl.Quick/qml (Join-Path $DistDir 'Swirl.exe')
    if($LASTEXITCODE){throw 'Qt runtime deployment failed.'}
    Copy-Item -LiteralPath 'src/Swirl.Quick/packaging/THIRD_PARTY_NOTICES.txt' -Destination $DistDir
    Copy-Item -LiteralPath 'src/Swirl.Quick/packaging/licenses' -Destination (Join-Path $DistDir 'licenses') -Recurse
    New-Item -ItemType Directory -Force -Path (Join-Path $DistDir 'docs') | Out-Null
    foreach($name in 'LOCAL_EXTENSIONS.md','FONTS.md','CURRENT_SOURCE_INTEGRATION.md','FONT_AND_MOTION_REPAIR.md','NETWORK_RELIABILITY_CURRENT.md','manual-acceptance.html'){
        Copy-Item -LiteralPath (Join-Path 'docs' $name) -Destination (Join-Path $DistDir 'docs')
    }
    $commit=git rev-parse HEAD
    @('Repository: SOLHK/Swirl',"SourceDirectory: $repo",'UI baseline: 0ae36d6',"Commit: $commit",'Branch: test',"UncommittedChanges: $([bool](git status --porcelain))",'Qt: 6.10.3 / C++23 / Windows x64 Release','UI test drivers: OFF','Human acceptance: NOT TESTED') | Set-Content -LiteralPath (Join-Path $DistDir 'BUILD.txt') -Encoding utf8
    Copy-Item -LiteralPath 'docs/manual-acceptance.html' -Destination (Join-Path $OutDir 'Swirl-人工验收.html')
    Compress-Archive -LiteralPath (Resolve-Path $DistDir).Path -DestinationPath (Join-Path $OutDir 'Swirl-current-win-x64.zip')
    Get-FileHash -LiteralPath (Join-Path $OutDir 'Swirl-current-win-x64.zip') -Algorithm SHA256 | Format-List
} finally {
    $env:PATH=$previousPath
    $env:QT_QPA_PLATFORM=$previousPlatform
    $env:QT_COMMAND_LINE_PARSER_NO_GUI_MESSAGE_BOXES=$previousHelpMode
    Pop-Location
}
