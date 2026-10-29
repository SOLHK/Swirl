param(
    [Parameter(Mandatory=$true)][string]$OpenSslRoot,
    [Parameter(Mandatory=$true)][string]$ApplicationDirectory,
    [Parameter(Mandatory=$true)][ValidateSet('VC-WIN64A','mingw64')][string]$Target,
    [string]$Python='python'
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'RustProductPackagePolicy.ps1')
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Assert-SwirlPathWithoutLinks $OpenSslRoot
Assert-SwirlPathWithoutLinks $ApplicationDirectory
$runtime=(Resolve-Path -LiteralPath $OpenSslRoot).Path
$app=(Resolve-Path -LiteralPath $ApplicationDirectory).Path
& $Python (Join-Path $repo 'tools/Build-OpenSslRuntime.py') --output $runtime --target $Target --verify-only
if ($LASTEXITCODE -ne 0) { throw 'Pinned OpenSSL runtime verification failed.' }
$mapped=[ordered]@{
    'bin/libssl-3-x64.dll'='libssl-3-x64.dll'
    'bin/libcrypto-3-x64.dll'='libcrypto-3-x64.dll'
    'licenses/LICENSE.txt'='licenses/OpenSSL-LICENSE.txt'
    'licenses/NOTICE.txt'='licenses/OpenSSL-NOTICE.txt'
    'openssl-runtime.json'='openssl-runtime.json'
}
foreach ($entry in $mapped.GetEnumerator()) {
    $targetFile=Join-Path $app $entry.Value
    Assert-SwirlPathWithoutLinks $targetFile
    New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($targetFile)) | Out-Null
    Copy-Item -LiteralPath (Join-Path $runtime $entry.Key) -Destination $targetFile
}
