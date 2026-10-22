param(
    [Parameter(Mandatory=$true)][string]$SourceDirectory,
    [Parameter(Mandatory=$true)][string]$ApplicationDirectory
)
$ErrorActionPreference='Stop'
$source=(Resolve-Path -LiteralPath $SourceDirectory -ErrorAction Stop).Path
$application=(Resolve-Path -LiteralPath $ApplicationDirectory -ErrorAction Stop).Path
$expected=@{
    'cn-domain.mrs'='E92BDA4F0B9F05623663A882331A320AB4E266CADA2046D3828A94572CDDED46'
    'cn-ip.mrs'='D95B3D125F6C74CE3C15E19EF794F142DE91E21C3B8FB7767E76AEBFABFF5149'
}
foreach($name in $expected.Keys) {
    $path=Join-Path $source $name
    if(-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required China rule missing: $name" }
    if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $expected[$name]) {
        throw "China rule checksum mismatch: $name"
    }
}
$destination=Join-Path $application 'rules'
if(Test-Path -LiteralPath $destination) { throw "Rules destination already exists: $destination" }
Copy-Item -LiteralPath $source -Destination $destination -Recurse -ErrorAction Stop
foreach($name in $expected.Keys) {
    $path=Join-Path $destination $name
    if(-not (Test-Path -LiteralPath $path -PathType Leaf) -or
       (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $expected[$name]) {
        throw "Packaged China rule missing or changed: $name"
    }
}
