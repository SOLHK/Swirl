# Package the normal Qt Swirl UI with its in-process Rust core. No Mihomo binary,
# test harness, private NodeStore, or user network setting is included.
param(
    [Parameter(Mandatory=$true)][string]$QtDir,
    [Parameter(Mandatory=$true)][string]$MinGwBin,
    [string]$Nsis = 'D:\Codex\toolchains\nsis-3.11\makensis.exe',
    [string]$BuildDir = 'build\rust-product',
    [string]$OutRoot = 'D:\Codex\outputs'
)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$build=[IO.Path]::GetFullPath((Join-Path $repo $BuildDir))
$qt=(Resolve-Path -LiteralPath $QtDir).Path
$mingw=(Resolve-Path -LiteralPath $MinGwBin).Path
$out=[IO.Path]::GetFullPath($OutRoot).TrimEnd('\')
$dRoot=[IO.Path]::GetFullPath('D:\Codex\')
if(-not $build.StartsWith($dRoot,[StringComparison]::OrdinalIgnoreCase) -or
   -not $out.StartsWith($dRoot,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build and output paths must stay under D:\Codex.'
}
if(-not (Test-Path -LiteralPath $Nsis -PathType Leaf) -or
   -not (Test-Path -LiteralPath (Join-Path $qt 'bin\windeployqt.exe') -PathType Leaf)) {
    throw 'NSIS or Qt deployment tool is missing.'
}
$dirty=& git -C $repo status --porcelain
if($LASTEXITCODE -ne 0 -or $dirty) { throw 'Commit source changes before packaging an exact SHA.' }
$sourceSha=(& git -C $repo rev-parse HEAD).Trim()
if($LASTEXITCODE -ne 0 -or $sourceSha -notmatch '^[0-9a-f]{40}$') { throw 'Source SHA is unavailable.' }
$cachePath=Join-Path $build 'CMakeCache.txt'
if(-not (Test-Path -LiteralPath $cachePath -PathType Leaf)) { throw 'CMake cache is missing.' }
$cache=Get-Content -LiteralPath $cachePath -Raw
if($cache -notmatch '(?m)^CMAKE_BUILD_TYPE:STRING=Release\s*$' -or
   $cache -notmatch '(?m)^SWIRL_USE_RUST_CORE:BOOL=ON\s*$' -or
   $cache -notmatch '(?m)^SWIRL_BUILD_UI_TESTS:BOOL=OFF\s*$' -or
   $cache -notmatch '(?m)^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$') {
    throw 'A Release Rust product build with UI tests OFF is required.'
}
$sourceHome=$Matches[1].Trim().Replace('/','\')
if(-not [string]::Equals([IO.Path]::GetFullPath($sourceHome),
    [IO.Path]::GetFullPath((Join-Path $repo 'src\Swirl.Quick')),[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build source checkout does not match this repository.'
}
$exe=Join-Path $build 'Swirl.exe'
$dll=Join-Path $build 'swirl_api.dll'
$rustDll=Join-Path $build 'rust-target\release\swirl_api.dll'
foreach($path in @($exe,$dll,$rustDll)) {
    if(-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required build file missing: $path" }
}
$exeHash=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
$dllHash=(Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash
if($dllHash -ne (Get-FileHash -LiteralPath $rustDll -Algorithm SHA256).Hash) {
    throw 'Deployed Rust DLL is stale.'
}
# The Qt executable embeds SWIRL_SOURCE_SHA as a UTF-16 QString literal.
$bytes=[IO.File]::ReadAllBytes($exe)
$needle=[Text.Encoding]::Unicode.GetBytes($sourceSha)
$shaFound=$false
for($i=0;$i -le $bytes.Length-$needle.Length;$i++) {
    if($bytes[$i] -ne $needle[0]) { continue }
    $j=1
    while($j -lt $needle.Length -and $bytes[$i+$j] -eq $needle[$j]) { $j++ }
    if($j -eq $needle.Length) { $shaFound=$true;break }
}
if(-not $shaFound) { throw 'Swirl.exe does not embed this source SHA.' }
if(-not (Test-Path -LiteralPath $out -PathType Container)) {
    New-Item -ItemType Directory -Path $out -ErrorAction Stop | Out-Null
}
$name='Swirl-Rust-App-'+$sourceSha.Substring(0,12)+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss')
$stage=Join-Path $out $name
if(Test-Path -LiteralPath $stage) { throw 'Fresh staging directory required.' }
New-Item -ItemType Directory -Path $stage -ErrorAction Stop | Out-Null
foreach($file in @('Swirl.exe','swirl_api.dll','SwirlProxyGuard.exe',
    'SwirlGatewayGuard.exe','SwirlScriptRunner.exe','SwirlCodexLauncher.exe',
    'SwirlCodexManage.py','SubscriptionCapture.py')) {
    $from=Join-Path $build $file
    if(-not (Test-Path -LiteralPath $from -PathType Leaf)) { throw "Companion missing: $file" }
    Copy-Item -LiteralPath $from -Destination (Join-Path $stage $file) -ErrorAction Stop
}
foreach($file in @('libgcc_s_seh-1.dll','libstdc++-6.dll','libwinpthread-1.dll')) {
    $from=Join-Path $mingw $file
    if(-not (Test-Path -LiteralPath $from -PathType Leaf)) { throw "MinGW runtime missing: $file" }
    Copy-Item -LiteralPath $from -Destination (Join-Path $stage $file) -ErrorAction Stop
}
Copy-Item -LiteralPath (Join-Path $repo 'src\Swirl.Quick\packaging\rules') -Destination (Join-Path $stage 'rules') -Recurse -ErrorAction Stop
$icon=Join-Path $build 'brand\Swirl.ico'
if(-not (Test-Path -LiteralPath $icon -PathType Leaf)) { throw 'Built Swirl icon is missing.' }
Copy-Item -LiteralPath $icon -Destination (Join-Path $stage 'Swirl-brand-phase3.ico') -ErrorAction Stop
Copy-Item -LiteralPath $icon -Destination (Join-Path $stage 'Swirl-brand-phase3-v2.ico') -ErrorAction Stop
New-Item -ItemType Directory -Path (Join-Path $stage 'licenses') -ErrorAction Stop | Out-Null
foreach($license in @('fkYAML-MIT.txt','FreeType-FTL.txt','GCC-exception-3.1.txt',
    'GPL-3.0-only.txt','HarmonyOS-Sans.txt','LGPL-3.0-only.txt',
    'nghttp2-MIT.txt','rust-browser-tls-dependencies.txt',
    'rust-reality-dependencies.txt','winpthreads-COPYING.txt')) {
    Copy-Item -LiteralPath (Join-Path $repo ('src\Swirl.Quick\packaging\licenses\'+$license)) -Destination (Join-Path $stage 'licenses') -ErrorAction Stop
}
Copy-Item -LiteralPath (Join-Path $repo 'src\Swirl.Quick\packaging\README-RustProductPreview.txt') -Destination (Join-Path $stage 'README-先看.txt') -ErrorAction Stop
@'
Swirl Core Windows preview

This normal Swirl Qt interface uses an in-process Rust proxy core. No Mihomo
executable is included or used as a fallback. Rust sessions reject unsupported
node capabilities and network modes rather than silently downgrading.

Qt 6.10.3 is dynamically linked under LGPL-3.0. The required Qt, FreeType,
GCC runtime, winpthreads, nghttp2, fkYAML, Rust TLS/REALITY dependencies,
HarmonyOS Sans fonts, and rules data retain their notices in licenses/ and
rules/. The Qt libraries can be replaced with compatible modified versions
as permitted by the LGPL.

Source: https://github.com/SOLHK/Swirl
Qt deployment: https://doc.qt.io/qt-6.10/windows-deployment.html
'@ | Set-Content -LiteralPath (Join-Path $stage 'THIRD_PARTY_NOTICES.txt') -Encoding utf8
$oldPath=$env:PATH
try {
    $env:PATH="$mingw;$(Join-Path $qt 'bin');$env:PATH"
    $deployOutput=@(& (Join-Path $qt 'bin\windeployqt.exe') --release --qmldir (Join-Path $repo 'src\Swirl.Quick\qml') (Join-Path $stage 'Swirl.exe') 2>&1)
    $deployExit=$LASTEXITCODE
} finally { $env:PATH=$oldPath }
if($deployExit -ne 0) { throw "Qt deployment failed with exit code $deployExit." }
foreach($file in @('Qt6Core.dll','Qt6Gui.dll','Qt6Qml.dll','Qt6Quick.dll','platforms\qwindows.dll')) {
    if(-not (Test-Path -LiteralPath (Join-Path $stage $file) -PathType Leaf)) {
        throw "Qt dependency missing: $file"
    }
}
$forbidden=@(Get-ChildItem -LiteralPath $stage -File -Recurse | Where-Object {
    $_.Name -match '(?i)^(mihomo\.exe|nodes\.dpapi|nodes\.dpapi\.selected|runtime-state\.json|TEST-SWIRL-NETWORK\.cmd)$'
})
if($forbidden.Count -gt 0 -or (Test-Path -LiteralPath (Join-Path $stage 'core'))) {
    throw 'Mihomo, test harness, or private runtime material entered the app package.'
}
$product=[ordered]@{
    kind='windows-rust-product-preview';sourceSha=$sourceSha
    exeSha256=$exeHash;rustDllSha256=$dllHash
    rustCore=$true;uiTestHarness=$false;mihomoBundled=$false;privateNodeStoreBundled=$false
    createdUtc=[DateTime]::UtcNow.ToString('o')
}
$product | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $stage 'PRODUCT.json') -Encoding utf8
@"
Swirl Core Windows product preview
Source SHA: $sourceSha
Swirl.exe SHA-256: $exeHash
swirl_api.dll SHA-256: $dllHash
Release build: SWIRL_USE_RUST_CORE=ON, SWIRL_BUILD_UI_TESTS=OFF
No Mihomo binary or private NodeStore is bundled.
This is a limited Rust-core preview, not a Mihomo feature-parity release.
"@ | Set-Content -LiteralPath (Join-Path $stage 'BUILD.txt') -Encoding utf8
$files=@(Get-ChildItem -LiteralPath $stage -File -Recurse -Force -ErrorAction Stop | Sort-Object FullName)
$dirs=@(Get-ChildItem -LiteralPath $stage -Directory -Recurse -Force -ErrorAction Stop | Sort-Object { $_.FullName.Length } -Descending)
$installRoot='D:\Codex\SwirlRust'
$uninstall=[Collections.Generic.List[string]]::new()
foreach($file in $files) {
    if(($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Linked package file: $($file.Name)" }
    $relative=$file.FullName.Substring($stage.Length+1)
    if($relative -match '["$\r\n]' -or $installRoot.Length+1+$relative.Length -ge 240) {
        throw "Unsupported or overly long install path: $relative"
    }
    $uninstall.Add('Delete "$INSTDIR\'+$relative+'"')
}
foreach($dir in $dirs) {
    if(($dir.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Linked package directory: $($dir.Name)" }
    $relative=$dir.FullName.Substring($stage.Length+1)
    if($relative -match '["$\r\n]') { throw "Unsupported install directory: $relative" }
    $uninstall.Add('RMDir "$INSTDIR\'+$relative+'"')
}
$temp=Join-Path 'D:\Codex\tmp' ('swirl-rust-product-installer-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp -ErrorAction Stop | Out-Null
$uninstallPath=Join-Path $temp 'UninstallFiles.nsh'
$uninstall | Set-Content -LiteralPath $uninstallPath -Encoding utf8
$short=$sourceSha.Substring(0,12)
$setupId=$short+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss')
$setup=Join-Path $out ('Swirl-Rust-Core-Setup-'+$setupId+'.exe')
if(Test-Path -LiteralPath $setup) { throw 'Fresh installer output path required.' }
$nsi=Join-Path $repo 'src\Swirl.Quick\packaging\SwirlRustProduct.nsi'
$arguments=@('/V2','/INPUTCHARSET','UTF8',
    "/DAPP_DIST=$stage", "/DOUT_DIR=$out", "/DUNINSTALL_LIST=$uninstallPath",
    "/DSOURCE_SHORT=$setupId", "/DSOURCE_SHA=$sourceSha", $nsi)
$compilerOutput=@(& $Nsis @arguments 2>&1)
$compilerExit=$LASTEXITCODE
$compilerOutput | Set-Content -LiteralPath (Join-Path $temp 'makensis.log') -Encoding utf8
if($compilerExit -ne 0 -or -not (Test-Path -LiteralPath $setup -PathType Leaf)) {
    throw "NSIS failed with exit code $compilerExit; see $temp"
}
$result=[ordered]@{
    kind='windows-rust-product-preview';sourceSha=$sourceSha
    stage=$stage;setup=$setup;setupSha256=(Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash
    setupBytes=(Get-Item -LiteralPath $setup).Length
    exeSha256=$exeHash;rustDllSha256=$dllHash
    fileCount=$files.Count;mihomoBundled=$false;privateNodeStoreBundled=$false
    signed=(Get-AuthenticodeSignature -LiteralPath $setup).Status -eq 'Valid'
}
$result | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath ($setup+'.json') -Encoding utf8
$result | ConvertTo-Json -Depth 3
