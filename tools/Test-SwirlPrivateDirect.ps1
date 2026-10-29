# Bounded loopback target verification for Rust native private-IP DIRECT rules.
# No public target, node credentials, or user network settings are involved.
param(
    [ValidateRange(1,65535)][int]$ProxyPort = 7898,
    [switch]$SelfTest,
    [string]$ExpectedSourceSha = ''
)
$ErrorActionPreference = 'Stop'
$result = [ordered]@{ status='NOT_TESTED'; routingMode='UNKNOWN'; ipv4='NOT_TESTED'; ipv6='NOT_TESTED'; reason=''; sourceSha=''; productIdentityFormat=''; routeNameVerification='NOT_TESTED'; changedNetworkSettings=$false }

function Invoke-LoopbackFixture([Net.IPAddress]$Address,[string]$Family,[bool]$UseProxy) {
    $token = [guid]::NewGuid().ToString('N')
    $listener = [Net.Sockets.TcpListener]::new($Address,0)
    $listener.Start()
    $port = ([Net.IPEndPoint]$listener.LocalEndpoint).Port
    $worker = [PowerShell]::Create()
    $code = @'
param($listener,[string]$token)
try {
    $client = $listener.AcceptTcpClient()
    try {
        $client.ReceiveTimeout = 8000
        $client.SendTimeout = 8000
        $stream = $client.GetStream()
        $header = [Collections.Generic.List[byte]]::new()
        while ($header.Count -lt 4096) {
            $b = $stream.ReadByte()
            if ($b -lt 0) { break }
            $header.Add([byte]$b)
            $n = $header.Count
            if ($n -ge 4 -and $header[$n-4] -eq 13 -and $header[$n-3] -eq 10 -and
                $header[$n-2] -eq 13 -and $header[$n-1] -eq 10) { break }
        }
        $request = [Text.Encoding]::ASCII.GetString($header.ToArray())
        $matched = $request.StartsWith("GET /$token HTTP/1.1`r`n",[StringComparison]::Ordinal)
        $body = if ($matched) { "SWIRL_FIXTURE_$token" } else { 'BAD_REQUEST' }
        $bytes = [Text.Encoding]::ASCII.GetBytes($body)
        $status = if ($matched) { '200 OK' } else { '400 Bad Request' }
        $head = [Text.Encoding]::ASCII.GetBytes("HTTP/1.1 $status`r`nContent-Length: $($bytes.Length)`r`nConnection: close`r`n`r`n")
        $stream.Write($head,0,$head.Length)
        $stream.Write($bytes,0,$bytes.Length)
        [pscustomobject]@{ received=$matched }
    } finally { $client.Dispose() }
} catch { [pscustomobject]@{ received=$false } }
'@
    $null = $worker.AddScript($code).AddArgument($listener).AddArgument($token)
    $handle = $worker.BeginInvoke()
    try {
        $hostText = if ($Family -eq 'IPv6') { '[::1]' } else { '127.0.0.1' }
        $url = "http://${hostText}:$port/$token"
        $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
        $args = @('--disable','--silent','--show-error','--http1.1','--max-time','8',
            '--connect-timeout','3','--proxy=','--noproxy=*','--output','-',
            '--write-out','SWIRL_META:%{proxy_used}:%{http_code}', $url)
        if ($UseProxy) { $args = @('--disable','--silent','--show-error','--http1.1','--max-time','8',
            '--connect-timeout','3','--proxy',"http://127.0.0.1:$ProxyPort",'--noproxy=',
            '--output','-','--write-out','SWIRL_META:%{proxy_used}:%{http_code}', $url) }
        $wire = (& $curl @args 2>$null) -join ''
        $curlExit = $LASTEXITCODE
        $received = $false
        if ($handle.AsyncWaitHandle.WaitOne(2000)) {
            $rows = @($worker.EndInvoke($handle))
            $received = $rows.Count -eq 1 -and $rows[0].received
        }
        $expectedProxy = if ($UseProxy) { '1' } else { '0' }
        return [pscustomobject]@{
            family=$Family
            status=if ($curlExit -eq 0 -and $received -and
                $wire -ceq "SWIRL_FIXTURE_${token}SWIRL_META:${expectedProxy}:200") { 'PASS' } else { 'FAIL' }
            localTargetReceived=[bool]$received
        }
    } finally {
        $listener.Stop()
        if (-not $handle.IsCompleted) { $null = $worker.BeginStop($null,$null) }
        $worker.Dispose()
    }
}

try {
    if ($SelfTest) { $result.routingMode='SELF_TEST_ONLY' }
    else {
        $powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'Test-SwirlCoreOffline.ps1'),'-Port',[string]$ProxyPort)
        if ($ExpectedSourceSha) { $arguments += @('-ExpectedSourceSha',$ExpectedSourceSha) }
        $wire = & $powershell @arguments
        if ($LASTEXITCODE -ne 0) { throw 'Offline Rust listener identity check did not pass; no proxy request was sent.' }
        $identity = ($wire -join "`n") | ConvertFrom-Json
        if ($identity.status -ne 'PASS') { throw 'Rust listener identity was not verified.' }
        $result.sourceSha = [string]$identity.sourceSha
        $result.productIdentityFormat = [string]$identity.productIdentityFormat
        $settings = Get-ItemProperty 'HKCU:\Software\SOLHK\Swirl\Proxy' -ErrorAction Stop
        $result.routingMode = [string]$settings.routingMode
        if ($result.routingMode -ne 'rule') {
            $result.status='RULE_MODE_OFF'; $result.reason='Saved Swirl routing mode is not rule.'
            $result | ConvertTo-Json -Depth 3
            exit 2
        }
    }
    $v4 = Invoke-LoopbackFixture ([Net.IPAddress]::Loopback) 'IPv4' (-not $SelfTest)
    $result.ipv4 = $v4.status
    try {
        $v6 = Invoke-LoopbackFixture ([Net.IPAddress]::IPv6Loopback) 'IPv6' (-not $SelfTest)
        $result.ipv6 = $v6.status
    } catch [Net.Sockets.SocketException] { $result.ipv6='NOT_AVAILABLE' }
    $result.status = if ($result.ipv4 -eq 'PASS' -and $result.ipv6 -eq 'PASS') { 'PASS' } else { 'FAIL' }
    $result.reason = if ($SelfTest) { 'Local fixture only; no Swirl rule was tested.' }
        else { 'Local IPv4/IPv6 targets received unique requests through the listener; saved mode alone does not prove the active Rust route name.' }
} catch { $result.status='INCONCLUSIVE'; $result.reason=$_.Exception.Message }
$result | ConvertTo-Json -Depth 3
if ($result.status -eq 'PASS') { exit 0 }
if ($result.status -eq 'RULE_MODE_OFF' -or $result.status -eq 'INCONCLUSIVE') { exit 2 }
exit 1
