[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$QtSource,
      [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$qt = (Resolve-Path $QtSource).Path
$out = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path $out) { throw 'Use a new A/B evidence directory' }
New-Item -ItemType Directory $out | Out-Null
$prepared = Join-Path $out 'd2-prepared'
$build = Join-Path $out 'qt-build'
$prefix = Join-Path $out 'qt-prefix'
$fixture = Join-Path $out 'fixtures'
$driver = Join-Path $PSScriptRoot 'd2_patched.py'
$platform = Split-Path $PSScriptRoot -Parent

function Invoke-Logged([string]$Name, [string]$Executable, [string[]]$Arguments) {
    $path = Join-Path $out ($Name + '.log')
    Write-Output ('D2_STAGE_START ' + $Name + ' ' + [DateTime]::UtcNow.ToString('o'))
    & $Executable @Arguments *> $path
    if ($LASTEXITCODE -ne 0) { Get-Content $path -Tail 100; throw "$Name failed: $LASTEXITCODE" }
    Write-Output ('D2_STAGE_PASS ' + $Name + ' ' + [DateTime]::UtcNow.ToString('o'))
}

# Discover the installed toolchain, not one inferred from the runner label.
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vs = (& $vswhere -latest -prerelease -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath).Trim()
if ($LASTEXITCODE -ne 0 -or -not $vs) { throw 'No MSVC C++ installation' }
$devcmd = Join-Path $vs 'Common7/Tools/VsDevCmd.bat'
$command = 'call "' + $devcmd + '" -arch=x64 -host_arch=x64 >nul && set'
$environment = & cmd.exe /d /s /c $command
if ($LASTEXITCODE -ne 0) { throw 'Cannot initialize MSVC environment' }
foreach ($line in $environment) {
    if ($line -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') }
}
$os = Get-CimInstance Win32_OperatingSystem
@{ source_commit=$env:GITHUB_SHA; qt_source_commit=(& git -C $qt rev-parse HEAD).Trim();
   windows_product=$os.Caption; windows_build=$os.BuildNumber; visual_studio=$vs;
   compiler=(Get-Command cl.exe).Source; cmake=(& cmake --version | Select-Object -First 1);
   runner=$env:RUNNER_OS; run_id=$env:GITHUB_RUN_ID; production_integration=$false } |
    ConvertTo-Json -Depth 8 | Set-Content (Join-Path $out 'environment.json') -Encoding utf8
Invoke-Logged 'prepare' 'python' @((Join-Path $PSScriptRoot 'd2_state.py'), 'prepare', $qt, $prepared)
Invoke-Logged 'fixtures' 'python' @((Join-Path $platform 'make_win_axis_precision_fixture.py'), $fixture)
# This private source-built Core/Gui installation never replaces a production SDK.
# Both sides use exactly these flags, the same build tree, compiler and prefix.
# Keep OpenGL enabled: this pinned Windows plugin has dynamicgl references
# that fail to compile in the first no-OpenGL experiment. No upstream workaround.
$options = @('-S', $qt, '-B', $build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
    "-DCMAKE_INSTALL_PREFIX=$prefix", '-DQT_BUILD_EXAMPLES=OFF', '-DQT_BUILD_TESTS=OFF',
    '-DFEATURE_system_freetype=OFF', '-DFEATURE_system_harfbuzz=OFF',
    '-DFEATURE_system_png=OFF', '-DFEATURE_system_zlib=OFF', '-DFEATURE_system_pcre2=OFF',
    '-DFEATURE_network=OFF', '-DFEATURE_sql=OFF', '-DFEATURE_xml=OFF', '-DFEATURE_concurrent=OFF',
    '-DFEATURE_dbus=OFF', '-DFEATURE_widgets=OFF', '-DFEATURE_printsupport=OFF', '-DFEATURE_testlib=OFF',
    '-DFEATURE_opengl=ON')
$options | ConvertTo-Json | Set-Content (Join-Path $out 'configure-arguments.json') -Encoding utf8
Invoke-Logged 'configure-qt' 'cmake' $options
Invoke-Logged 'build-baseline-qt' 'cmake' @('--build', $build, '--parallel', '4')
Invoke-Logged 'install-baseline-qt' 'cmake' @('--install', $build)
$env:PATH = (Join-Path $prefix 'bin') + ';' + $env:PATH
$env:CMAKE_PREFIX_PATH = $prefix
$env:QT_PLUGIN_PATH = Join-Path $prefix 'plugins'
$env:QT_QPA_PLATFORM_PLUGIN_PATH = Join-Path $prefix 'plugins/platforms'
$env:QT_FORCE_STDERR_LOGGING = '1'
$env:D1_RUNNER_LABEL = $env:RUNNER_OS + '-source-built'

foreach ($kind in @('baseline', 'patched')) {
    if ($kind -eq 'patched') {
        Invoke-Logged 'apply-patch' 'python' @($driver, 'apply', $qt, $prepared,
            (Join-Path $repo 'docs/patches/SWIRL_VF_WINDOWS_D2_1_QT_6_10_3.patch'),
            (Join-Path $out 'applied-patch.json'), $env:GITHUB_SHA)
        Invoke-Logged 'build-patched-qt' 'cmake' @('--build', $build, '--parallel', '4')
        Invoke-Logged 'install-patched-qt' 'cmake' @('--install', $build)
    }
    # Bind the actual built products; an unchanged QtGui hash fails final validation.
    $identities = @{}
    foreach ($name in @('bin/Qt6Core.dll', 'bin/Qt6Gui.dll', 'plugins/platforms/qwindows.dll')) {
        $path = Join-Path $prefix $name
        $identities[$name] = (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $identities | ConvertTo-Json | Set-Content (Join-Path $out ($kind + '-dlls.json')) -Encoding utf8
    $d1 = Join-Path $out ($kind + '-d1')
    & (Join-Path $platform 'run_win_axis_precision.ps1') -FixtureDirectory $fixture -OutputDirectory $d1 -InstallPerUserFont *> (Join-Path $out ($kind + '-d1.log'))
    $exit = $LASTEXITCODE
    @{ kind=$kind; exit_code=$exit } | ConvertTo-Json | Set-Content (Join-Path $out ($kind + '-d1-exit.json')) -Encoding utf8
    if (($kind -eq 'baseline' -and $exit -ne 1) -or ($kind -eq 'patched' -and $exit -ne 0)) {
        Get-Content (Join-Path $out ($kind + '-d1.log')) -Tail 40
        throw "Unexpected D1 $kind exit: $exit"
    }
    & python (Join-Path $platform 'analyze_win_axis_precision.py') $d1 --expected-source-sha $env:GITHUB_SHA *> (Join-Path $out ($kind + '-d1-analysis.log'))
    $expectedAnalysis = if ($kind -eq 'baseline') { 1 } else { 0 }
    if ($LASTEXITCODE -ne $expectedAnalysis) { throw "Unexpected D1 $kind analysis" }
    $env:D2_QTBASE_SOURCE = $qt
    $env:D2_PREPARED = $prepared
    Invoke-Logged ($kind + '-configure-probe') 'cmake' @('-S', $PSScriptRoot, '-B', (Join-Path $d1 'build'))
    Invoke-Logged ($kind + '-build-probe') 'cmake' @('--build', (Join-Path $d1 'build'), '--config', 'Release', '--target', 'win_axis_precision_d2', '--parallel', '2')
    Invoke-Logged ($kind + '-probe') 'python' @($driver, 'probe', (Join-Path $d1 'build/Release/win_axis_precision_d2.exe'),
        (Join-Path $fixture 'ordinary.ttf'), (Join-Path $out ($kind + '-probe')), $prepared, $prefix, $env:GITHUB_SHA, $kind)
}
Invoke-Logged 'compare' 'python' @($driver, 'compare', $out, $prepared, $env:GITHUB_SHA)
Get-Content (Join-Path $out 'patched-qt-analysis.json')
