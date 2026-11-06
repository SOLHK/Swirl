param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$PackageDirectory,
    [Parameter(Mandatory=$true)][string]$ExpectedSourceSha,
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory,
    [Parameter(Mandatory=$true)][string]$NodeStoreHelper,
    [string]$ExpectedUserSid,
    [string]$ExpectedNodeStoreHelperSha256,
    [object]$NodeStoreHelperEnvironment,
    [ValidateSet('clean','restore','edits','upgrade','cross-version')][string]$Scenario='clean',
    [bool]$NegativeControl=$false,
    [string]$ProductVersion,
    [string]$CrossVersionInput,
    [string]$BaselineInstaller,
    [string]$BaselineAdmission
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $repo 'scripts/WindowsUserIntegration.ps1')
. (Join-Path $PSScriptRoot 'WindowsProcessCapture.ps1')
. (Join-Path $PSScriptRoot 'WindowsShortcutFixture.ps1')
$evidence=[IO.Path]::GetFullPath($EvidenceDirectory)
[IO.Directory]::CreateDirectory($evidence)|Out-Null
$setup=(Resolve-Path -LiteralPath $Installer).Path
$package=(Resolve-Path -LiteralPath $PackageDirectory).Path
$manifestPath=Join-Path $package 'package-manifest.json'
$manifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8|ConvertFrom-Json
if($ExpectedSourceSha -notmatch '^[0-9a-f]{40}$' -or $manifest.source_sha -cne $ExpectedSourceSha -or $manifest.rust.source_sha -cne $ExpectedSourceSha){throw 'Normal installer package source mismatch.'}

