param(
    [string]$Nsis = 'D:/Codex/toolchains/nsis-3.11/makensis.exe',
    [string]$Icon = 'D:/Codex/build-swirl-s3-max-20261023/brand/Swirl.ico',
    [string]$EvidenceRoot = 'D:/Codex/outputs/s4/package-lifecycle'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $repo 'scripts/RustProductPackagePolicy.ps1')
$base = [IO.Path]::GetFullPath('D:/Codex/tmp/s4').TrimEnd('\')
$root = Join-Path $base ('installer-lifecycle-' + [guid]::NewGuid().ToString('N'))
$target = Join-Path $root 'install'
$cases = New-Object 'System.Collections.Generic.List[object]'
$sourceHashes = [ordered]@{}
foreach ($source in @('scripts/RustProductPackagePolicy.ps1','scripts/Finalize-WindowsRustProduct.ps1',
    'scripts/Maintain-WindowsRustProduct.ps1','src/Swirl.Quick/packaging/Swirl.nsi','scripts/tests/Test-S4InstallerLifecycle.ps1')) {
    $sourceHashes[$source] = (Get-FileHash -LiteralPath (Join-Path $repo $source)).Hash.ToLowerInvariant()
}

function Assert-FixturePath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if ($full -ne $root -and -not $full.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing a lifecycle operation outside the unique fixture root.'
    }
    $ancestor = $full
    while ($ancestor -and $ancestor -ne [IO.Path]::GetPathRoot($ancestor)) {
        if (Test-Path -LiteralPath $ancestor) {
            if (((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Refusing a lifecycle operation through a reparse point.'
            }
        }
        $ancestor = [IO.Path]::GetDirectoryName($ancestor)
    }
    return $full
}
function Record([string]$Name, [bool]$Passed, [string]$Detail = '') {
    $cases.Add([ordered]@{name=$Name; passed=$Passed; detail=$Detail})
    Write-Host "$Name : $Passed"
}
function Snapshot-UserIntegration {
    $data = [ordered]@{}
    foreach ($key in @('HKCU:\Software\Swirl', 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Swirl')) {
        $data[$key] = if (Test-Path -LiteralPath $key) {
            $item = Get-Item -LiteralPath $key
            $values = [ordered]@{}
            foreach ($name in @($item.GetValueNames() | Sort-Object)) { $values[$name] = $item.GetValue($name) }
            $values
        } else { $null }
    }
    foreach ($path in @(
        (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Swirl.lnk'),
        (Join-Path ([Environment]::GetFolderPath('Programs')) 'Swirl')
    )) {
        $data[$path] = if (Test-Path -LiteralPath $path) {
            @(Get-ChildItem -LiteralPath $path -Recurse -File -Force -ErrorAction Stop | Sort-Object FullName |
                ForEach-Object { @{path=$_.FullName; hash=(Get-FileHash -LiteralPath $_.FullName).Hash} })
        } else { $null }
    }
    return ($data | ConvertTo-Json -Depth 8 -Compress)
}
function Make-Payload([string]$Directory, [string]$Version) {
    $null = Assert-FixturePath $Directory
    New-Item -ItemType Directory -Path (Join-Path $Directory 'resources') -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $Directory 'Swirl.exe'), "Synthetic non-executed payload $Version")
    [IO.File]::WriteAllText((Join-Path $Directory 'runtime.dat'), "Synthetic runtime $Version")
    [IO.File]::WriteAllText((Join-Path $Directory 'unchanged-vendor.dat'), 'Shared vendor bytes across versions')
    $leaf = if ($Version -eq '1') { 'obsolete.dat' } else { 'current.dat' }
    [IO.File]::WriteAllText((Join-Path $Directory "resources/$leaf"), "Owned vendor resource $Version")
    $manifest = [ordered]@{schema=1; source_sha=$sha; rust=@{source_sha=$sha}; files=@()}
    foreach ($file in (Get-ChildItem -LiteralPath $Directory -Recurse -File | Sort-Object FullName)) {
        $manifest.files += @{path=$file.FullName.Substring($Directory.Length + 1).Replace('\','/');
                            sha256=(Get-FileHash -LiteralPath $file.FullName).Hash.ToLowerInvariant()}
    }
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Directory 'package-manifest.json') -Encoding utf8
    return $manifest
}
function Run-Hidden([string]$Executable, [string]$Arguments) {
    $null = Assert-FixturePath $Executable
    $null = Assert-FixturePath $target
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $root -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(45000)) { $process.Kill(); throw 'Disposable installer timed out.' }
    return $process.ExitCode
}
function Exact-Installed([object]$Manifest, [string[]]$Extra) {
    $expected = @($Manifest.files | ForEach-Object { [string]$_.path }) + @('package-manifest.json') + $Extra
    $actual = @(Get-ChildItem -LiteralPath $target -Recurse -File -Force | ForEach-Object {
        $_.FullName.Substring($target.Length + 1).Replace('\','/') })
    $difference = @(Compare-Object ($expected | Sort-Object) ($actual | Sort-Object))
    foreach ($entry in $Manifest.files) {
        $path = Join-Path $target $entry.path
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-FileHash -LiteralPath $path).Hash -ine $entry.sha256) { return $false }
    }
    return $difference.Count -eq 0
}
function Snapshot-Installed {
    return (@(Get-ChildItem -LiteralPath $target -Recurse -File -Force | Sort-Object FullName | ForEach-Object {
        [ordered]@{path=$_.FullName.Substring($target.Length + 1).Replace('\','/');
                   sha256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
    }) | ConvertTo-Json -Depth 5 -Compress)
}

$null = Assert-FixturePath $root
New-Item -ItemType Directory -Path $root | Out-Null
New-Item -ItemType Directory -Path $EvidenceRoot -Force | Out-Null
$reportPath = Join-Path $EvidenceRoot ((Split-Path $root -Leaf) + '.json')
$sha = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot read fixture source identity.' }
$before = Snapshot-UserIntegration
$originalIsolation = $env:SWIRL_ISOLATED_INSTALL_ROOT
$env:SWIRL_ISOLATED_INSTALL_ROOT = $root
$errorText = $null
try {
    foreach ($version in @('1','2')) {
        $payload = Join-Path $root "payload-$version"
        $manifest = Make-Payload $payload $version
        $evidence = Join-Path $root "evidence-$version"
        $include = Join-Path $root "uninstall-$version.nsh"
        $buildOut = Join-Path $root "installer-$version"
        New-Item -ItemType Directory -Path $buildOut | Out-Null
        if ($version -eq '1') {
            [IO.File]::WriteAllText((Join-Path $payload 'Swirl-diagnostics.txt'), 'Synthetic smoke evidence')
        }
        & (Join-Path $repo 'scripts/Finalize-WindowsRustProduct.ps1') -ApplicationDirectory $payload `
            -EvidenceDirectory $evidence -UninstallList $include
        $null = Assert-SwirlProductManifest -ApplicationDirectory $payload -ExpectedSourceSha $sha
        Record "final-manifest-$version" $true
        if ($version -eq '1') {
            Record 'smoke-evidence-retained-outside-payload' ((Test-Path -LiteralPath (Join-Path $evidence 'Swirl-diagnostics.txt')) -and
                -not (Test-Path -LiteralPath (Join-Path $payload 'Swirl-diagnostics.txt')))
        }
        # Preserve absolute-path coverage and exercise the relative invocation
        # used by the actual product workflow. NSIS changes its working directory.
        $scriptPath = if ($version -eq '1') { Join-Path $repo 'src/Swirl.Quick/packaging/Swirl.nsi' } else { 'src/Swirl.Quick/packaging/Swirl.nsi' }
        Push-Location $repo
        try {
            & $Nsis /INPUTCHARSET UTF8 "/DAPP_DIST=$payload" "/DOUT_DIR=$buildOut" "/DAPP_ICON=$Icon" `
                "/DAPP_VERSION=0.0.$version" "/DUNINSTALL_LIST=$include" "/DREPO_ROOT=$repo" "/DPACKAGE_TEST_TRACE=$root\maintenance-$version.log" $scriptPath `
                *> (Join-Path $root "nsis-$version.log")
            $compilerExit=$LASTEXITCODE
        } finally { Pop-Location }
        if ($compilerExit -ne 0) { throw "NSIS fixture $version compilation failed." }
        Record "nsis-build-$version" $true
        Record $(if ($version -eq '1') { 'nsis-absolute-script-path' } else { 'nsis-relative-script-path-matches-product-workflow' }) $true
        $exitCode = Run-Hidden (Join-Path $buildOut 'Swirl-Setup.exe') "/S /ISOLATED /D=$target"
        Record "installer-exit-$version" ($exitCode -eq 0) "Exit $exitCode"
        if ($exitCode -ne 0) { throw 'Disposable installer refused fixture target.' }
        if ($version -eq '1') {
            Record 'installed-inventory-1' (Exact-Installed $manifest @('.swirl-install-owned','.swirl-isolated-install','卸载 Swirl.exe'))
            Copy-Item -LiteralPath (Join-Path $target '卸载 Swirl.exe') -Destination (Join-Path $root 'saved-v1-uninstaller.exe')
            New-Item -ItemType Directory -Path (Join-Path $target 'data') | Out-Null
            [IO.File]::WriteAllText((Join-Path $target 'data/subscriptions.dpapi'), 'Synthetic encrypted-state sentinel; not user data')
            [IO.File]::WriteAllText((Join-Path $target 'user.txt'), 'Synthetic user-owned file')
            $dataHash = (Get-FileHash -LiteralPath (Join-Path $target 'data/subscriptions.dpapi')).Hash
            $userHash = (Get-FileHash -LiteralPath (Join-Path $target 'user.txt')).Hash
        } else {
            Record 'installed-inventory-2-removes-obsolete-vendor-files' (Exact-Installed $manifest @(
                '.swirl-install-owned','.swirl-isolated-install','卸载 Swirl.exe','data/subscriptions.dpapi','user.txt'))
            Record 'upgrade-preserves-user-data' ((Get-FileHash -LiteralPath (Join-Path $target 'data/subscriptions.dpapi')).Hash -ceq $dataHash -and
                (Get-FileHash -LiteralPath (Join-Path $target 'user.txt')).Hash -ceq $userHash)
        }
    }
    $beforeStale = Snapshot-Installed
    $staleExit = Run-Hidden (Join-Path $root 'saved-v1-uninstaller.exe') "/S _?=$target"
    Record 'stale-v1-uninstaller-refuses-installed-v2' ($staleExit -eq 2) "Exit $staleExit"
    $stalePreserved = $beforeStale -ceq (Snapshot-Installed)
    Record 'stale-v1-uninstaller-preserves-all-v2-user-and-marker-bytes' $stalePreserved
    if (-not $stalePreserved) { throw 'Stale uninstaller changed upgraded payload.' }
    $uninstaller = Join-Path $root 'uninstall-runner.exe'
    Copy-Item -LiteralPath (Join-Path $target '卸载 Swirl.exe') -Destination $uninstaller
    $exitCode = Run-Hidden $uninstaller "/S _?=$target"
    Record 'uninstaller-exit' ($exitCode -eq 0) "Exit $exitCode"
    $remaining = @(Get-ChildItem -LiteralPath $target -Recurse -File -Force | ForEach-Object {
        $_.FullName.Substring($target.Length + 1).Replace('\','/') })
    Record 'uninstall-leaves-only-user-data' (@(Compare-Object @('data/subscriptions.dpapi','user.txt') ($remaining | Sort-Object)).Count -eq 0)
    Record 'uninstall-preserves-user-data-bytes' ((Get-FileHash -LiteralPath (Join-Path $target 'data/subscriptions.dpapi')).Hash -ceq $dataHash -and
        (Get-FileHash -LiteralPath (Join-Path $target 'user.txt')).Hash -ceq $userHash)
    $setup = Join-Path $root 'installer-2/Swirl-Setup.exe'
    Record 'isolated-install-refuses-unmarked-user-directory' ((Run-Hidden $setup "/S /ISOLATED /D=$target") -eq 2)
    Record 'uninstaller-refuses-missing-ownership-marker' ((Run-Hidden $uninstaller "/S _?=$target") -eq 2)
    $env:SWIRL_ISOLATED_INSTALL_ROOT = $root + '-mismatch'
    Record 'isolated-install-refuses-wrong-expected-root' ((Run-Hidden $setup "/S /ISOLATED /D=$target") -eq 2)
    $env:SWIRL_ISOLATED_INSTALL_ROOT = $root
    $escape = Join-Path $root 'escape'
    Record 'isolated-install-refuses-traversal-to-other-fixture-child' ((Run-Hidden $setup "/S /ISOLATED /D=$target\..\escape") -eq 2 -and
        -not (Test-Path -LiteralPath $escape))
    Record 'negative-install-attempts-preserve-user-data' ((Get-FileHash -LiteralPath (Join-Path $target 'data/subscriptions.dpapi')).Hash -ceq $dataHash -and
        (Get-FileHash -LiteralPath (Join-Path $target 'user.txt')).Hash -ceq $userHash)

    $maintenance = Join-Path $repo 'scripts/Maintain-WindowsRustProduct.ps1'
    $expectedV2 = Join-Path $root 'payload-2/package-manifest.json'
    $modified = Join-Path $root 'modified-owned-file'
    $null = Make-Payload $modified '1'
    [IO.File]::WriteAllText((Join-Path $modified '.swirl-install-owned'), 'Synthetic ownership')
    [IO.File]::WriteAllText((Join-Path $modified 'resources/obsolete.dat'), 'Synthetic user modification')
    $modifiedHash = (Get-FileHash -LiteralPath (Join-Path $modified 'resources/obsolete.dat')).Hash
    & $maintenance -Mode Upgrade -ApplicationDirectory $modified -ExpectedManifest $expectedV2
    Record 'upgrade-preserves-modified-obsolete-vendor-file' ((Get-FileHash -LiteralPath (Join-Path $modified 'resources/obsolete.dat')).Hash -ceq $modifiedHash)
    & $maintenance -Mode Uninstall -ApplicationDirectory $modified -ExpectedManifest (Join-Path $root 'payload-1/package-manifest.json')
    Record 'uninstall-preserves-modified-vendor-file' ((Get-FileHash -LiteralPath (Join-Path $modified 'resources/obsolete.dat')).Hash -ceq $modifiedHash)

    $unsafe = Join-Path $root 'unsafe-old-manifest'
    $unsafeManifest = Make-Payload $unsafe '1'
    [IO.File]::WriteAllText((Join-Path $unsafe '.swirl-install-owned'), 'Synthetic ownership')
    $victim = Join-Path $root 'must-retain.txt'
    [IO.File]::WriteAllText($victim, 'Outside-installation synthetic sentinel')
    $victimHash = (Get-FileHash -LiteralPath $victim).Hash
    $unsafeManifest.files += @{path='../must-retain.txt';sha256=$victimHash.ToLowerInvariant()}
    $unsafeManifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $unsafe 'package-manifest.json') -Encoding utf8
    $rejected = $false
    try { & $maintenance -Mode Upgrade -ApplicationDirectory $unsafe -ExpectedManifest $expectedV2 } catch { $rejected = $true }
    Record 'malformed-old-manifest-rejected-before-any-deletion' ($rejected -and (Test-Path -LiteralPath (Join-Path $unsafe 'resources/obsolete.dat')) -and
        (Get-FileHash -LiteralPath $victim).Hash -ceq $victimHash)

    $corrupt = Join-Path $root 'corrupt-installed-payload'
    $null = Make-Payload $corrupt '2'
    [IO.File]::WriteAllText((Join-Path $corrupt 'runtime.dat'), 'Changed after staging')
    $rejected = $false
    try { & $maintenance -Mode Verify -ApplicationDirectory $corrupt -ExpectedManifest $expectedV2 } catch { $rejected = $true }
    Record 'post-copy-vendor-hash-mismatch-rejected' $rejected

    # Safe adversarial paths remain inside this disposable fixture. No linked
    # tree is recursively removed; artifacts are retained for review.
    $linkedPayload = Join-Path $root 'linked-payload'
    $null = Make-Payload $linkedPayload '2'
    $alias = Join-Path $root 'payload-alias'
    New-Item -ItemType Junction -Path $alias -Target $linkedPayload | Out-Null
    $rejected = $false
    try { $null = Assert-SwirlProductManifest -ApplicationDirectory $alias -ExpectedSourceSha $sha } catch { $rejected = $true }
    Record 'payload-root-junction-rejected' $rejected

    $outputAlias = Join-Path $root 'output-alias'
    New-Item -ItemType Junction -Path $outputAlias -Target $linkedPayload | Out-Null
    $rejected = $false
    try {
        & (Join-Path $repo 'scripts/Finalize-WindowsRustProduct.ps1') -ApplicationDirectory $linkedPayload `
            -EvidenceDirectory $outputAlias -UninstallList (Join-Path $root 'linked-output.nsh')
    } catch { $rejected = $true }
    Record 'evidence-junction-into-payload-rejected' $rejected
    $installerAlias = Join-Path $root 'installer-target-alias'
    New-Item -ItemType Junction -Path $installerAlias -Target $target | Out-Null
    Record 'isolated-installer-rejects-linked-destination' ((Run-Hidden $setup "/S /ISOLATED /D=$installerAlias") -eq 2)
} catch {
    $errorText = $_.Exception.Message
    Record 'lifecycle-execution' $false $errorText
} finally {
    $env:SWIRL_ISOLATED_INSTALL_ROOT = $originalIsolation
    $after = Snapshot-UserIntegration
    Record 'existing-user-registry-and-shortcuts-unchanged' ($before -ceq $after)
    $report = [ordered]@{schema=1; source_base_sha=$sha; fixture_root=$root; install_target=$target;
        source_sha256=$sourceHashes;
        actual_nsis=$Nsis; actual_nsis_sha256=(Get-FileHash -LiteralPath $Nsis).Hash.ToLowerInvariant();
        actual_product_runtime_executed=$false; private_inputs=$false; existing_user_product_modified=$false;
        artifacts_retained=$true; success=(@($cases | Where-Object { -not $_.passed }).Count -eq 0);
        cases=$cases.ToArray(); error=$errorText}
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding utf8
    Write-Host "Lifecycle evidence: $reportPath"
}
if (-not $report.success) { exit 1 }
