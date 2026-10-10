param(
    [Parameter(Mandatory)][string]$QtDir,
    [string]$BuildDir = "build/swirl-quick",
    [string]$DistDir = "dist/swirl-quick",
    [string]$OutDir = "out",
    [string]$Nsis = "C:/Program Files (x86)/NSIS/makensis.exe",
    [string]$Generator = "Ninja",
    [switch]$InputTests
)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
Push-Location $repo
try {
    $qt = (Resolve-Path -LiteralPath $QtDir).Path
    $env:PATH = "$qt/bin;$env:PATH"
    $testFlag = if ($InputTests) { "ON" } else { "OFF" }
    cmake -S src/Swirl.Quick -B $BuildDir -G $Generator -DCMAKE_BUILD_TYPE=Release "-DCMAKE_PREFIX_PATH=$qt" "-DSWIRL_BUILD_UI_TESTS=$testFlag"
    if ($LASTEXITCODE) { throw "CMake configure failed." }
    cmake --build $BuildDir --config Release --parallel
    if ($LASTEXITCODE) { throw "Release build failed." }
    $exe = Join-Path $BuildDir "Swirl.exe"
    if (!(Test-Path $exe)) { $exe = Join-Path $BuildDir "Release/Swirl.exe" }
    $exe = (Resolve-Path $exe).Path
    if ($InputTests) {
        # This input test uses the actual Windows platform plugin and fonts.
        $test = Start-Process $exe -ArgumentList "--interaction-test" -WindowStyle Hidden -Wait -PassThru
        if ($test.ExitCode) { throw "Input checks failed: $($test.ExitCode). See Swirl-diagnostics.txt." }
        cmake -S src/Swirl.Quick -B $BuildDir -DSWIRL_BUILD_UI_TESTS=OFF
        if ($LASTEXITCODE) { throw "Production reconfigure failed." }
        cmake --build $BuildDir --config Release --parallel
        if ($LASTEXITCODE) { throw "Production build failed." }
    }
    if (Test-Path (Join-Path $DistDir "Swirl.exe")) {
        throw "Use a fresh DistDir so stale plugins cannot enter the installer."
    }
    New-Item -ItemType Directory -Force $DistDir,$OutDir | Out-Null
    Copy-Item -LiteralPath $exe -Destination $DistDir
    & "$qt/bin/windeployqt.exe" --release --qmldir src/Swirl.Quick/qml (Join-Path $DistDir "Swirl.exe")
    if ($LASTEXITCODE) { throw "Qt runtime deployment failed." }
    Copy-Item src/Swirl.Quick/packaging/THIRD_PARTY_NOTICES.txt $DistDir
    Copy-Item src/Swirl.Quick/packaging/licenses (Join-Path $DistDir "licenses") -Recurse
    $dist = (Resolve-Path $DistDir).Path
    $out = (Resolve-Path $OutDir).Path
    & $Nsis /INPUTCHARSET UTF8 "/DAPP_DIST=$dist" "/DOUT_DIR=$out" src/Swirl.Quick/packaging/Swirl.nsi
    if ($LASTEXITCODE) { throw "NSIS packaging failed." }
    Get-Item (Join-Path $out "Swirl-Setup.exe")
} finally { Pop-Location }