function Read-Json([string]$Path){return Get-Content -LiteralPath $Path -Raw -Encoding UTF8|ConvertFrom-Json}
function Fixed-ProductVersion([string]$Path) {
    # These numeric VERSIONINFO fields exist in Windows PowerShell 5.1's
    # .NET Framework as well as the hosted PowerShell 7 parent.
    $info=[Diagnostics.FileVersionInfo]::GetVersionInfo($Path)
    return '{0}.{1}.{2}.{3}' -f $info.ProductMajorPart,$info.ProductMinorPart,$info.ProductBuildPart,$info.ProductPrivatePart
}
$crossVersion=-not [string]::IsNullOrWhiteSpace($CrossVersionInput)
if($crossVersion -or $BaselineInstaller -or $BaselineAdmission -or $Scenario -eq 'cross-version') {
    if(-not $crossVersion -or -not $BaselineInstaller -or -not $BaselineAdmission -or $NegativeControl){throw 'Cross-version acceptance requires all three admitted baseline inputs and no negative-control substitution.'}
    foreach($path in @($CrossVersionInput,$BaselineInstaller,$BaselineAdmission)){Assert-SwirlPathWithoutLinks $path}
    $CrossVersionInput=(Resolve-Path -LiteralPath $CrossVersionInput).Path;$BaselineAdmission=(Resolve-Path -LiteralPath $BaselineAdmission).Path
    $crossInput=Read-Json $CrossVersionInput;$admission=Read-Json $BaselineAdmission
    $old=$crossInput.baseline;$oldSetup=(Resolve-Path -LiteralPath $BaselineInstaller).Path
    if($crossInput.schema -ne 1 -or $crossInput.scope -cne 'optional-pr61-synthetic-cross-version-installer-acceptance' -or
       $crossInput.repository -cne 'SOLHK/Swirl' -or $crossInput.pull_request -ne 61 -or
       $crossInput.head_branch -cne 'work/node-probe-render-20261105' -or $crossInput.base_branch -cne 'test' -or
       $crossInput.opt_in_label -cne 'qa-cross-version-upgrade' -or $crossInput.candidate_version -cne '0.2.40' -or $old.version -cne '0.2.39' -or
       $admission.success -ne $true -or $admission.candidate_source_sha -cne $ExpectedSourceSha -or
       $admission.input_sha256 -cne (Get-SwirlIntegrationHash $CrossVersionInput) -or
       $admission.baseline_source_sha -cne $old.source_sha -or $admission.exe_sha256 -cne $old.exe_sha256 -or
       $admission.run_id -ne $old.run_id -or $admission.artifact_id -ne $old.artifact_id -or $admission.persistence_sources_verified -ne $true -or
       (Get-SwirlIntegrationHash $oldSetup) -cne $old.exe_sha256 -or (Get-Item -LiteralPath $oldSetup).Length -ne $old.exe_bytes -or
       (Fixed-ProductVersion $oldSetup) -cne ($old.version+'.0')) {
        throw 'Cross-version baseline admission, source, hash or version mismatch.'
    }
}
function Profile-ProxyFingerprint {
    # Only a fingerprint leaves the hosted parent profile; never publish any
    # parent proxy URL or credential-bearing registry value.
    $snapshot=[ordered]@{}
    foreach($view in @([Microsoft.Win32.RegistryView]::Registry32,[Microsoft.Win32.RegistryView]::Registry64)) {
        $hive=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,$view)
        try {foreach($suffix in @('','\Connections')) {
            $key=$hive.OpenSubKey(('Software\Microsoft\Windows\CurrentVersion\Internet Settings'+$suffix),$false)
            try {
                $values=[ordered]@{}
                if($null -ne $key){foreach($name in @($key.GetValueNames()|Sort-Object)) {
                    if($suffix -or $name -in @('ProxyEnable','ProxyServer','ProxyOverride','AutoConfigURL','AutoDetect')) {
                        $values[$name]=[ordered]@{kind=$key.GetValueKind($name).ToString();value=$key.GetValue($name,$null,[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)}
                    }
                }}
                $snapshot[($view.ToString()+$suffix)]=$values
            }finally{if($null -ne $key){$key.Dispose()}}
        }}finally{$hive.Dispose()}
    }
    $hash=[Security.Cryptography.SHA256]::Create()
    try{return -join ($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes(($snapshot|ConvertTo-Json -Depth 8 -Compress)))|ForEach-Object {$_.ToString('x2')})}finally{$hash.Dispose()}
}
function Snapshot-Integration([object]$Context) {
    $states=[ordered]@{}
    foreach($id in @($Context.Targets.Keys|Sort-Object)){$states[$id]=Get-SwirlIntegrationState $Context $id}
    function Read-Key([Microsoft.Win32.RegistryKey]$Key) {
        $values=[ordered]@{};$children=[ordered]@{}
        foreach($name in @($Key.GetValueNames()|Sort-Object)){$values[$name]=@{kind=$Key.GetValueKind($name).ToString();value=$Key.GetValue($name,$null,[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)}}
        foreach($name in @($Key.GetSubKeyNames()|Sort-Object)){$child=$Key.OpenSubKey($name,$false);try{$children[$name]=Read-Key $child}finally{$child.Dispose()}}
        return [ordered]@{values=$values;children=$children}
    }
    $keys=[ordered]@{};$hive=Open-SwirlIntegrationHive
    try{foreach($name in $Context.Keys){$key=$hive.OpenSubKey($name,$false);if($null -eq $key){$keys[$name]=$null}else{try{$keys[$name]=Read-Key $key}finally{$key.Dispose()}}}}finally{$hive.Dispose()}
    return ConvertTo-SwirlIntegrationJson ([ordered]@{states=$states;keys=$keys})
}

if(-not $ExpectedUserSid) {
    if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:SWIRL_DISPOSABLE_INSTALL_TEST -ne '1'){throw 'Normal installer execution requires an opted-in disposable hosted Windows runner.'}
    $source=(& git -C $repo rev-parse HEAD).Trim()
    if($LASTEXITCODE -ne 0 -or $source -cne $ExpectedSourceSha){throw 'Normal installer checkout identity mismatch.'}
    $null=Assert-SwirlProductManifest -ApplicationDirectory $package -ExpectedSourceSha $source
    Assert-SwirlPathWithoutLinks $NodeStoreHelper
    $helper=(Resolve-Path -LiteralPath $NodeStoreHelper).Path
    if([IO.Path]::GetFileName($helper) -cne 'SwirlPrivateSubscriptionAcceptance.exe'){throw 'The offline installer fixture requires its separate QA helper.'}
    $helperHash=Get-SwirlIntegrationHash $helper
    $helperPair=Read-Json (Join-Path ([IO.Path]::GetDirectoryName($helper)) 'swirl-rust-build.json')
    # Both configurations use the same Rust input/source identity calculation.
    # Fail on a stale QA helper or differently paired runtime; never bypass it.
    if($helperPair.source_sha -cne $source -or $helperPair.build_id -cne $manifest.rust.build_id){throw 'QA helper and production Rust runtime must have the same exact source/build pairing.'}
    $version=(Get-Content -LiteralPath (Join-Path $repo 'src/Swirl.Quick/PRODUCT_VERSION.txt') -Raw -Encoding UTF8).Trim()
    $installerHash=Get-SwirlIntegrationHash $setup
    $parentContext=New-SwirlIntegrationContext (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs/Swirl') $manifestPath $version
    $parentBefore=Snapshot-Integration $parentContext
    $runs=New-Object 'System.Collections.Generic.List[object]'
    $baseline=[ordered]@{source_commit='b6e22aad6cdaa370c95a35abe9f935cf0d91aa81';scope='Exact legacy NSIS script with current candidate payload and the same current common package-maintenance helper; not the historical complete b6 binary.';source_blob=$null;source_sha256=$null;installer_sha256=$null;compile_exit_code=$null;required_assertion_failed=$false}
    $failure=$null
    function Invoke-NormalCase([string]$Name,[string]$CaseInstaller,[string]$CaseScenario,[bool]$IsNegative,[string]$CaseEvidence) {
        [IO.Directory]::CreateDirectory($CaseEvidence)|Out-Null
        $caseHelper=$helper;$helperRuntime=$null
        if($CaseScenario -in @('upgrade','cross-version') -and -not $IsNegative) {
            # Evidence already receives the disposable SID's scoped ACL. Keep
            # the helper/runtime outside the product and usable after uninstall.
            $helperRuntime=Join-Path $CaseEvidence 'qa-node-store-runtime'
            if(Test-Path -LiteralPath $helperRuntime){throw 'QA runtime staging must start from an absent owned directory.'}
            [IO.Directory]::CreateDirectory($helperRuntime)|Out-Null
            $caseHelper=Join-Path $helperRuntime 'SwirlPrivateSubscriptionAcceptance.exe'
            [IO.File]::Copy($helper,$caseHelper,$false)
            if((Get-SwirlIntegrationHash $caseHelper) -cne $helperHash){throw 'QA helper copy changed.'}
            $runtime=@($manifest.files|Where-Object {$_.path -cmatch '^[^/\\]+\.dll$' -or $_.path -ceq 'swirl-rust-build.json'})
            foreach($required in @('Qt6Core.dll','Qt6Network.dll','Qt6Gui.dll','swirl_api.dll','swirl-rust-build.json')) {
                if(@($runtime|Where-Object {$_.path -ceq $required}).Count -ne 1){throw ('Missing QA runtime dependency: '+$required)}
            }
            foreach($entry in $runtime) {
                $runtimeInput=Join-Path $package $entry.path;$runtimeOutput=Join-Path $helperRuntime $entry.path
                Assert-SwirlPathWithoutLinks $runtimeInput
                [IO.File]::Copy($runtimeInput,$runtimeOutput,$false)
                if((Get-SwirlIntegrationHash $runtimeOutput) -cne $entry.sha256){throw 'QA runtime copy differs from verified product dependency.'}
            }
            @{schema=1;source_sha=$source;helper_sha256=$helperHash;rust_build_id=$helperPair.build_id;scope='Separate offline QA oracle with exact paired product runtime; never product payload';files=$runtime}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $CaseEvidence 'qa-node-store-runtime.json') -Encoding UTF8
        }
        $argumentsPath=Join-Path $CaseEvidence 'child-arguments.json'
        # CreateProcessWithLogonW(NULL environment) creates the new user's
        # profile environment. Forward only these already-verified host values,
        # not the runner's full environment or its credentials/profile paths.
        $helperEnvironment=@{GITHUB_ACTIONS=$env:GITHUB_ACTIONS;RUNNER_ENVIRONMENT=$env:RUNNER_ENVIRONMENT;SWIRL_DISPOSABLE_INSTALL_TEST=$env:SWIRL_DISPOSABLE_INSTALL_TEST}
        $childArguments=@{Installer=$CaseInstaller;PackageDirectory=$package;ExpectedSourceSha=$source;EvidenceDirectory=$CaseEvidence;Scenario=$CaseScenario;NegativeControl=$IsNegative;ProductVersion=$version;NodeStoreHelper=$caseHelper;ExpectedNodeStoreHelperSha256=$helperHash;NodeStoreHelperEnvironment=$helperEnvironment}
        if($CaseScenario -eq 'cross-version'){$childArguments.CrossVersionInput=$CrossVersionInput;$childArguments.BaselineInstaller=$oldSetup;$childArguments.BaselineAdmission=$BaselineAdmission}
        $childArguments|ConvertTo-Json -Depth 4|Set-Content -LiteralPath $argumentsPath -Encoding UTF8
        try {
            & (Join-Path $PSScriptRoot 'Invoke-DisposableWindowsUser.ps1') -Script $PSCommandPath -ArgumentsFile $argumentsPath -EvidenceDirectory $CaseEvidence -TimeoutSeconds 600
        } finally {
            if($null -ne $helperRuntime -and (Test-Path -LiteralPath $helperRuntime)){Assert-SwirlPathWithoutLinks $helperRuntime;Remove-Item -LiteralPath $helperRuntime -Recurse -Force}
        }
        $case=Read-Json (Join-Path $CaseEvidence 'case.json')
        $runner=Read-Json (Join-Path $CaseEvidence 'standard-user-runner.json')
        if(-not $case.success -or -not $runner.success -or $runner.forced_termination -or $runner.token.Administrator -or $runner.token.Elevated -or $runner.token.IntegritySid -cne 'S-1-16-8192'){throw ('Normal installer case failed: '+$Name)}
        $runs.Add([ordered]@{name=$Name;case=$case;standard_user=$runner;directory=$CaseEvidence})
    }
    if($crossVersion) {
        $parentProxyBefore=Profile-ProxyFingerprint
        try {
            if($version -cne $crossInput.candidate_version){throw 'Cross-version candidate version differs from the explicit QA input.'}
            foreach($entry in $crossInput.identical_persistence_sources.PSObject.Properties) {
                foreach($revision in @($source,$old.source_sha)) {
                    $blob=(& git -C $repo rev-parse ($revision+':'+$entry.Name)).Trim()
                    if($LASTEXITCODE -ne 0 -or $blob -cne $entry.Value){throw 'Cross-version persistence sources are not the explicitly identical reviewed blobs.'}
                }
            }
            Invoke-NormalCase 'actual-0239-to-0240-synthetic-configuration-upgrade' $setup 'cross-version' $false $evidence
        }catch{$failure=$_.Exception.Message}
        finally {
            $casePath=Join-Path $evidence 'case.json';$runnerPath=Join-Path $evidence 'standard-user-runner.json'
            $case=if(Test-Path -LiteralPath $casePath){Read-Json $casePath}else{$null}
            $runner=if(Test-Path -LiteralPath $runnerPath){Read-Json $runnerPath}else{$null}
            $parentUnchanged=(Snapshot-Integration $parentContext) -ceq $parentBefore
            $parentProxyUnchanged=(Profile-ProxyFingerprint) -ceq $parentProxyBefore
            $candidateUnchanged=(Get-SwirlIntegrationHash $setup) -ceq $installerHash
            $baselineUnchanged=(Get-SwirlIntegrationHash $oldSetup) -ceq $old.exe_sha256
            $complete=$null -ne $case -and $null -ne $runner -and $case.success -and $runner.success -and -not $runner.forced_termination -and
                $runner.remaining_job_processes -eq 0 -and $runner.account_removed -and $runner.profile_removed -and $runner.input_acls_restored -and
                $case.cross_version_upgrade.verified -and $case.dpapi_store_preservation.stages.Count -eq 5
            $summary=[ordered]@{schema=1;scope='actual-0239-to-0240-installers-with-current-helper-synthetic-v1-data';source_sha=$source;candidate_version=$version;installer_sha256=$installerHash;baseline=$old;baseline_admission=$admission;identical_persistence_sources=$crossInput.identical_persistence_sources;fixture_writer='Current separately paired QA helper using identical production NodeStore sources; not the historical application writer.';original_private_profile_tested=$false;provider_requests=0;case=$case;standard_user=$runner;host_user_integration_unchanged=$parentUnchanged;host_system_proxy_unchanged=$parentProxyUnchanged;candidate_installer_unchanged=$candidateUnchanged;baseline_installer_unchanged=$baselineUnchanged;success=($null -eq $failure -and $complete -and $parentUnchanged -and $parentProxyUnchanged -and $candidateUnchanged -and $baselineUnchanged);error=$failure}
            $summary|ConvertTo-Json -Depth 22|Set-Content -LiteralPath (Join-Path $evidence 'cross-version.json') -Encoding UTF8
        }
        if(-not $summary.success){throw ('Cross-version installer acceptance failed: '+$failure)}
        Write-Host 'Actual 0.2.39 to 0.2.40 installers preserved current-helper synthetic V1 data in one standard-user profile; original private profiles were not tested.'
        return
    }
    try {
        Invoke-NormalCase 'candidate-clean-runtime-and-retry' $setup 'clean' $false $evidence
        Invoke-NormalCase 'candidate-restores-preexisting-integration' $setup 'restore' $false (Join-Path $evidence 'restore')
        Invoke-NormalCase 'candidate-preserves-later-user-edits' $setup 'edits' $false (Join-Path $evidence 'edits')
        Invoke-NormalCase 'candidate-upgrade-preserves-baseline-and-user-edits' $setup 'upgrade' $false (Join-Path $evidence 'upgrade')

        # Compile the exact old production NSIS source in a separate directory.
        # Neither the tested current installer nor its payload is overwritten.
        & git -C $repo cat-file -e $baseline.source_commit 2>$null
        if($LASTEXITCODE -ne 0){& git -C $repo fetch --no-tags --depth=1 origin $baseline.source_commit;if($LASTEXITCODE -ne 0){throw 'Legacy NSIS commit fetch failed.'}}
        $diagnostic=Join-Path $evidence 'negative-control-build'
        [IO.Directory]::CreateDirectory($diagnostic)|Out-Null
        $legacySource=Join-Path $diagnostic 'Swirl.nsi'
        $process=New-Object Diagnostics.Process
        $process.StartInfo.FileName='git';$process.StartInfo.WorkingDirectory=$repo
        $process.StartInfo.Arguments='cat-file blob '+$baseline.source_commit+':src/Swirl.Quick/packaging/Swirl.nsi'
        $process.StartInfo.UseShellExecute=$false;$process.StartInfo.RedirectStandardOutput=$true
        $stream=[IO.File]::Create($legacySource)
        try{$null=$process.Start();$process.StandardOutput.BaseStream.CopyTo($stream);$process.WaitForExit();if($process.ExitCode -ne 0){throw 'Exact old NSIS extraction failed.'}}finally{$stream.Dispose();$process.Dispose()}
        $expectedBlob=(& git -C $repo rev-parse ($baseline.source_commit+':src/Swirl.Quick/packaging/Swirl.nsi')).Trim()
        if($LASTEXITCODE -ne 0){throw 'Legacy NSIS blob identity unavailable.'}
        $actualBlob=(& git -C $repo hash-object $legacySource).Trim()
        if($LASTEXITCODE -ne 0 -or $actualBlob -cne $expectedBlob){throw 'Legacy NSIS source bytes differ from the exact Git object.'}
        $baseline.source_blob=$actualBlob;$baseline.source_sha256=Get-SwirlIntegrationHash $legacySource
        $include=Join-Path $diagnostic 'verified-package.nsh'
        @('; Diagnostic baseline, same already-verified candidate payload.',('!define SWIRL_VERIFIED_SOURCE_SHA "'+$source+'"'),('!define SWIRL_VERIFIED_FILE_COUNT '+@($manifest.files).Count))|Set-Content -LiteralPath $include -Encoding UTF8
        $nsis=Join-Path ${env:ProgramFiles(x86)} 'NSIS/makensis.exe'
        if(-not [IO.File]::Exists($nsis)){throw 'The actual NSIS compiler is unavailable for the negative control.'}
        $icon=Join-Path $package 'Swirl-brand-0217-optical.ico'
        & $nsis /INPUTCHARSET UTF8 "/DAPP_DIST=$package" "/DOUT_DIR=$diagnostic" "/DAPP_ICON=$icon" "/DAPP_VERSION=$version" "/DUNINSTALL_LIST=$include" "/DREPO_ROOT=$repo" $legacySource *> (Join-Path $diagnostic 'compile.log')
        $baseline.compile_exit_code=$LASTEXITCODE
        if($LASTEXITCODE -ne 0){throw 'Legacy NSIS compilation failed; compilation errors are not a successful negative control.'}
        $legacyInstaller=Join-Path $diagnostic 'Swirl-Setup.exe'
        $baseline.installer_sha256=Get-SwirlIntegrationHash $legacyInstaller
        Invoke-NormalCase 'legacy-actual-installer-negative-control' $legacyInstaller 'edits' $true (Join-Path $evidence 'negative-control')
        $last=$runs[$runs.Count-1].case
        $baseline.required_assertion_failed=$last.negative_control.required_assertion_failed
        if(-not $baseline.required_assertion_failed){throw 'The exact old NSIS did not fail the required preservation assertion.'}
    }catch{$failure=$_.Exception.Message}
    finally {
        $parentUnchanged=(Snapshot-Integration $parentContext) -ceq $parentBefore
        $candidateUnchanged=(Get-SwirlIntegrationHash $setup) -ceq $installerHash
        $allRuns=$runs.Count -eq 5 -and @($runs|Where-Object {-not $_.case.success -or -not $_.standard_user.success -or $_.standard_user.forced_termination}).Count -eq 0
        $clean=if($runs.Count){$runs[0].case}else{$null}
        $upgrade=@($runs|Where-Object {$_.case.scenario -eq 'upgrade' -and -not $_.case.negative})
        $dpapi=if($upgrade.Count -eq 1){$upgrade[0].case.dpapi_store_preservation}else{$null}
        $dpapiVerified=$null -ne $dpapi -and $dpapi.verified -and $dpapi.parent_host_scope_forwarded -and $dpapi.existing_store_create_refused -and $dpapi.stages.Count -eq 4
        $summary=[ordered]@{schema=1;source_sha=$source;installer_sha256=$installerHash;scope='Actual default per-user NSIS install without /ISOLATED or /D, normal application startup/close and uninstall under fresh real non-administrator accounts on a disposable hosted Windows runner.';normal_user_installation=$allRuns;non_admin_token_verified=$allRuns;windows11_codex_desktop='NOT_RUN';physical_windows11_display_acceptance='NOT_RUN';candidate_installer_unchanged=$candidateUnchanged;host_user_integration_unchanged=$parentUnchanged;cases=@($runs.ToArray());negative_control=$baseline;production_runtime=$clean;success=($null -eq $failure -and $allRuns -and $baseline.required_assertion_failed -and $candidateUnchanged -and $parentUnchanged);error=$failure}
        $summary.same_package_dpapi_store=$dpapi
        $summary.success=$summary.success -and $dpapiVerified
        $summary|ConvertTo-Json -Depth 18|Set-Content -LiteralPath (Join-Path $evidence 'lifecycle.json') -Encoding UTF8
    }
    if(-not $summary.success){throw ('Normal installer acceptance failed: '+$failure)}
    Write-Host 'Actual normal per-user install/runtime/uninstall, same-package synthetic DPAPI preservation, user edits, retry and exact old NSIS negative control verified; no previous-release migration.'
    return
}

