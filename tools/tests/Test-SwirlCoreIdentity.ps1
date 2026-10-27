# No Pester dependency. These tests create fake package bytes only: no proxy,
# DLL, Windows settings, Swirl process or Internet endpoint is opened.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../SwirlCoreIdentity.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ('swirl-identity-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $root
$script:passed = 0
$source = '0123456789abcdef0123456789abcdef01234567'
$buildId = 'a' * 64

function Write-Json($Path,$Value) {
    [IO.File]::WriteAllText($Path,($Value | ConvertTo-Json -Depth 10),[Text.UTF8Encoding]::new($false))
}
function New-Fixture([string]$Name,[bool]$Legacy = $false) {
    $path = Join-Path $root $Name
    $null = New-Item -ItemType Directory -Path (Join-Path $path 'rules') -Force
    [IO.File]::WriteAllText((Join-Path $path 'Swirl.exe'),'fixture executable')
    [IO.File]::WriteAllText((Join-Path $path 'swirl_api.dll'),'fixture Rust DLL')
    if ($Legacy) {
        Write-Json (Join-Path $path 'PRODUCT.json') ([ordered]@{
            sourceSha=$source; kind='windows-rust-product-preview'; rustCore=$true; mihomoBundled=$false
            exeSha256=(Get-SwirlFileSha256 (Join-Path $path 'Swirl.exe'))
            rustDllSha256=(Get-SwirlFileSha256 (Join-Path $path 'swirl_api.dll'))
        })
        [IO.File]::WriteAllText((Join-Path $path 'BUILD.txt'),"source=$source`nSWIRL_USE_RUST_CORE=ON`n")
    } else {
        $rust = [ordered]@{ abi_version=1; build_id=$buildId; source_sha=$source; target='x86_64-pc-windows-msvc' }
        Write-Json (Join-Path $path 'swirl-rust-build.json') $rust
        [IO.File]::WriteAllText((Join-Path $path 'rules/cn-domain.mrs'),'fixture domain rules')
        [IO.File]::WriteAllText((Join-Path $path 'rules/cn-ip.mrs'),'fixture IP rules')
        $files = @(foreach ($name in @('Swirl.exe','swirl_api.dll','swirl-rust-build.json','rules/cn-domain.mrs','rules/cn-ip.mrs')) {
            [ordered]@{ path=$name; sha256=(Get-SwirlFileSha256 (Join-Path $path $name)) }
        })
        Write-Json (Join-Path $path 'package-manifest.json') ([ordered]@{ schema=1; source_sha=$source; rust=$rust; files=$files })
    }
    return $path
}
function Assert-Rejected([string]$Name,[scriptblock]$Mutation,[string]$Code,[bool]$Legacy = $false) {
    $path = New-Fixture $Name $Legacy
    & $Mutation $path
    $errorCode = ''
    try { $null = Get-SwirlInstalledIdentity $path } catch { $errorCode = $_.Exception.Message }
    if ($errorCode -cne $Code) { throw "${Name}: expected $Code, got '$errorCode'." }
    $script:passed++
}

