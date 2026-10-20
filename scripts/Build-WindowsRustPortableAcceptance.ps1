# Packages a test-build Rust/Qt executable and a self-contained one-click check.
# This is a development acceptance preview, not the ordinary-user release.
param(
    [Parameter(Mandatory=$true)][string]$QtDir,
    [string]$MinGwBin = '',
    [string]$PowerShellRuntimeDir = '',
    [string]$BuildDir = 'build\rust-qt',
    [string]$OutRoot = 'D:\Codex\outputs'
)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
$repo=(Resolve-Path -LiteralPath $repo).Path
$build=[IO.Path]::GetFullPath((Join-Path $repo $BuildDir))
$qt=(Resolve-Path -LiteralPath $QtDir).Path
$mingw=if($MinGwBin) {
    (Resolve-Path -LiteralPath $MinGwBin).Path
} else {
    (Resolve-Path -LiteralPath (Join-Path (Split-Path (Split-Path $qt -Parent) -Parent) 'Tools\mingw1310_64\bin')).Path
}
$pwshSource=if($PowerShellRuntimeDir) {
    (Resolve-Path -LiteralPath $PowerShellRuntimeDir).Path
} else {
    Split-Path (Get-Command pwsh -ErrorAction Stop).Source -Parent
}
$pwshExe=Join-Path $pwshSource 'pwsh.exe'
if(-not (Test-Path -LiteralPath $pwshExe -PathType Leaf) -or
   -not (Test-Path -LiteralPath (Join-Path $pwshSource 'LICENSE.txt') -PathType Leaf) -or
   -not (Test-Path -LiteralPath (Join-Path $pwshSource 'ThirdPartyNotices.txt') -PathType Leaf)) {
    throw 'Complete licensed PowerShell runtime is missing.'
}
$pwshSignature=Get-AuthenticodeSignature -LiteralPath $pwshExe
if($pwshSignature.Status -ne 'Valid' -or
   $pwshSignature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
    throw 'PowerShell runtime signature is not valid Microsoft code.'
}
$out=[IO.Path]::GetFullPath($OutRoot)
if(-not $out.StartsWith([IO.Path]::GetFullPath('D:\Codex\'),[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Output must remain under D:\Codex.'
}
if(-not (Test-Path -LiteralPath (Join-Path $qt 'bin\windeployqt.exe') -PathType Leaf)) {
    throw 'Qt windeployqt.exe is missing.'
}
if(-not (Test-Path -LiteralPath (Join-Path $mingw 'objdump.exe') -PathType Leaf)) {
    throw 'MinGW objdump.exe is missing.'
}
$dirty=& git -C $repo status --porcelain
if($LASTEXITCODE -ne 0 -or $dirty) { throw 'Commit source changes before exact-SHA packaging.' }
$sourceSha=(& git -C $repo rev-parse HEAD).Trim()
if($LASTEXITCODE -ne 0 -or $sourceSha -notmatch '^[0-9a-f]{40}$') { throw 'Git source SHA unavailable.' }
$cachePath=Join-Path $build 'CMakeCache.txt'
if(-not (Test-Path -LiteralPath $cachePath -PathType Leaf)) { throw 'CMake cache missing.' }
$cache=Get-Content -LiteralPath $cachePath -Raw
if($cache -notmatch '(?m)^CMAKE_BUILD_TYPE:STRING=Release\s*$' -or
   $cache -notmatch '(?m)^SWIRL_USE_RUST_CORE:BOOL=ON\s*$' -or
   $cache -notmatch '(?m)^SWIRL_BUILD_UI_TESTS:BOOL=ON\s*$' -or
   $cache -notmatch '(?m)^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$') {
    throw 'Build is not the required Release Rust test-build configuration.'
}
$homeDir=$Matches[1].Trim().Replace('/','\')
if(-not [string]::Equals([IO.Path]::GetFullPath($homeDir),
    [IO.Path]::GetFullPath((Join-Path $repo 'src\Swirl.Quick')),[StringComparison]::OrdinalIgnoreCase)) {
    throw 'CMake source directory does not match this checkout.'
}
$exe=Join-Path $build 'Swirl.exe'
$dll=Join-Path $build 'swirl_api.dll'
foreach($path in @($exe,$dll)) {
    if(-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required build file missing: $path" }
}
$exeHash=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
$dllHash=(Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash
# The UI test binary embeds SWIRL_SOURCE_SHA as a UTF-16 QString literal.
# Reject a stale binary even if CMakeCache was configured for the new checkout.
$bytes=[IO.File]::ReadAllBytes($exe)
$needle=[Text.Encoding]::Unicode.GetBytes($sourceSha)
$shaFound=$false
for($i=0;$i -le $bytes.Length-$needle.Length;$i++) {
    if($bytes[$i] -ne $needle[0]) { continue }
    $j=1
    while($j -lt $needle.Length -and $bytes[$i+$j] -eq $needle[$j]) { $j++ }
    if($j -eq $needle.Length) { $shaFound=$true;break }
}
if(-not $shaFound) { throw 'Swirl.exe does not embed the exact source SHA.' }
if(-not (Test-Path -LiteralPath $out -PathType Container)) {
    New-Item -ItemType Directory -Path $out -ErrorAction Stop | Out-Null
}
$name='Swirl-Rust-Portable-Check-'+$sourceSha.Substring(0,12)+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss')
$stage=Join-Path $out $name
$zip=Join-Path $out ($name+'.zip')
if((Test-Path -LiteralPath $stage) -or (Test-Path -LiteralPath $zip)) {
    throw 'Fresh package path required; existing output was preserved.'
}
New-Item -ItemType Directory -Path $stage -ErrorAction Stop | Out-Null
foreach($file in @('Swirl.exe','swirl_api.dll','SwirlProxyGuard.exe',
    'SwirlGatewayGuard.exe','SwirlScriptRunner.exe','SwirlCodexLauncher.exe',
    'SwirlCodexManage.py','SubscriptionCapture.py')) {
    $from=Join-Path $build $file
    if(-not (Test-Path -LiteralPath $from -PathType Leaf)) { throw "Required companion missing: $file" }
    Copy-Item -LiteralPath $from -Destination (Join-Path $stage $file) -ErrorAction Stop
}
foreach($file in @('libgcc_s_seh-1.dll','libstdc++-6.dll','libwinpthread-1.dll')) {
    Copy-Item -LiteralPath (Join-Path $build $file) -Destination (Join-Path $stage $file) -ErrorAction Stop
}
Copy-Item -LiteralPath (Join-Path $repo 'src\Swirl.Quick\packaging\rules') -Destination (Join-Path $stage 'rules') -Recurse -ErrorAction Stop
New-Item -ItemType Directory -Path (Join-Path $stage 'tools'),(Join-Path $stage 'licenses') -ErrorAction Stop | Out-Null
Copy-Item -LiteralPath (Join-Path $repo 'tools\Invoke-WindowsRustAcceptance.ps1') -Destination (Join-Path $stage 'tools') -ErrorAction Stop
Copy-Item -LiteralPath (Join-Path $repo 'tools\Invoke-WindowsRustPortableCheck.ps1') -Destination (Join-Path $stage 'tools') -ErrorAction Stop
Copy-Item -LiteralPath (Join-Path $repo 'tools\TEST-SWIRL-NETWORK.cmd') -Destination (Join-Path $stage 'TEST-SWIRL-NETWORK.cmd') -ErrorAction Stop
$runtimeTarget=Join-Path $stage 'runtime\powershell'
New-Item -ItemType Directory -Path $runtimeTarget -ErrorAction Stop | Out-Null
foreach($item in @(Get-ChildItem -LiteralPath $pwshSource -Force -ErrorAction Stop)) {
    Copy-Item -LiteralPath $item.FullName -Destination $runtimeTarget -Recurse -Force -ErrorAction Stop
}
if(-not (Test-Path -LiteralPath (Join-Path $runtimeTarget 'pwsh.exe') -PathType Leaf) -or
   -not (Test-Path -LiteralPath (Join-Path $runtimeTarget 'LICENSE.txt') -PathType Leaf) -or
   -not (Test-Path -LiteralPath (Join-Path $runtimeTarget 'ThirdPartyNotices.txt') -PathType Leaf)) {
    throw 'Bundled PowerShell runtime is incomplete.'
}
$bundledVersion=(& (Join-Path $runtimeTarget 'pwsh.exe') -NoProfile -Command '$PSVersionTable.PSVersion.ToString()').Trim()
if($LASTEXITCODE -ne 0 -or $bundledVersion -notmatch '^7\.') {
    throw 'Bundled PowerShell runtime cannot launch.'
}
foreach($file in @('fkYAML-MIT.txt','FreeType-FTL.txt','GCC-exception-3.1.txt',
    'GPL-3.0-only.txt','HarmonyOS-Sans.txt','LGPL-3.0-only.txt',
    'nghttp2-MIT.txt','rust-browser-tls-dependencies.txt',
    'rust-reality-dependencies.txt','winpthreads-COPYING.txt')) {
    Copy-Item -LiteralPath (Join-Path $repo ('src\Swirl.Quick\packaging\licenses\'+$file)) -Destination (Join-Path $stage 'licenses') -ErrorAction Stop
}
$previousPath=$env:PATH
try {
    $env:PATH="$mingw;$(Join-Path $qt 'bin');$env:PATH"
    & (Join-Path $qt 'bin\windeployqt.exe') --release --qmldir (Join-Path $repo 'src\Swirl.Quick\qml') (Join-Path $stage 'Swirl.exe')
    if($LASTEXITCODE -ne 0) { throw 'windeployqt failed.' }
} finally {
    $env:PATH=$previousPath
}
foreach($file in @('Qt6Core.dll','Qt6Gui.dll','Qt6Qml.dll','Qt6Quick.dll','Qt6Test.dll','platforms\qwindows.dll')) {
    if(-not (Test-Path -LiteralPath (Join-Path $stage $file) -PathType Leaf)) {
        throw "Deployed Qt dependency missing: $file"
    }
}
$manifest=[ordered]@{
    schemaVersion=1;kind='windows-rust-acceptance-preview';sourceSha=$sourceSha
    exeSha256=$exeHash;rustDllSha256=$dllHash
    acceptanceScriptSha256=(Get-FileHash -LiteralPath (Join-Path $stage 'tools\Invoke-WindowsRustAcceptance.ps1') -Algorithm SHA256).Hash
    portableRunnerSha256=(Get-FileHash -LiteralPath (Join-Path $stage 'tools\Invoke-WindowsRustPortableCheck.ps1') -Algorithm SHA256).Hash
    launcherCmdSha256=(Get-FileHash -LiteralPath (Join-Path $stage 'TEST-SWIRL-NETWORK.cmd') -Algorithm SHA256).Hash
    bundledPowerShellSha256=(Get-FileHash -LiteralPath (Join-Path $runtimeTarget 'pwsh.exe') -Algorithm SHA256).Hash
    bundledPowerShellVersion=$bundledVersion
    rustCore=$true;uiTestHarness=$true;privateNodeStoreBundled=$false;mihomoBundled=$false
    createdUtc=[DateTime]::UtcNow.ToString('o')
}
$manifest | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $stage 'PACKAGE.json') -Encoding utf8
@"
Swirl Rust Windows development acceptance preview
Source SHA: $sourceSha
Swirl.exe SHA-256: $exeHash
swirl_api.dll SHA-256: $dllHash
Build: Release, SWIRL_USE_RUST_CORE=ON, SWIRL_BUILD_UI_TESTS=ON
This is a test harness package, not the ordinary-user release.
Mihomo binary and private NodeStore are not bundled.
PowerShell $bundledVersion runtime is bundled under runtime/powershell.
"@ | Set-Content -LiteralPath (Join-Path $stage 'BUILD.txt') -Encoding utf8
@'
Swirl Rust 便携联网测试包（开发验收版）

1. 保持 Mihomo 正常运行，先双击 TEST-SWIRL-NETWORK.cmd。
2. 黑色窗口会分别显示“电脑当前代理控制请求”和“Swirl Rust 显式代理”。等它写出结果后按任意键关闭。
3. 如果 Codex 或浏览器断网，仍可在同一窗口看 Swirl 的结果；普通应用是否能联网与 Swirl 显式请求是两件事。
4. 结果只保存在 D:\Codex\Swirl-acceptance-private-20261020\portable-runs；打开最新 run-* 目录里的“结果-直接看.txt”即可，包内没有私有 NodeStore。
5. 不要直接双击 Swirl.exe 来做这个隔离测试；那会使用普通应用的单实例和用户配置。
包内自带 PowerShell 7；你不需要单独安装，也不需要先打开 CMD 再双击 Swirl.exe。

脚本不会关闭/暂停 Mihomo，不会修改 Windows 系统代理、TUN、路由或 DNS。
每个 curl 请求最多 20 秒，整轮子进程最多 270 秒；如果某项失败，会显示 FAIL 并保留脱敏结果。
“Swirl Rust 显式代理 PASS”只证明本次请求通过测试版 Swirl Rust；完整 Mihomo 独立性仍需另外证明。
如果 D 盘加密 NodeStore 副本不存在，脚本会报告 BLOCKED，不会尝试下载订阅。
'@ | Set-Content -LiteralPath (Join-Path $stage 'README-先看.txt') -Encoding utf8
@'
This development preview contains an in-process Rust proxy core and dynamically
linked Qt 6.10.3/MinGW runtime libraries. It does not bundle Mihomo. The
separate Mihomo compatibility notice from the ordinary package does not apply.
Qt is used under LGPL-3.0; FreeType, GCC runtime, winpthreads, nghttp2,
fkYAML, Rust browser TLS dependencies, and the bundled HarmonyOS Sans font
retain their applicable notices and license texts in licenses/.
PowerShell 7 is bundled under runtime/powershell with its LICENSE.txt and
ThirdPartyNotices.txt; pwsh.exe was Authenticode-verified as Microsoft code.
See source: https://github.com/SOLHK/Swirl
Qt deployment reference: https://doc.qt.io/qt-6.10/windows-deployment.html
'@ | Set-Content -LiteralPath (Join-Path $stage 'THIRD_PARTY_NOTICES.txt') -Encoding utf8
$forbidden=@(Get-ChildItem -LiteralPath $stage -File -Recurse | Where-Object {
    $_.Name -match '(?i)^(mihomo\.exe|nodes\.dpapi|nodes\.dpapi\.selected|runtime-state\.json)$'
})
if($forbidden.Count -gt 0) { throw 'Private material or Mihomo found in package.' }
Compress-Archive -LiteralPath $stage -DestinationPath $zip -CompressionLevel Optimal -ErrorAction Stop
[pscustomobject]@{
    sourceSha=$sourceSha;folder=$stage;zip=$zip
    zipSha256=(Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
    exeSha256=$exeHash;rustDllSha256=$dllHash
    fileCount=@(Get-ChildItem -LiteralPath $stage -File -Recurse).Count
    mihomoBundled=$false;privateNodeStoreBundled=$false
} | ConvertTo-Json