$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal $identity
if($identity.User.Value -cne $ExpectedUserSid -or $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -or [Environment]::Is64BitProcess){throw 'Normal installation requires the exact disposable standard-user x86 process.'}
foreach($name in @('SWIRL_ISOLATED_INSTALL_ROOT','SWIRL_TEST_ROOT','QT_QUICK_BACKEND','QT_SCALE_FACTOR','QT_SCREEN_SCALE_FACTORS','QT_PLUGIN_PATH','QML_IMPORT_PATH','QML2_IMPORT_PATH')){[Environment]::SetEnvironmentVariable($name,$null,'Process')}
$env:QT_QPA_PLATFORM='windows';$env:QSG_RHI_BACKEND='d3d11'
$target=Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs/Swirl'
$context=New-SwirlIntegrationContext $target $manifestPath $ProductVersion
$checks=New-Object 'System.Collections.Generic.List[object]'
$processes=New-Object 'System.Collections.Generic.List[object]'
$report=[ordered]@{schema=1;source_sha=$ExpectedSourceSha;installer_sha256=(Get-SwirlIntegrationHash $setup);scenario=$Scenario;negative=$NegativeControl;user_sid=$ExpectedUserSid;normal_user_installation=$true;non_admin_token_verified=$true;install_arguments='/S';isolated=$false;install_directory=$target;installed_files=0;installed_exe_sha256=$null;installed_rust_dll_sha256=$null;installed_manifest_sha256=$null;rust_roundtrips_verified=$false;tls_runtime_verified=$false;normal_ui_no_test_arguments=$false;normal_ui_closed_normally=$false;normal_ui_inherited_standard_user_profile=$false;normal_qml_cache_identity='NOT_REPORTED_BY_NORMAL_APPLICATION';smoke_cache_identity=$null;ui_test_hooks_disabled=$false;installed_ui_pages=0;integration_restored_or_user_edits_preserved=$false;user_data_preserved=$false;install_directory_removed=$false;retry_after_restore_failure=$false;forced_termination=$false;processes=$processes;checks=$checks;negative_control=@{required_assertion_failed=$false;assertion='original-integration-and-later-user-edits-preserved';observed_pass=$null};success=$false;error=$null}
$storeStages=New-Object 'System.Collections.Generic.List[object]'
$report.dpapi_store_preservation=[ordered]@{requested=($Scenario -in @('upgrade','cross-version'));scope='same-package-reinstall-synthetic-v1-node-store';previous_release_migration=$false;helper_sha256=$ExpectedNodeStoreHelperSha256;rust_build_id=$manifest.rust.build_id;parent_host_scope_forwarded=$false;existing_store_create_refused=$false;verified=$false;stages=$storeStages}
if($crossVersion){
    $report.cross_version_upgrade=[ordered]@{scope='actual-0239-to-0240-installers-with-current-helper-synthetic-v1-data';baseline_source_sha=$old.source_sha;baseline_version=$old.version;baseline_installer_sha256=$old.exe_sha256;candidate_source_sha=$ExpectedSourceSha;candidate_version=$ProductVersion;candidate_installer_sha256=$report.installer_sha256;current_helper_is_fixture_writer=$true;historical_application_writer_verified=$false;identical_persistence_sources=$crossInput.identical_persistence_sources;old_installed_manifest_sha256=$null;old_application_sha256=$null;old_rust_build_id=$null;old_normal_ui_closed_normally=$false;new_normal_ui_closed_normally=$false;system_proxy_settings_unchanged=$false;verified=$false}
    $profileProxyBefore=Profile-ProxyFingerprint
    # Stage diagnostics only read raw registry bytes. Do not prime WinINet
    # before the real applications or alter the original comparison baseline.
    . (Join-Path $PSScriptRoot 'WindowsProxyDiagnostics.ps1')
    $proxyStages=New-Object 'System.Collections.Generic.List[object]'
    $proxyDiagnostic=[ordered]@{schema=1;source_sha=$ExpectedSourceSha;scope='Raw-only redacted observations in the actual cross-version standard-user profile; original raw-fingerprint assertion remains unchanged.';original_fingerprint_before=$profileProxyBefore;original_fingerprint_after=$null;raw_baseline=$null;stages=$proxyStages;raw_final=$null;final_difference=$null;final_diagnostic_error=$null;post_assertion_query=$null;post_assertion_query_ran=$false;post_assertion_query_error=$null;post_assertion_query_scope='Runs only after the original fingerprint decision; never contributes to that decision or to the case success result.'}
    $report.cross_version_upgrade.proxy_diagnostics='proxy-diagnostics.json'
}
$nodeStorePath=Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'SOLHK/Swirl/nodes.dpapi'
$storeBaseline=$null

