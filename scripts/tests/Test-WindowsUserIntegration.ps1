param(
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory,
    [string]$ExpectedSourceSha,
    [string]$ExpectedUserSid,
    [string]$LegacyInstallerSource
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $repo 'scripts/WindowsUserIntegration.ps1')
$evidence=[IO.Path]::GetFullPath($EvidenceDirectory)
[IO.Directory]::CreateDirectory($evidence)|Out-Null

if (-not $ExpectedUserSid) {
    if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:SWIRL_DISPOSABLE_INSTALL_TEST -ne '1') {
        throw 'Integration execution requires an opted-in disposable hosted Windows runner.'
    }
    $source=(& git -C $repo rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $source -notmatch '^[0-9a-f]{40}$' -or ($ExpectedSourceSha -and $source -cne $ExpectedSourceSha)) { throw 'Integration regression source identity mismatch.' }
    $baseline='b6e22aad6cdaa370c95a35abe9f935cf0d91aa81'
    & git -C $repo cat-file -e $baseline 2>$null
    if ($LASTEXITCODE -ne 0) {
        & git -C $repo fetch --no-tags --depth=1 origin $baseline
        if ($LASTEXITCODE -ne 0) { throw 'Exact legacy installer commit is unavailable.' }
    }
    $legacy=Join-Path $evidence 'legacy-Swirl.nsi'
    $process=New-Object Diagnostics.Process
    $process.StartInfo.FileName='git';$process.StartInfo.WorkingDirectory=$repo
    $process.StartInfo.Arguments='cat-file blob '+$baseline+':src/Swirl.Quick/packaging/Swirl.nsi'
    $process.StartInfo.UseShellExecute=$false;$process.StartInfo.RedirectStandardOutput=$true
    $stream=[IO.File]::Create($legacy)
    try {$null=$process.Start();$process.StandardOutput.BaseStream.CopyTo($stream);$process.WaitForExit();if($process.ExitCode -ne 0){throw 'Cannot read exact legacy NSIS bytes.'}}
    finally {$stream.Dispose();$process.Dispose()}
    $argsPath=Join-Path $evidence 'child-arguments.json'
    @{EvidenceDirectory=$evidence;ExpectedSourceSha=$source;LegacyInstallerSource=$legacy}|ConvertTo-Json|Set-Content -LiteralPath $argsPath -Encoding UTF8
    & (Join-Path $PSScriptRoot 'Invoke-DisposableWindowsUser.ps1') -Script $PSCommandPath -ArgumentsFile $argsPath -EvidenceDirectory $evidence -TimeoutSeconds 240
    $result=Get-Content -LiteralPath (Join-Path $evidence 'integration-policy.json') -Raw -Encoding UTF8|ConvertFrom-Json
    if(-not $result.success -or $result.source_sha -cne $source -or -not $result.negative_control.required_assertion_failed){throw 'Integration policy or legacy negative-control evidence is incomplete.'}
    Write-Host 'Raw registry/shortcut ownership, upgrade, recovery and legacy negative control verified in actual x86 standard-user PowerShell.'
    return
}

$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal $identity
if($identity.User.Value -cne $ExpectedUserSid -or $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -or [Environment]::Is64BitProcess){throw 'Integration child must use the actual new standard-user x86 token.'}
$root=Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) ('SwirlIntegrationPolicy-'+[guid]::NewGuid().ToString('N'))
$null=Assert-SwirlIntegrationPath $root
[IO.Directory]::CreateDirectory($root)|Out-Null
$manifestPath=Join-Path $root 'package-manifest.json'
@{schema=1;source_sha=$ExpectedSourceSha;rust=@{source_sha=$ExpectedSourceSha};files=@()}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $manifestPath -Encoding UTF8
$context=New-SwirlIntegrationContext $root $manifestPath '0.2.33'
$cases=New-Object 'System.Collections.Generic.List[object]'
$negative=[ordered]@{scope='Exact old unconditional cleanup operations on synthetic standard-user integration; actual old NSIS executable is tested separately in normal lifecycle.';source_commit='b6e22aad6cdaa370c95a35abe9f935cf0d91aa81';source_sha256=(Get-SwirlIntegrationHash $LegacyInstallerSource);executed=$false;assertion='original-integration-and-later-user-edits-preserved';observed_pass=$null;required_assertion_failed=$false}
$errorText=$null

