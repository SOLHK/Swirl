param(
    [Parameter(Mandatory)][string]$QtDir,
    [string]$BuildDir = "build/swirl-quick",
    [string]$DistDir = "dist/swirl-quick",
    [string]$OutDir = "out",
    [string]$Nsis = "C:/Program Files (x86)/NSIS/makensis.exe",
    [string]$Generator = "Ninja",
    [int]$Parallel = 6,
    [string]$MihomoArchive,
    [switch]$InputTests,
    [switch]$NativeBackdropTests
)
$ErrorActionPreference = "Stop"
if ($NativeBackdropTests -and !$InputTests) { throw "Native backdrop checks require -InputTests and an unlocked Windows desktop." }
$repo = Split-Path $PSScriptRoot -Parent
Push-Location $repo
try {
    $qt = (Resolve-Path -LiteralPath $QtDir).Path
    $env:PATH = "$qt/bin;$env:PATH"
    $testFlag = if ($InputTests) { "ON" } else { "OFF" }
    cmake -S src/Swirl.Quick -B $BuildDir -G $Generator -DCMAKE_BUILD_TYPE=Release "-DCMAKE_PREFIX_PATH=$qt" "-DSWIRL_BUILD_UI_TESTS=$testFlag"
    if ($LASTEXITCODE) { throw "CMake configure failed." }
    cmake --build $BuildDir --config Release --parallel $Parallel
    if ($LASTEXITCODE) { throw "Release build failed." }
    $exe = Join-Path $BuildDir "Swirl.exe"
    if (!(Test-Path $exe)) { $exe = Join-Path $BuildDir "Release/Swirl.exe" }
    $exe = (Resolve-Path $exe).Path
    & (Join-Path $PSScriptRoot 'stage-mihomo.ps1') -Destination (Split-Path $exe) -Archive $MihomoArchive
    if ($InputTests) {
        ctest --test-dir $BuildDir -C Release -R 'swirl-engine-(contract|real)|swirl-native-engine|swirl-subscription-formats|swirl-appearance-ui|swirl-node-real-chain|swirl-import-subscription|swirl-motion|swirl-hero|swirl-font|swirl-local-extensions|swirl-gateway-network|swirl-telemetry-accounting' --output-on-failure
        if ($LASTEXITCODE) { throw "Engine contract, integration or QML checks failed." }
        $test = Start-Process $exe -ArgumentList '--engine-self-test' -WindowStyle Hidden -Wait -PassThru
        if ($test.ExitCode) { throw "Native engine QML checks failed: $($test.ExitCode)." }
        $test = Start-Process $exe -ArgumentList "--node-self-test" -WindowStyle Hidden -Wait -PassThru
        if ($test.ExitCode) { throw "Native node QML checks failed: $($test.ExitCode)." }
        # This input test uses the actual Windows platform plugin and fonts.
        $test = Start-Process $exe -ArgumentList "--interaction-test" -WindowStyle Hidden -Wait -PassThru
        if ($test.ExitCode) { throw "Input checks failed: $($test.ExitCode). See Swirl-diagnostics.txt." }
        $test = Start-Process $exe -ArgumentList "--capture-self-test" -WindowStyle Hidden -Wait -PassThru
        if ($test.ExitCode) { throw "Capture checks failed: $($test.ExitCode)." }
        $test = Start-Process $exe -ArgumentList "--smoke-test" -WindowStyle Hidden -Wait -PassThru
        if ($test.ExitCode) { throw "Module startup checks failed: $($test.ExitCode)." }
        if ($NativeBackdropTests) {
            New-Item -ItemType Directory -Force $OutDir | Out-Null
            $nativeOutput = Join-Path (Resolve-Path $OutDir).Path "window-validation"
            $test = Start-Process $exe -ArgumentList @("--window-test", ('"--window-test-output=' + $nativeOutput + '"')) -WindowStyle Hidden -Wait -PassThru
            if ($test.ExitCode) { throw "Native compositor checks failed: $($test.ExitCode)." }
            Copy-Item (Join-Path (Split-Path $exe) "Swirl-diagnostics.txt") (Join-Path $OutDir "window-validation.log") -Force
        }
        cmake -S src/Swirl.Quick -B $BuildDir -DSWIRL_BUILD_UI_TESTS=OFF
        if ($LASTEXITCODE) { throw "Production reconfigure failed." }
        cmake --build $BuildDir --config Release --parallel $Parallel
        if ($LASTEXITCODE) { throw "Production build failed." }
    }
    if (Test-Path (Join-Path $DistDir "Swirl.exe")) {
        throw "Use a fresh DistDir so stale plugins cannot enter the installer."
    }
    New-Item -ItemType Directory -Force $DistDir,$OutDir | Out-Null
    Copy-Item -LiteralPath $exe -Destination $DistDir
    Copy-Item -LiteralPath (Join-Path (Split-Path $exe) 'SwirlProxyGuard.exe') -Destination $DistDir
    Copy-Item -LiteralPath (Join-Path (Split-Path $exe) 'SwirlGatewayGuard.exe') -Destination $DistDir
    Copy-Item -LiteralPath (Join-Path (Split-Path $exe) 'SwirlScriptRunner.exe') -Destination $DistDir
    Copy-Item -LiteralPath 'src/Swirl.Quick/packaging/rules' -Destination (Join-Path $DistDir 'rules') -Recurse
    Copy-Item -LiteralPath (Join-Path (Split-Path $exe) 'core') -Destination (Join-Path $DistDir 'core') -Recurse
    $icon = Join-Path (Resolve-Path $BuildDir).Path "brand/Swirl.ico"
    if (!(Test-Path -LiteralPath $icon)) { throw "SVG-derived icon is missing: $icon" }
    Copy-Item -LiteralPath $icon -Destination (Join-Path $DistDir "Swirl-brand-phase3.ico")
    Copy-Item -LiteralPath $icon -Destination (Join-Path $DistDir "Swirl-brand-phase3-v2.ico")
    & "$qt/bin/windeployqt.exe" --release --qmldir src/Swirl.Quick/qml (Join-Path $DistDir "Swirl.exe")
    if ($LASTEXITCODE) { throw "Qt runtime deployment failed." }
    Copy-Item src/Swirl.Quick/packaging/THIRD_PARTY_NOTICES.txt $DistDir
    Copy-Item src/Swirl.Quick/packaging/licenses (Join-Path $DistDir "licenses") -Recurse
    $documentation = Join-Path $DistDir 'docs'
    New-Item -ItemType Directory -Force -Path $documentation | Out-Null
    Copy-Item -LiteralPath 'src/Swirl.Quick/CAPTURE.md','docs/LOCAL_EXTENSIONS.md','docs/FONTS.md','docs/ANIMATION_DEPENDENCY_RESEARCH.md','docs/PR12_GRAPHICS_UPGRADE.md','docs/PR12_NATIVE_ACCEPTANCE.md','docs/PR12_NATIVE_UI_FIXES.md','docs/SWIRL_NATIVE_RESEARCH.md' -Destination $documentation
    $dist = (Resolve-Path $DistDir).Path
    $out = (Resolve-Path $OutDir).Path
    $appVersion = (Get-Content -LiteralPath 'src/Swirl.Quick/PRODUCT_VERSION.txt' -Raw).Trim()
    if ($appVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid PRODUCT_VERSION.txt' }
    & $Nsis /INPUTCHARSET UTF8 "/DAPP_DIST=$dist" "/DOUT_DIR=$out" "/DAPP_ICON=$icon" "/DAPP_VERSION=$appVersion" src/Swirl.Quick/packaging/Swirl.nsi
    if ($LASTEXITCODE) { throw "NSIS packaging failed." }
    Get-Item (Join-Path $out "Swirl-Setup.exe")
} finally { Pop-Location }