function Require([string]$Name,[bool]$Passed){$checks.Add([ordered]@{name=$Name;passed=$Passed});if(-not $Passed){throw ('Normal installer regression failed: '+$Name)}}
function Record-ProfileProxyObservation([string]$Stage) {
    $raw=Get-SwirlProxyRegistryDiagnostic
    $entry=[ordered]@{stage=$Stage;observation_mode='raw-registry-only';raw=$raw;difference_from_original_baseline=(Compare-SwirlProxyRegistryDiagnostic $proxyDiagnostic.raw_baseline $raw);difference_since_previous_observation=$null}
    if($proxyStages.Count -gt 0){$entry.difference_since_previous_observation=Compare-SwirlProxyRegistryDiagnostic $proxyStages[$proxyStages.Count-1].raw $raw}
    $proxyStages.Add($entry)
    # Save every stage before the disposable account is removed, including when
    # a later installer assertion fails. Only names, types, lengths and hashes.
    $proxyDiagnostic|ConvertTo-Json -Depth 14|Set-Content -LiteralPath (Join-Path $evidence 'proxy-diagnostics.json') -Encoding UTF8
}
function Run-Process([string]$Name,[string]$Executable,[string]$Arguments,[int]$Seconds,[int]$ExpectedExit=0) {
    $entry=[ordered]@{name=$Name;expected_exit_code=$ExpectedExit;exit_code=$null;exited=$false;elapsed_ms=$null;created_handle_retained=$false;output_drains_completed=$false;failure_receipts=@()};$processes.Add($entry)
    $capture=$null;$timer=[Diagnostics.Stopwatch]::StartNew()
    try {
        $capture=Start-SwirlCapturedProcess -Executable $Executable -Arguments $Arguments -WorkingDirectory $evidence -StdoutPath (Join-Path $evidence ($Name+'.stdout.log')) -StderrPath (Join-Path $evidence ($Name+'.stderr.log'))
        $entry.exited=Wait-SwirlCapturedProcess $capture ($Seconds*1000)
        if(-not $entry.exited){throw ('Actual process timed out: '+$Name)}
        $entry.exit_code=$capture.ExitCode
        if($entry.exit_code -ne $ExpectedExit){throw ("Actual process $Name returned $($entry.exit_code); required $ExpectedExit")}
    }finally {
        $timer.Stop();$entry.elapsed_ms=$timer.Elapsed.TotalMilliseconds
        if($null -ne $capture){try{Close-SwirlCapturedProcess $capture}finally{$entry.exited=$capture.Exited;$entry.exit_code=$capture.ExitCode;$entry.created_handle_retained=$capture.CreatedHandleRetained;$entry.output_drains_completed=$capture.OutputsComplete;if($capture.ForcedTermination){$report.forced_termination=$true}}}
        $stderrPath=Join-Path $evidence ($Name+'.stderr.log')
        if($null -ne $entry.exit_code -and $entry.exit_code -ne 0 -and [IO.File]::Exists($stderrPath) -and (Get-Item -LiteralPath $stderrPath).Length -le 4096){
            $receipts=[regex]::Matches([IO.File]::ReadAllText($stderrPath),'(?m)^SWIRL_(INSTALL|UNINSTALL)_FAILURE phase=([A-Za-z-]{1,64}) code=(-?\d{1,10}|error|timeout|missing-payload|unavailable)\r?$')
            $entry.failure_receipts=@($receipts|ForEach-Object {[ordered]@{operation=$_.Groups[1].Value;phase=$_.Groups[2].Value;code=$_.Groups[3].Value}})
        }
    }
}
function Invoke-NormalUi([string]$LogPrefix) {
    $normal=$null;$normalCapture=$null
    $normalEntry=[ordered]@{name=($LogPrefix+'-no-arguments');expected_exit_code=0;exit_code=$null;exited=$false;close_requested=$false;created_handle_retained=$false;output_drains_completed=$false};$processes.Add($normalEntry)
    try {
        $normalCapture=Start-SwirlCapturedProcess -Executable $exe -Arguments '' -WorkingDirectory ([Environment]::GetFolderPath('UserProfile')) -StdoutPath (Join-Path $evidence ($LogPrefix+'.stdout.log')) -StderrPath (Join-Path $evidence ($LogPrefix+'.stderr.log'))
        $normal=$normalCapture.Process
        $watch=[Diagnostics.Stopwatch]::StartNew()
        do {$normal.Refresh();if($normal.HasExited){throw 'Ordinary application exited before showing its main window.'};if($normal.MainWindowHandle -ne [IntPtr]::Zero -and $normal.MainWindowTitle -ceq 'Swirl'){break};Start-Sleep -Milliseconds 100}while($watch.Elapsed.TotalSeconds -lt 15)
        Require 'normal-ui-main-window-created-without-test-arguments' ($normal.MainWindowHandle -ne [IntPtr]::Zero -and $normal.MainWindowTitle -ceq 'Swirl')
        $report.normal_ui_no_test_arguments=$true
        $normalEntry.close_requested=$normal.CloseMainWindow()
        Require 'normal-ui-accepts-user-window-close' $normalEntry.close_requested
        $normalEntry.exited=Wait-SwirlCapturedProcess $normalCapture 15000
        if(-not $normalEntry.exited){throw 'Ordinary UI close did not complete.'}
        $normalEntry.exit_code=$normalCapture.ExitCode
        Require 'normal-ui-exits-successfully' ($normalEntry.exit_code -eq 0)
    }finally{if($null -ne $normalCapture){try{Close-SwirlCapturedProcess $normalCapture}finally{$normalEntry.exited=$normalCapture.Exited;$normalEntry.exit_code=$normalCapture.ExitCode;$normalEntry.created_handle_retained=$normalCapture.CreatedHandleRetained;$normalEntry.output_drains_completed=$normalCapture.OutputsComplete;if($normalCapture.ForcedTermination){$report.forced_termination=$true}}}}
    # Normal application startup deliberately has no test-only diagnostic
    # handler/cache marker. Its actual HWND, WM_CLOSE and natural exit above
    # are evidence; the later smoke/cache report belongs to its own process.
    $profile=[IO.Path]::GetFullPath([Environment]::GetFolderPath('UserProfile')).TrimEnd('\')
    Require 'normal-ui-inherits-the-real-standard-user-profile' ($env:USERPROFILE -ieq $profile -and $identity.User.Value -ceq $ExpectedUserSid -and -not $env:SWIRL_TEST_ROOT)
    $report.normal_ui_closed_normally=$true;$report.normal_ui_inherited_standard_user_profile=$true
}
function Invoke-NodeStoreFixture([string]$Stage,[string]$Operation='verify',[int]$ExpectedExit=0) {
    Assert-SwirlPathWithoutLinks $nodeStorePath
    Assert-SwirlPathWithoutLinks $NodeStoreHelper
    Require 'offline-qa-helper-hash-matches-staged-identity' ($ExpectedNodeStoreHelperSha256 -cmatch '^[0-9a-f]{64}$' -and (Get-SwirlIntegrationHash $NodeStoreHelper) -ceq $ExpectedNodeStoreHelperSha256)
    $receiptPath=Join-Path $evidence ('dpapi-'+$Stage+'.json')
    Require 'offline-node-store-phase-receipt-is-new' (-not (Test-Path -LiteralPath $receiptPath))
    $arguments='--installer-store-fixture '+$Operation+' "'+$ExpectedSourceSha+'" "'+$ExpectedUserSid+'" "'+$nodeStorePath+'" "'+$receiptPath+'"'
    $hostValues=@{GITHUB_ACTIONS='true';RUNNER_ENVIRONMENT='github-hosted';SWIRL_DISPOSABLE_INSTALL_TEST='1'}
    $previousEnvironment=@{PATH=$env:PATH}
    foreach($environmentName in $hostValues.Keys) {
        $provided=$NodeStoreHelperEnvironment.PSObject.Properties[$environmentName]
        Require 'offline-helper-receives-verified-disposable-host-context' ($null -ne $provided -and $provided.Value -ceq $hostValues[$environmentName])
        $previousEnvironment[$environmentName]=[Environment]::GetEnvironmentVariable($environmentName,'Process')
    }
    try {
        $env:PATH=[IO.Path]::GetDirectoryName($NodeStoreHelper)+';'+$env:WINDIR+'\System32;'+$env:WINDIR
        foreach($environmentName in $hostValues.Keys){[Environment]::SetEnvironmentVariable($environmentName,[string]$NodeStoreHelperEnvironment.PSObject.Properties[$environmentName].Value,'Process')}
        Run-Process ('dpapi-'+$Stage) $NodeStoreHelper $arguments 30 $ExpectedExit
    } finally {foreach($environmentName in $previousEnvironment.Keys){[Environment]::SetEnvironmentVariable($environmentName,$previousEnvironment[$environmentName],'Process')}}
    $receipt=Read-Json $receiptPath
    Require 'offline-node-store-receipt-has-exact-user-source-and-scope' ($receipt.schema -eq 1 -and $receipt.kind -ceq 'installer-node-store-fixture' -and $receipt.scope -ceq 'same-package-reinstall-synthetic-v1-node-store' -and $receipt.operation -ceq $Operation -and $receipt.source_sha -ceq $ExpectedSourceSha -and $receipt.user_sid -ceq $ExpectedUserSid -and [IO.Path]::GetFullPath($receipt.store_path) -ieq [IO.Path]::GetFullPath($nodeStorePath) -and $receipt.ordinary_profile -eq $true -and $receipt.host_scope_verified -eq $true -and $receipt.rust_build_id -ceq $manifest.rust.build_id -and $receipt.qt_runtime_version -ceq '6.12.0' -and $receipt.network_requests -eq 0 -and $receipt.engine_started -eq $false)
    $report.dpapi_store_preservation.parent_host_scope_forwarded=$true
    if($ExpectedExit -ne 0) {
        Require 'existing-node-store-create-refused-without-writing' ($receipt.success -eq $false -and $receipt.store_write_attempted -eq $false -and $receipt.error_code -ceq 'ExistingStoreRefused')
        return $receipt
    }
    Require 'production-node-store-decrypts-and-preserves-fixed-semantics' ($receipt.success -eq $true -and $receipt.store_format -ceq 'SWIRLNODE1' -and $receipt.dpapi_roundtrip_verified -eq $true -and $receipt.plaintext_absent -eq $true -and $receipt.read_only_reload -eq $true -and $receipt.node_count -eq 2 -and $receipt.subscription_count -eq 1 -and $receipt.node_parameters_match -eq $true -and $receipt.selection_matches -eq $true -and $receipt.disabled_subscription_matches -eq $true -and $receipt.network_configuration_matches -eq $true)
    Require 'node-store-receipt-hashes-match-actual-profile-files' ($receipt.ciphertext_sha256 -cmatch '^[0-9a-f]{64}$' -and $receipt.selection_sha256 -cmatch '^[0-9a-f]{64}$' -and (Get-SwirlIntegrationHash $nodeStorePath) -ceq $receipt.ciphertext_sha256 -and (Get-SwirlIntegrationHash ($nodeStorePath+'.selected')) -ceq $receipt.selection_sha256)
    if($Operation -eq 'verify') {
        Require 'same-package-node-store-and-selection-bytes-unchanged' ($receipt.store_write_attempted -eq $false -and $null -ne $storeBaseline -and $receipt.ciphertext_sha256 -ceq $storeBaseline.ciphertext_sha256 -and $receipt.selection_sha256 -ceq $storeBaseline.selection_sha256)
        $storeStages.Add([ordered]@{stage=$Stage;receipt=$receipt})
    }
    return $receipt
}
function Assert-Payload([string[]]$Extra=@(),[object]$ExpectedManifest=$manifest,[string]$ExpectedManifestPath=$manifestPath) {
    $known=@('package-manifest.json','.swirl-install-owned','卸载 Swirl.exe')+$Extra
    if(-not $NegativeControl){$known+=@('.swirl-user-integration.json')}
    $expected=@($ExpectedManifest.files|ForEach-Object {[string]$_.path})+$known
    $dirs=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach($name in $expected){$p=$name;while($p.LastIndexOf('/') -gt 0){$p=$p.Substring(0,$p.LastIndexOf('/'));$null=$dirs.Add($p)}}
    $inventory=@(Get-ChildItem -LiteralPath $target -Recurse -Force|ForEach-Object {Assert-SwirlPathWithoutLinks $_.FullName;$(if($_.PSIsContainer){'directory:'}else{'file:'})+$_.FullName.Substring($target.Length+1).Replace('\','/')})
    $wanted=@($expected|ForEach-Object {'file:'+$_})+@($dirs|ForEach-Object {'directory:'+$_})
    if(@(Compare-Object ($wanted|Sort-Object) ($inventory|Sort-Object)).Count){throw 'Actual normal installation file/directory inventory differs from ownership.'}
    foreach($entry in $ExpectedManifest.files){if((Get-SwirlIntegrationHash (Join-Path $target $entry.path)) -ine $entry.sha256){throw ('Installed payload hash mismatch: '+$entry.path)}}
    if((Get-SwirlIntegrationHash (Join-Path $target 'package-manifest.json')) -cne (Get-SwirlIntegrationHash $ExpectedManifestPath)){throw 'Installed manifest differs from the expected payload.'}
    Require 'no-isolated-install-marker' (-not [IO.File]::Exists((Join-Path $target '.swirl-isolated-install')))
}
function Save-Shortcut([string]$Path,[string]$Description) {
    $fixture=Save-SwirlTestShortcut -Path $Path -Description $Description
    if(-not $fixture.success){throw ('Real Unicode shortcut fixture failed: '+$fixture.error)}
}
function Capture-States {
    $state=@{};foreach($id in $context.Targets.Keys){$state[$id]=Get-SwirlIntegrationState $context $id};return $state
}
function Original-Preserved([hashtable]$Expected) {
    foreach($id in $Expected.Keys){if(-not (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context $id) $Expected[$id])){return $false}}
    if($Scenario -ne 'clean') {
        $hive=Open-SwirlIntegrationHive;$key=$null
        try{$key=$hive.OpenSubKey('Software\Swirl\UserOwned',$false);if($null -eq $key -or $key.GetValueKind('Preserve') -ne [Microsoft.Win32.RegistryValueKind]::QWord -or [long]$key.GetValue('Preserve') -ne [long]9223372036854775806){return $false}}finally{if($null -ne $key){$key.Dispose()};$hive.Dispose()}
        if(-not [IO.File]::Exists((Join-Path $context.Menu 'user-note.txt')) -or [IO.File]::ReadAllText((Join-Path $context.Menu 'user-note.txt')) -cne 'Synthetic pre-existing menu data'){return $false}
    }
    return $true
}
try {
    if($crossVersion){
        $proxyDiagnostic.raw_baseline=Get-SwirlProxyRegistryDiagnostic
        $proxyDiagnostic|ConvertTo-Json -Depth 14|Set-Content -LiteralPath (Join-Path $evidence 'proxy-diagnostics.json') -Encoding UTF8
    }
    Require 'fresh-default-user-install-directory' (-not (Test-Path -LiteralPath $target))
    $original=Capture-States
    Require 'fresh-account-has-no-existing-swirl-integration' (@($original.Values|Where-Object {$_.exists}).Count -eq 0)
    if($Scenario -ne 'clean') {
        Set-SwirlIntegrationState $context 'install-directory' (New-SwirlRegistryValueState 'String' $target)
        Set-SwirlIntegrationState $context 'display-name' (New-SwirlRegistryValueState 'ExpandString' '%LOCALAPPDATA%\原始 Swirl')
        Set-SwirlIntegrationState $context 'display-version' (New-SwirlRegistryValueState 'Binary' ([byte[]](0,255,17,0)))
        Set-SwirlIntegrationState $context 'no-modify' (New-SwirlRegistryValueState 'DWord' ([int]-2147483648))
        foreach($id in @('desktop','start-menu','codex-start-menu','owned-pin')){Save-Shortcut $context.Targets[$id].path ('用户原始快捷方式 '+$id)}
        [IO.File]::WriteAllText((Join-Path $context.Menu 'user-note.txt'),'Synthetic pre-existing menu data')
        $hive=Open-SwirlIntegrationHive;try{$key=$hive.CreateSubKey('Software\Swirl\UserOwned');try{$key.SetValue('Preserve',[long]9223372036854775806,[Microsoft.Win32.RegistryValueKind]::QWord)}finally{$key.Dispose()}}finally{$hive.Dispose()}
        $original=Capture-States
    }
    $crossVersionExtras=@()
    if($crossVersion) {
        Require 'cross-version-child-has-the-explicit-scenario' ($Scenario -ceq 'cross-version' -and $ProductVersion -ceq $crossInput.candidate_version)
        Record-ProfileProxyObservation 'before-old-install'
        Run-Process 'baseline-install-0239' $oldSetup '/S' 120
        Record-ProfileProxyObservation 'after-old-install'
        $oldManifestPath=Join-Path $target 'package-manifest.json'
        Require 'baseline-installed-manifest-matches-reviewed-old-package' ((Get-SwirlIntegrationHash $oldManifestPath) -ceq $old.package_manifest_sha256)
        $oldManifest=Read-Json $oldManifestPath
        Require 'baseline-installed-source-and-rust-build-match' ($oldManifest.source_sha -ceq $old.source_sha -and $oldManifest.rust.source_sha -ceq $old.source_sha -and $oldManifest.rust.build_id -ceq $old.rust_build_id)
        Assert-Payload -ExpectedManifest $oldManifest -ExpectedManifestPath $oldManifestPath
        $exe=Join-Path $target 'Swirl.exe'
        Require 'actual-old-application-version-and-hash-match' ((Get-SwirlIntegrationHash $exe) -ceq $old.application_sha256 -and (Fixed-ProductVersion $exe) -ceq ($old.version+'.0'))
        Require 'actual-old-version-is-registered' (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'display-version') (New-SwirlRegistryValueState 'String' ($old.version+'.0')))
        $report.cross_version_upgrade.old_installed_manifest_sha256=Get-SwirlIntegrationHash $oldManifestPath
        $report.cross_version_upgrade.old_application_sha256=Get-SwirlIntegrationHash $exe
        $report.cross_version_upgrade.old_rust_build_id=$oldManifest.rust.build_id
        # Seed an offline oracle only after installing the actual old package.
        # The helper stays paired to the current source, outside both payloads.
        Require 'old-profile-starts-with-no-node-store-or-sidecar' (-not (Test-Path -LiteralPath $nodeStorePath) -and -not (Test-Path -LiteralPath ($nodeStorePath+'.selected')))
        $storeBaseline=Invoke-NodeStoreFixture 'create' 'create'
        $null=Invoke-NodeStoreFixture 'create-existing-refused' 'create' 2
        Require 'cross-version-refused-create-preserves-both-files' ((Get-SwirlIntegrationHash $nodeStorePath) -ceq $storeBaseline.ciphertext_sha256 -and (Get-SwirlIntegrationHash ($nodeStorePath+'.selected')) -ceq $storeBaseline.selection_sha256)
        $report.dpapi_store_preservation.existing_store_create_refused=$true
        $null=Invoke-NodeStoreFixture 'before-old-start'
        $env:PATH=$target+';'+$env:WINDIR+'\System32;'+$env:WINDIR
        Record-ProfileProxyObservation 'before-old-normal-ui'
        Invoke-NormalUi 'baseline-0239-normal-ui'
        Record-ProfileProxyObservation 'after-old-normal-ui'
        $report.cross_version_upgrade.old_normal_ui_closed_normally=$report.normal_ui_closed_normally
        $null=Invoke-NodeStoreFixture 'after-old-close'
        $report.normal_ui_no_test_arguments=$false;$report.normal_ui_closed_normally=$false;$report.normal_ui_inherited_standard_user_profile=$false
        Save-Shortcut $context.Targets['desktop'].path '用户安装后编辑的快捷方式'
        Set-SwirlIntegrationState $context 'publisher' (New-SwirlRegistryValueState 'ExpandString' '%LOCALAPPDATA%\用户安装后修改')
        Set-SwirlIntegrationState $context 'no-repair' ([ordered]@{exists=$false})
        foreach($id in @('desktop','publisher','no-repair')){$original[$id]=Get-SwirlIntegrationState $context $id}
        [IO.File]::WriteAllText((Join-Path $target 'user-notes.txt'),'Synthetic user-owned installation file')
        [IO.Directory]::CreateDirectory((Join-Path $target 'data'))|Out-Null
        [IO.File]::WriteAllText((Join-Path $target 'data/user-store.dpapi'),'Synthetic bytes only; no private credential')
        $crossVersionExtras=@('user-notes.txt','data/user-store.dpapi')
    }
    if($crossVersion){Record-ProfileProxyObservation 'before-new-install'}
    Run-Process 'install' $setup '/S' 120
    if($crossVersion){Record-ProfileProxyObservation 'after-new-install'}
    Assert-Payload $crossVersionExtras
    if($crossVersion) {
        Require 'actual-new-version-is-registered' (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'display-version') (New-SwirlRegistryValueState 'String' ($ProductVersion+'.0')))
        Require 'cross-version-upgrade-preserves-later-integration-edits' ((Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'desktop') $original['desktop']) -and (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'publisher') $original['publisher']) -and -not (Get-SwirlIntegrationState $context 'no-repair').exists)
        $null=Invoke-NodeStoreFixture 'after-cross-version-install'
    }
    $report.installed_files=@($manifest.files).Count
    $report.installed_exe_sha256=Get-SwirlIntegrationHash (Join-Path $target 'Swirl.exe')
    $report.installed_rust_dll_sha256=Get-SwirlIntegrationHash (Join-Path $target 'swirl_api.dll')
    $report.installed_manifest_sha256=Get-SwirlIntegrationHash (Join-Path $target 'package-manifest.json')
    $layout=@(Get-ChildItem -LiteralPath $target -Recurse -Force|Sort-Object FullName|ForEach-Object {if($_.PSIsContainer){[ordered]@{path=$_.FullName.Substring($target.Length+1).Replace('\','/');kind='directory'}}else{[ordered]@{path=$_.FullName.Substring($target.Length+1).Replace('\','/');kind='file';length=$_.Length;sha256=(Get-SwirlIntegrationHash $_.FullName)}}})
    ConvertTo-Json -InputObject $layout -Depth 5|Set-Content -LiteralPath (Join-Path $evidence 'installed-layout.json') -Encoding UTF8
    $uninstallState=Get-SwirlIntegrationState $context 'uninstall-command'
    Require 'normal-uninstall-command-is-a-real-reg-sz' ($uninstallState.exists -and $uninstallState.type -eq 1)
    $uninstallCommand=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String([string]$uninstallState.bytes)).TrimEnd([char]0)
    $uninstallMatch=[regex]::Match($uninstallCommand,'^"([^"\x00]+)"$')
    # Legacy NSIS used duplicate path separators. Windows normalization is
    # part of the same executable-identity check for both candidate and control.
    Require 'normal-uninstall-command-resolves-exact-unicode-executable' ($uninstallMatch.Success -and [IO.Path]::GetFullPath($uninstallMatch.Groups[1].Value) -ieq [IO.Path]::GetFullPath((Join-Path $target '卸载 Swirl.exe')))
    $canonicalUninstall=Test-SwirlIntegrationState $uninstallState (New-SwirlRegistryValueState 'String' ('"'+(Join-Path $target '卸载 Swirl.exe')+'"'))
    if($NegativeControl){$report.negative_control.legacy_uninstall_command_canonical_raw=$canonicalUninstall}
    else{Require 'candidate-uninstall-command-has-exact-canonical-raw-unicode-bytes' $canonicalUninstall}
    $shell=New-Object -ComObject WScript.Shell
    try{foreach($id in @('desktop','start-menu')){
        if($crossVersion -and $id -ceq 'desktop') {
            Require 'cross-version-keeps-the-exact-user-edited-shortcut' (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context $id) $original[$id])
            continue
        }
        $link=$shell.CreateShortcut($context.Targets[$id].path);try{
        $location=[string]$link.IconLocation;$comma=$location.LastIndexOf(',')
        Require ('shortcut-icon-index-'+$id) ($comma -gt 0 -and $location.Substring($comma+1).Trim() -ceq '0')
        Require ('shortcut-target-and-icon-'+$id) ([IO.Path]::GetFullPath([string]$link.TargetPath) -ieq [IO.Path]::GetFullPath((Join-Path $target 'Swirl.exe')) -and [IO.Path]::GetFullPath($location.Substring(0,$comma).Trim('"')) -ieq [IO.Path]::GetFullPath((Join-Path $target 'Swirl-brand-0217-optical.ico')))
    }finally{$null=[Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}}}
    finally{$null=[Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
    $exe=Join-Path $target 'Swirl.exe'
    $env:PATH=$target+';'+$env:WINDIR+'\System32;'+$env:WINDIR
    Run-Process 'installed-rust' $exe ('--rust-core-self-test "'+(Join-Path $evidence 'installed-rust-self-test.json')+'"') 30
    $rust=Read-Json (Join-Path $evidence 'installed-rust-self-test.json')
    Require 'installed-rust-real-data-path-and-source' ($rust.success -and $rust.http_response_verified -and $rust.connect_response_verified -and $rust.socks5_response_verified -and $rust.listener_released -and $rust.origin_requests -eq 3 -and $rust.library.source_sha -ceq $ExpectedSourceSha -and $rust.library.build_id -ceq $manifest.rust.build_id)
    $report.rust_roundtrips_verified=$true
    Run-Process 'installed-tls' $exe ('--tls-runtime-self-test "'+(Join-Path $evidence 'installed-tls-runtime.json')+'"') 30
    $tls=Read-Json (Join-Path $evidence 'installed-tls-runtime.json')
    Require 'installed-qt612-and-local-tls-runtime' ($tls.success -and $tls.qt_build_version -ceq '6.12.0' -and $tls.qt_runtime_version -ceq '6.12.0' -and $tls.client_alpn_supported -and $tls.expected_version -ceq '3.5.9')
    $report.tls_runtime_verified=$true
    $diagnostics=Join-Path $target 'Swirl-diagnostics.txt'
    if([IO.File]::Exists($diagnostics)){[IO.File]::Delete($diagnostics)}
    if($crossVersion) {
        Record-ProfileProxyObservation 'before-new-normal-ui'
        Invoke-NormalUi 'candidate-0240-normal-ui'
        Record-ProfileProxyObservation 'after-new-normal-ui'
        $report.cross_version_upgrade.new_normal_ui_closed_normally=$report.normal_ui_closed_normally
        $null=Invoke-NodeStoreFixture 'after-new-normal-close'
    }
    if($Scenario -eq 'clean') {
        Run-Process 'production-ui-test-hooks-disabled' $exe '--policy-self-test' 30 4
        $report.ui_test_hooks_disabled=$true
        if([IO.File]::Exists($diagnostics)){[IO.File]::Delete($diagnostics)}
        Invoke-NormalUi 'normal-ui'
        $smokeRoot=Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'SwirlNormalInstallerSmoke'
        [IO.Directory]::CreateDirectory($smokeRoot)|Out-Null;$env:SWIRL_TEST_ROOT=$smokeRoot
        Run-Process 'installed-all-pages' $exe '--smoke-test --font-review' 60
        $text=[IO.File]::ReadAllText($diagnostics);[IO.File]::Copy($diagnostics,(Join-Path $evidence 'installed-ui.log'),$false)
        $cache=[regex]::Matches($text,'(?m)^4:\s+QML_CACHE_EVIDENCE\s+(\{.*\})\s*$')
        Require 'isolated-smoke-emits-one-cache-identity' ($cache.Count -eq 1)
        $report.smoke_cache_identity=$cache[0].Groups[1].Value|ConvertFrom-Json
        Require 'smoke-cache-identity-belongs-to-the-smoke-root' ([IO.Path]::GetFullPath([string]$report.smoke_cache_identity.path).StartsWith([IO.Path]::GetFullPath($smokeRoot).TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase) -and $report.smoke_cache_identity.flavor -ceq 'release' -and $report.smoke_cache_identity.qtVersion -ceq '6.12.0')
        $completed=[regex]::Matches($text,'(?m)^4:\s+SMOKE_PAGES\s+(\d+)\s*$')
        $ready=[regex]::Matches($text,'(?m)^4:\s+FONT_SMOKE_ROUTE_READY\s+(\S+)\s+(\S+)\s*$')
        Require 'installed-smoke-confirms-every-traversed-page-ready' ($completed.Count -eq 1 -and [int]$completed[0].Groups[1].Value -gt 0 -and $ready.Count -eq [int]$completed[0].Groups[1].Value -and $text -notmatch '(?m)^[123]:')
        foreach($route in $ready){$requested=$route.Groups[1].Value.Trim('"');$actual=$route.Groups[2].Value.Trim('"');$expected=if($requested -in @('requestlogs','dashboard')){'activity'}else{$requested};Require 'installed-smoke-ready-route-matches-request' ($actual -ceq $expected)}
        $report.installed_ui_pages=$ready.Count
        [Environment]::SetEnvironmentVariable('SWIRL_TEST_ROOT',$null,'Process');[IO.File]::Delete($diagnostics)
    }
    $userData=Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'SOLHK/Swirl/installer-user-sentinel.txt'
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($userData))|Out-Null
    [IO.File]::WriteAllText($userData,'Synthetic normal-user data that uninstall must preserve.');$dataHash=Get-SwirlIntegrationHash $userData
    $extras=$crossVersionExtras
    if($Scenario -in @('edits','upgrade')) {
        Save-Shortcut $context.Targets['desktop'].path '用户安装后编辑的快捷方式'
        Set-SwirlIntegrationState $context 'publisher' (New-SwirlRegistryValueState 'ExpandString' '%LOCALAPPDATA%\用户安装后修改')
        Set-SwirlIntegrationState $context 'no-repair' ([ordered]@{exists=$false})
        foreach($id in @('desktop','publisher','no-repair')){$original[$id]=Get-SwirlIntegrationState $context $id}
        [IO.File]::WriteAllText((Join-Path $target 'user-notes.txt'),'Synthetic user-owned installation file')
        [IO.Directory]::CreateDirectory((Join-Path $target 'data'))|Out-Null
        [IO.File]::WriteAllText((Join-Path $target 'data/user-store.dpapi'),'Synthetic bytes only; no private credential')
        $extras=@('user-notes.txt','data/user-store.dpapi')
    }
    if($Scenario -eq 'upgrade') {
        Require 'fresh-ordinary-profile-has-no-node-store-or-sidecar' (-not (Test-Path -LiteralPath $nodeStorePath) -and -not (Test-Path -LiteralPath ($nodeStorePath+'.selected')))
        $storeBaseline=Invoke-NodeStoreFixture 'create' 'create'
        $null=Invoke-NodeStoreFixture 'create-existing-refused' 'create' 2
        Require 'refused-create-keeps-both-original-profile-file-hashes' ((Get-SwirlIntegrationHash $nodeStorePath) -ceq $storeBaseline.ciphertext_sha256 -and (Get-SwirlIntegrationHash ($nodeStorePath+'.selected')) -ceq $storeBaseline.selection_sha256)
        $report.dpapi_store_preservation.existing_store_create_refused=$true
        $null=Invoke-NodeStoreFixture 'before-reinstall'
        Run-Process 'same-package-upgrade' $setup '/S' 120
        Assert-Payload $extras
        Require 'actual-upgrade-preserves-later-shortcut-registry-edit-and-delete' ((Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'desktop') $original['desktop']) -and (Test-SwirlIntegrationState (Get-SwirlIntegrationState $context 'publisher') $original['publisher']) -and -not (Get-SwirlIntegrationState $context 'no-repair').exists)
        $null=Invoke-NodeStoreFixture 'after-reinstall'
        Invoke-NormalUi 'upgrade-normal-ui'
        $null=Invoke-NodeStoreFixture 'after-normal-close'
    }
    $uninstaller=Join-Path $evidence 'actual-installed-uninstaller.exe'
    [IO.File]::Copy((Join-Path $target '卸载 Swirl.exe'),$uninstaller,$false)
    if($Scenario -eq 'clean') {
        $held=[IO.File]::Open($context.Targets['desktop'].path,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
        try{Run-Process 'uninstall-locked-integration-must-fail' $uninstaller ('/S _?='+$target) 120 2}finally{$held.Dispose()}
        Assert-Payload
        Require 'failed-integration-restore-retains-manifest-and-committed-receipt' ([IO.File]::Exists((Join-Path $target 'package-manifest.json')) -and (Read-SwirlIntegrationReceipt $context).phase -eq 'committed')
        $report.retry_after_restore_failure=$true
    }
    if($crossVersion){Record-ProfileProxyObservation 'before-uninstall'}
    Run-Process 'uninstall' $uninstaller ('/S _?='+$target) 120
    if($crossVersion){Record-ProfileProxyObservation 'after-uninstall'}
    $preserved=Original-Preserved $original
    $report.integration_restored_or_user_edits_preserved=$preserved
    $report.negative_control.observed_pass=$preserved
    if($NegativeControl){
        $report.negative_control.required_assertion_failed=-not $preserved
        Require 'legacy-actual-uninstaller-fails-required-preservation-assertion' (-not $preserved)
    }else{Require 'original-integration-and-later-user-edits-preserved' $preserved}
    $report.install_directory_removed=-not (Test-Path -LiteralPath $target)
    if($extras.Count){
        $remaining=@(Get-ChildItem -LiteralPath $target -File -Recurse -Force|ForEach-Object {$_.FullName.Substring($target.Length+1).Replace('\','/')}|Sort-Object)
        Require 'uninstall-leaves-only-explicit-user-owned-files' (@(Compare-Object ($extras|Sort-Object) $remaining).Count -eq 0)
        Require 'user-owned-installation-bytes-preserved' ([IO.File]::ReadAllText((Join-Path $target 'user-notes.txt')) -ceq 'Synthetic user-owned installation file' -and [IO.File]::ReadAllText((Join-Path $target 'data/user-store.dpapi')) -ceq 'Synthetic bytes only; no private credential')
    }else{Require 'clean-payload-installation-directory-removed' $report.install_directory_removed}
    Require 'ordinary-profile-user-data-survives-uninstall' ((Get-SwirlIntegrationHash $userData) -ceq $dataHash)
    if($Scenario -eq 'upgrade') {
        $null=Invoke-NodeStoreFixture 'after-uninstall'
        Require 'all-four-same-package-dpapi-preservation-phases-ran' ($storeStages.Count -eq 4 -and $report.normal_ui_no_test_arguments -and $report.normal_ui_closed_normally -and $report.normal_ui_inherited_standard_user_profile)
        $report.dpapi_store_preservation.verified=$true
    }
    if($crossVersion) {
        $null=Invoke-NodeStoreFixture 'after-uninstall'
        Require 'all-five-cross-version-offline-preservation-phases-ran' ($storeStages.Count -eq 5 -and $report.cross_version_upgrade.old_normal_ui_closed_normally -and $report.cross_version_upgrade.new_normal_ui_closed_normally -and $report.normal_ui_inherited_standard_user_profile)
        $profileProxyAfter=Profile-ProxyFingerprint
        $proxyDiagnostic.original_fingerprint_after=$profileProxyAfter
        $report.cross_version_upgrade.system_proxy_settings_unchanged=$profileProxyAfter -ceq $profileProxyBefore
        Require 'ordinary-standard-user-proxy-settings-unchanged-after-upgrade-and-uninstall' $report.cross_version_upgrade.system_proxy_settings_unchanged
        $report.dpapi_store_preservation.verified=$true
        $report.cross_version_upgrade.verified=$true
    }
    $report.user_data_preserved=$true
    $report.success=-not $report.forced_termination
}catch{$report.error=$_.Exception.Message;$report.success=$false}
finally{
    if($crossVersion) {
        try {
            $proxyDiagnostic.raw_final=Get-SwirlProxyRegistryDiagnostic
            if($null -ne $proxyDiagnostic.raw_baseline){$proxyDiagnostic.final_difference=Compare-SwirlProxyRegistryDiagnostic $proxyDiagnostic.raw_baseline $proxyDiagnostic.raw_final}
        }catch{
            $report.success=$false;$proxyDiagnostic.final_diagnostic_error=$_.Exception.Message
            if($null -eq $report.error){$report.error='Final redacted proxy diagnostic failed; inspect proxy-diagnostics.json.'}
        }
        if($null -ne $proxyDiagnostic.original_fingerprint_after) {
            try {
                $proxyDiagnostic.post_assertion_query_ran=$true
                $proxyDiagnostic.post_assertion_query=Get-SwirlProxyQueryDiagnostic
                if(-not $proxyDiagnostic.post_assertion_query.query_success){$proxyDiagnostic.post_assertion_query_error='Both documented WinINet query variants failed; inspect numeric errors.'}
            }catch{$proxyDiagnostic.post_assertion_query_error=$_.Exception.Message}
        }
        $proxyDiagnostic|ConvertTo-Json -Depth 14|Set-Content -LiteralPath (Join-Path $evidence 'proxy-diagnostics.json') -Encoding UTF8
    }
    $report|ConvertTo-Json -Depth 14|Set-Content -LiteralPath (Join-Path $evidence 'case.json') -Encoding UTF8
}
if(-not $report.success){throw ('Normal installer child failed: '+$report.error)}
