#Requires -Version 7.4
param(
    [string]$RepositoryRoot=(Join-Path $PSScriptRoot '../..'),
    [string]$OutputPath=''
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$source=Join-Path (Resolve-Path -LiteralPath $RepositoryRoot).Path 'scripts/Test-EtwProviderEnablement.ps1'
$tokens=$null;$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw 'ProbeSourcePowerShellParseFailed' }
# Import only the two pure functions; no top-level native probe code is evaluated.
foreach ($functionName in @('ConvertFrom-ProbeLogmanCollector','Test-ProbeCollector')) {
    $definitions=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq $functionName},$true))
    if ($definitions.Count -ne 1) { throw ('PureFunctionMissingOrDuplicated:'+ $functionName) }
    . ([scriptblock]::Create($definitions[0].Extent.Text))
}
$providerGuids=@{'Microsoft-Windows-DXGI'='ca11c036-0102-4a2d-a6ad-f03cfed5d3c9';'Microsoft-Windows-DxgKrnl'='802ec45a-1e99-4b83-9920-87c98277ba9d'}
$nonce='72f542c83dce4f0183be98890f78e84b'
$collector='WPR_initiated_SwirlEtwInstance'+$nonce+'_SwirlEtwCollector'+$nonce
$provider='Microsoft-Windows-DxgKrnl'
$expectedGuid=[guid]$providerGuids[$provider]
$all=[UInt64]::MaxValue
# Public a399 run42311748093/artifact13548617939 G1 query, with repository line endings.
$fixture=@'

Name:                 WPR_initiated_SwirlEtwInstance72f542c83dce4f0183be98890f78e84b_SwirlEtwCollector72f542c83dce4f0183be98890f78e84b
Status:               Running
Root Path:            %systemdrive%\PerfLogs\Admin
Segment:              Off
Schedules:            On

Name:                 WPR_initiated_SwirlEtwInstance72f542c83dce4f0183be98890f78e84b_SwirlEtwCollector72f542c83dce4f0183be98890f78e84b\WPR_initiated_SwirlEtwInstance72f542c83dce4f0183be98890f78e84b_SwirlEtwCollector72f542c83dce4f0183be98890f78e84b
Type:                 Trace
Append:               Off
Circular:             Off
Overwrite:            Off
Buffer Size:          128
Buffers Lost:         0
Buffers Written:      0
Buffer Flush Timer:   0
Clock Type:           Performance
File Mode:            Buffering

Provider:
Name:                 Microsoft-Windows-DxgKrnl
Provider Guid:        {802EC45A-1E99-4B83-9920-87C98277BA9D}
Level:                5
KeywordsAll:          0x0
KeywordsAny:          0xffffffffffffffff (Base,Profiler,References,ForceVsync,Patch,Cdd,Resource,Memory,Dxgkrnl_StatusChangeNotify,DxgKrnl_Power,DriverEvents,LongHaul,StablePower,DefaultOverride,HistoryBuffer,GPUScheduler,DxgKrnl,DxgKrnl_WDI,Miracast,IndirectSwapChain,GPUVA,VidMmWorkerThread,Diagnostics,VirtualGpu,AdapterLock,MixedReality,HardwareSchedulingLog,Present,DxgKrnl_Int,PerfData,AzureTriageLogging,win:ResponseTime,Microsoft-Windows-DxgKrnl/Diagnostic,Microsoft-Windows-DxgKrnl/Performance,Microsoft-Windows-DxgKrnl/Power,Microsoft-Windows-DxgKrnl/Contention,Microsoft-Windows-DxgKrnl-Admin,Microsoft-Windows-DxgKrnl-Operational,0x80000000,0x100000000,0x200000000,0x400000000,0x800000000,0x1000000000,0x2000000000,0x4000000000,0x8000000000,0x10000000000,0x20000000000,0x40000000000,0x80000000000,0x100000000000,0x200000000000,0x400000000000,0x800000000000,0x2000000000000,0x4000000000000,0x8000000000000,0x10000000000000,0x20000000000000,0x40000000000000,0x80000000000000,0x100000000000000,0x200000000000000)
Properties:           64
Filter Type:          0

