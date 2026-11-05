# Build a separate per-user NSIS monitor installer. No Swirl binaries or private
# NodeStore files are packaged, and the running Swirl app is not modified.
param(
    [string]$Nsis = 'D:\Codex\toolchains\nsis-3.11\makensis.exe',
    [string]$OutRoot = 'D:\Codex\outputs'
)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$out=[IO.Path]::GetFullPath($OutRoot)
if(-not $out.StartsWith('D:\Codex\',[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Installer output must stay under D:\Codex.'
}
if(-not (Test-Path -LiteralPath $Nsis -PathType Leaf)) { throw 'NSIS compiler is missing.' }
if((& git -C $repo status --porcelain) -or $LASTEXITCODE -ne 0) {
    throw 'Commit source changes before building the installer.'
}
$branch=(& git -C $repo branch --show-current).Trim()
if($branch -ne 'work/core-completion-20261017') { throw 'Unexpected source branch.' }
$sha=(& git -C $repo rev-parse HEAD).Trim()
$required=@(
    'tools\Test-SwirlCoreOffline.ps1','tools\Test-SwirlMihomoPath.ps1',
    'tools\Test-SwirlPrivateDirect.ps1','tools\Monitor-SwirlCore.ps1',
    'tools\Start-SwirlCoreMonitor.ps1','tools\Stop-SwirlCoreMonitor.ps1',
    'tools\SwirlCoreMonitor.config.json','tools\Run-SwirlCoreMonitor.cmd',
    'tools\Stop-SwirlCoreMonitor.cmd','tools\Open-SwirlCoreMonitorReport.cmd',
    'src\Swirl.Quick\packaging\README-SwirlCoreMonitor.txt',
    'src\Swirl.Quick\packaging\SwirlCoreMonitor.nsi'
)
foreach($relative in $required) {
    $file=Join-Path $repo $relative
    if(-not (Test-Path -LiteralPath $file -PathType Leaf) -or
        ((Get-Item -LiteralPath $file).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Invalid installer input: $relative"
    }
}
if(-not (Test-Path -LiteralPath $out -PathType Container)) {
    New-Item -ItemType Directory -Path $out | Out-Null
}
$short=$sha.Substring(0,12)+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss')
$setup=Join-Path $out "Swirl-Core-Monitor-Setup-$short.exe"
if(Test-Path -LiteralPath $setup) { throw 'Installer output already exists.' }
$nsi=Join-Path $repo 'src\Swirl.Quick\packaging\SwirlCoreMonitor.nsi'
$args=@('/V2','/INPUTCHARSET','UTF8',"/DREPO_DIR=$repo","/DOUT_DIR=$out","/DSOURCE_SHORT=$short",$nsi)
$compiler=@(& $Nsis @args 2>&1)
if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $setup -PathType Leaf)) {
    $compiler | Select-Object -Last 20
    throw 'NSIS monitor packaging failed.'
}
$result=[ordered]@{
    kind='swirl-core-monitor-installer';sourceSha=$sha;setup=$setup
    sha256=(Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash
    bytes=(Get-Item -LiteralPath $setup).Length
    installDir='D:\Codex\SwirlCoreMonitor';dataDir='D:\Codex\SwirlCoreMonitorData'
    privateNodeStoreBundled=$false;mihomoBundled=$false;swirlBinaryBundled=$false
    signed=(Get-AuthenticodeSignature -LiteralPath $setup).Status -eq 'Valid'
}
$result | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath ($setup+'.json') -Encoding utf8
$result | ConvertTo-Json -Depth 3
