# Run in an x64 MSVC developer shell. Test builds and release products use
# separate CMake directories; no external proxy executable is downloaded.
param(
    [Parameter(Mandatory)][string]$QtDir,
    [string]$BuildDir = 'D:\Codex\build\swirl-rust-product',
    [string]$DistDir = 'D:\Codex\outputs\Swirl-Rust-x64',
    [string]$OutDir = 'D:\Codex\outputs',
    [string]$Nsis = 'D:\Codex\toolchains\nsis-3.11\makensis.exe',
    [ValidateSet('Ninja','Visual Studio 17 2022')][string]$Generator = 'Ninja',
    [ValidateRange(1,64)][int]$Parallel = 4,
    [switch]$InputTests,
    [switch]$NativeBackdropTests,
    [switch]$PortableOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($NativeBackdropTests -and -not $InputTests) { throw 'Native backdrop checks require InputTests and an unlocked Windows desktop.' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$previousPath = $env:PATH
Push-Location $repo
try {
    if (Test-Path -LiteralPath $DistDir) { throw 'Use a fresh DistDir; existing files are never overwritten.' }
    $qt = (Resolve-Path -LiteralPath $QtDir).Path
    $env:PATH = "$(Join-Path $qt 'bin');$env:PATH"
    $configure = @('-G', $Generator, '-DCMAKE_BUILD_TYPE=Release', "-DCMAKE_PREFIX_PATH=$qt")
    if ($Generator -eq 'Visual Studio 17 2022') { $configure += @('-A','x64') }
    else {
        if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) { throw 'Run this script in an x64 MSVC developer shell.' }
        $configure += @('-DCMAKE_C_COMPILER=cl.exe','-DCMAKE_CXX_COMPILER=cl.exe')
    }
    if ($InputTests) {
        $testBuild = "$BuildDir-tests"
        cmake -S src/Swirl.Quick -B $testBuild @configure -DSWIRL_BUILD_UI_TESTS=ON
        if ($LASTEXITCODE) { throw 'Test configuration failed.' }
        cmake --build $testBuild --config Release --parallel $Parallel
        if ($LASTEXITCODE) { throw 'Test build failed.' }
        $testBin = Join-Path $testBuild 'Release'
        if (-not (Test-Path (Join-Path $testBin 'Swirl.exe'))) { $testBin = $testBuild }
        & windeployqt --release --compiler-runtime --qmldir src/Swirl.Quick/qml (Join-Path $testBin 'Swirl.exe')
        if ($LASTEXITCODE) { throw 'Test UI deployment failed.' }
        & windeployqt --release --compiler-runtime (Join-Path $testBin 'SwirlRustCoreTests.exe')
        if ($LASTEXITCODE) { throw 'Test dependency deployment failed.' }
        ctest --test-dir $testBuild -C Release -R '^swirl-(rust-|node-real-chain|import-subscription|subscription-formats|stream-regression|local-extensions|telemetry-accounting|diagnostic-export)' --output-on-failure
        if ($LASTEXITCODE) { throw 'Rust and retained product regression tests failed.' }
        if ($NativeBackdropTests) {
            New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
            $report = Join-Path ([IO.Path]::GetFullPath($OutDir)) 'window-validation'
            $p = Start-Process (Join-Path $testBin 'Swirl.exe') -ArgumentList @('--window-test',('"--window-test-output='+$report+'"')) -PassThru
            if (-not $p.WaitForExit(90000)) { $p.Kill(); throw 'Native compositor test timed out.' }
            if ($p.ExitCode) { throw 'Native compositor test failed.' }
        }
    }
    cmake -S src/Swirl.Quick -B $BuildDir @configure -DSWIRL_BUILD_UI_TESTS=OFF
    if ($LASTEXITCODE) { throw 'Production configuration failed.' }
    cmake --build $BuildDir --config Release --target Swirl --parallel $Parallel
    if ($LASTEXITCODE) { throw 'Production build failed; no package was staged.' }
    & (Join-Path $PSScriptRoot 'Stage-WindowsRustProduct.ps1') -BuildDirectory $BuildDir -Destination $DistDir
    $stage = (Resolve-Path -LiteralPath $DistDir).Path
    $p = Start-Process (Join-Path $stage 'Swirl.exe') -ArgumentList '--smoke-test' -WorkingDirectory ([IO.Path]::GetTempPath()) -WindowStyle Hidden -PassThru
    if (-not $p.WaitForExit(75000)) { $p.Kill(); throw 'Packaged Qt UI smoke timed out.' }
    if ($p.ExitCode) { throw 'Packaged Qt UI smoke failed.' }
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    $out = (Resolve-Path -LiteralPath $OutDir).Path
    $uninstallList = Join-Path $out 'Swirl-UninstallFiles.nsh'
    & (Join-Path $PSScriptRoot 'Finalize-WindowsRustProduct.ps1') -ApplicationDirectory $stage `
        -EvidenceDirectory (Join-Path $out 'package-evidence') -UninstallList $uninstallList
    $zip = Join-Path $out 'Swirl-Rust-x64.zip'
    if (Test-Path -LiteralPath $zip) { throw 'Use a fresh OutDir; existing archive is preserved.' }
    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip
    if (-not $PortableOnly) {
        if (-not (Test-Path -LiteralPath $Nsis -PathType Leaf)) { throw 'NSIS is unavailable; verified portable output is retained.' }
        if (Test-Path -LiteralPath (Join-Path $out 'Swirl-Setup.exe')) { throw 'Existing installer is preserved; use a fresh OutDir.' }
        $icon = (Resolve-Path -LiteralPath (Join-Path $BuildDir 'brand/Swirl.ico')).Path
        $appVersion = (Get-Content -LiteralPath 'src/Swirl.Quick/PRODUCT_VERSION.txt' -Raw).Trim()
        if ($appVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid PRODUCT_VERSION.txt' }
        & $Nsis /INPUTCHARSET UTF8 "/DAPP_DIST=$stage" "/DOUT_DIR=$out" "/DAPP_ICON=$icon" "/DAPP_VERSION=$appVersion" "/DUNINSTALL_LIST=$uninstallList" src/Swirl.Quick/packaging/Swirl.nsi
        if ($LASTEXITCODE) { throw 'NSIS failed; verified portable output is retained.' }
    }
    Write-Host "Verified Rust-only product: $stage"
} finally { $env:PATH=$previousPath; Pop-Location }
