param(
    [Parameter(Mandatory=$true)][string]$VersionFile,
    [Parameter(Mandatory=$true)][string]$OutRoot,
    [string]$PreviousSourceVersion = '',
    [string]$InstallRoot = 'D:\Codex\SwirlRust',
    [string]$UninstallRegistryKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustCorePreview'
)
$ErrorActionPreference='Stop'

function Parse-ProductVersion([string]$text,[string]$source) {
    if(-not [regex]::IsMatch($text,'\A(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:\.(0|[1-9][0-9]*))?\z')) {
        throw "Invalid product version in ${source}: $text"
    }
    $parts=@($text.Split('.') | ForEach-Object { [int]::Parse($_) })
    if(@($parts | Where-Object { $_ -gt 65535 }).Count -gt 0) {
        throw "Product version exceeds the Windows version-field limit in ${source}: $text"
    }
    if($parts.Count -eq 3) { return [version]::new($parts[0],$parts[1],$parts[2],0) }
    return [version]::new($parts[0],$parts[1],$parts[2],$parts[3])
}

$versionText=(Get-Content -LiteralPath $VersionFile -Raw -Encoding UTF8).Trim()
if(-not [regex]::IsMatch($versionText,'\A(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\z')) {
    throw "VERSION must contain one major.minor.patch number: $VersionFile"
}
$current=Parse-ProductVersion $versionText $VersionFile
function Assert-Newer([string]$previous,[string]$source) {
    $old=Parse-ProductVersion $previous $source
    if($current -le $old) {
        throw "Product version $versionText must be greater than $previous in $source before packaging an update."
    }
}
function InstalledFileVersion([string]$path) {
    if(-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Product version cannot be checked: $path is missing." }
    $value=(Get-Item -LiteralPath $path).VersionInfo.ProductVersionRaw.ToString()
    if($value -eq '0.0.0.0') { throw "Product version cannot be checked in $path." }
    return $value
}

if($PreviousSourceVersion) {
    Assert-Newer $PreviousSourceVersion 'previous source revision'
}

if($UninstallRegistryKey -and (Test-Path -LiteralPath $UninstallRegistryKey)) {
    $installed=(Get-ItemProperty -LiteralPath $UninstallRegistryKey).DisplayVersion
    Assert-Newer ([string]$installed) 'installed Swirl Core registration'
}
$installedManifest=Join-Path $InstallRoot 'PRODUCT.json'
if(Test-Path -LiteralPath $installedManifest -PathType Leaf) {
    $product=Get-Content -LiteralPath $installedManifest -Raw -Encoding UTF8 | ConvertFrom-Json
    if($product.kind -ne 'windows-rust-product-preview') { throw "Unexpected product manifest: $installedManifest" }
    if($product.appVersion) {
        Assert-Newer ([string]$product.appVersion) $installedManifest
    } else {
        $uninstaller=Join-Path $InstallRoot 'Uninstall-SwirlRust.exe'
        Assert-Newer (InstalledFileVersion $uninstaller) $uninstaller
    }
}
if(Test-Path -LiteralPath (Join-Path $InstallRoot '.swirl-rust-app-owned') -PathType Leaf) {
    $uninstaller=Join-Path $InstallRoot 'Uninstall-SwirlRust.exe'
    Assert-Newer (InstalledFileVersion $uninstaller) $uninstaller
}
if(Test-Path -LiteralPath $OutRoot -PathType Container) {
    $seen=@{}
    foreach($manifest in Get-ChildItem -LiteralPath $OutRoot -File -Filter 'Swirl-Rust-Core-Setup-*.exe.json') {
        $package=Get-Content -LiteralPath $manifest.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        if($package.kind -ne 'windows-rust-product-preview') { throw "Unexpected product manifest: $($manifest.FullName)" }
        if($package.appVersion) { Assert-Newer ([string]$package.appVersion) $manifest.FullName }
        $setupPath=$manifest.FullName.Substring(0,$manifest.FullName.Length-5)
        if(Test-Path -LiteralPath $setupPath -PathType Leaf) {
            Assert-Newer (InstalledFileVersion $setupPath) $setupPath
            $seen[$setupPath]=$true
        } elseif(-not $package.appVersion) {
            throw "Version cannot be recovered from legacy product manifest: $($manifest.FullName)"
        }
    }
    foreach($setup in Get-ChildItem -LiteralPath $OutRoot -File -Filter 'Swirl-Rust-Core-Setup-*.exe') {
        if(-not $seen.ContainsKey($setup.FullName)) {
            Assert-Newer (InstalledFileVersion $setup.FullName) $setup.FullName
        }
    }
}
$versionText
