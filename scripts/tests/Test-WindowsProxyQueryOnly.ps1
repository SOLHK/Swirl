param(
    [Parameter(Mandatory=$true)][string]$ExpectedSourceSha,
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory,
    [Parameter(Mandatory=$true)][string]$ExpectedUserSid,
    [ValidateSet('x86','x64')][string]$ExpectedPowerShellArchitecture='x86'
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$ExpectedPowerShellArchitecture=$ExpectedPowerShellArchitecture.ToLowerInvariant()
. (Join-Path $PSScriptRoot 'WindowsProxyDiagnostics.ps1')
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal $identity
$windowsPowerShell51=$PSVersionTable.PSEdition -ceq 'Desktop' -and $PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1
$actualArchitecture=if([Environment]::Is64BitProcess){'x64'}else{'x86'}
$evidence=[IO.Path]::GetFullPath($EvidenceDirectory)
if(-not [IO.Directory]::Exists($evidence)){throw 'The disposable-user wrapper must create the evidence directory.'}
$receipt=Join-Path $evidence 'proxy-query-only.json'
if([IO.File]::Exists($receipt)){throw 'Proxy query observation requires a new receipt path.'}
$report=[ordered]@{
    schema=1;source_sha=$ExpectedSourceSha;scope='Fresh standard-user WinINet query-only observation; no Swirl or proxy-setting writes.'
    actual_non_admin_token=($identity.User.Value -ceq $ExpectedUserSid -and -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))
    actual_standard_user_powershell=($windowsPowerShell51 -and $actualArchitecture -ceq $ExpectedPowerShellArchitecture -and $identity.User.Value -ceq $ExpectedUserSid -and -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))
    actual_x86_powershell=($windowsPowerShell51 -and $actualArchitecture -ceq 'x86')
    architecture=$actualArchitecture;expected_architecture=$ExpectedPowerShellArchitecture
    powershell_version=$PSVersionTable.PSVersion.ToString();process_bits=([IntPtr]::Size*8)
    direct_registry_write_apis_used=$false;direct_proxy_setting_apis_used=$false;direct_http_request_apis_used=$false;swirl_application_launched=$false
    api_scope_basis='Audited diagnostic call path; not operating-system-internal instrumentation.'
    attribution='Read-only native API calls can still have operating-system side effects. Differences are observations, not a product-fix claim or packet-level egress measurement.'
    negative_controls=$null;no_query_control=$null;queries=@();success=$false;error=$null
}
try {
    if(-not $report.actual_non_admin_token -or -not $report.actual_standard_user_powershell -or $ExpectedSourceSha -cnotmatch '^[0-9a-f]{40}$'){throw 'Expected the exact disposable standard-user Windows PowerShell 5.1 architecture, identity and full source SHA.'}
    $repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
    $source=(& git -c ('safe.directory='+$repo) -C $repo rev-parse HEAD).Trim()
    if($LASTEXITCODE -ne 0 -or $source -cne $ExpectedSourceSha){throw 'Proxy observation checkout source differs from the supplied identity.'}

    # Pure-memory controls cannot prime WinINet or alter any real setting.
    $values=@('ProxyEnable','ProxyServer','ProxyOverride','AutoConfigURL','AutoDetect')|ForEach-Object {
        [ordered]@{name=$_;present=$true;native_type=4;byte_length=4;sha256=('a'*64)}
    }
    $synthetic=[ordered]@{keys=@([ordered]@{view='Registry32';path='InternetSettings';present=$true;values=@($values)},[ordered]@{view='Registry32';path='Connections';present=$true;values=@([ordered]@{name='name-sha256:'+('c'*64);present=$true;native_type=3;byte_length=4;sha256=('d'*64)})})}
    $encoded=$synthetic|ConvertTo-Json -Depth 8 -Compress
    $baseline=$encoded|ConvertFrom-Json
    $controls=New-Object 'System.Collections.Generic.List[object]'
    $controls.Add([ordered]@{name='identical-memory-snapshot';passed=(Compare-SwirlProxyRegistryDiagnostic $baseline ($encoded|ConvertFrom-Json)).equal})
    foreach($name in @('ProxyEnable','ProxyServer','ProxyOverride','AutoConfigURL','AutoDetect')) {
        foreach($field in @('present','native_type','byte_length','sha256')) {
            $changed=$encoded|ConvertFrom-Json
            $value=@($changed.keys[0].values|Where-Object {$_.name -ceq $name})[0]
            switch($field){'present'{$value.present=$false};'native_type'{$value.native_type=1};'byte_length'{$value.byte_length=8};'sha256'{$value.sha256='b'*64}}
            $difference=Compare-SwirlProxyRegistryDiagnostic $baseline $changed
            $controls.Add([ordered]@{name=($name+'-'+$field);passed=(-not $difference.equal -and @($difference.changes|Where-Object {$_.path -ceq ('Registry32/InternetSettings/'+$name+'/'+$field)}).Count -eq 1)})
        }
    }
    $changed=$encoded|ConvertFrom-Json;$changed.keys[1].values[0].sha256='e'*64
    $controls.Add([ordered]@{name='opaque-connections-byte-change';passed=(-not (Compare-SwirlProxyRegistryDiagnostic $baseline $changed).equal)})
    $changed=$encoded|ConvertFrom-Json;$changed.keys[1].present=$false
    $controls.Add([ordered]@{name='connections-key-presence-change';passed=(-not (Compare-SwirlProxyRegistryDiagnostic $baseline $changed).equal)})
    $changed=$encoded|ConvertFrom-Json;$changed.keys[1].values=@()
    $controls.Add([ordered]@{name='unknown-connection-value-removal';passed=(-not (Compare-SwirlProxyRegistryDiagnostic $baseline $changed).equal)})
    $report.negative_controls=[ordered]@{scope='In-memory digest comparison only; no operating-system settings were changed.';cases=@($controls.ToArray());success=(@($controls|Where-Object {-not $_.passed}).Count -eq 0)}
    if(-not $report.negative_controls.success){throw 'Proxy diagnostic comparator negative control failed.'}

    # Use the same 100 ms observation delay with and without a query. The query
    # also has an immediate post-call snapshot and measured duration. This is not proof that
    # the operating system cannot perform later asynchronous initialization.
    $before=Get-SwirlProxyRegistryDiagnostic
    $immediate=Get-SwirlProxyRegistryDiagnostic
    Start-Sleep -Milliseconds 100
    $after=Get-SwirlProxyRegistryDiagnostic
    $report.no_query_control=[ordered]@{wait_ms=100;raw_before=$before;raw_immediate=$immediate;raw_read_difference=(Compare-SwirlProxyRegistryDiagnostic $before $immediate);raw_after=$after;raw_difference=(Compare-SwirlProxyRegistryDiagnostic $before $after)}
    $queries=New-Object 'System.Collections.Generic.List[object]'
    for($index=1;$index -le 2;++$index) {
        $observation=Get-SwirlProxyQueryDiagnostic 100
        $queries.Add([ordered]@{query_number=$index;observation=$observation})
        $report.queries=@($queries.ToArray())
        if(-not $observation.query_success){throw 'Both documented WinINet query variants failed; inspect numeric errors in the receipt.'}
    }
    $report.success=$true
}catch{$report.error=$_.Exception.Message}
finally{$report|ConvertTo-Json -Depth 14|Set-Content -LiteralPath $receipt -Encoding UTF8}
if(-not $report.success){throw ('Fresh standard-user proxy query observation failed: '+$report.error)}
Write-Host 'Fresh standard-user WinINet query observations and in-memory negative controls saved; no installer assertion was changed.'
