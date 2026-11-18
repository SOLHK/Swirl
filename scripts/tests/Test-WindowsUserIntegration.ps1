param(
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory,
    [string]$ExpectedSourceSha,
    [string]$ExpectedUserSid,
    [string]$LegacyInstallerSource,
    [string]$LegacyIntegrationHelper
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $repo 'scripts/WindowsUserIntegration.ps1')
. (Join-Path $PSScriptRoot 'WindowsShortcutFixture.ps1')
. (Join-Path $PSScriptRoot 'WindowsProcessCapture.ps1')
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
    # Preserve the exact old helper for the native System.dll shadowing control.
    $helperBaseline='7c756b1773934ebfde82c42769d5ccfde7427f1d'
    & git -C $repo cat-file -e $helperBaseline 2>$null
    if($LASTEXITCODE -ne 0){& git -C $repo fetch --no-tags --depth=1 origin $helperBaseline;if($LASTEXITCODE -ne 0){throw 'Exact legacy integration helper is unavailable.'}}
    $legacyHelperDirectory=Join-Path $evidence 'legacy-integration-helper'
    [IO.Directory]::CreateDirectory($legacyHelperDirectory)|Out-Null
    $legacyHelper=Join-Path $legacyHelperDirectory 'WindowsUserIntegration.ps1'
    $process=New-Object Diagnostics.Process
    $process.StartInfo.FileName='git';$process.StartInfo.WorkingDirectory=$repo
    $process.StartInfo.Arguments='cat-file blob '+$helperBaseline+':scripts/WindowsUserIntegration.ps1'
    $process.StartInfo.UseShellExecute=$false;$process.StartInfo.RedirectStandardOutput=$true
    $stream=[IO.File]::Create($legacyHelper)
    try{$null=$process.Start();$process.StandardOutput.BaseStream.CopyTo($stream);$process.WaitForExit();if($process.ExitCode -ne 0){throw 'Cannot read exact legacy integration helper bytes.'}}
    finally{$stream.Dispose();$process.Dispose()}
    $legacyHelperBlob=(& git -C $repo hash-object $legacyHelper).Trim()
    if($LASTEXITCODE -ne 0 -or $legacyHelperBlob -cne 'b7413edb755ab4e90a9298a9652a17e3a00dc2ec'){throw 'Legacy integration helper differs from the recorded Git blob.'}
    [IO.File]::Copy((Join-Path $repo 'scripts/RustProductPackagePolicy.ps1'),(Join-Path $legacyHelperDirectory 'RustProductPackagePolicy.ps1'),$true)
    $argsPath=Join-Path $evidence 'child-arguments.json'
    @{EvidenceDirectory=$evidence;ExpectedSourceSha=$source;LegacyInstallerSource=$legacy;LegacyIntegrationHelper=$legacyHelper}|ConvertTo-Json|Set-Content -LiteralPath $argsPath -Encoding UTF8
    & (Join-Path $PSScriptRoot 'Invoke-DisposableWindowsUser.ps1') -Script $PSCommandPath -ArgumentsFile $argsPath -EvidenceDirectory $evidence -TimeoutSeconds 240
    $capturePolicy=Get-Content -LiteralPath (Join-Path $evidence 'process-capture/process-capture-policy.json') -Raw -Encoding UTF8|ConvertFrom-Json
    if($capturePolicy.schema -ne 1 -or -not $capturePolicy.success -or $capturePolicy.source_sha -cne $source -or -not $capturePolicy.actual_non_admin_token -or -not $capturePolicy.actual_x86_powershell -or $capturePolicy.forced_termination -or -not $capturePolicy.fixture_removed -or @($capturePolicy.processes).Count -ne 5 -or @($capturePolicy.processes|Where-Object {-not $_.passed}).Count){throw 'Actual x86 standard-user process capture evidence is incomplete.'}
    $shortcutPolicy=Get-Content -LiteralPath (Join-Path $evidence 'shortcut-fixture/shortcut-fixture-policy.json') -Raw -Encoding UTF8|ConvertFrom-Json
    if($shortcutPolicy.schema -ne 1 -or -not $shortcutPolicy.success -or $shortcutPolicy.source_sha -cne $source -or $shortcutPolicy.user_sid -cne $capturePolicy.user_sid -or -not $shortcutPolicy.actual_non_admin_token -or -not $shortcutPolicy.actual_x86_powershell -or -not $shortcutPolicy.fixture_removed -or -not $shortcutPolicy.operation.success -or -not $shortcutPolicy.operation.staging_removed -or -not $shortcutPolicy.operation.final_bytes_match -or -not $shortcutPolicy.operation.target_matches -or -not $shortcutPolicy.operation.arguments_match -or -not $shortcutPolicy.operation.description_matches){throw 'Actual x86 standard-user Unicode shortcut fixture evidence is incomplete.'}
    $result=Get-Content -LiteralPath (Join-Path $evidence 'integration-policy.json') -Raw -Encoding UTF8|ConvertFrom-Json
    if(-not $result.success -or $result.source_sha -cne $source -or -not $result.negative_control.required_assertion_failed){throw 'Integration policy or legacy negative-control evidence is incomplete.'}
    Write-Host 'Raw registry/shortcut ownership, upgrade, recovery and legacy negative control verified in actual x86 standard-user PowerShell.'
    return
}

