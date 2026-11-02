# Synthetic privacy/package tests plus read-only native API smoke on Windows.
# No application launch, credentials, proxy mutation or external network IO.
param([string]$CollectorPath=(Join-Path $PSScriptRoot '../Collect-CodexNetworkEvidence.ps1'))
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot '../CodexNetworkEvidence.psm1') -Force
$script:checks=0
function Assert([bool]$Value,[string]$Message) { if (!$Value) { throw $Message }; ++$script:checks }
$secret='sensitive-value-must-never-be-exported'
foreach ($value in @(
    ('http://user:'+ $secret +'@proxy.invalid:8080/path/'+$secret+'?token='+$secret+'#'+$secret),
    ('http=proxy.invalid:8080;https=http://user:'+$secret+'@proxy.invalid:8081'),
    ('http=http://proxy.invalid:8080/?token='+$secret+';https='+$secret+':8081'),
    ('http=http://proxy.invalid:8080/private;https='+$secret+':8081'),
    ('http://proxy.invalid:8080/' + $secret),
    ("http://proxy.invalid:8080`r`nAuthorization: Bearer "+$secret),
    ('not a proxy Cookie='+$secret),
    ('file:///C:/'+$secret)
)) {
    $report=@{endpoint=(ConvertTo-ProxyEndpointEvidence $value);map=(ConvertTo-ProxyMapEvidence $value);bypass=(ConvertTo-ProxyBypassEvidence $value)}
    Assert (!(($report | ConvertTo-Json -Depth 8 -Compress).Contains($secret))) 'Secret text escaped proxy evidence allowlists.'
}
$endpoint=ConvertTo-ProxyEndpointEvidence ('http://user:'+$secret+'@proxy.invalid:8080/?token='+$secret)
Assert ($endpoint.valid -and $endpoint.host -eq 'proxy.invalid' -and $endpoint.port -eq 8080 -and $endpoint.credentialsPresent -and $endpoint.extraUriComponentsPresent) 'Endpoint metadata was lost while removing credentials and URI suffixes.'
$v6=ConvertTo-ProxyEndpointEvidence '[::1]:7897'
Assert ($v6.valid -and $v6.host -eq '::1' -and $v6.port -eq 7897 -and $v6.scheme -eq 'http') 'IPv6 HTTP proxy was not represented correctly.'
$ordinary=ConvertTo-ProxyMapEvidence '127.0.0.1:7897'
Assert ($ordinary.entries.Count -eq 1 -and $ordinary.entries[0].mapping -eq 'all' -and $ordinary.entries[0].endpoint.scheme -eq 'http') 'Swirl single proxy was mistaken for SOCKS.'
$map=ConvertTo-ProxyMapEvidence 'http=127.0.0.1:7897;https=[::1]:7898;socks=127.0.0.1:7899'
Assert ($map.entries.Count -eq 3 -and $map.entries[1].endpoint.host -eq '::1' -and $map.entries[2].endpoint.scheme -eq 'socks4') 'Windows protocol map or implicit SOCKSv4 semantics were lost.'
$explicit=ConvertTo-ProxyMapEvidence 'socks=socks5://127.0.0.1:7899'
Assert ($explicit.entries[0].endpoint.scheme -eq 'socks5') 'Explicit SOCKSv5 scheme was overwritten.'
Assert (!(ConvertTo-ProxyEndpointEvidence '').configured) 'Empty endpoint was reported configured.'
foreach ($invalid in @('http://host.invalid:0','http://host.invalid:65536','ftp://host.invalid:21',('x'*4097))) {
    Assert (!(ConvertTo-ProxyEndpointEvidence $invalid).valid) 'Invalid or oversized proxy endpoint was accepted.'
}
$a=ConvertTo-ProxyBypassEvidence 'localhost;127.*;<local>;private.invalid'
$b=ConvertTo-ProxyBypassEvidence 'localhost;127.*;<local>;private.invalid'
$c=ConvertTo-ProxyBypassEvidence 'localhost;127.*;<local>'
Assert ($a.entryCount -eq 4 -and $a.includesLocal -and $a.sha256 -eq $b.sha256 -and $a.sha256 -ne $c.sha256) 'Private bypass comparisons are not stable or distinct.'
Assert (!(($a|ConvertTo-Json).Contains('private.invalid'))) 'Private bypass names were exported.'