function Require([string]$Name,[bool]$Passed) {
    $cases.Add([ordered]@{name=$Name;passed=$Passed})
    if(-not $Passed){throw ('Integration regression failed: '+$Name)}
}
function Bytes([string]$Text){return [ordered]@{exists=$true;bytes=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Text))}}
function Snapshot {
    $states=[ordered]@{}
    foreach($id in @($context.Targets.Keys|Sort-Object)){$states[$id]=Get-SwirlIntegrationState $context $id}
    $hive=Open-SwirlIntegrationHive;$extra=$null
    try {
        $key=$hive.OpenSubKey('Software\Swirl\UserOwned',$false)
        if($null -ne $key){try{$extra=@{kind=$key.GetValueKind('Preserve').ToString();value=$key.GetValue('Preserve')}}finally{$key.Dispose()}}
    }finally{$hive.Dispose()}
    return ConvertTo-SwirlIntegrationJson ([ordered]@{states=$states;extra=$extra})
}
function Seed {
    if([IO.File]::Exists($context.Receipt)){[IO.File]::Delete($context.Receipt)}
    $original=@{
        'install-directory'=(New-SwirlRegistryValueState -Kind String -Value $root)
        'display-name'=(New-SwirlRegistryValueState -Kind ExpandString -Value '%LOCALAPPDATA%\Original')
        'display-version'=(New-SwirlRegistryValueState -Kind Binary -Value ([byte[]](0,1,255,42)))
        'install-location'=(New-SwirlRegistryValueState -Kind MultiString -Value @('first','','第三项'))
        'uninstall-command'=(New-SwirlRegistryValueState -Kind QWord -Value '9223372036854775806')
        'display-icon'=(New-SwirlRegistryValueState -Kind None -Value ([byte[]](2,0,17)))
        'publisher'=(New-SwirlRegistryValueState -Kind String -Value 'Original publisher')
        'no-modify'=(New-SwirlRegistryValueState -Kind DWord -Value '-2147483648')
        'no-repair'=(New-SwirlRegistryValueState -Kind DWord -Value 0)
    }
    foreach($id in @('desktop','start-menu','codex-start-menu','owned-pin')){$original[$id]=Bytes ('Original exact bytes '+$id)}
    foreach($id in $original.Keys){Set-SwirlIntegrationState $context $id $original[$id]}
    $hive=Open-SwirlIntegrationHive
    try {$key=$hive.CreateSubKey('Software\Swirl\UserOwned');try{$key.SetValue('Preserve',[long]9223372036854775806,[Microsoft.Win32.RegistryValueKind]::QWord)}finally{$key.Dispose()}}
    finally{$hive.Dispose()}
    return $original
}
function Desired([string]$Suffix) {
    $values=@{}
    foreach($id in $context.Targets.Keys){
        $values[$id]=if($context.Targets[$id].kind -eq 'shortcut'){Bytes ('Installed '+$id+' '+$Suffix)}else{New-SwirlRegistryValueState -Kind String -Value ('Installed '+$id+' '+$Suffix)}
    }
    return $values
}
try {
    $legacyText=[IO.File]::ReadAllText($LegacyInstallerSource)
    Require 'negative-control-source-has-old-blanket-key-and-shortcut-deletes' ($legacyText.Contains('DeleteRegKey HKCU "Software\\Swirl"') -and $legacyText.Contains('Delete "$DESKTOP\\Swirl.lnk"') -and -not $legacyText.Contains('MaintainUserIntegration'))
    $original=Seed;$before=Snapshot;$wanted=Desired 'v1'
    $null=Install-SwirlUserIntegration $context $wanted
    Require 'all-desired-values-and-shortcut-bytes-applied' (@($wanted.Keys|Where-Object {-not (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context $_) $wanted[$_])}).Count -eq 0)
    $receipt=Read-SwirlIntegrationReceipt $context
    Require 'receipt-binds-sid-source-manifest-and-embedded-helper' ($receipt.user_sid -ceq $ExpectedUserSid -and $receipt.source_sha -ceq $ExpectedSourceSha -and $receipt.manifest_sha256 -ceq $context.ManifestHash -and $receipt.helper_sha256 -ceq $context.HelperHash)
    $null=Uninstall-SwirlUserIntegration $context
    Require 'uninstall-restores-all-original-raw-types-and-shortcut-bytes' ((Snapshot) -ceq $before)

    # Write deliberately noncanonical strings with the native API. A typed
    # GetValue/SetValue snapshot would normalize these bytes and cannot pass.
    $rawStrings=@(
        @{name='sz-without-terminator';type=[uint32]1;bytes=[Text.Encoding]::Unicode.GetBytes('unterminated')},
        @{name='sz-with-extra-terminators';type=[uint32]1;bytes=[Text.Encoding]::Unicode.GetBytes('extra'+[char]0+[char]0+[char]0)},
        @{name='multi-sz-with-empty-item-and-single-final-null';type=[uint32]7;bytes=[Text.Encoding]::Unicode.GetBytes('first'+[char]0+[char]0+'third'+[char]0)},
        @{name='present-zero-byte-expand-sz';type=[uint32]2;bytes=[byte[]]@()},
        @{name='sz-with-odd-byte-count';type=[uint32]1;bytes=[byte[]](65,0,66)}
    )
    foreach($case in $rawStrings){
        $original=Seed
        $rawState=[ordered]@{exists=$true;type=$case.type;bytes=[Convert]::ToBase64String([byte[]]$case.bytes)}
        Set-SwirlIntegrationState $context 'display-name' $rawState
        Require ('native-raw-fixture-retained-'+$case.name) (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'display-name') $rawState)
        $wanted=Desired 'raw-roundtrip';$null=Install-SwirlUserIntegration $context $wanted
        $null=Uninstall-SwirlUserIntegration $context
        Require ('uninstall-restores-exact-raw-registry-'+$case.name) (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'display-name') $rawState)
    }

    $original=Seed;$wanted=Desired 'v1';$null=Install-SwirlUserIntegration $context $wanted
    $edited=Bytes 'A later user replacement shortcut'
    $editedValue=New-SwirlRegistryValueState -Kind Binary -Value ([byte[]](51,0,255))
    Set-SwirlIntegrationState $context 'desktop' $edited
    Set-SwirlIntegrationState $context 'publisher' $editedValue
    Set-SwirlIntegrationState $context 'no-repair' ([ordered]@{exists=$false})
    $null=Uninstall-SwirlUserIntegration $context
    Require 'uninstall-preserves-later-shortcut-value-type-and-deletion' ((Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'desktop') $edited) -and (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'publisher') $editedValue) -and -not (Get-SwirlIntegrationState $context 'no-repair').exists)
    Require 'uninstall-restores-unchanged-owned-values-after-user-edits' (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'display-name') $original['display-name'])

    $original=Seed;$wanted=Desired 'v1';$null=Install-SwirlUserIntegration $context $wanted
    Set-SwirlIntegrationState $context 'desktop' $edited
    Set-SwirlIntegrationState $context 'publisher' $editedValue
    $v2=Desired 'v2';$null=Install-SwirlUserIntegration $context $v2
    Require 'upgrade-does-not-overwrite-later-user-edits' ((Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'desktop') $edited) -and (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'publisher') $editedValue))
    Require 'upgrade-updates-still-owned-integration' (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'display-name') $v2['display-name'])
    $null=Uninstall-SwirlUserIntegration $context
    Require 'upgrade-retains-the-first-installation-baseline' (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'display-version') $original['display-version'])

    $original=Seed;$before=Snapshot
    $containers=Get-SwirlIntegrationContainers $context
    $ops=@(
        [ordered]@{id='display-name';before=(Get-SwirlIntegrationState $context 'display-name');after=$wanted['display-name']},
        [ordered]@{id='desktop';before=(Get-SwirlIntegrationState $context 'desktop');after=$wanted['desktop']}
    )
    $final=New-SwirlIntegrationReceipt $context $containers $ops 'committed'
    $held=[IO.File]::Open($context.Targets['desktop'].path,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    $rejected=$false
    try {try{Invoke-SwirlIntegrationTransaction $context $final $ops}catch{$rejected=$true}}
    finally{$held.Dispose()}
    Require 'real-sharing-failure-is-reported' $rejected
    Require 'rollback-restores-earlier-writes-even-if-another-target-is-locked' (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'display-name') $original['display-name'])
    $pending=Read-SwirlIntegrationReceipt $context
    Require 'failed-recovery-retains-a-bounded-retryable-journal' ($null -ne $pending -and $pending.phase -eq 'pending')
    Restore-SwirlIntegrationTransaction $context $pending
    Require 'retry-after-unlocking-restores-exact-baseline' ((Snapshot) -ceq $before -and -not [IO.File]::Exists($context.Receipt))

    $original=Seed;$wanted=Desired 'v1';$null=Install-SwirlUserIntegration $context $wanted
    $before=Snapshot;$saved=[IO.File]::ReadAllBytes($context.Receipt)
    $bad=Read-SwirlIntegrationReceipt $context;$bad.entries[0].id='../../outside'
    Write-SwirlIntegrationReceipt $context $bad
    $rejected=$false;try{$null=Uninstall-SwirlUserIntegration $context}catch{$rejected=$true}
    Require 'invalid-receipt-is-rejected-before-any-integration-write' ($rejected -and (Snapshot) -ceq $before)
    [IO.File]::WriteAllBytes($context.Receipt,$saved)
    $null=Uninstall-SwirlUserIntegration $context
    $rejected=$false;try{$null=Assert-SwirlIntegrationPath '\\server\share\Swirl'}catch{$rejected=$true}
    Require 'unc-integration-destination-is-rejected' $rejected

    # A negative control performs the old production cleanup operations in
    # this freshly created synthetic profile. Its failed preservation assertion
    # is required; a setup/runtime error is not accepted as the negative result.
    $original=Seed;$before=Snapshot;$wanted=Desired 'legacy'
    foreach($id in $wanted.Keys){Set-SwirlIntegrationState $context $id $wanted[$id]}
    Set-SwirlIntegrationState $context 'desktop' $edited
    Set-SwirlIntegrationState $context 'publisher' $editedValue
    foreach($id in @('desktop','start-menu','codex-start-menu')){[IO.File]::Delete($context.Targets[$id].path)}
    $hive=Open-SwirlIntegrationHive
    try {foreach($key in $context.Keys){$hive.DeleteSubKeyTree($key,$false)}}finally{$hive.Dispose()}
    $negative.executed=$true
    $negative.observed_pass=(Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'desktop') $edited) -and (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'publisher') $editedValue)
    $negative.required_assertion_failed=-not $negative.observed_pass
    Require 'legacy-control-fails-the-same-user-edit-preservation-assertion' $negative.required_assertion_failed
} catch {$errorText=$_.Exception.Message}
finally {
    $report=[ordered]@{schema=1;source_sha=$ExpectedSourceSha;helper_sha256=$context.HelperHash;user_sid=$ExpectedUserSid;actual_non_admin_token=$true;actual_x86_powershell=$true;registry_snapshot_format='Win32 DWORD type and exact RegQueryValueExW bytes';scope='Real raw HKCU and shortcut transaction tests in a disposable standard-user profile; synthetic values and bytes, not product UI acceptance.';cases=@($cases.ToArray());negative_control=$negative;success=($null -eq $errorText -and @($cases|Where-Object {-not $_.passed}).Count -eq 0 -and $negative.required_assertion_failed);error=$errorText}
    $report|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $evidence 'integration-policy.json') -Encoding UTF8
}
if(-not $report.success){throw ('User integration policy regression failed: '+$errorText)}