The command completed successfully.
'@
$fixture=$fixture.Replace("`r`n","`n")
$checks=[Collections.Generic.List[object]]::new()
function Invoke-Control([string]$Name,[scriptblock]$Action,[bool]$ExpectedSuccess=$true) {
    $observed=$false;$errorType=$null;$errorMessage=$null
    try { $null=& $Action;$observed=$true }
    catch { $errorType=$_.Exception.GetType().Name;$errorMessage=$_.Exception.Message }
    $checks.Add([ordered]@{name=$Name;expected_success=$ExpectedSuccess;observed_success=$observed;passed=($observed -eq $ExpectedSuccess);error_type=$errorType;error=$errorMessage})
}
function Parse-Fixture([string]$Text,[UInt64]$Any=[UInt64]::MaxValue) {
    ConvertFrom-ProbeLogmanCollector $Text $collector $provider $expectedGuid $Any
}
function New-CollectorCase {
    $parsed=Parse-Fixture $fixture
    $metadata=[ordered]@{
        status='verified-owned-provider-fields';wpr_ownership_confirmed=$true
        actual_collector_name=$collector;session_identity_verified=$true;query_ok=$true;query_exit_code=0;fields_verified=$true
    }
    foreach ($key in @('provider_name','provider_guid','level','match_any_keyword','match_all_keyword','trace_name')) { $metadata[$key]=$parsed[$key] }
    return [ordered]@{
        component='DxgKrnl';instance_name=('SwirlEtwInstance'+$nonce);collector_token=('SwirlEtwCollector'+$nonce)
        keywords='0xffffffffffffffff';stacks=$false;ownership_confirmed=$true;logman_session_metadata=$metadata
        actual_system_keywords=@();actual_system_stacks=@();actual_provider=$null;collector_names=@()
    }
}
function Assert-Collector($Case,[string]$Text,[bool]$Expected) {
    $accepted=Test-ProbeCollector $Case $Text
    if ($accepted -ne $Expected) { throw 'UnexpectedCollectorCrosscheckVerdict' }
}
$wpr="Collector Name : $collector`nProviders`n  ${provider}: : 0x05`n"
Invoke-Control 'actual-public-same-owned-session' {
    $result=Parse-Fixture $fixture
    if ($result.provider_guid -cne $expectedGuid.ToString() -or $result.match_any_keyword -cne '0xffffffffffffffff' -or $result.match_all_keyword -cne '0x0000000000000000' -or $result.level -ne 5) { throw 'DecodedFieldMismatch' }
}
Invoke-Control 'numeric-subset-is-compared-as-uint64' { Parse-Fixture ($fixture.Replace('0xffffffffffffffff','0x10')) ([UInt64]16) }
Invoke-Control 'actual-layout-with-windows-crlf' { Parse-Fixture ($fixture.Replace("`n","`r`n")) }
Invoke-Control 'uint64-high-bit-is-not-signed' { Parse-Fixture ($fixture.Replace('0xffffffffffffffff','0x8000000000000000')) ([Convert]::ToUInt64('8000000000000000',16)) }
Invoke-Control 'wrong-session-root' { Parse-Fixture ($fixture.Replace("Name:                 $collector`nStatus:","Name:                 Wrong`nStatus:")) } $false
Invoke-Control 'wrong-trace-session' { Parse-Fixture ($fixture.Replace($collector+'\'+$collector,$collector+'\Other')) } $false
Invoke-Control 'wrong-provider-name' { Parse-Fixture ($fixture.Replace('Name:                 Microsoft-Windows-DxgKrnl','Name:                 Microsoft-Windows-DXGI')) } $false
Invoke-Control 'wrong-provider-guid' { Parse-Fixture ($fixture.Replace('802EC45A-1E99-4B83-9920-87C98277BA9D','CA11C036-0102-4A2D-A6AD-F03CFED5D3C9')) } $false
Invoke-Control 'wrong-level' { Parse-Fixture ($fixture.Replace('Level:                5','Level:                4')) } $false
Invoke-Control 'wrong-any-mask' { Parse-Fixture ($fixture.Replace('0xffffffffffffffff','0x10')) } $false
Invoke-Control 'nonzero-all-mask' { Parse-Fixture ($fixture.Replace('KeywordsAll:          0x0','KeywordsAll:          0x1')) } $false
Invoke-Control 'overflow-any-mask' { Parse-Fixture ($fixture.Replace('0xffffffffffffffff','0x1ffffffffffffffff')) } $false
Invoke-Control 'malformed-any-mask' { Parse-Fixture ($fixture.Replace('0xffffffffffffffff','0xZZ')) } $false
Invoke-Control 'overflow-level' { Parse-Fixture ($fixture.Replace('Level:                5','Level:                4294967296')) } $false
Invoke-Control 'stopped-session' { Parse-Fixture ($fixture.Replace('Status:               Running','Status:               Stopped')) } $false
Invoke-Control 'wrong-collector-type' { Parse-Fixture ($fixture.Replace('Type:                 Trace','Type:                 Counter')) } $false
Invoke-Control 'missing-guid' { Parse-Fixture ([regex]::Replace($fixture,'(?m)^Provider Guid:[^\r\n]*\r?\n','')) } $false
Invoke-Control 'duplicate-guid' { Parse-Fixture ([regex]::Replace($fixture,'(?m)^(Provider Guid:[^\r\n]*)','$1'+"`n"+'$1')) } $false
Invoke-Control 'duplicate-provider-block' { Parse-Fixture ($fixture.Replace('Provider:',"Provider:`nProvider:")) } $false
Invoke-Control 'unknown-field' { Parse-Fixture ($fixture.Replace('Filter Type:          0',"Filter Type:          0`nUnrecognized:          1")) } $false
Invoke-Control 'unknown-keyword-suffix' { Parse-Fixture ($fixture.Replace('KeywordsAll:          0x0','KeywordsAll:          0x0 unknown')) } $false
Invoke-Control 'missing-success-footer' { Parse-Fixture ($fixture.Replace('The command completed successfully.','')) } $false
Invoke-Control 'wpr-blank-mask-needs-verified-query' { Assert-Collector (New-CollectorCase) $wpr $true }
Invoke-Control 'nonempty-wpr-agrees-with-query' { Assert-Collector (New-CollectorCase) ($wpr.Replace(': : 0x05',': 0xffffffffffffffff : 0x05')) $true }
Invoke-Control 'nonempty-wpr-mask-conflict' { Assert-Collector (New-CollectorCase) ($wpr.Replace(': : 0x05',': 0x10 : 0x05')) $false }
Invoke-Control 'wpr-level-conflict' { Assert-Collector (New-CollectorCase) ($wpr.Replace('0x05','0x04')) $false }
Invoke-Control 'wpr-guid-conflict' { Assert-Collector (New-CollectorCase) ($wpr.Replace($provider,'ca11c036-0102-4a2d-a6ad-f03cfed5d3c9')) $false }
Invoke-Control 'duplicate-wpr-provider' { Assert-Collector (New-CollectorCase) ($wpr+"  ${provider}: : 0x05`n") $false }
Invoke-Control 'unknown-wpr-provider-line' { Assert-Collector (New-CollectorCase) ($wpr+"  malformed provider`n") $false }
Invoke-Control 'unverified-fields' { $case=New-CollectorCase;$case.logman_session_metadata.fields_verified=$false;Assert-Collector $case $wpr $false }
Invoke-Control 'failed-query' { $case=New-CollectorCase;$case.logman_session_metadata.query_ok=$false;Assert-Collector $case $wpr $false }
Invoke-Control 'unconfirmed-ownership' { $case=New-CollectorCase;$case.ownership_confirmed=$false;Assert-Collector $case $wpr $false }
Invoke-Control 'no-metadata' { $case=New-CollectorCase;$case.logman_session_metadata=$null;Assert-Collector $case $wpr $false }
Invoke-Control 'different-case-instance' { $case=New-CollectorCase;$case.instance_name='Other';Assert-Collector $case $wpr $false }
Invoke-Control 'metadata-trace-mismatch' { $case=New-CollectorCase;$case.logman_session_metadata.trace_name='Other';Assert-Collector $case $wpr $false }
$systemText="Collector Name : NT Kernel Logger`nSystem Keywords`nLoader`nCSwitch`nReadyThread`n"
function New-SystemCase([bool]$Stacks=$false) { return [ordered]@{component='System';instance_name='unused';stacks=$Stacks;actual_system_keywords=@();actual_system_stacks=@();collector_names=@()} }
Invoke-Control 'unchanged-system-base' { Assert-Collector (New-SystemCase) $systemText $true }
Invoke-Control 'unchanged-system-stack-set' { Assert-Collector (New-SystemCase $true) ($systemText+"System Stacks`nCSwitch`nReadyThread`n") $true }
Invoke-Control 'unchanged-system-missing-keyword-rejected' { Assert-Collector (New-SystemCase) ($systemText.Replace("ReadyThread`n",'')) $false }
$report=[ordered]@{
    schema=1;scope='Pure parsing and rejection controls; no native tool, Swirl, session or event collection.'
    source_sha256=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    fixture_origin='a3997ef run42311748093 artifact13548617939 probe/018-G1-logman-owned-collector.stdout.log'
    raw_fixture_sha256='0bed670b304c3c2576fbe7f68c62b810a0529614f0ee47ab47813d1896f7f673'
    fixture_line_endings='Normalized to LF for deterministic mutations; a positive control also exercises CRLF. Raw CI original remains unchanged.'
    checks=$checks.ToArray();success=(@($checks | Where-Object { -not $_.passed }).Count -eq 0)
}
if ($OutputPath) {
    $full=[IO.Path]::GetFullPath($OutputPath)
    if (Test-Path -LiteralPath $full) { throw 'PureControlOutputAlreadyExists' }
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($full)) | Out-Null
    [IO.File]::WriteAllText($full,($report | ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
}
$report | ConvertTo-Json -Depth 12
if (-not $report.success) { throw 'EtwCollectorPureControlsFailed' }
