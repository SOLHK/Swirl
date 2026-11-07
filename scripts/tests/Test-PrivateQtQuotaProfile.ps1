#Requires -Version 7.4
param()
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
Set-StrictMode -Version Latest

# This fixed CI-only build never supplies a private subscription or publishes a
# runtime. The existing test entry owns its synthetic ledger, process and IPC.
if ($args.Count -ne 0 -or -not $IsWindows -or [IntPtr]::Size -ne 8 -or
    $env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    $env:GITHUB_REPOSITORY -cne 'SOLHK/Swirl' -or $env:GITHUB_SHA -cnotmatch '^[0-9a-f]{40}$') {
    throw 'Private Qt quota acceptance requires the fixed GitHub-hosted Windows x64 checkout.'
}
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path.TrimEnd('\','/')
$workspace = (Resolve-Path -LiteralPath $env:GITHUB_WORKSPACE).Path.TrimEnd('\','/')
if (-not $repo.Equals($workspace, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Private Qt quota acceptance must use the current workflow checkout.'
}
. (Join-Path $repo 'scripts/Assert-BuildSource.ps1')
. (Join-Path $repo 'scripts/Copy-VerifiedMsvcRuntime.ps1')
Assert-SwirlPathWithoutLinks $repo
$output = Join-Path $repo 'build-evidence/private-ui-quota'
$qaBuild = Join-Path $repo 'build/private-ui-quota'
$qaRust = Join-Path $qaBuild 'rust-target'
$qaRuntime = Join-Path $qaBuild 'Release'
$dist = Join-Path $repo 'dist'
$product = Join-Path $repo 'installer-bin'
foreach ($path in @($output,$qaBuild,$qaRust,$dist,$product)) { Assert-SwirlPathWithoutLinks $path }
if (Test-Path -LiteralPath $output) { throw 'Existing private Qt quota evidence will not be overwritten.' }
New-Item -ItemType Directory -Path $output | Out-Null
New-Item -ItemType Directory -Path (Join-Path $output 'logs') | Out-Null
New-Item -ItemType Directory -Path (Join-Path $output 'build') | Out-Null
$steps = [Collections.Generic.List[object]]::new()
$errors = [Collections.Generic.List[string]]::new()
$receipt = [ordered]@{
    schema=1; source_sha=$env:GITHUB_SHA; run_id=$env:GITHUB_RUN_ID; run_attempt=$env:GITHUB_RUN_ATTEMPT
    started_utc=[DateTime]::UtcNow.ToString('o'); status='failed'; success=$false
    scope='Fixed synthetic private Qt UI quota profile and owned subscription-form/policy/probe controls; no provider, wire, system-proxy or TUN acceptance'
    live_ready=$false; ordinary_runtimes_unchanged=$false; private_session_files_uploaded=$false
    build_directory=$qaBuild; rust_target=$qaRust; runtime_directory=$qaRuntime
    test_inventory=$null; steps=@(); errors=@()
}
$primary = $null
$before = $null
$sourceVerified = $false

function Write-QuotaJson([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path, (ConvertTo-Json -InputObject $Value -Depth 30), [Text.UTF8Encoding]::new($false))
}
function Get-QuotaFile([string]$Path) {
    Assert-SwirlPathWithoutLinks $Path
    $file = Get-Item -LiteralPath $Path -Force
    if ($file.PSIsContainer) { throw 'Expected a regular quota evidence input.' }
    return [ordered]@{path=$file.FullName; bytes=$file.Length; sha256=(Get-SwirlMsvcHash $file.FullName)}
}
function Get-QuotaCacheValue([string]$Text, [string]$Name) {
    $found = [regex]::Matches($Text, ('(?m)^'+[regex]::Escape($Name)+':[^=\r\n]+=([^\r\n]*)\r?$'))
    if ($found.Count -ne 1) { throw ('Missing or ambiguous CMake value: '+$Name) }
    return $found[0].Groups[1].Value
}
function Test-QuotaSamePath([string]$Left, [string]$Right) {
    return [IO.Path]::GetFullPath($Left).TrimEnd('\','/').Equals(
        [IO.Path]::GetFullPath($Right).TrimEnd('\','/'), [StringComparison]::OrdinalIgnoreCase)
}
function Save-QuotaFile([string]$Source, [string]$Relative) {
    $target = Join-Path $output $Relative
    Assert-SwirlPathWithoutLinks $Source
    Assert-SwirlPathWithoutLinks $target
    New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)) -Force | Out-Null
    [IO.File]::Copy($Source,$target,$false)
    if ((Get-SwirlMsvcHash $Source) -cne (Get-SwirlMsvcHash $target)) { throw 'Evidence copy identity changed.' }
}
function Invoke-QuotaTool([string]$Name, [string]$Program, [string[]]$Arguments,
                          [hashtable]$Environment=@{}, [string[]]$RemoveEnvironment=@()) {
    if ($Name -cnotmatch '^[a-z0-9-]+$' -or -not [IO.Path]::IsPathFullyQualified($Program)) {
        throw 'Expected a fixed tool name and absolute executable.'
    }
    Assert-SwirlPathWithoutLinks $Program
    $log = Join-Path $output ('logs/'+$Name+'.log')
    if (Test-Path -LiteralPath $log) { throw 'Tool log names must be unique.' }
    $entry = [ordered]@{name=$Name; tool=(Get-QuotaFile $Program); arguments=@($Arguments)
        started_utc=[DateTime]::UtcNow.ToString('o'); exit_code=$null; log=$null}
    $steps.Add($entry)
    $saved = @{}
    foreach ($nameToSet in @($Environment.Keys)+@($RemoveEnvironment)) {
        if (-not $saved.ContainsKey($nameToSet)) {
            $saved[$nameToSet] = [Environment]::GetEnvironmentVariable($nameToSet,'Process')
        }
    }
    try {
        foreach ($nameToRemove in $RemoveEnvironment) { [Environment]::SetEnvironmentVariable($nameToRemove,$null,'Process') }
        foreach ($item in $Environment.GetEnumerator()) { [Environment]::SetEnvironmentVariable($item.Key,[string]$item.Value,'Process') }
        $global:LASTEXITCODE = 0
        # Native output is public build/test output only. Do not invoke the UI
        # grant protocol here or copy any test session directory into evidence.
        & $Program @Arguments 2>&1 | Tee-Object -FilePath $log | Out-Host
        $entry.exit_code = $LASTEXITCODE
    } finally {
        foreach ($item in $saved.GetEnumerator()) { [Environment]::SetEnvironmentVariable($item.Key,$item.Value,'Process') }
        $entry.finished_utc = [DateTime]::UtcNow.ToString('o')
        if (Test-Path -LiteralPath $log -PathType Leaf) { $entry.log = Get-QuotaFile $log }
    }
    if ($entry.exit_code -ne 0) { throw ('Private Qt quota tool failed: '+$Name+'; exit='+$entry.exit_code) }
    return $log
}
function Get-QuotaCompiler([string]$Build, [string]$Label) {
    $cachePath = Join-Path $Build 'CMakeCache.txt'
    Assert-SwirlPathWithoutLinks $cachePath
    if ((Get-Item -LiteralPath $cachePath).Length -gt 2097152) { throw 'CMake cache is unexpectedly large.' }
    $cache = [IO.File]::ReadAllText($cachePath)
    $parts = foreach ($part in @('MAJOR','MINOR','PATCH')) {
        $value = Get-QuotaCacheValue $cache ('CMAKE_CACHE_'+$part+'_VERSION')
        if ($value -cnotmatch '^[0-9]+$') { throw 'Invalid CMake version metadata.' }
        $value
    }
    $metadata = Join-Path $Build ('CMakeFiles/'+($parts -join '.')+'/CMakeCXXCompiler.cmake')
    Assert-SwirlPathWithoutLinks $metadata
    $text = [IO.File]::ReadAllText($metadata)
    if ($text -notmatch '(?m)^set\(CMAKE_CXX_COMPILER_ID "MSVC"\)\s*$' -or
        $text -notmatch '(?m)^set\(MSVC_CXX_ARCHITECTURE_ID "?x64"?\)\s*$') { throw 'Expected actual MSVC x64 compiler metadata.' }
    if ($text -notmatch '(?m)^set\(CMAKE_CXX_COMPILER "([^"\r\n]+)"\)\s*$') { throw 'Missing actual C++ compiler path.' }
    $compiler = Resolve-SwirlMsvcPath $Matches[1]
    if ($text -notmatch '(?m)^set\(CMAKE_CXX_COMPILER_VERSION "([0-9.]+)"\)\s*$') { throw 'Missing actual C++ compiler version.' }
    $version = $Matches[1]
    Save-QuotaFile $cachePath ('build/'+$Label+'-CMakeCache.txt')
    Save-QuotaFile $metadata ('build/'+$Label+'-CMakeCXXCompiler.cmake')
    return [ordered]@{path=$compiler; sha256=(Get-SwirlMsvcHash $compiler); version=$version
        metadata=(Get-QuotaFile $metadata); cache=(Get-QuotaFile $cachePath)
        private_ui_quota=(Get-QuotaCacheValue $cache 'SWIRL_PRIVATE_UI_QUOTA')
        ui_tests=(Get-QuotaCacheValue $cache 'SWIRL_BUILD_UI_TESTS')
        core_tests=(Get-QuotaCacheValue $cache 'SWIRL_BUILD_CORE_TESTS')
        rust_target=(Get-QuotaCacheValue $cache 'SWIRL_RUST_TARGET')
        cmake_command=(Get-QuotaCacheValue $cache 'CMAKE_COMMAND')}
}
function Get-QuotaTree([string]$Root) {
    Assert-SwirlPathWithoutLinks $Root
    $files = [Collections.Generic.List[object]]::new()
    $pending = [Collections.Generic.Queue[string]]::new(); $pending.Enqueue($Root)
    while ($pending.Count) {
        $directory = $pending.Dequeue()
        foreach ($item in (Get-ChildItem -LiteralPath $directory -Force)) {
            Assert-SwirlPathWithoutLinks $item.FullName
            if ($item.PSIsContainer) { $pending.Enqueue($item.FullName); continue }
            $files.Add([ordered]@{path=[IO.Path]::GetRelativePath($Root,$item.FullName).Replace('\','/')
                bytes=$item.Length; sha256=(Get-SwirlMsvcHash $item.FullName)})
            if ($files.Count -gt 10000) { throw 'Ordinary runtime inventory exceeded its bound.' }
        }
    }
    return @($files | Sort-Object { $_.path })
}
function Assert-QuotaNormalDirectory([string]$Root) {
    foreach ($file in @(Get-QuotaTree $Root)) {
        $name = [IO.Path]::GetFileName([string]$file.path)
        if ($name -match '^(?:SwirlPrivateUiQuota|swirl-private-worker)(?:[.-]|$)') {
            throw 'A private QA executable reached an ordinary runtime directory.'
        }
    }
}
function Read-QuotaExports([string]$Label, [string]$Library, [string]$Dumpbin, [bool]$Private) {
    $log = Invoke-QuotaTool ('exports-'+$Label) $Dumpbin @('/nologo','/exports',$Library)
    $names = @([regex]::Matches([IO.File]::ReadAllText($log),
        '(?m)^\s+[0-9]+\s+[0-9A-Fa-f]+\s+[0-9A-Fa-f]{8,16}\s+([A-Za-z_][A-Za-z0-9_]*)\s*$') |
        ForEach-Object { $_.Groups[1].Value })
    if (-not $names.Count -or $names -cnotcontains 'swirl_core_command' -or
        $names -cnotcontains 'swirl_core_build_info') { throw 'Rust export output was missing or unrecognized.' }
    $privateNames = @($names | Where-Object { $_ -cmatch '^swirl_private_' })
    if (($Private -and ($privateNames.Count -ne 1 -or $privateNames[0] -cne 'swirl_private_ui_quota_v1')) -or
        (-not $Private -and $privateNames.Count -ne 0)) { throw 'Private QA ABI export separation failed.' }
    return [ordered]@{library=(Get-QuotaFile $Library); exports=$names; private_exports=$privateNames; output=(Get-QuotaFile $log)}
}
function Save-QuotaPartialBuildMetadata {
    # Fixed compiler/configuration filenames only; never the build/runtime tree
    # or the test's temporary fixture, ledger, proof or encrypted node store.
    foreach ($name in @('CMakeCache.txt','swirl-rust-build.json','generated/SwirlBuildIdentity.h',
        'CMakeFiles/CMakeConfigureLog.yaml','CMakeFiles/CMakeOutput.log','CMakeFiles/CMakeError.log')) {
        $path = Join-Path $qaBuild $name
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $target = 'build/partial-'+$name.Replace('/','-')
            Save-QuotaFile $path $target
        }
    }
}

try {
    Assert-SwirlBuildSource -RepositoryRoot $repo -ExpectedSourceSha $env:GITHUB_SHA
    $sourceVerified = $true
    if (Test-Path -LiteralPath $qaBuild) { throw 'Private Qt quota build and Cargo target must be new.' }
    foreach ($path in @($dist,$product)) {
        if (-not (Test-Path -LiteralPath $path -PathType Container)) { throw 'Both accepted ordinary runtimes must already exist.' }
        Assert-QuotaNormalDirectory $path
    }
    $before = [ordered]@{dist=@(Get-QuotaTree $dist); installer_bin=@(Get-QuotaTree $product)}
    Write-QuotaJson (Join-Path $output 'ordinary-runtime-before.json') $before
    $crt = Assert-SwirlMsvcRuntimePayload -ApplicationDirectory $dist
    Save-QuotaFile (Join-Path $dist 'msvc-runtime.json') 'ordinary-msvc-runtime.json'
    $ordinaryCompiler = Get-QuotaCompiler (Join-Path $repo 'build/swirl-quick') 'ordinary-qa'
    $releaseCompiler = Get-QuotaCompiler (Join-Path $repo 'build/swirl-product') 'ordinary-release'
    foreach ($compiler in @($ordinaryCompiler,$releaseCompiler)) {
        if ($compiler.private_ui_quota -cne 'OFF' -or
            -not (Test-QuotaSamePath $compiler.path $crt.source.compiler_path) -or
            $compiler.sha256 -cne $crt.source.compiler_sha256 -or $compiler.version -cne $crt.source.compiler_version) {
            throw 'Ordinary compiler identity or disabled QA profile differs from its verified CRT receipt.'
        }
    }
    if ($ordinaryCompiler.ui_tests -cne 'ON' -or $releaseCompiler.ui_tests -cne 'OFF') {
        throw 'Ordinary QA and Release build flavors differ from their expected scope.'
    }
    $qtRoot = Resolve-SwirlMsvcPath $env:QT_ROOT_DIR
    $sslRoot = Resolve-SwirlMsvcPath $env:SWIRL_OPENSSL_ROOT
    # Get-Command -CommandType Application can enumerate both the standalone
    # and Visual Studio copies. Reuse the exact command recorded by the real
    # ordinary builds instead of coercing that result array into one filename.
    $cmake = Resolve-SwirlMsvcPath $ordinaryCompiler.cmake_command
    if (-not (Test-QuotaSamePath $releaseCompiler.cmake_command $cmake)) {
        throw 'Ordinary QA and Release used different CMake executables.'
    }
    $python = Resolve-SwirlMsvcPath $env:SWIRL_PROFILE_OWNER_PYTHON
    $pwsh = Join-Path $PSHOME 'pwsh.exe'
    $windeployqt = Join-Path $qtRoot 'bin/windeployqt.exe'
    $qtpaths = Join-Path $qtRoot 'bin/qtpaths.exe'
    $qmake = Join-Path $qtRoot 'bin/qmake.exe'
    $dumpbin = Join-Path ([IO.Path]::GetDirectoryName($ordinaryCompiler.path)) 'dumpbin.exe'
    foreach ($tool in @($cmake,$python,$pwsh,$windeployqt,$qtpaths,$qmake,$dumpbin)) { $null = Get-QuotaFile $tool }
    $sdkPath = Join-Path $repo 'build-evidence/qt-sdk.json'
    $sdk = Get-Content -LiteralPath $sdkPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $stockRoot = Resolve-SwirlMsvcPath $sdk.kit_root
    if ($sdk.version -cne '6.12.0' -or $sdk.qmake_version -cne '6.12.0' -or
        $sdk.arch -cne 'win64_msvc2022_64' -or -not (Test-QuotaSamePath $stockRoot $env:SWIRL_QT_STOCK_ROOT)) {
        throw 'The original official Qt 6.12 MSVC receipt or kit identity changed.'
    }
    $sdkNames = @('bin/qmake.exe','bin/Qt6Core.dll','bin/Qt6Gui.dll','bin/Qt6Quick.dll',
        'bin/qt.conf','lib/cmake/Qt6/Qt6ConfigVersionImpl.cmake',
        'lib/cmake/Qt6GuiPrivate/Qt6GuiPrivateConfig.cmake',
        'lib/cmake/Qt6ShaderTools/Qt6ShaderToolsConfig.cmake')
    if ((@($sdk.files.PSObject.Properties.Name | Sort-Object) -join "`n") -cne
        (@($sdkNames | Sort-Object) -join "`n")) { throw 'The verified Qt fingerprint set differs from the fixed installer contract.' }
    foreach ($entry in $sdk.files.PSObject.Properties) {
        if ($entry.Name -cnotmatch '^[A-Za-z0-9_./-]+$' -or $entry.Name.StartsWith('/') -or
            @($entry.Name.Split('/') | Where-Object { $_ -in @('','.', '..') }).Count -or
            [string]$entry.Value -cnotmatch '^[0-9a-f]{64}$' -or
            (Get-SwirlMsvcHash (Join-Path $stockRoot $entry.Name)) -cne [string]$entry.Value) { throw 'Official Qt SDK fingerprint changed.' }
    }
    Save-QuotaFile $sdkPath 'qt-sdk.json'
    $selectedPath = Resolve-SwirlMsvcPath $env:SWIRL_QT_SELECTED_RECEIPT
    $selected = Get-Content -LiteralPath $selectedPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $selectedHook = Resolve-SwirlMsvcPath $env:SWIRL_QT_SELECTED_CMAKE
    if ($selected.schema -ne 1 -or $selected.kind -cne 'swirl-selected-qt612-product-sdk' -or
        $selected.success -ne $true -or $selected.consumer.source_sha -cne $env:GITHUB_SHA -or
        -not (Test-QuotaSamePath $selected.kit_root $qtRoot) -or
        -not (Test-QuotaSamePath $selected.stock_kit_root $stockRoot) -or
        -not (Test-QuotaSamePath $selected.cmake_capture_hook.path $selectedHook) -or
        $selected.selected_content_id -cne $env:SWIRL_QT_SELECTED_CONTENT_ID) {
        throw 'Private QA must use the same complete selected Qt SDK as ordinary QA and Release.'
    }
    Save-QuotaFile $selectedPath 'qt-selected-sdk.json'
    $sdkVerifier = Join-Path $repo 'tools/Compose-Qt612ProductSdk.py'
    foreach ($normalQt in @(@{name='ordinary-qa';build=(Join-Path $repo 'build/swirl-quick');runtime=$dist},
                           @{name='ordinary-release';build=(Join-Path $repo 'build/swirl-product');runtime=$product})) {
        $null = Invoke-QuotaTool ('qt-'+$normalQt.name) $python @($sdkVerifier,'verify','--receipt',$selectedPath,
            '--build-dir',$normalQt.build,'--phase','post-deploy','--runtime-dir',$normalQt.runtime,
            '--evidence',(Join-Path $output ('qt-'+$normalQt.name)))
    }
    $receipt.selected_qt_sdk = [ordered]@{content_id=$selected.selected_content_id; derivation_id=$selected.derivation_id
        receipt=(Get-QuotaFile $selectedPath); qml=$selected.qml_files; product_root_cause_claim=$false}
    $qtVersionLog = Invoke-QuotaTool 'qt-version' $qmake @('-query','QT_VERSION')
    if ([IO.File]::ReadAllText($qtVersionLog).Trim() -cne '6.12.0') { throw 'Actual Qt version changed.' }
    $receipt.qt_tools = [ordered]@{qmake=(Get-QuotaFile $qmake); windeployqt=(Get-QuotaFile $windeployqt); qtpaths=(Get-QuotaFile $qtpaths)}
    $normalExports = [ordered]@{
        qa=(Read-QuotaExports 'ordinary-qa' (Join-Path $dist 'swirl_api.dll') $dumpbin $false)
        release=(Read-QuotaExports 'ordinary-release' (Join-Path $product 'swirl_api.dll') $dumpbin $false)
    }
    $receipt.ordinary_exports = $normalExports
    $configure = @('-S',(Join-Path $repo 'src/Swirl.Quick'),'-B',$qaBuild,'-G','Visual Studio 17 2022','-A','x64',
        '-DSWIRL_BUILD_UI_TESTS:BOOL=ON','-DSWIRL_BUILD_CORE_TESTS:BOOL=OFF','-DSWIRL_PRIVATE_UI_QUOTA:BOOL=ON',
        ('-DSWIRL_RUST_TARGET:PATH='+$qaRust.Replace('\','/')),('-DCMAKE_PREFIX_PATH:PATH='+$qtRoot.Replace('\','/')),
        ('-DCMAKE_PROJECT_TOP_LEVEL_INCLUDES:FILEPATH='+$selectedHook.Replace('\','/')))
    $null = Invoke-QuotaTool 'configure' $cmake $configure
    $null = Invoke-QuotaTool 'qt-configured' $python @($sdkVerifier,'verify','--receipt',$selectedPath,
        '--build-dir',$qaBuild,'--phase','configured','--evidence',(Join-Path $output 'qt-configured'))
    $privateCompiler = Get-QuotaCompiler $qaBuild 'private-qa'
    if ($privateCompiler.private_ui_quota -cne 'ON' -or $privateCompiler.ui_tests -cne 'ON' -or
        $privateCompiler.core_tests -cne 'OFF' -or -not (Test-QuotaSamePath $privateCompiler.rust_target $qaRust) -or
        -not (Test-QuotaSamePath $privateCompiler.cmake_command $cmake) -or
        -not (Test-QuotaSamePath $privateCompiler.path $crt.source.compiler_path) -or
        $privateCompiler.sha256 -cne $crt.source.compiler_sha256 -or $privateCompiler.version -cne $crt.source.compiler_version) {
        throw 'Private QA compiler, Cargo target or CMake configuration differs from the admitted contract.'
    }
    $privateCache = [IO.File]::ReadAllText((Join-Path $qaBuild 'CMakeCache.txt'))
    if (-not (Test-QuotaSamePath (Get-QuotaCacheValue $privateCache 'Qt6_DIR') (Join-Path $qtRoot 'lib/cmake/Qt6')) -or
        (Get-QuotaCacheValue $privateCache 'SWIRL_TUN_BROKER') -cne '' -or
        (Get-QuotaCacheValue $privateCache 'SWIRL_TUN_HELPER') -cne '') { throw 'Private QA kit or excluded TUN outputs differ.' }
    $receipt.compilers = [ordered]@{ordinary_qa=$ordinaryCompiler; ordinary_release=$releaseCompiler; private_qa=$privateCompiler}
    $null = Invoke-QuotaTool 'build' $cmake @('--build',$qaBuild,'--target','Swirl','--config','Release','--parallel','4')
    $qaExe = Join-Path $qaRuntime 'SwirlPrivateUiQuota.exe'
    $qaCore = Join-Path $qaRuntime 'swirl_api.dll'
    foreach ($file in @($qaExe,$qaCore)) {
        $null = Get-QuotaFile $file
        if ([SwirlMsvcPackage.PeImage]::Read($file).Machine -cne '0x8664') { throw 'Private QA output is not AMD64.' }
    }
    foreach ($name in @('Swirl.exe','swirl-private-worker.exe','swirl-tun-broker.exe','swirl-tun-helper.exe')) {
        if (Test-Path -LiteralPath (Join-Path $qaRuntime $name)) { throw 'Unexpected executable in private QA runtime.' }
    }
    $pair = Get-Content -LiteralPath (Join-Path $qaRuntime 'swirl-rust-build.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $rustLibrary = Get-QuotaCacheValue $privateCache 'SWIRL_RUST_LIBRARY'
    if ($pair.abi_version -ne 1 -or $pair.source_sha -cne $env:GITHUB_SHA -or
        $pair.target -cne 'x86_64-pc-windows-msvc' -or $pair.build_id -cnotmatch '^[0-9a-f]{64}$' -or
        $pair.build_id -cne (Get-QuotaCacheValue $privateCache 'SWIRL_RUST_BUILD_ID') -or
        -not (Test-QuotaSamePath $rustLibrary (Join-Path $qaRust 'x86_64-pc-windows-msvc/release/swirl_api.dll')) -or
        (Get-SwirlMsvcHash $rustLibrary) -cne (Get-SwirlMsvcHash $qaCore)) { throw 'Private QA staged DLL/source/build pairing failed.' }
    foreach ($normal in @($dist,$product)) {
        $normalPair = Get-Content -LiteralPath (Join-Path $normal 'swirl-rust-build.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($normalPair.source_sha -cne $env:GITHUB_SHA -or $normalPair.build_id -ceq $pair.build_id) {
            throw 'Private QA salt does not separate it from the current ordinary runtime.'
        }
    }
    Save-QuotaFile (Join-Path $qaRuntime 'swirl-rust-build.json') 'private-rust-pairing.json'
    $receipt.private_pairing = $pair
    $receipt.private_exports = Read-QuotaExports 'private-qa' $qaCore $dumpbin $true
    $null = Invoke-QuotaTool 'qt-pre-deploy' $python @($sdkVerifier,'verify','--receipt',$selectedPath,
        '--build-dir',$qaBuild,'--phase','pre-deploy','--evidence',(Join-Path $output 'qt-pre-deploy'))
    $null = Invoke-QuotaTool 'deploy-openssl' $pwsh @('-NoProfile','-NonInteractive','-File',
        (Join-Path $repo 'scripts/Copy-VerifiedOpenSslRuntime.ps1'),'-OpenSslRoot',$sslRoot,
        '-ApplicationDirectory',$qaRuntime,'-Target','VC-WIN64A','-Python',$python)
    $null = Invoke-QuotaTool 'deploy-qt' $windeployqt @('--qtpaths',$qtpaths,'--release','--no-compiler-runtime','--no-system-d3d-compiler','--openssl-root',$sslRoot,
        '--include-plugins','qoffscreen,qopensslbackend','--qmldir',(Join-Path $repo 'src/Swirl.Quick/qml'),$qaExe)
    $null = Invoke-QuotaTool 'deploy-qt-shaders' $pwsh @('-NoProfile','-NonInteractive','-File',
        (Join-Path $repo 'scripts/Copy-QtSdkShaderRuntime.ps1'),'-QtRoot',$qtRoot,'-ApplicationDirectory',$qaRuntime,
        '-QtSdkReceipt',$selectedPath,'-EvidenceDirectory',(Join-Path $output 'qt-d3d'),'-Python',$python)
    $null = Invoke-QuotaTool 'qt-post-deploy' $python @($sdkVerifier,'verify','--receipt',$selectedPath,
        '--build-dir',$qaBuild,'--phase','post-deploy','--runtime-dir',$qaRuntime,
        '--evidence',(Join-Path $output 'qt-post-deploy'))
    $ssl = Get-Content -LiteralPath (Join-Path $sslRoot 'openssl-runtime.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($item in @(@('bin/libssl-3-x64.dll','libssl-3-x64.dll'),@('bin/libcrypto-3-x64.dll','libcrypto-3-x64.dll'),
        @('licenses/LICENSE.txt','licenses/OpenSSL-LICENSE.txt'),@('licenses/NOTICE.txt','licenses/OpenSSL-NOTICE.txt'))) {
        $entry = $ssl.files.PSObject.Properties[$item[0]].Value
        $file = Get-QuotaFile (Join-Path $qaRuntime $item[1])
        if ($file.sha256 -cne $entry.sha256 -or $file.bytes -ne $entry.size) { throw 'Deployed OpenSSL bytes differ from the verified receipt.' }
    }
    if ((Get-SwirlMsvcHash (Join-Path $qaRuntime 'openssl-runtime.json')) -cne
        (Get-SwirlMsvcHash (Join-Path $sslRoot 'openssl-runtime.json'))) { throw 'Deployed OpenSSL receipt is not the verified original.' }
    Save-QuotaFile (Join-Path $qaRuntime 'openssl-runtime.json') 'openssl-runtime.json'
    foreach ($name in @('Qt6Core.dll','Qt6Gui.dll','Qt6Quick.dll','Qt6Qml.dll','Qt6Network.dll')) {
        if ((Get-SwirlMsvcHash (Join-Path $qaRuntime $name)) -cne (Get-SwirlMsvcHash (Join-Path $qtRoot ('bin/'+$name)))) {
            throw 'Private QA Qt runtime differs from the complete selected kit.'
        }
    }
    $crtCopies = [Collections.Generic.List[object]]::new()
    $crtNames = @($crt.files.PSObject.Properties.Name)
    foreach ($name in $crtNames) {
        if ($name -cnotmatch $script:SwirlMsvcNamePattern) { throw 'Unsafe CRT filename.' }
        $entry = $crt.files.PSObject.Properties[$name].Value
        $source = Join-Path $dist $name; $destination = Join-Path $qaRuntime $name
        $sourceIdentity = Get-QuotaFile $source
        if ($sourceIdentity.bytes -ne $entry.size -or $sourceIdentity.sha256 -cne $entry.sha256) { throw 'Original CRT changed before copy.' }
        Assert-SwirlPathWithoutLinks $destination
        if (Test-Path -LiteralPath $destination) { throw 'Unexpected preexisting compiler runtime in fresh QA deployment.' }
        [IO.File]::Copy($source,$destination,$false)
        $copyIdentity = Get-QuotaFile $destination
        if ($copyIdentity.bytes -ne $entry.size -or $copyIdentity.sha256 -cne $entry.sha256 -or
            (Get-SwirlMsvcHash $source) -cne $entry.sha256) { throw 'CRT copy identity changed.' }
        $crtCopies.Add([ordered]@{name=$name; source=$sourceIdentity; destination=$copyIdentity})
    }
    $peFiles = [Collections.Generic.List[object]]::new()
    foreach ($file in @(Get-QuotaTree $qaRuntime)) {
        if ([IO.Path]::GetExtension([string]$file.path) -notin @('.exe','.dll')) { continue }
        $path = Join-Path $qaRuntime $file.path
        $image = [SwirlMsvcPackage.PeImage]::Read($path)
        if ($image.Machine -cne '0x8664') { throw 'Non-AMD64 image in the QA deployment.' }
        $name = [IO.Path]::GetFileName([string]$file.path).ToLowerInvariant()
        if ($name -match $script:SwirlMsvcNamePattern -and
            ($file.path -cne $name -or $name -cnotin $crtNames)) { throw 'Unlisted or nested compiler runtime in QA deployment.' }
        foreach ($dependency in @($image.Imports)+@($image.DelayImports)) {
            $lower = $dependency.ToLowerInvariant()
            if ($lower -match $script:SwirlMsvcNamePattern) {
                if ($lower -cnotin $crtNames) { throw 'QA PE imports require a compiler runtime outside the verified ordinary manifest.' }
            } elseif ($lower -match '^(?:msvcr|msvcp|vcruntime|concrt|vccorlib|vcomp|mfc|mfcm|atl)[0-9].*\.dll$') {
                throw 'Unsupported compiler runtime import in QA deployment.'
            }
        }
        $peFiles.Add([ordered]@{path=$file.path; bytes=$file.bytes; sha256=$file.sha256
            machine=$image.Machine; imports=@($image.Imports); delay_imports=@($image.DelayImports)})
    }
    Write-QuotaJson (Join-Path $output 'qa-crt-import-closure.json') ([ordered]@{schema=1; source_sha=$env:GITHUB_SHA
        ordinary_manifest=(Get-QuotaFile (Join-Path $dist 'msvc-runtime.json')); files=$crtCopies.ToArray(); pe_images=$peFiles.ToArray()})
    $exeIdentity = Get-QuotaFile $qaExe; $coreIdentity = Get-QuotaFile $qaCore
    $receipt.private_binary = [ordered]@{exe=$exeIdentity; core=$coreIdentity}
    Assert-SwirlBuildSource -RepositoryRoot $repo -ExpectedSourceSha $env:GITHUB_SHA
    $tests = Join-Path $output 'tests'
    if (Test-Path -LiteralPath $tests) { throw 'Private UI tests require a new evidence subdirectory.' }
    $testEnvironment = @{
        SWIRL_PRIVATE_UI_EXE=$qaExe; SWIRL_PRIVATE_UI_EXE_SHA256=$exeIdentity.sha256
        SWIRL_PRIVATE_UI_CORE_SHA256=$coreIdentity.sha256; SWIRL_PRIVATE_EXPECTED_SOURCE=$env:GITHUB_SHA
        PYTHONDONTWRITEBYTECODE='1'
    }
    $null = Invoke-QuotaTool 'tests' $python @((Join-Path $repo 'tools/tests/test_private_subscription_ui.py'),'--evidence',$tests) `
        -Environment $testEnvironment -RemoveEnvironment @('SWIRL_PRIVATE_UI_QT_ROOT')
    $testPath = Join-Path $tests 'private-ui-quota-results.json'
    $result = Get-Content -LiteralPath $testPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $skipped = @($result.skipped)
    if ($result.schema -ne 1 -or $result.platform -cne 'win32' -or $result.testsRun -ne 10 -or
        $result.failures -ne 0 -or $result.errors -ne 0 -or $skipped.Count -ne 1 -or
        $skipped[0].test -cnotmatch '\.test_suspended_mode_rejects_before_non_windows_spawn$' -or
        $result.realNodeRequests -ne 0 -or $result.providerRequests -ne 0 -or $result.liveReady -ne $false) {
        throw 'Private Qt UI test inventory differs from 10 tests / 9 passes / one POSIX-only skip.'
    }
    if ((Get-SwirlMsvcHash $qaExe) -cne $exeIdentity.sha256 -or
        (Get-SwirlMsvcHash $qaCore) -cne $coreIdentity.sha256) { throw 'Private QA executable or DLL changed during tests.' }
    $receipt.test_inventory = [ordered]@{tests_run=10; passed=9; failures=0; errors=0; skipped=$skipped; original_report=(Get-QuotaFile $testPath)}
    # A separately built synthetic billing worker must never share the salted
    # private Qt DLL Cargo target or overwrite that DLL. The existing UI suite
    # above remains a separate 9-pass/one-POSIX-skip gate.
    $billingRust = Join-Path $qaBuild 'billing-rust-target'
    $billingWorker = Join-Path $billingRust 'x86_64-pc-windows-msvc/debug/swirl-private-worker.exe'
    $billingTests = Join-Path $output 'billing-tests'
    foreach ($path in @($billingRust,$billingWorker,$billingTests)) { Assert-SwirlPathWithoutLinks $path }
    if ((Test-Path -LiteralPath $billingRust) -or (Test-Path -LiteralPath $billingTests)) {
        throw 'Synthetic Qt billing requires a new independent Cargo target and evidence directory.'
    }
    $cargo = Resolve-SwirlMsvcPath (Get-QuotaCacheValue $privateCache 'SWIRL_CARGO')
    $null = Get-QuotaFile $cargo
    $billingWorkerBefore = $null
    $receipt.billing_scope = 'Same synthetic ledger, guarded Rust billing worker and actual Windows Qt quota; no provider authority or live readiness'
    $receipt.billing_rust_target = $billingRust
    $receipt.billing_binary_identity_unchanged = $false
    try {
        if ((Get-SwirlMsvcHash $qaExe) -cne $exeIdentity.sha256 -or
            (Get-SwirlMsvcHash $qaCore) -cne $coreIdentity.sha256) { throw 'Private QA identity changed before billing worker build.' }
        $null = Invoke-QuotaTool 'billing-worker-build' $cargo @('build','--locked',
            '--manifest-path',(Join-Path $repo 'core/Cargo.toml'),'-p','swirl-api',
            '--features','private-acceptance-worker','--bin','swirl-private-worker',
            '--target','x86_64-pc-windows-msvc','--target-dir',$billingRust) `
            -Environment @{SWIRL_SOURCE_SHA=$env:GITHUB_SHA; SWIRL_BUILD_ID='standalone'}
        $billingWorkerBefore = Get-QuotaFile $billingWorker
        if ([SwirlMsvcPackage.PeImage]::Read($billingWorker).Machine -cne '0x8664') {
            throw 'The designated synthetic billing worker is not AMD64.'
        }
        if ((Get-SwirlMsvcHash $qaExe) -cne $exeIdentity.sha256 -or
            (Get-SwirlMsvcHash $qaCore) -cne $coreIdentity.sha256) { throw 'Independent billing build changed the private QA executable or DLL.' }
        # WorkerIdentity.inspect executes only the explicitly built, hash-pinned
        # --build-info entry in OwnedProcess, and validates its exit and identity.
        # This entry sends no grant and does not execute a billing request.
        $billingIdentityCode = @'
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from PrivateSubscriptionSupervisor import WorkerIdentity
identity = WorkerIdentity.inspect(Path(sys.argv[2]), sys.argv[3], sys.argv[4])
identity.recheck()
print(json.dumps({"schema": 1, "factory": "PrivateSubscriptionSupervisor.WorkerIdentity.inspect",
                  "path": str(identity.path), "sha256": identity.sha256, "metadata": identity.metadata}, sort_keys=True))
'@
        $identityLog = Invoke-QuotaTool 'billing-worker-identity' $python @('-c',$billingIdentityCode,
            (Join-Path $repo 'tools'),$billingWorker,$env:GITHUB_SHA,$billingWorkerBefore.sha256) `
            -Environment @{PYTHONDONTWRITEBYTECODE='1'}
        $billingIdentity = Get-Content -LiteralPath $identityLog -Raw -Encoding UTF8 | ConvertFrom-Json
        $billingMetadata = $billingIdentity.metadata
        if ($billingIdentity.schema -ne 1 -or
            $billingIdentity.factory -cne 'PrivateSubscriptionSupervisor.WorkerIdentity.inspect' -or
            -not (Test-QuotaSamePath $billingIdentity.path $billingWorker) -or
            $billingIdentity.sha256 -cne $billingWorkerBefore.sha256 -or
            $billingMetadata.source_sha -cne $env:GITHUB_SHA -or
            $billingMetadata.build_id -cne 'standalone' -or
            $billingMetadata.target -cne 'x86_64-pc-windows-msvc' -or
            $billingMetadata.role -cne 'swirl_private_worker' -or
            $billingMetadata.guard_mode -cne 'mandatory_before_grant' -or
            $billingMetadata.abi_version -ne 1 -or $billingMetadata.private_worker_schema -ne 1 -or
            $billingMetadata.live -ne $false -or
            (Get-SwirlMsvcHash $billingWorker) -cne $billingWorkerBefore.sha256) {
            throw 'Synthetic billing worker factory identity differs from its designated Debug build.'
        }
        $receipt.billing_worker = [ordered]@{binary=$billingWorkerBefore; factory_identity=$billingIdentity
            original_identity_log=(Get-QuotaFile $identityLog); profile='Debug'; target='x86_64-pc-windows-msvc'}
        $billingTestEnvironment = $testEnvironment.Clone()
        $billingTestEnvironment.SWIRL_PRIVATE_WORKER = $billingWorker
        $billingTestEnvironment.SWIRL_PRIVATE_EXPECTED_WORKER_SHA256 = $billingWorkerBefore.sha256
        $null = Invoke-QuotaTool 'billing-tests' $python @(
            (Join-Path $repo 'tools/tests/test_private_subscription_ui_billing.py'),'--evidence',$billingTests) `
            -Environment $billingTestEnvironment -RemoveEnvironment @('SWIRL_PRIVATE_UI_QT_ROOT')
        $billingTestPath = Join-Path $billingTests 'private-ui-billing-results.json'
        $billingResult = Get-Content -LiteralPath $billingTestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($billingResult.schema -ne 1 -or $billingResult.platform -cne 'win32' -or
            $billingResult.testsRun -ne 10 -or $billingResult.failures -ne 0 -or $billingResult.errors -ne 0 -or
            @($billingResult.skipped).Count -ne 0 -or $billingResult.realNodeRequests -ne 0 -or
            $billingResult.providerRequests -ne 0 -or $billingResult.providerStatisticsAuthenticated -ne $false -or
            $billingResult.liveReady -ne $false) {
            throw 'Private Qt billing test inventory differs from 10 Windows tests / 10 passes / zero skips.'
        }
        $reportedWorker = $billingResult.identities.billingWorker
        foreach ($entry in $billingMetadata.PSObject.Properties) {
            if ($reportedWorker.PSObject.Properties[$entry.Name].Value -cne $entry.Value) {
                throw 'Actual billing suite worker metadata differs from the preflight factory identity.'
            }
        }
        $reportedUi = $billingResult.identities.qtUi
        if ($reportedWorker.exe_sha256 -cne $billingWorkerBefore.sha256 -or
            $reportedUi.role -cne 'swirl_private_qt_ui' -or $reportedUi.source_sha -cne $env:GITHUB_SHA -or
            $reportedUi.build_id -cne $pair.build_id -or $reportedUi.target -cne $pair.target -or
            $reportedUi.exe_sha256 -cne $exeIdentity.sha256 -or $reportedUi.core_sha256 -cne $coreIdentity.sha256 -or
            $reportedUi.qt_version -cne '6.12.0' -or $reportedUi.guard_mode -cne 'mandatory_before_grant' -or
            $reportedUi.abi_version -ne 1 -or $reportedUi.private_worker_schema -ne 1 -or $reportedUi.live -ne $false) {
            throw 'Actual billing suite Qt and worker identities differ from their separate designated binaries.'
        }
        $receipt.billing_test_inventory = [ordered]@{tests_run=10; passed=10; failures=0; errors=0; skipped=@()
            original_report=(Get-QuotaFile $billingTestPath); identities=$billingResult.identities}
        # Additional fixed synthetic workflow. The original 9+1 UI and 10+0
        # billing gates above keep their exact assertions and source identity.
        $importTests = Join-Path $output 'import-tests'
        if (Test-Path -LiteralPath $importTests) { throw 'Private UI import evidence must be new.' }
        $null = Invoke-QuotaTool 'import-tests' $python @(
            (Join-Path $repo 'tools/tests/test_private_subscription_ui_import.py'),'--evidence',$importTests) `
            -Environment $billingTestEnvironment -RemoveEnvironment @('SWIRL_PRIVATE_UI_QT_ROOT')
        $importTestPath = Join-Path $importTests 'private-ui-import-results.json'
        $importResult = Get-Content -LiteralPath $importTestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($importResult.schema -ne 1 -or $importResult.platform -cne 'win32' -or
            $importResult.testsRun -ne 14 -or $importResult.failures -ne 0 -or $importResult.errors -ne 0 -or
            @($importResult.skipped).Count -ne 0 -or $importResult.realNodeRequests -ne 0 -or
            $importResult.providerRequests -ne 0 -or $importResult.providerStatisticsAuthenticated -ne $false -or
            $importResult.liveReady -ne $false) {
            throw 'Private Qt import inventory differs from 14 Windows tests / 14 passes / zero skips.'
        }
        $importWorker = $importResult.identities.billingWorker
        foreach ($entry in $billingMetadata.PSObject.Properties) {
            if ($importWorker.PSObject.Properties[$entry.Name].Value -cne $entry.Value) {
                throw 'Import suite billing worker differs from its designated factory identity.'
            }
        }
        $importUi = $importResult.identities.qtUi
        if ($importWorker.exe_sha256 -cne $billingWorkerBefore.sha256 -or
            $importUi.source_sha -cne $env:GITHUB_SHA -or $importUi.build_id -cne $pair.build_id -or
            $importUi.target -cne $pair.target -or $importUi.role -cne 'swirl_private_qt_ui' -or
            $importUi.exe_sha256 -cne $exeIdentity.sha256 -or $importUi.core_sha256 -cne $coreIdentity.sha256 -or
            $importUi.qt_version -cne '6.12.0' -or $importUi.guard_mode -cne 'mandatory_before_grant' -or
            $importUi.abi_version -ne 1 -or $importUi.private_worker_schema -ne 1 -or $importUi.live -ne $false) {
            throw 'Import suite Qt/worker identity differs from the separate designated binaries.'
        }
        $receipt.import_test_inventory = [ordered]@{tests_run=14; passed=14; failures=0; errors=0; skipped=@()
            original_report=(Get-QuotaFile $importTestPath); identities=$importResult.identities}
        # Separate DoT variant: retain the original 14 import assertions above.
        # Six is the Rust outbound attempt cap, not the local HMAC IPC count.
        $dnsTests = Join-Path $output 'dns-tests'
        if (Test-Path -LiteralPath $dnsTests) { throw 'Private UI DNS evidence must be new.' }
        $null = Invoke-QuotaTool 'dns-tests' $python @(
            (Join-Path $repo 'tools/tests/test_private_subscription_ui_dns.py'),'--evidence',$dnsTests) `
            -Environment $billingTestEnvironment -RemoveEnvironment @('SWIRL_PRIVATE_UI_QT_ROOT')
        $dnsTestPath = Join-Path $dnsTests 'private-ui-dns-results.json'
        $dnsResult = Get-Content -LiteralPath $dnsTestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($dnsResult.schema -ne 1 -or $dnsResult.platform -cne 'win32' -or
            $dnsResult.testsRun -ne 11 -or $dnsResult.failures -ne 0 -or $dnsResult.errors -ne 0 -or
            @($dnsResult.skipped).Count -ne 0 -or $dnsResult.realNodeRequests -ne 0 -or
            $dnsResult.providerRequests -ne 0 -or $dnsResult.providerStatisticsAuthenticated -ne $false -or
            $dnsResult.liveReady -ne $false) {
            throw 'Private Qt DNS inventory differs from 11 Windows tests / 11 passes / zero skips.'
        }
        $dnsWorker = $dnsResult.identities.billingWorker
        foreach ($entry in $billingMetadata.PSObject.Properties) {
            if ($dnsWorker.PSObject.Properties[$entry.Name].Value -cne $entry.Value) {
                throw 'DNS suite billing worker differs from its designated factory identity.'
            }
        }
        $dnsUi = $dnsResult.identities.qtUi
        if ($dnsWorker.exe_sha256 -cne $billingWorkerBefore.sha256 -or
            $dnsUi.source_sha -cne $env:GITHUB_SHA -or $dnsUi.build_id -cne $pair.build_id -or
            $dnsUi.target -cne $pair.target -or $dnsUi.role -cne 'swirl_private_qt_ui' -or
            $dnsUi.exe_sha256 -cne $exeIdentity.sha256 -or $dnsUi.core_sha256 -cne $coreIdentity.sha256 -or
            $dnsUi.qt_version -cne '6.12.0' -or $dnsUi.guard_mode -cne 'mandatory_before_grant' -or
            $dnsUi.abi_version -ne 1 -or $dnsUi.private_worker_schema -ne 1 -or $dnsUi.live -ne $false) {
            throw 'DNS suite Qt/worker identity differs from the separate designated binaries.'
        }
        $receipt.dns_test_inventory = [ordered]@{tests_run=11; passed=11; failures=0; errors=0; skipped=@()
            original_report=(Get-QuotaFile $dnsTestPath); identities=$dnsResult.identities
            scope='fixed DoT through production Resolver; six Rust outbound attempts and separate local ownership IPC'}
    } finally {
        # Run even after a failed test. Keep the original error while recording
        # any changed or missing private binary; the outer ordinary-runtime
        # comparison remains unchanged and runs independently below.
        try {
            $billingAfter = [ordered]@{exe=(Get-QuotaFile $qaExe); core=(Get-QuotaFile $qaCore); worker=$null}
            if ($null -ne $billingWorkerBefore) { $billingAfter.worker = Get-QuotaFile $billingWorker }
            Write-QuotaJson (Join-Path $output 'billing-binary-identity.json') ([ordered]@{schema=1
                source_sha=$env:GITHUB_SHA
                before=[ordered]@{exe=$exeIdentity; core=$coreIdentity; worker=$billingWorkerBefore}
                after=$billingAfter})
            if ($billingAfter.exe.sha256 -cne $exeIdentity.sha256 -or
                $billingAfter.core.sha256 -cne $coreIdentity.sha256 -or
                ($null -ne $billingWorkerBefore -and $billingAfter.worker.sha256 -cne $billingWorkerBefore.sha256)) {
                throw 'Private Qt executable, paired DLL or independent billing worker changed during billing acceptance.'
            }
            $receipt.billing_binary_identity_unchanged = ($null -ne $billingWorkerBefore)
        } catch { $errors.Add('PrivateBillingBinaryIdentityFailed: '+$_.Exception.Message) }
    }
    $receipt.status = 'passed'; $receipt.success = $true
} catch {
    $primary = $_.Exception
    $errors.Add($_.Exception.GetType().FullName+': '+$_.Exception.Message)
} finally {
    try { Save-QuotaPartialBuildMetadata } catch { $errors.Add('PartialBuildEvidenceFailed: '+$_.Exception.Message) }
    if ($sourceVerified) {
        try { Assert-SwirlBuildSource -RepositoryRoot $repo -ExpectedSourceSha $env:GITHUB_SHA }
        catch { $errors.Add('FinalSourceIdentityFailed: '+$_.Exception.Message) }
    }
    if ($null -ne $before) {
        try {
            foreach ($path in @($dist,$product)) { Assert-QuotaNormalDirectory $path }
            $after = [ordered]@{dist=@(Get-QuotaTree $dist); installer_bin=@(Get-QuotaTree $product)}
            Write-QuotaJson (Join-Path $output 'ordinary-runtime-after.json') $after
            if ((ConvertTo-Json -InputObject $before -Depth 5 -Compress) -cne
                (ConvertTo-Json -InputObject $after -Depth 5 -Compress)) { throw 'The separate QA build changed an ordinary runtime.' }
            $receipt.ordinary_runtimes_unchanged = $true
        } catch { $errors.Add('OrdinaryRuntimeIsolationFailed: '+$_.Exception.Message) }
    }
    if ($errors.Count) { $receipt.status='failed'; $receipt.success=$false }
    $receipt.finished_utc = [DateTime]::UtcNow.ToString('o')
    $receipt.steps = $steps.ToArray(); $receipt.errors = $errors.ToArray()
    Write-QuotaJson (Join-Path $output 'receipt.json') $receipt
}
if ($null -ne $primary) { throw $primary }
if (-not $receipt.success) { throw 'Private Qt quota profile acceptance or evidence preservation failed.' }
Write-Host 'Verified separate private Qt quota profile: 9 Windows-applicable tests passed; one POSIX-only control skipped.'
Write-Host 'Verified same-ledger synthetic Qt billing: 10 Windows tests passed; zero skips; live remains unavailable.'
Write-Host 'Verified owned HTTPS subscription UI: 14 Windows tests passed; zero skips; no real-provider authority.'
Write-Host 'Verified fixed DoT UI variant: 11 Windows tests passed; zero skips; original six-attempt/eight-second grant unchanged.'