try {
    $path = New-Fixture 'current'
    $before = Get-SwirlFileSha256 (Join-Path $path 'package-manifest.json')
    # A different working directory cannot redirect package inputs.
    Push-Location ([IO.Path]::GetTempPath())
    try { $identity = Get-SwirlInstalledIdentity -Directory $path -ExpectedSourceSha $source }
    finally { Pop-Location }
    if ($identity.sourceSha -cne $source -or $identity.buildId -cne $buildId -or
        $identity.format -cne 'r1-paired-package-v1' -or -not $identity.rulesHashesVerified -or
        -not $identity.executableHashMatchesManifest -or -not $identity.rustDllHashMatchesManifest -or
        $identity.publisherAuthenticity -cne 'NOT_VERIFIED' -or
        (Get-SwirlFileSha256 (Join-Path $path 'package-manifest.json')) -cne $before) { throw 'Current identity failed or changed files.' }
    $script:passed++
    $legacyPath = New-Fixture 'legacy' $true
    $legacy = Get-SwirlInstalledIdentity $legacyPath
    if ($legacy.format -cne 'legacy-product-preview' -or $legacy.rulesHashesVerified -or $legacy.buildId -or
        $legacy.sourceSha -cne $source -or -not $legacy.rustBuildFlagEnabled) { throw 'Legacy identity has incorrect claims.' }
    $script:passed++
    # Hidden installed files must still hash under Windows PowerShell 5.1.
    $dll = Join-Path $path 'swirl_api.dll'
    $oldAttributes = [IO.File]::GetAttributes($dll)
    try {
        [IO.File]::SetAttributes($dll,($oldAttributes -bor [IO.FileAttributes]::Hidden))
        $null = Get-SwirlInstalledIdentity $path
    } finally { [IO.File]::SetAttributes($dll,$oldAttributes) }
    $script:passed++
    $rejected = $false
    try { $null = Get-SwirlInstalledIdentity -Directory $path -ExpectedSourceSha ('f' * 40) }
    catch { $rejected = $_.Exception.Message -ceq 'IDENTITY_EXPECTED_SOURCE_MISMATCH' }
    if (-not $rejected) { throw 'Expected source mismatch was not rejected.' }
    $script:passed++

    Assert-Rejected 'mixed-good-legacy' {
        param($p)
        Copy-Item (Join-Path $legacyPath 'PRODUCT.json') $p
        Copy-Item (Join-Path $legacyPath 'BUILD.txt') $p
    } 'IDENTITY_MIXED_PACKAGE_FORMATS'
    Assert-Rejected 'mixed-partial-legacy' { param($p) [IO.File]::WriteAllText((Join-Path $p 'BUILD.txt'),'old') } 'IDENTITY_MIXED_PACKAGE_FORMATS'
    Assert-Rejected 'current-missing-rust' { param($p) Remove-Item (Join-Path $p 'swirl-rust-build.json') } 'IDENTITY_CURRENT_PAIR_INCOMPLETE'
    Assert-Rejected 'current-missing-package' { param($p) Remove-Item (Join-Path $p 'package-manifest.json') } 'IDENTITY_CURRENT_PAIR_INCOMPLETE'
    Assert-Rejected 'source-mismatch' {
        param($p) $file=Join-Path $p 'swirl-rust-build.json';$json=Read-SwirlIdentityJson $file 65536
        $json.source_sha='b'*40;Write-Json $file $json
    } 'IDENTITY_RUST_METADATA_MISMATCH'
    Assert-Rejected 'build-mismatch' {
        param($p) $file=Join-Path $p 'swirl-rust-build.json';$json=Read-SwirlIdentityJson $file 65536
        $json.build_id='b'*64;Write-Json $file $json
    } 'IDENTITY_RUST_BUILD_MISMATCH'
    Assert-Rejected 'wrong-platform' {
        param($p) $file=Join-Path $p 'swirl-rust-build.json';$json=Read-SwirlIdentityJson $file 65536
        $json.target='i686-pc-windows-msvc';Write-Json $file $json
    } 'IDENTITY_RUST_METADATA_MISMATCH'
    Assert-Rejected 'boolean-schema' {
        param($p) $file=Join-Path $p 'package-manifest.json';$json=Read-SwirlIdentityJson $file (8*1024*1024)
        $json.schema=$true;Write-Json $file $json
    } 'IDENTITY_CURRENT_MANIFEST_INVALID'
    Assert-Rejected 'boolean-abi' {
        param($p) $file=Join-Path $p 'swirl-rust-build.json';$json=Read-SwirlIdentityJson $file 65536
        $json.abi_version=$true;Write-Json $file $json
    } 'IDENTITY_RUST_METADATA_MISMATCH'
    Assert-Rejected 'changed-executable' { param($p) [IO.File]::AppendAllText((Join-Path $p 'Swirl.exe'),'wrong build') } 'IDENTITY_FILE_HASH_MISMATCH'
    Assert-Rejected 'changed-dll' { param($p) [IO.File]::AppendAllText((Join-Path $p 'swirl_api.dll'),'wrong build') } 'IDENTITY_FILE_HASH_MISMATCH'
    Assert-Rejected 'changed-rules' { param($p) [IO.File]::AppendAllText((Join-Path $p 'rules/cn-ip.mrs'),'corrupt') } 'IDENTITY_FILE_HASH_MISMATCH'
    Assert-Rejected 'missing-rules' { param($p) Remove-Item (Join-Path $p 'rules/cn-domain.mrs') } 'IDENTITY_FILE_MISSING'
    Assert-Rejected 'unlisted-required' {
        param($p) $file=Join-Path $p 'package-manifest.json';$json=Read-SwirlIdentityJson $file (8*1024*1024)
        $json.files[0].path='other.exe';Write-Json $file $json
    } 'IDENTITY_REQUIRED_FILE_UNLISTED'
    Assert-Rejected 'duplicate-path-case' {
        param($p) $file=Join-Path $p 'package-manifest.json';$json=Read-SwirlIdentityJson $file (8*1024*1024)
        $json.files+=@([pscustomobject]@{path='SWIRL.EXE';sha256='0'*64});Write-Json $file $json
    } 'IDENTITY_MANIFEST_ENTRY_INVALID'
    foreach ($badPath in @('../outside','/absolute','C:/outside','rules/../Swirl.exe','rules\\file','rules//file','Swirl.exe.','Swirl.exe ')) {
        $script:badPath = $badPath
        Assert-Rejected ('unsafe-path-'+$script:passed) {
            param($p) $file=Join-Path $p 'package-manifest.json';$json=Read-SwirlIdentityJson $file (8*1024*1024)
            $json.files[0].path=$script:badPath;Write-Json $file $json
        } 'IDENTITY_MANIFEST_ENTRY_INVALID'
    }
    Assert-Rejected 'bad-json' { param($p) [IO.File]::WriteAllText((Join-Path $p 'package-manifest.json'),'{') } 'IDENTITY_METADATA_SIZE'
    Assert-Rejected 'invalid-json' { param($p) [IO.File]::WriteAllText((Join-Path $p 'package-manifest.json'),'{broken}') } 'IDENTITY_METADATA_JSON'
    Assert-Rejected 'array-json' { param($p) [IO.File]::WriteAllText((Join-Path $p 'package-manifest.json'),'[]') } 'IDENTITY_METADATA_OBJECT'
    Assert-Rejected 'single-manifest-array' {
        param($p) $file=Join-Path $p 'package-manifest.json';$json=[IO.File]::ReadAllText($file)
        [IO.File]::WriteAllText($file,(" `r`n["+$json+"] `r`n"))
    } 'IDENTITY_METADATA_OBJECT'
    Assert-Rejected 'multiple-manifest-array' {
        param($p) $file=Join-Path $p 'package-manifest.json';$json=[IO.File]::ReadAllText($file)
        [IO.File]::WriteAllText($file,('['+$json+','+$json+']'))
    } 'IDENTITY_METADATA_OBJECT'
    Assert-Rejected 'single-rust-array' {
        param($p) $file=Join-Path $p 'swirl-rust-build.json';$json=[IO.File]::ReadAllText($file)
        [IO.File]::WriteAllText($file,('['+$json+']'))
    } 'IDENTITY_METADATA_OBJECT'
    Assert-Rejected 'single-legacy-array' {
        param($p) $file=Join-Path $p 'PRODUCT.json';$json=[IO.File]::ReadAllText($file)
        [IO.File]::WriteAllText($file,('['+$json+']'))
    } 'IDENTITY_METADATA_OBJECT' $true
    Assert-Rejected 'nested-rust-array' {
        param($p) $file=Join-Path $p 'package-manifest.json';$json=Read-SwirlIdentityJson $file (8*1024*1024)
        $json.rust=@($json.rust);Write-Json $file $json
    } 'IDENTITY_CURRENT_MANIFEST_INVALID'
    Assert-Rejected 'nested-file-entry-array' {
        param($p) $file=Join-Path $p 'package-manifest.json';$json=Read-SwirlIdentityJson $file (8*1024*1024)
        $json.files[0]=@($json.files[0]);Write-Json $file $json
    } 'IDENTITY_MANIFEST_ENTRY_INVALID'
    Assert-Rejected 'oversized-json' { param($p) [IO.File]::WriteAllText((Join-Path $p 'swirl-rust-build.json'),(' ' * 65537)) } 'IDENTITY_METADATA_SIZE'
    Assert-Rejected 'legacy-build-disabled' { param($p) [IO.File]::WriteAllText((Join-Path $p 'BUILD.txt'),"$source SWIRL_USE_RUST_CORE=OFF") } 'IDENTITY_LEGACY_BUILD_MISMATCH' $true
    Assert-Rejected 'legacy-core-claim' {
        param($p) $file=Join-Path $p 'PRODUCT.json';$json=Read-SwirlIdentityJson $file 131072
        $json.rustCore='true';Write-Json $file $json
    } 'IDENTITY_LEGACY_MANIFEST_INVALID' $true
    Assert-Rejected 'legacy-corrupt-dll' { param($p) [IO.File]::AppendAllText((Join-Path $p 'swirl_api.dll'),'wrong') } 'IDENTITY_FILE_HASH_MISMATCH' $true
    Assert-Rejected 'legacy-incomplete' { param($p) Remove-Item (Join-Path $p 'BUILD.txt') } 'IDENTITY_LEGACY_PAIR_INCOMPLETE' $true

    $tools = Split-Path $PSScriptRoot -Parent
    $readOnlyTools = @('SwirlCoreIdentity.ps1','Test-SwirlCoreOffline.ps1','Test-SwirlPrivateDirect.ps1')
    $denied = @('Set-ItemProperty','New-ItemProperty','Remove-ItemProperty','Register-ScheduledTask','Start-ScheduledTask',
        'New-Service','Start-Service','Stop-Process','Invoke-Expression','Invoke-WebRequest','Invoke-RestMethod','Start-BitsTransfer','Start-Process','Add-Type')
    foreach ($name in $readOnlyTools) {
        $tokens=$null;$errors=$null
        $ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $tools $name),[ref]$tokens,[ref]$errors)
        if ($errors.Count) { throw "PowerShell syntax error in $name : $($errors[0].Message)" }
        $commands=$ast.FindAll({param($n) $n -is [Management.Automation.Language.CommandAst]},$true)
        foreach ($command in $commands) {
            if ($command.GetCommandName() -in $denied) { throw "Side-effecting command in $name : $($command.GetCommandName())" }
        }
    }
    foreach ($name in @('Monitor-SwirlCore.ps1','Test-SwirlMihomoPath.ps1',
                        'Invoke-WindowsRustIndependentAcceptance.ps1','Start-WindowsRustIndependentAcceptance.ps1')) {
        if (Test-Path -LiteralPath (Join-Path $tools $name)) { throw "Retired external-core tool returned: $name" }
    }
    $script:passed++
    Write-Output "Swirl Core identity: PASS ($script:passed cases; current and legacy manifests, mix/tamper rejection, read-only script guards)."
} finally {
    if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($root)) -ne [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\','/')) { throw 'Unexpected test cleanup path.' }
    Remove-Item -LiteralPath $root -Recurse -Force
}