# Exercise the actual collector with synthetic command results. In the original
# collector ProxyServer/netsh output exposed this marker directly in the JSON.
$capture=Join-Path ([IO.Path]::GetTempPath()) ('SwirlEvidenceCapture-'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($capture) | Out-Null
try {
    $output=Join-Path $capture 'capture.json'
    & {
        param($Collector,$Output,$LogDirectory,$Marker)
        function Get-CimInstance { param($ClassName,$Property)
            [pscustomobject]@{ProcessId=42;ParentProcessId=1;Name='ChatGPT.exe';ExecutablePath='C:\fixture\ChatGPT.exe';CreationDate=[DateTime]::UtcNow}
            [pscustomobject]@{ProcessId=43;ParentProcessId=42;Name='codex.exe';ExecutablePath='C:\fixture\codex.exe';CreationDate=[DateTime]::UtcNow}
        }
        function Get-ItemProperty { param($Path)
            [pscustomobject]@{ProxyEnable=1;ProxyServer=('http://user:'+$Marker+'@proxy.invalid:8080/?token='+$Marker);
                ProxyOverride=('private.'+$Marker);AutoConfigURL=('http://pac.invalid/'+$Marker)}
        }
        function Get-NetTCPConnection { [CmdletBinding()]param() }
        function Get-NetIPInterface { [CmdletBinding()]param() }
        function Get-DnsClientCache { [CmdletBinding()]param() }
        function Get-AppxPackage { [CmdletBinding()]param($Name) [pscustomobject]@{Version='26.10.1.0'} }
        function netsh { 'http://user:'+$Marker+'@proxy.invalid:8080' }
        # Evidence helpers are already imported above. Keep log discovery fully
        # synthetic, so the collector test never inspects a real user profile.
        function Import-Module { param($Name,[switch]$Force)
            if ([IO.Path]::GetFileName($Name) -notin @('CodexNetworkEvidence.psm1','CodexLogSummary.psm1')) { throw 'Unexpected fixture module.' }
        }
        function Get-CodexLogSummary { param($LogDirectory) @{state='no_logs';filesRead=0} }
        & $Collector -OutputPath $Output -CodexLogDirectory $LogDirectory | Out-Null
    } $CollectorPath $output $capture $secret
    $captured=Get-Content -LiteralPath $output -Raw
    Assert (!$captured.Contains($secret)) 'Collector exported raw registry/WinHTTP credentials or PAC/bypass text.'
    $report=$captured | ConvertFrom-Json
    Assert ($report.schema -eq 2 -and $report.comparisonLabel -eq 'Baseline' -and $report.processes.Count -eq 2) 'Collector lost schema, comparison label or unpackaged ChatGPT process.'
    Assert ($report.windowsProxy.proxy.entries[0].endpoint.credentialsPresent -and $report.codexPackages[0].version -eq '26.10.1.0') 'Collector omitted safe endpoint or package version metadata.'
} finally {
    Remove-Item -LiteralPath $capture -Recurse -Force
}

if ($env:OS -eq 'Windows_NT') {
    $native=Get-WindowsNativeProxyEvidence
    Assert $native.available 'Native proxy APIs could not be queried.'
    Assert $native.winInet.available 'WinINet ABI/query failed.'
    Assert $native.winHttpDefault.available 'WinHTTP default proxy ABI/query failed.'
    Assert $native.winHttpCurrentUser.available 'WinHTTP current-user ABI/query failed.'
    # Do not print the real settings. Only the fixed assertion count is emitted.
    $temp=Join-Path ([IO.Path]::GetTempPath()) ('SwirlNetworkEvidence-'+[guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($temp) | Out-Null
    try {
        $source='a'*40
        $manifest=@{schema=1;source_sha=$source;rust=@{source_sha=$source};files=@()}
        foreach ($name in @('Swirl.exe','swirl_api.dll','swirl-rust-build.json')) {
            $path=Join-Path $temp $name
            if ($name -eq 'swirl-rust-build.json') {
                @{source_sha=$source} | ConvertTo-Json | Set-Content -LiteralPath $path -Encoding utf8
            } else { [IO.File]::WriteAllText($path,'Synthetic file, never executable: '+$name) }
            $manifest.files+=@{path=$name;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash}
        }
        $manifestFile=Join-Path $temp 'package-manifest.json'
        $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestFile -Encoding utf8
        $exe=Join-Path $temp 'Swirl.exe'
        $good=Get-SwirlPackageEvidence $exe
        Assert ($good.available -and $good.identityFilesMatchManifest -and $good.manifestSourcesAgree -and $good.buildReceiptSourcesAgree -and $good.claimedSourceSha -eq $source) 'Matching product file hashes and source receipts were not recognized.'
        Assert (!$good.sourceIdentityVerified) 'Untrusted on-disk manifest became verified build/loaded-source identity.'
        [IO.File]::AppendAllText((Join-Path $temp 'swirl_api.dll'),'modified')
        $changed=Get-SwirlPackageEvidence $exe
        Assert (!$changed.identityFilesMatchManifest) 'Changed installed DLL was reported hash matched.'
        $manifest.source_sha=$secret
        $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestFile -Encoding utf8
        $invalid=Get-SwirlPackageEvidence $exe
        Assert (!(($invalid|ConvertTo-Json -Depth 8).Contains($secret))) 'Unexpected manifest metadata escaped source-hash validation.'
        $remote=Get-SwirlPackageEvidence ('\\unreachable.invalid\'+$secret+'\Swirl.exe')
        Assert (!$remote.available -and !(($remote|ConvertTo-Json).Contains($secret))) 'Remote package path was accessed or echoed.'
    } finally {
        $resolved=[IO.Path]::GetFullPath($temp)
        if ([IO.Path]::GetDirectoryName($resolved) -ne [IO.Path]::GetTempPath().TrimEnd('\','/')) { throw 'Unsafe fixture cleanup target.' }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
} else {
    Assert (!(Get-WindowsNativeProxyEvidence).available) 'Non-Windows environment claimed native Windows evidence.'
    Write-Output 'Windows native/API and package path tests: NOT_RUN (requires Windows).'
}
Write-Output "Codex network evidence: $script:checks assertions passed."
