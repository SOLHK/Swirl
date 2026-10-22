$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot '../RustProductPackagePolicy.ps1')
$allowed = @('licenses/mihomo-GPL-3.0.txt','licenses\mihomo-GPL-3.0.txt',
    'LICENSES/MIHOMO-GPL-3.0.TXT','Swirl.exe','swirl_api.dll','Qt6Core.dll',
    'rules/cn-domain.mrs','rules/cn-ip.mrs','THIRD_PARTY_NOTICES.txt')
$denied = @('mihomo.exe','engine/mihomo-windows-amd64.exe','licenses/mihomo.exe',
    'licenses/mihomo-GPL-3.0.txt.exe','mihomo-GPL-3.0.txt','other/licenses/mihomo-GPL-3.0.txt',
    'Mihomo.dll','clash.exe','xray.exe','sing-box.exe','mihomo-manifest.json',
    'SwirlRustCoreTests.exe','SwirlEngineFixture.exe','swirl_loader_fixture_1.dll',
    'swirl_loader_fixture_10.dll','nodes.dpapi','subscriptions.private')
foreach ($path in $allowed) {
    if (Test-SwirlForbiddenProductPath $path) { throw "Allowed package entry was rejected: $path" }
}
foreach ($path in $denied) {
    if (-not (Test-SwirlForbiddenProductPath $path)) { throw "Forbidden package entry was accepted: $path" }
}
$root = Join-Path ([IO.Path]::GetTempPath()) ('swirl-package-policy-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $root 'licenses') -Force | Out-Null
try {
    [IO.File]::WriteAllText((Join-Path $root 'licenses/mihomo-GPL-3.0.txt'), 'historical license fixture')
    [IO.File]::WriteAllText((Join-Path $root 'Swirl.exe'), 'product fixture')
    if (@(Get-SwirlForbiddenProductFiles $root).Count -ne 0) { throw 'Historical license poisoned clean package.' }
    [IO.File]::WriteAllText((Join-Path $root 'licenses/mihomo.exe'), 'forbidden runtime fixture')
    $actual = @(Get-SwirlForbiddenProductFiles $root)
    if ($actual.Count -ne 1 -or $actual[0] -ne 'licenses/mihomo.exe') { throw 'Runtime hidden in licenses escaped enumeration.' }
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force
}
Write-Host "Package policy: $($allowed.Count + $denied.Count + 2) assertions passed."