$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal $identity
if($identity.User.Value -cne $ExpectedUserSid -or $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -or [Environment]::Is64BitProcess){throw 'Integration child must use the actual new standard-user x86 token.'}
& (Join-Path $PSScriptRoot 'Test-WindowsProcessCapture.ps1') -EvidenceDirectory (Join-Path $evidence 'process-capture') -ExpectedUserSid $ExpectedUserSid -ExpectedSourceSha $ExpectedSourceSha
# The normal installer uses this exact fixture function for pre-existing and
# later edited real shortcuts. Exercise its Unicode final path before builds.
$shortcutEvidence=Join-Path $evidence 'shortcut-fixture'
$null=[IO.Directory]::CreateDirectory($shortcutEvidence)
$shortcutRoot=Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) ('SwirlUnicodeShortcutPolicy-'+[guid]::NewGuid().ToString('N'))
$shortcutDirectory=Join-Path $shortcutRoot '原始 快捷方式'
$shortcutPath=Join-Path $shortcutDirectory '通过 Swirl 启动 Codex.lnk'
$shortcutReport=[ordered]@{schema=1;source_sha=$ExpectedSourceSha;user_sid=$ExpectedUserSid;actual_non_admin_token=$true;actual_x86_powershell=$true;powershell_version=$PSVersionTable.PSVersion.ToString();helper_sha256=(Get-SwirlIntegrationHash (Join-Path $PSScriptRoot 'WindowsShortcutFixture.ps1'));operation=$null;fixture_removed=$false;success=$false;error=$null}
try {
    $null=Assert-SwirlIntegrationPath $shortcutRoot
    if(Test-Path -LiteralPath $shortcutRoot){throw 'The unique Unicode shortcut fixture directory already exists.'}
    $shortcutReport.operation=Save-SwirlTestShortcut -Path $shortcutPath -Description '用户原始快捷方式 codex-start-menu'
    # Preserve the actual final file bytes with the receipt for independent
    # artifact verification; neither the COM input nor a generated substitute.
    if([IO.File]::Exists($shortcutPath)){[IO.File]::WriteAllBytes((Join-Path $shortcutEvidence 'final-unicode-shortcut.lnk'),[IO.File]::ReadAllBytes($shortcutPath))}
    $shortcutReport.success=$shortcutReport.operation.success -and $shortcutReport.operation.staging_removed
    if(-not $shortcutReport.success){$shortcutReport.error=$shortcutReport.operation.error}
}catch{$shortcutReport.error=$_.Exception.Message;$shortcutReport.success=$false}
finally {
    try {
        foreach($path in @($shortcutPath,$shortcutDirectory,$shortcutRoot)){$null=Assert-SwirlIntegrationPath $path}
        if([IO.File]::Exists($shortcutPath)){[IO.File]::Delete($shortcutPath)}
        if([IO.Directory]::Exists($shortcutDirectory)){[IO.Directory]::Delete($shortcutDirectory,$false)}
        if([IO.Directory]::Exists($shortcutRoot)){[IO.Directory]::Delete($shortcutRoot,$false)}
        $shortcutReport.fixture_removed=-not [IO.Directory]::Exists($shortcutRoot)
    }catch{$shortcutReport.success=$false;$shortcutReport.error=([string]$shortcutReport.error+'; Unicode shortcut fixture cleanup: '+$_.Exception.Message)}
    if(-not $shortcutReport.fixture_removed){$shortcutReport.success=$false}
    $shortcutReport|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $shortcutEvidence 'shortcut-fixture-policy.json') -Encoding UTF8
}
if(-not $shortcutReport.success){throw ('Unicode shortcut fixture regression failed: '+$shortcutReport.error)}
$root=Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) ('SwirlIntegrationPolicy-'+[guid]::NewGuid().ToString('N'))
$null=Assert-SwirlIntegrationPath $root
[IO.Directory]::CreateDirectory($root)|Out-Null
$manifestPath=Join-Path $root 'package-manifest.json'
@{schema=1;source_sha=$ExpectedSourceSha;rust=@{source_sha=$ExpectedSourceSha};files=@()}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $manifestPath -Encoding UTF8
$context=New-SwirlIntegrationContext $root $manifestPath '0.2.33'
$cases=New-Object 'System.Collections.Generic.List[object]'
$rawRoundTrips=New-Object 'System.Collections.Generic.List[object]'
$helperProcesses=New-Object 'System.Collections.Generic.List[object]'
$shadowDirectory=Join-Path $root 'native-plugin-cwd'
[IO.Directory]::CreateDirectory($shadowDirectory)|Out-Null
# A trusted native Windows DLL has no .NET metadata, just like NSIS System.dll.
# It is copied, never executed, to reproduce the compiler's basename collision.
$shadowDll=Join-Path $shadowDirectory 'System.dll'
[IO.File]::Copy((Join-Path ([Environment]::SystemDirectory) 'version.dll'),$shadowDll,$false)
$helperBootstrap=[ordered]@{legacy_source_commit='7c756b1773934ebfde82c42769d5ccfde7427f1d';legacy_source_blob='b7413edb755ab4e90a9298a9652a17e3a00dc2ec';legacy_helper_sha256=(Get-SwirlIntegrationHash $LegacyIntegrationHelper);native_shadow_sha256=(Get-SwirlIntegrationHash $shadowDll);legacy_cs0009_observed=$false;legacy_compiler_error=$null;processes=$helperProcesses}
$legacyProbe=Join-Path $evidence 'legacy-helper-probe.ps1'
$probeSource=@'
param([string]$Helper)
$ErrorActionPreference='Stop'
try { & $Helper }
catch {
    # Windows PowerShell 5.1 omits ErrorNumber from its formatted error text.
    # Preserve the actual compiler ErrorRecord instead of guessing from text.
    $failure=$_;$compiler=$failure.TargetObject
    $number=if($null -ne $compiler -and $null -ne $compiler.PSObject.Properties['ErrorNumber']){[string]$compiler.ErrorNumber}else{''}
    [ordered]@{error_number=$number;error_id=[string]$failure.FullyQualifiedErrorId}|ConvertTo-Json -Compress|Write-Output
    [Console]::Error.WriteLine(($failure|Out-String))
    exit 1
}
'@
[IO.File]::WriteAllText($legacyProbe,$probeSource,(New-Object Text.UTF8Encoding($false)))
$legacyWriter=[ordered]@{scope='A test-only RegSetValueExW probe with explicit zero padding outside cbData; not a claim about unrecorded bytes in the earlier CI failure.';executed=$false;expected=$null;observed=$null;requested_byte_count=$null;observed_byte_count=$null;appended_one_utf16_null=$false}
$negative=[ordered]@{scope='Exact old unconditional cleanup operations on synthetic standard-user integration; actual old NSIS executable is tested separately in normal lifecycle.';source_commit='b6e22aad6cdaa370c95a35abe9f935cf0d91aa81';source_sha256=(Get-SwirlIntegrationHash $LegacyInstallerSource);executed=$false;assertion='original-integration-and-later-user-edits-preserved';observed_pass=$null;required_assertion_failed=$false}
$errorText=$null

