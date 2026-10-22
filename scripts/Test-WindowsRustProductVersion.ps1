$ErrorActionPreference='Stop'
$root=Join-Path 'D:\Codex\tmp' ('swirl-product-version-test-'+[guid]::NewGuid().ToString('N'))
$out=Join-Path $root 'outputs'
$install=Join-Path $root 'installed'
$versionFile=Join-Path $root 'VERSION'
$installedManifest=Join-Path $install 'PRODUCT.json'
$packageManifest=Join-Path $out 'Swirl-Rust-Core-Setup-test.exe.json'
$gate=Join-Path $PSScriptRoot 'Assert-WindowsRustProductVersion.ps1'
function Check-Version([bool]$shouldPass,[string]$previousSourceVersion='') {
    $passed=$true
    try { & $gate -VersionFile $versionFile -OutRoot $out -InstallRoot $install -UninstallRegistryKey '' -PreviousSourceVersion $previousSourceVersion | Out-Null }
    catch { $passed=$false }
    if($passed -ne $shouldPass) { throw "Version gate result was unexpected for $(Get-Content -LiteralPath $versionFile -Raw)." }
}
try {
    New-Item -ItemType Directory -Path $out,$install -Force | Out-Null
    Set-Content -LiteralPath $versionFile -Value '0.1.1' -Encoding utf8
    Check-Version $true
    Check-Version $false '0.1.1'
    Check-Version $true '0.1.0'
    '{"kind":"windows-rust-product-preview","appVersion":"0.1.1"}' | Set-Content -LiteralPath $installedManifest -Encoding utf8
    Check-Version $false
    Remove-Item -LiteralPath $installedManifest
    '{"kind":"windows-rust-product-preview","appVersion":"0.1.1"}' | Set-Content -LiteralPath $packageManifest -Encoding utf8
    Check-Version $false
    Set-Content -LiteralPath $versionFile -Value '0.1.0' -Encoding utf8
    Check-Version $false
    Set-Content -LiteralPath $versionFile -Value '0.1.2' -Encoding utf8
    Check-Version $true
    'PASS: empty output, installed version, package version, same and lower versions'
} finally {
    foreach($file in @($installedManifest,$packageManifest,$versionFile)) {
        if(Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file }
    }
    foreach($dir in @($out,$install,$root)) {
        if(Test-Path -LiteralPath $dir) { Remove-Item -LiteralPath $dir }
    }
}
