param(
    [Parameter(Mandatory)][string]$BuildDirectory,
    [Parameter(Mandatory)][string]$ApplicationDirectory
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'RustProductPackagePolicy.ps1')
$cache=Get-Content -LiteralPath (Join-Path $BuildDirectory 'CMakeCache.txt') -Raw
if($cache -notmatch '(?m)^CMAKE_CXX_COMPILER:FILEPATH=(.+)$'){throw 'Configured compiler is missing.'}
$compiler=(Resolve-Path -LiteralPath $Matches[1].Trim()).Path
Assert-SwirlPathWithoutLinks $compiler
$machine=(& $compiler -dumpmachine).Trim()
if($LASTEXITCODE -ne 0 -or $machine -cne 'x86_64-w64-mingw32'){throw 'The configured compiler is not Windows x64 MinGW.'}
$version=(& $compiler -dumpfullversion).Trim()
if($LASTEXITCODE -ne 0){throw 'Compiler version verification failed.'}
$bin=Split-Path -Parent $compiler
$root=Split-Path -Parent $bin
$receipt=[ordered]@{schema=1;kind='mingw-runtime';target=$machine;compiler_version=$version;
    compiler_sha256=(Get-FileHash -LiteralPath $compiler -Algorithm SHA256).Hash.ToLowerInvariant();files=@()}
foreach($name in @('libgcc_s_seh-1.dll','libstdc++-6.dll','libwinpthread-1.dll')){
    $source=Join-Path $bin $name;Assert-SwirlPathWithoutLinks $source;Assert-SwirlAmd64Image $source
    $destination=Join-Path $ApplicationDirectory $name
    Copy-Item -LiteralPath $source -Destination $destination
    $hash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    if((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -cne $hash){throw 'Compiler runtime copy mismatch.'}
    $receipt.files += @{path=$name;sha256=$hash}
}
$licenses=Join-Path $ApplicationDirectory 'licenses/mingw-runtime'
New-Item -ItemType Directory -Force -Path $licenses | Out-Null
foreach($component in @('gcc','winpthreads','mingw-w64')){
    $source=Join-Path $root ('licenses/'+$component)
    if(-not (Test-Path -LiteralPath $source -PathType Container)){throw ('Missing compiler runtime license: '+$component)}
    Copy-Item -LiteralPath $source -Destination (Join-Path $licenses $component) -Recurse
}
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $ApplicationDirectory 'mingw-runtime.json') -Encoding utf8