# This deliberately exercises the old Win32 API, separate from the production
# writer. Padding makes the length-adjacent NUL observable and deterministic;
# no byte beyond an allocated buffer is read or written by this fixture.
if (-not ('SwirlIntegration.PolicyTests.LegacyRegistryWriter' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

namespace SwirlIntegration.PolicyTests {
    public static class LegacyRegistryWriter {
        [DllImport("advapi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
        private static extern int RegOpenKeyExW(IntPtr root, string path, int options, int access, out IntPtr key);
        [DllImport("advapi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
        private static extern int RegSetValueExW(IntPtr key, string name, int reserved,
            UInt32 type, byte[] data, int size);
        [DllImport("advapi32.dll", ExactSpelling=true)]
        private static extern int RegCloseKey(IntPtr key);

        public static void WriteWithZeroPadding(string path, string name, UInt32 type, byte[] bytes) {
            if (bytes == null || bytes.Length > 65536) throw new ArgumentException("Invalid test buffer.");
            byte[] padded = new byte[bytes.Length + 2];
            Buffer.BlockCopy(bytes, 0, padded, 0, bytes.Length);
            IntPtr key;
            int error = RegOpenKeyExW(new IntPtr(unchecked((int)0x80000001)), path, 0, 0x0002 | 0x0200, out key);
            if (error != 0) throw new Win32Exception(error);
            try {
                error = RegSetValueExW(key, name, 0, type, padded, bytes.Length);
                if (error != 0) throw new Win32Exception(error);
            } finally { RegCloseKey(key); }
        }
    }
}
'@
}

function Require([string]$Name,[bool]$Passed) {
    $cases.Add([ordered]@{name=$Name;passed=$Passed})
    if(-not $Passed){throw ('Integration regression failed: '+$Name)}
}
function Invoke-HelperProcess([string]$Name,[string]$Helper,[string]$WorkingDirectory,[string]$HelperMode,[int]$ExpectedExit,[string]$ProbeHelper='') {
    $stdout=Join-Path $evidence ($Name+'.stdout.log');$stderr=Join-Path $evidence ($Name+'.stderr.log')
    $arguments='-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$Helper+'"'
    if($ProbeHelper){$arguments+=' -Helper "'+$ProbeHelper+'"'}
    if($HelperMode){$arguments+=' -Mode '+$HelperMode+' -ApplicationDirectory "'+$root+'" -ExpectedManifest "'+$manifestPath+'" -AppVersion "0.2.33"'}
    $entry=[ordered]@{name=$Name;expected_exit=$ExpectedExit;exit_code=$null;outputs_complete=$false;forced_termination=$false}
    $helperProcesses.Add($entry);$capture=$null
    try {
        $capture=Start-SwirlCapturedProcess -Executable (Join-Path $PSHOME 'powershell.exe') -Arguments $arguments -WorkingDirectory $WorkingDirectory -StdoutPath $stdout -StderrPath $stderr
        if(-not (Wait-SwirlCapturedProcess $capture 30000)){throw ('Integration helper process timed out: '+$Name)}
        Require ($Name+'-exit-code') ($capture.ExitCode -eq $ExpectedExit)
    }finally {
        if($null -ne $capture){try{Close-SwirlCapturedProcess $capture}finally{$entry.exit_code=$capture.ExitCode;$entry.outputs_complete=$capture.OutputsComplete;$entry.forced_termination=$capture.ForcedTermination}}
    }
    Require ($Name+'-bounded-process-completed') ($entry.outputs_complete -and -not $entry.forced_termination)
    return $stderr
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
    # Fresh processes exercise the actual -File entry before expensive builds.
    # The exact old helper must compile from a clean cwd, then fail specifically
    # with CS0009 when the native plugin name shadows its bare System.dll ref.
    $null=Invoke-HelperProcess 'legacy-helper-clean-cwd' $legacyProbe $root '' 0 $LegacyIntegrationHelper
    $null=Invoke-HelperProcess 'legacy-helper-native-shadow' $legacyProbe $shadowDirectory '' 1 $LegacyIntegrationHelper
    $compilerFailure=Get-Content -LiteralPath (Join-Path $evidence 'legacy-helper-native-shadow.stdout.log') -Raw -Encoding UTF8|ConvertFrom-Json
    $helperBootstrap.legacy_cs0009_observed=$compilerFailure.error_number -ceq 'CS0009' -and $compilerFailure.error_id -ceq 'SOURCE_CODE_ERROR,Microsoft.PowerShell.Commands.AddTypeCommand'
    $helperBootstrap.legacy_compiler_error=$compilerFailure
    Require 'legacy-helper-fails-on-native-system-dll-metadata' $helperBootstrap.legacy_cs0009_observed
    $currentHelper=Join-Path $repo 'scripts/WindowsUserIntegration.ps1'
    $null=Invoke-HelperProcess 'current-helper-validates-with-native-shadow' $currentHelper $shadowDirectory 'ValidateUninstall' 0
    $installedState=Snapshot;$savedReceipt=[IO.File]::ReadAllBytes($context.Receipt)
    foreach($field in @('source_sha','manifest_sha256','helper_sha256')) {
        try {
            $bad=Read-SwirlIntegrationReceipt $context
            $bad.$field='0' * ([string]$bad.$field).Length
            Write-SwirlIntegrationReceipt $context $bad
            $null=Invoke-HelperProcess ('current-helper-rejects-'+$field) $currentHelper $shadowDirectory 'ValidateUninstall' 1
            Require ('identity-mismatch-preserves-integration-'+$field) ((Snapshot) -ceq $installedState)
        }finally{[IO.File]::WriteAllBytes($context.Receipt,$savedReceipt)}
    }
    $null=Invoke-HelperProcess 'current-helper-uninstalls-with-native-shadow' $currentHelper $shadowDirectory 'Uninstall' 0
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
    $original=Seed
    [byte[]]$probeBytes=$rawStrings[0].bytes
    $legacyWriter.expected=[ordered]@{exists=$true;type=[uint32]1;bytes=[Convert]::ToBase64String($probeBytes)}
    $legacyWriter.requested_byte_count=$probeBytes.Length
    $target=$context.Targets['display-name']
    [SwirlIntegration.PolicyTests.LegacyRegistryWriter]::WriteWithZeroPadding($target.key,$target.name,[uint32]1,$probeBytes)
    $legacyWriter.executed=$true
    $legacyWriter.observed=Get-SwirlIntegrationState $context 'display-name'
    $legacyWriter.observed_byte_count=[Convert]::FromBase64String($legacyWriter.observed.bytes).Length
    $withTerminator=[ordered]@{exists=$true;type=[uint32]1;bytes=[Convert]::ToBase64String([byte[]]($probeBytes+0+0))}
    $legacyWriter.appended_one_utf16_null=Test-SwirlIntegrationState $legacyWriter.observed $withTerminator
    Require 'legacy-regsetvalueexw-probe-changes-declared-raw-bytes' ($legacyWriter.appended_one_utf16_null -and -not (Test-SwirlIntegrationState $legacyWriter.observed $legacyWriter.expected))
    foreach($case in $rawStrings){
        $original=Seed
        $rawState=[ordered]@{exists=$true;type=$case.type;bytes=[Convert]::ToBase64String([byte[]]$case.bytes)}
        $rawResult=[ordered]@{name=$case.name;expected=$rawState;after_seed=$null;after_install=$null;after_uninstall=$null;seed_exact=$false;restore_exact=$false}
        $rawRoundTrips.Add($rawResult)
        try { Set-SwirlIntegrationState $context 'display-name' $rawState }
        finally {
            $rawResult.after_seed=Get-SwirlIntegrationState $context 'display-name'
            $rawResult.seed_exact=Test-SwirlIntegrationState $rawResult.after_seed $rawState
        }
        Require ('native-raw-fixture-retained-'+$case.name) $rawResult.seed_exact
        $wanted=Desired 'raw-roundtrip';$null=Install-SwirlUserIntegration $context $wanted
        $rawResult.after_install=Get-SwirlIntegrationState $context 'display-name'
        try { $null=Uninstall-SwirlUserIntegration $context }
        finally {
            $rawResult.after_uninstall=Get-SwirlIntegrationState $context 'display-name'
            $rawResult.restore_exact=Test-SwirlIntegrationState $rawResult.after_uninstall $rawState
        }
        Require ('uninstall-restores-exact-raw-registry-'+$case.name) $rawResult.restore_exact
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
    $report=[ordered]@{schema=1;source_sha=$ExpectedSourceSha;helper_sha256=$context.HelperHash;user_sid=$ExpectedUserSid;actual_non_admin_token=$true;actual_x86_powershell=$true;registry_snapshot_format='Win32 DWORD type and exact RegQueryValueExW bytes';registry_write_api='NtSetValueKey with exact DataSize';scope='Real raw HKCU and shortcut transaction tests in a disposable standard-user profile; synthetic values and bytes, not product UI acceptance.';cases=@($cases.ToArray());raw_registry_roundtrips=@($rawRoundTrips.ToArray());helper_bootstrap=$helperBootstrap;legacy_writer_probe=$legacyWriter;negative_control=$negative;success=($null -eq $errorText -and @($cases|Where-Object {-not $_.passed}).Count -eq 0 -and $negative.required_assertion_failed);error=$errorText}
    $report|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $evidence 'integration-policy.json') -Encoding UTF8
}
if(-not $report.success){throw ('User integration policy regression failed: '+$errorText)}
