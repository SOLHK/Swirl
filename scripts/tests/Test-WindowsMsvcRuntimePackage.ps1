param(
    [Parameter(Mandatory=$true)][string]$ApplicationDirectory,
    [Parameter(Mandatory=$true)][string]$ExpectedSourceSha,
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
# Dot-sourced helper parameters must not replace this entry point's arguments.
$package=[IO.Path]::GetFullPath($ApplicationDirectory)
$evidence=[IO.Path]::GetFullPath($EvidenceDirectory)
. (Join-Path $PSScriptRoot '../Copy-VerifiedMsvcRuntime.ps1')
Assert-SwirlPathWithoutLinks $package;Assert-SwirlPathWithoutLinks $evidence
[IO.Directory]::CreateDirectory($evidence)|Out-Null
$manifestPath=Join-Path $package 'package-manifest.json'
$manifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8|ConvertFrom-Json
if($ExpectedSourceSha -notmatch '^[0-9a-f]{40}$' -or $manifest.source_sha -cne $ExpectedSourceSha){throw 'MSVC package regression source identity mismatch.'}
$null=Assert-SwirlProductManifest -ApplicationDirectory $package -ExpectedSourceSha $ExpectedSourceSha
$receipt=Assert-SwirlMsvcRuntimePayload -ApplicationDirectory $package
$manifestHash=Get-SwirlMsvcHash $manifestPath
$metadataHash=Get-SwirlMsvcHash (Join-Path $package 'msvc-runtime.json')
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('swirl-msvc-runtime-'+[guid]::NewGuid().ToString('N'))
Assert-SwirlPathWithoutLinks $fixture
$runtime=Join-Path $fixture 'application'
$checks=New-Object 'System.Collections.Generic.List[object]'
$processes=New-Object 'System.Collections.Generic.List[object]'
$negative=New-Object 'System.Collections.Generic.List[object]'
$result=[ordered]@{schema=1;source_sha=$ExpectedSourceSha;scope='Actual candidate PE closure copied to a new fixture; remove one known core CRT DLL at a time and require the real TLS self-test to reject system-runtime fallback. No system-directory or installed-user files are changed.';metadata_sha256=$metadataHash;manifest_sha256=$manifestHash;application_sha256=(Get-SwirlMsvcHash (Join-Path $package 'Swirl.exe'));compiler_source=$receipt.source;required_imports=@($receipt.required_imports);required_modules=@($receipt.required_modules);negative_controls=$negative;checks=$checks;processes=$processes;candidate_unchanged=$false;fixture_removed=$false;forced_termination=$false;success=$false;error=$null}
function Require([string]$Name,[bool]$Passed){$checks.Add([ordered]@{name=$Name;passed=$Passed});if(-not $Passed){throw ('MSVC package regression failed: '+$Name)}}
function Run-Tls([string]$Name,[int]$ExpectedExit) {
    $reportPath=Join-Path $evidence ($Name+'.json')
    $entry=[ordered]@{name=$Name;expected_exit_code=$ExpectedExit;exit_code=$null;exited=$false};$processes.Add($entry)
    $process=$null
    try {
        $process=Start-Process -FilePath (Join-Path $runtime 'Swirl.exe') -ArgumentList ('--tls-runtime-self-test "'+$reportPath+'"') -WorkingDirectory $fixture -PassThru -RedirectStandardOutput (Join-Path $evidence ($Name+'.stdout.log')) -RedirectStandardError (Join-Path $evidence ($Name+'.stderr.log'))
        $entry.exited=$process.WaitForExit(30000)
        if(-not $entry.exited){throw ('TLS runtime process timed out: '+$Name)}
        $process.Refresh();$entry.exit_code=$process.ExitCode
        if($entry.exit_code -ne $ExpectedExit){throw ('TLS runtime process returned an unexpected exit code: '+$Name+' '+$entry.exit_code)}
        if(-not [IO.File]::Exists($reportPath)){throw ('The real TLS runtime did not write its report: '+$Name)}
        return (Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8|ConvertFrom-Json)
    } finally {
        if($null -ne $process){if(-not $process.HasExited){$result.forced_termination=$true;$process.Kill();$null=$process.WaitForExit(5000)};$process.Dispose()}
    }
}
$savedEnvironment=@{}
foreach($name in @('PATH','QT_PLUGIN_PATH','QML_IMPORT_PATH','QML2_IMPORT_PATH')){$savedEnvironment[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
try {
    [IO.Directory]::CreateDirectory($runtime)|Out-Null
    foreach($file in @(Get-ChildItem -LiteralPath $package -Recurse -File -Force|Where-Object {$_.Extension -in @('.dll','.exe') -or $_.Name -in @('msvc-runtime.json','qt.conf')})) {
        Assert-SwirlPathWithoutLinks $file.FullName
        $relative=$file.FullName.Substring($package.TrimEnd('\','/').Length+1)
        $destination=Join-Path $runtime $relative
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))|Out-Null
        [IO.File]::Copy($file.FullName,$destination,$false)
        Require ('exact-fixture-bytes-'+$relative) ((Get-SwirlMsvcHash $destination) -ceq (Get-SwirlMsvcHash $file.FullName))
    }
    $env:PATH=$runtime+';'+$env:SystemRoot+'\System32;'+$env:SystemRoot
    foreach($name in @('QT_PLUGIN_PATH','QML_IMPORT_PATH','QML2_IMPORT_PATH')){[Environment]::SetEnvironmentVariable($name,$null,'Process')}
    $null=Assert-SwirlMsvcRuntimePayload -ApplicationDirectory $runtime
    $positive=Run-Tls 'complete-app-local-runtime' 0
    Require 'actual-complete-runtime-loaded-from-app-local-files' ($positive.success -and $positive.msvc_runtime.required -and $positive.msvc_runtime.metadata_valid -and $positive.msvc_runtime.success)
    foreach($name in $script:SwirlMsvcCoreModules) {
        $path=Join-Path $runtime $name;$held=Join-Path $fixture ('held-'+$name)
        $row=[ordered]@{name=$name;expected_sha256=$receipt.files.PSObject.Properties[$name].Value.sha256;removed_exact_module=$false;static_missing_dependency_rejected=$false;actual_system_fallback_rejected=$false;module_observation=$null;expected_assertion_failed=$false};$negative.Add($row)
        [IO.File]::Move($path,$held);$row.removed_exact_module=-not [IO.File]::Exists($path)
        try {
            $failure=$null
            try{$null=Assert-SwirlMsvcRuntimePayload -ApplicationDirectory $runtime}catch{$failure=$_.Exception.Message}
            $row.static_missing_dependency_rejected=$failure -ceq ('Missing app-local compiler runtime: '+$name)
            Require ('missing-dependency-static-guard-'+$name) $row.static_missing_dependency_rejected
            $failed=Run-Tls ('missing-'+$name) 1
            $module=$failed.msvc_runtime.modules.PSObject.Properties[$name].Value
            $row.module_observation=$module
            $row.actual_system_fallback_rejected=($failed.success -eq $false -and $failed.msvc_runtime.required -and $failed.msvc_runtime.metadata_present -and $failed.msvc_runtime.metadata_valid -and $failed.msvc_runtime.success -eq $false -and $module.required_loaded -and $module.loaded -and $module.inside_application -eq $false -and $module.file_inside_application -eq $false -and $module.hash_matches -eq $false -and $module.success -eq $false)
            $row.expected_assertion_failed=$row.static_missing_dependency_rejected -and $row.actual_system_fallback_rejected
            Require ('real-loaded-system-fallback-is-not-accepted-'+$name) $row.expected_assertion_failed
        } finally {[IO.File]::Move($held,$path)}
    }
    $null=Assert-SwirlMsvcRuntimePayload -ApplicationDirectory $runtime
    $restored=Run-Tls 'restored-complete-app-local-runtime' 0
    Require 'restoring-the-same-dlls-restores-real-runtime-success' ($restored.success -and $restored.msvc_runtime.success)
    $null=Assert-SwirlProductManifest -ApplicationDirectory $package -ExpectedSourceSha $ExpectedSourceSha
    $null=Assert-SwirlMsvcRuntimePayload -ApplicationDirectory $package
    $result.candidate_unchanged=(Get-SwirlMsvcHash $manifestPath) -ceq $manifestHash -and (Get-SwirlMsvcHash (Join-Path $package 'msvc-runtime.json')) -ceq $metadataHash
    Require 'the-real-candidate-package-is-unchanged' $result.candidate_unchanged
    Require 'all-five-real-missing-runtime-negatives-executed' ($negative.Count -eq 5 -and @($negative|Where-Object {-not $_.expected_assertion_failed}).Count -eq 0)
} catch {$result.error=$_.Exception.Message}
finally {
    foreach($name in $savedEnvironment.Keys){[Environment]::SetEnvironmentVariable($name,$savedEnvironment[$name],'Process')}
    if([IO.Directory]::Exists($fixture)) {
        try {Assert-SwirlPathWithoutLinks $fixture;Remove-Item -LiteralPath $fixture -Recurse -Force;$result.fixture_removed=-not [IO.Directory]::Exists($fixture)}
        catch {if(-not $result.error){$result.error='MSVC fixture cleanup failed: '+$_.Exception.Message}}
    }
    $result.success=$null -eq $result.error -and $result.candidate_unchanged -and $result.fixture_removed -and -not $result.forced_termination -and $negative.Count -eq 5 -and @($checks|Where-Object {-not $_.passed}).Count -eq 0
    $result|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $evidence 'msvc-runtime-policy.json') -Encoding UTF8
}
if(-not $result.success){throw ('Actual app-local MSVC runtime acceptance failed: '+$result.error)}
