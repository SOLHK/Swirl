# Build a short-path, per-user NSIS installer from an already verified Rust
# acceptance folder. The embedded engine keeps the SHA recorded in PACKAGE.json.
param(
    [Parameter(Mandatory=$true)][string]$StageDir,
    [string]$Nsis = 'D:\Codex\toolchains\nsis-3.11\makensis.exe',
    [string]$OutRoot = 'D:\Codex\outputs'
)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$stage=(Resolve-Path -LiteralPath $StageDir).Path.TrimEnd('\')
$out=[IO.Path]::GetFullPath($OutRoot).TrimEnd('\')
$dRoot=[IO.Path]::GetFullPath('D:\Codex\')
if(-not $stage.StartsWith($dRoot,[StringComparison]::OrdinalIgnoreCase) -or
   -not $out.StartsWith($dRoot,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Installer inputs and outputs must stay under D:\Codex.'
}
if(-not (Test-Path -LiteralPath $Nsis -PathType Leaf)) { throw 'NSIS compiler is missing.' }
$nsi=Join-Path $repo 'src\Swirl.Quick\packaging\SwirlRustNetworkCheck.nsi'
$readme=Join-Path $repo 'src\Swirl.Quick\packaging\README-RustNetworkCheckInstaller.txt'
if(-not (Test-Path -LiteralPath $nsi -PathType Leaf) -or
   -not (Test-Path -LiteralPath $readme -PathType Leaf)) { throw 'Installer source is missing.' }
if((& git -C $repo status --porcelain) -or $LASTEXITCODE -ne 0) {
    throw 'Commit source changes before building the installer.'
}
$installerSourceSha=(& git -C $repo rev-parse HEAD).Trim()
$manifestPath=Join-Path $stage 'PACKAGE.json'
if(-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'Package manifest is missing.' }
$manifest=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if($manifest.kind -ne 'windows-rust-acceptance-preview' -or
   $manifest.sourceSha -notmatch '^[0-9a-f]{40}$' -or
   -not $manifest.rustCore -or -not $manifest.uiTestHarness -or
   $manifest.privateNodeStoreBundled -or $manifest.mihomoBundled) {
    throw 'This is not a complete, private-data-free Rust acceptance folder.'
}
& git -C $repo merge-base --is-ancestor $manifest.sourceSha HEAD
if($LASTEXITCODE -ne 0) { throw 'Packaged engine source is not an ancestor of the installer source.' }
$hashes=@(
    @('Swirl.exe','exeSha256'),
    @('swirl_api.dll','rustDllSha256'),
    @('tools\Invoke-WindowsRustAcceptance.ps1','acceptanceScriptSha256'),
    @('tools\Invoke-WindowsRustPortableCheck.ps1','portableRunnerSha256'),
    @('TEST-SWIRL-NETWORK.cmd','launcherCmdSha256'),
    @('runtime\powershell\pwsh.exe','bundledPowerShellSha256')
)
foreach($row in $hashes) {
    $path=Join-Path $stage $row[0]
    if(-not (Test-Path -LiteralPath $path -PathType Leaf) -or
       (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $manifest.($row[1])) {
        throw "Package file is missing or has changed: $($row[0])"
    }
}
$files=@(Get-ChildItem -LiteralPath $stage -File -Recurse -Force -ErrorAction Stop |
    Sort-Object FullName)
$dirs=@(Get-ChildItem -LiteralPath $stage -Directory -Recurse -Force -ErrorAction Stop |
    Sort-Object { $_.FullName.Length } -Descending)
if($files.Count -lt 100) { throw 'Installer input is unexpectedly small.' }
$installRoot='D:\Codex\SwirlRustCheck'
$deleteLines=[Collections.Generic.List[string]]::new()
foreach($file in $files) {
    if(($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
       $file.Name -match '(?i)^(mihomo\.exe|nodes\.dpapi|nodes\.dpapi\.selected|runtime-state\.json)$') {
        throw "Forbidden or linked file in installer input: $($file.Name)"
    }
    $relative=$file.FullName.Substring($stage.Length+1)
    if($relative -match '["$\r\n]' -or $installRoot.Length+1+$relative.Length -ge 240) {
        throw "Unsupported or overly long installer path: $relative"
    }
    $deleteLines.Add('Delete "$INSTDIR\'+$relative+'"')
}
foreach($dir in $dirs) {
    if(($dir.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Linked directory in installer input: $($dir.Name)"
    }
    $relative=$dir.FullName.Substring($stage.Length+1)
    if($relative -match '["$\r\n]') { throw "Unsupported installer directory: $relative" }
    $deleteLines.Add('RMDir "$INSTDIR\'+$relative+'"')
}
if(-not (Test-Path -LiteralPath $out -PathType Container)) {
    New-Item -ItemType Directory -Path $out -ErrorAction Stop | Out-Null
}
$buildRoot=Join-Path 'D:\Codex\tmp' ('swirl-installer-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $buildRoot -ErrorAction Stop | Out-Null
$uninstallList=Join-Path $buildRoot 'UninstallFiles.nsh'
$deleteLines | Set-Content -LiteralPath $uninstallList -Encoding utf8
$short=$manifest.sourceSha.Substring(0,12)
$setupId=$short+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss')
$setup=Join-Path $out ('Swirl-Rust-Network-Check-Setup-'+$setupId+'.exe')
if(Test-Path -LiteralPath $setup) { throw 'Installer output already exists.' }
$arguments=@('/V2','/INPUTCHARSET','UTF8',
    "/DAPP_DIST=$stage", "/DOUT_DIR=$out", "/DUNINSTALL_LIST=$uninstallList",
    "/DSOURCE_SHORT=$setupId", "/DENGINE_SHA=$($manifest.sourceSha)",
    "/DINSTALL_README=$readme", $nsi)
$compilerOutput=@(& $Nsis @arguments 2>&1)
$compilerExit=$LASTEXITCODE
$compilerOutput | Set-Content -LiteralPath (Join-Path $buildRoot 'makensis.log') -Encoding utf8
if($compilerExit -ne 0 -or -not (Test-Path -LiteralPath $setup -PathType Leaf)) {
    throw "NSIS compilation failed with exit code $compilerExit; see $buildRoot"
}
$result=[ordered]@{
    kind='swirl-rust-network-check-installer';engineSourceSha=$manifest.sourceSha
    installerSourceSha=$installerSourceSha;setup=$setup
    setupSha256=(Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash
    setupBytes=(Get-Item -LiteralPath $setup).Length
    inputFileCount=$files.Count;installDir=$installRoot
    privateNodeStoreBundled=$false;mihomoBundled=$false
    signed=(Get-AuthenticodeSignature -LiteralPath $setup).Status -eq 'Valid'
    createdUtc=[DateTime]::UtcNow.ToString('o')
}
$result | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath ($setup+'.json') -Encoding utf8
$result | ConvertTo-Json -Depth 3
