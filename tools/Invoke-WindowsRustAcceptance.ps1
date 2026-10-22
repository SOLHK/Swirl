# Read-only network acceptance around an isolated, encrypted NodeStore copy.
# Never pass a production store or write the generated private runtime state to Git.
param(
    [Parameter(Mandatory=$true)][string]$SwirlExe,
    [Parameter(Mandatory=$true)][string]$EncryptedStore,
    [Parameter(Mandatory=$true)][string]$WorkDirectory,
    [string]$ExpectedSourceSha = '',
    [switch]$ObserveRustOutbound,
    [switch]$WriteProgress
)
$ErrorActionPreference = 'Stop'
$proxyPort = 17988
$result = [ordered]@{ status='BLOCKED'; identity=$null; requests=@(); diagnostics=@(); independence='独立性未证实'; pre=$null; post=$null; reason='' }
$started = $null

function Save-AcceptanceProgress {
    if (-not $WriteProgress -or -not $WorkDirectory -or -not (Test-Path -LiteralPath $WorkDirectory)) { return }
    $path=Join-Path $WorkDirectory 'acceptance-progress.json'
    $temp=Join-Path $WorkDirectory 'acceptance-progress.tmp'
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temp -Encoding utf8
    Move-Item -LiteralPath $temp -Destination $path -Force
}

function Get-ListenerPid {
    $rows = @(Get-NetTCPConnection -LocalPort $proxyPort -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -eq '127.0.0.1' -or $_.LocalAddress -eq '0.0.0.0' })
    $ids = @($rows | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($ids.Count -eq 0) { return 0 }
    if ($ids.Count -ne 1) { return -1 }
    return [int]$ids[0]
}
function Get-Snapshot {
    $proxy = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    $proxyText = @($proxy.ProxyEnable,$proxy.ProxyServer,$proxy.AutoConfigURL,$proxy.ProxyOverride) -join "`n"
    $bytes = [Text.Encoding]::UTF8.GetBytes($proxyText)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $proxyHash = [Convert]::ToHexString($sha.ComputeHash($bytes)) } finally { $sha.Dispose() }
    $mihomo = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '(?i)mihomo|clash' } |
        Select-Object -ExpandProperty ProcessId | Sort-Object)
    $proxyEnv = @(Get-ChildItem Env: | Where-Object { $_.Name -match '^(?i)(http|https|all|no)_proxy$' } |
        Select-Object -ExpandProperty Name | Sort-Object -Unique)
    $envText = @($proxyEnv | ForEach-Object { $_ + '=' + [Environment]::GetEnvironmentVariable($_,'Process') }) -join "`n"
    $envSha = [Security.Cryptography.SHA256]::Create()
    try { $envHash = [Convert]::ToHexString($envSha.ComputeHash([Text.Encoding]::UTF8.GetBytes($envText))) } finally { $envSha.Dispose() }
    $tunAdapters = @(Get-NetAdapter -ErrorAction Stop | Where-Object {
        ($_.Name + ' ' + $_.InterfaceDescription) -match '(?i)wintun|wireguard|\btun\b|\btap\b|mihomo|clash'
    } | Select-Object -ExpandProperty ifIndex)
    $tunRoutes = @(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction Stop |
        Where-Object { $tunAdapters -contains $_.InterfaceIndex })
    $drivers = @(Get-CimInstance Win32_SystemDriver | Where-Object {
        $_.State -eq 'Running' -and $_.Name -match '(?i)windivert|wintun|wireguard'
    } | Select-Object -ExpandProperty Name)
    return [ordered]@{
        listenerPid=(Get-ListenerPid); mihomoPids=$mihomo; proxySettingsSha256=$proxyHash
        proxyEnabled=[bool]$proxy.ProxyEnable; proxyEnvironmentNames=$proxyEnv; proxyEnvironmentSha256=$envHash
        tunAdapterCount=$tunAdapters.Count; tunDefaultRouteCount=$tunRoutes.Count
        transparentDriverCount=$drivers.Count
    }
}
function Wait-Ready([int]$testPid,[string]$statePath) {
    for ($i=0; $i -lt 80; $i++) {
        if (-not (Get-Process -Id $testPid -ErrorAction SilentlyContinue)) { throw 'Test Swirl exited before runtime readiness.' }
        if (Test-Path -LiteralPath $statePath) {
            try {
                $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
                if ($state.processAlive -and $state.apiHealthy) { return $state }
                if ($state.engineError -eq 'InvalidOptions') { throw 'Rust startup rejected options.' }
            } catch [System.ArgumentException] { }
        }
        Start-Sleep -Milliseconds 250
    }
    throw 'Rust runtime did not become healthy within 20 seconds.'
}

function Start-RustOutboundSampler([int]$testPid) {
    # Run in another runspace of this PowerShell process, so the synchronous curl
    # call does not prevent sampling. Only counts leave the sampler; endpoint
    # addresses and ports remain transient in the NetTCPIP cmdlet's result.
    $stop = [Threading.ManualResetEventSlim]::new($false)
    $ready = [Threading.ManualResetEventSlim]::new($false)
    $ps = [PowerShell]::Create()
    $sampler = @'
param([int]$targetProcessId, $stopSignal, $readySignal)
$samples = 0
$maximum = 0
try {
    $deadline = [DateTime]::UtcNow.AddSeconds(23)
    do {
        $active = @(Get-NetTCPConnection -ErrorAction Stop | Where-Object {
            if ($_.OwningProcess -ne $targetProcessId -or $_.State -eq 'Listen') { return $false }
            $address = $null
            if (-not [Net.IPAddress]::TryParse([string]$_.RemoteAddress, [ref]$address)) { return $false }
            return -not [Net.IPAddress]::IsLoopback($address) -and
                -not $address.Equals([Net.IPAddress]::Any) -and
                -not $address.Equals([Net.IPAddress]::IPv6Any)
        })
        $samples++
        $maximum = [Math]::Max($maximum, $active.Count)
        $readySignal.Set()
    } while (-not $stopSignal.Wait(100) -and [DateTime]::UtcNow -lt $deadline)
    [pscustomobject]@{ status='SAMPLED'; samples=$samples; maxConcurrent=$maximum }
} catch {
    $readySignal.Set()
    [pscustomobject]@{ status='UNAVAILABLE'; samples=$samples; maxConcurrent=$maximum }
}
'@
    try {
        $null = $ps.AddScript($sampler).AddArgument($testPid).AddArgument($stop).AddArgument($ready)
        $handle = $ps.BeginInvoke()
        if (-not $ready.Wait(3000)) {
            $stop.Set()
            return [pscustomobject]@{ powershell=$ps; handle=$handle; stop=$stop; ready=$ready; started=$false }
        }
        return [pscustomobject]@{ powershell=$ps; handle=$handle; stop=$stop; ready=$ready; started=$true }
    } catch {
        $stop.Dispose()
        $ready.Dispose()
        $ps.Dispose()
        return $null
    }
}

function Stop-RustOutboundSampler($sampler) {
    if (-not $sampler) {
        return [ordered]@{ status='UNAVAILABLE'; samples=0; maxConcurrent=0; observed=$false }
    }
    $observation = [ordered]@{ status='UNAVAILABLE'; samples=0; maxConcurrent=0; observed=$false }
    try {
        $sampler.stop.Set()
        if ($sampler.handle.AsyncWaitHandle.WaitOne(3000)) {
            $items = @($sampler.powershell.EndInvoke($sampler.handle))
            if ($sampler.started -and $items.Count -eq 1 -and $items[0].status -eq 'SAMPLED') {
                $observation.status = 'SAMPLED'
                $observation.samples = [int]$items[0].samples
                $observation.maxConcurrent = [int]$items[0].maxConcurrent
                $observation.observed = $observation.maxConcurrent -gt 0
            }
        } else {
            $null = $sampler.powershell.BeginStop($null, $null)
        }
    } catch {
        # Failure of optional observation must not mask the curl result.
    } finally {
        $sampler.powershell.Dispose()
        $sampler.stop.Dispose()
        $sampler.ready.Dispose()
    }
    return $observation
}

function Get-RustTrafficCounters {
    if (-not (Test-Path -LiteralPath $statePath)) { return $null }
    try {
        $state=Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        if ($state.actualEngineType -ne 'rust' -or
            $null -eq $state.rustUploadTotal -or $null -eq $state.rustDownloadTotal -or
            $null -eq $state.rustAccepted -or $null -eq $state.rustFailed) { return $null }
        return [pscustomobject]@{
            upload=[int64]$state.rustUploadTotal
            download=[int64]$state.rustDownloadTotal
            accepted=[int64]$state.rustAccepted
            failed=[int64]$state.rustFailed
            errorStage=if ([string]$state.rustLastErrorStage -match '^[A-Za-z0-9_]{0,64}$') { [string]$state.rustLastErrorStage } else { '' }
        }
    } catch { return $null }
}

function Wait-StableRustTrafficCounters {
    $deadline=[DateTime]::UtcNow.AddMilliseconds(2500)
    $latest=Get-RustTrafficCounters
    if (-not $latest) { return $null }
    $stableSince=[DateTime]::UtcNow
    do {
        Start-Sleep -Milliseconds 150
        $next=Get-RustTrafficCounters
        if (-not $next) { return $null }
        if ($next.upload -ne $latest.upload -or $next.download -ne $latest.download -or
            $next.accepted -ne $latest.accepted -or $next.failed -ne $latest.failed) {
            $latest=$next
            $stableSince=[DateTime]::UtcNow
        } elseif (([DateTime]::UtcNow-$stableSince).TotalMilliseconds -ge 700) {
            return $next
        }
    } while ([DateTime]::UtcNow -lt $deadline)
    return $null
}

function Wait-RustTrafficCounters($before) {
    if (-not $before) { return $null }
    $deadline=[DateTime]::UtcNow.AddMilliseconds(3000)
    $latest=$null
    do {
        $latest=Get-RustTrafficCounters
        if ($latest -and $latest.accepted -gt $before.accepted -and
            $latest.upload -gt $before.upload -and $latest.download -gt $before.download) { break }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    return $latest
}

function Invoke-Probe([string]$name,[string]$url,[string]$scheme,[bool]$tunnel,[int]$testPid,[int]$expectedHttp,[string]$expectedBody,[int]$timeoutSeconds=20) {
    if ((Get-ListenerPid) -ne $testPid) { throw '17988 listener ownership changed during request.' }
    $bodyPath = Join-Path $WorkDirectory ($name + '.body')
    $proxy = if ($scheme -eq 'socks5h') { 'socks5h://127.0.0.1:17988' } else { 'http://127.0.0.1:17988' }
    # curl --write-out fields are cumulative seconds and body byte counts;
    # see https://curl.se/docs/manpage.html#-w for the primary definitions.
    $args = @('--disable','--silent','--max-time',"$timeoutSeconds",'--proxy',$proxy,
        '--noproxy=','--output',$bodyPath,'--write-out',
        '{"http_code":%{http_code},"http_connect":%{http_connect},"time_connect":%{time_connect},"time_appconnect":%{time_appconnect},"time_pretransfer":%{time_pretransfer},"time_starttransfer":%{time_starttransfer},"time_total":%{time_total},"size_request":%{size_request},"size_upload":%{size_upload},"size_download":%{size_download},"proxy_used":%{proxy_used},"ssl_verify_result":%{ssl_verify_result}}')
    if ($tunnel) { $args += '--proxytunnel' }
    $args += $url
    $saved = @{}
    $sampler = $null
    $trafficBefore = if ($ObserveRustOutbound) { Wait-StableRustTrafficCounters } else { $null }
    $trafficAfter = $null
    # Windows environment names are case-insensitive; enumerate each real key
    # once so restoring it cannot be overwritten by its lower-case alias.
    try {
        foreach ($key in @(Get-ChildItem Env: | Where-Object { $_.Name -match '^(?i)(http|https|all|no)_proxy$' } | Select-Object -ExpandProperty Name)) {
            $saved[$key] = [Environment]::GetEnvironmentVariable($key,'Process')
            [Environment]::SetEnvironmentVariable($key,$null,'Process')
        }
        $sampler = if ($ObserveRustOutbound) { Start-RustOutboundSampler $testPid } else { $null }
        $wire = & curl.exe @args 2>$null
        $code = $LASTEXITCODE
    } finally {
        try {
            $outbound = if ($ObserveRustOutbound) { Stop-RustOutboundSampler $sampler } else { [ordered]@{ status='NOT_TESTED'; samples=0; maxConcurrent=0; observed=$false } }
            if ($ObserveRustOutbound) { $trafficAfter = Wait-RustTrafficCounters $trafficBefore }
        } finally {
            foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key,$saved[$key],'Process') }
        }
    }
    $data = try { $wire | ConvertFrom-Json } catch { $null }
    $bodyValid = $false
    if ($null -ne $data -and (Test-Path -LiteralPath $bodyPath)) {
        $bytes = [IO.File]::ReadAllBytes($bodyPath)
        if ($expectedBody.Length -eq 0) { $bodyValid = $bytes.Length -eq 0 }
        else { $bodyValid = [Text.Encoding]::UTF8.GetString($bytes).Trim() -ceq $expectedBody }
    }
    Remove-Item -LiteralPath $bodyPath -ErrorAction SilentlyContinue
    $uploadDelta = if ($trafficBefore -and $trafficAfter -and $trafficAfter.upload -ge $trafficBefore.upload) { $trafficAfter.upload-$trafficBefore.upload } else { $null }
    $downloadDelta = if ($trafficBefore -and $trafficAfter -and $trafficAfter.download -ge $trafficBefore.download) { $trafficAfter.download-$trafficBefore.download } else { $null }
    $acceptedDelta = if ($trafficBefore -and $trafficAfter -and $trafficAfter.accepted -ge $trafficBefore.accepted) { $trafficAfter.accepted-$trafficBefore.accepted } else { $null }
    $failedDelta = if ($trafficBefore -and $trafficAfter -and $trafficAfter.failed -ge $trafficBefore.failed) { $trafficAfter.failed-$trafficBefore.failed } else { $null }
    return [ordered]@{
        name=$name; proxy_used=if ($data) { [int]$data.proxy_used } else { 0 }
        listenerPid=(Get-ListenerPid); exitCode=$code
        httpStatus=if ($data) { [int]$data.http_code } else { 0 }
        httpConnectStatus=if ($data) { [int]$data.http_connect } else { $null }
        tcpConnectMs=if ($data) { [int][Math]::Round(1000*$data.time_connect) } else { $null }
        appConnectMs=if ($data) { [int][Math]::Round(1000*$data.time_appconnect) } else { $null }
        preTransferMs=if ($data) { [int][Math]::Round(1000*$data.time_pretransfer) } else { $null }
        firstByteMs=if ($data) { [int][Math]::Round(1000*$data.time_starttransfer) } else { $null }
        durationMs=if ($data) { [int][Math]::Round(1000*$data.time_total) } else { 0 }
        requestBytes=if ($data) { [int64][Math]::Round($data.size_request) } else { $null }
        uploadBodyBytes=if ($data) { [int64][Math]::Round($data.size_upload) } else { $null }
        downloadBodyBytes=if ($data) { [int64][Math]::Round($data.size_download) } else { $null }
        rustOutboundObservation=$outbound
        rustUploadDelta=$uploadDelta; rustDownloadDelta=$downloadDelta
        rustAcceptedDelta=$acceptedDelta; rustFailedDelta=$failedDelta
        rustLastErrorStage=if ($failedDelta -gt 0 -and $trafficAfter) { $trafficAfter.errorStage } else { $null }
        rustTransferObserved=($acceptedDelta -eq 1 -and $null -ne $uploadDelta -and $null -ne $downloadDelta -and $uploadDelta -gt 0 -and $downloadDelta -gt 0)
        bodyValid=$bodyValid
        tlsCertificateVerified=if ($url.StartsWith('https://')) { [bool]($data -and [int]$data.ssl_verify_result -eq 0) } else { $null }
        status=if ($code -eq 0 -and $data -and [int]$data.proxy_used -eq 1 -and (Get-ListenerPid) -eq $testPid -and [int]$data.http_code -eq $expectedHttp -and $bodyValid -and (!$url.StartsWith('https://') -or [int]$data.ssl_verify_result -eq 0)) { 'PASS' } else { 'FAIL' }
    }
}

try {
    $SwirlExe = (Resolve-Path -LiteralPath $SwirlExe).Path
    $EncryptedStore = (Resolve-Path -LiteralPath $EncryptedStore).Path
    if (-not (Test-Path -LiteralPath $WorkDirectory)) { New-Item -ItemType Directory -Path $WorkDirectory | Out-Null }
    $WorkDirectory = (Resolve-Path -LiteralPath $WorkDirectory).Path
    $result.pre = Get-Snapshot
    if ($result.pre.listenerPid -ne 0) { throw '17988 is already owned; no test process was started.' }
    $expectedHash = (Get-FileHash -LiteralPath $SwirlExe -Algorithm SHA256).Hash
    $commandPath = Join-Path $WorkDirectory 'runtime-command.json'
    $statePath = Join-Path $WorkDirectory 'runtime-state.json'
    Remove-Item -LiteralPath $commandPath,$statePath -ErrorAction SilentlyContinue
    # The test Swirl must not inherit proxy environment variables pointing to
    # Mihomo. This changes only this PowerShell process for Start-Process and
    # restores its exact values before the child becomes ready.
    $savedStartupProxyEnv = @{}
    try {
        foreach ($key in @(Get-ChildItem Env: | Where-Object { $_.Name -match '^(?i)(http|https|all|no)_proxy$' } | Select-Object -ExpandProperty Name)) {
            $savedStartupProxyEnv[$key] = [Environment]::GetEnvironmentVariable($key,'Process')
            [Environment]::SetEnvironmentVariable($key,$null,'Process')
        }
        $started = Start-Process -FilePath $SwirlExe -ArgumentList @("--runtime-store=`"$EncryptedStore`"","--runtime-commands=`"$commandPath`"","--runtime-state=`"$statePath`"") -PassThru -WindowStyle Hidden
    } finally {
        foreach ($key in $savedStartupProxyEnv.Keys) { [Environment]::SetEnvironmentVariable($key,$savedStartupProxyEnv[$key],'Process') }
    }
    $state = Wait-Ready $started.Id $statePath
    $identity = Get-CimInstance Win32_Process -Filter "ProcessId=$($started.Id)"
    if (-not $identity.ExecutablePath -or $identity.ExecutablePath.Replace('/','\') -ne $SwirlExe.Replace('/','\') -or (Get-FileHash -LiteralPath $identity.ExecutablePath -Algorithm SHA256).Hash -ne $expectedHash) { throw 'Started process executable identity mismatch.' }
    if ($state.actualEngineType -ne 'rust' -or [int]$state.engineProcessId -ne $started.Id -or $state.routingMode -ne 'global') { throw 'In-process Rust engine identity or global route mismatch.' }
    if ($state.executablePath.Replace('/','\') -ne $SwirlExe.Replace('/','\') -or $state.executableSha256.ToUpperInvariant() -ne $expectedHash) { throw 'Runtime binary path/hash mismatch.' }
    if ($ExpectedSourceSha -and $state.sourceSha -ne $ExpectedSourceSha) { throw 'Runtime source SHA mismatch.' }
    $modules = @(Get-Process -Id $started.Id -Module -ErrorAction Stop | Where-Object { $_.ModuleName -ieq 'swirl_api.dll' })
    if ($modules.Count -ne 1 -or $modules[0].FileName -ne (Join-Path (Split-Path $SwirlExe) 'swirl_api.dll')) { throw 'swirl_api.dll is not loaded inside test Swirl.' }
    if ((Get-ListenerPid) -ne $started.Id) { throw '17988 does not belong to test Swirl.' }
    $result.identity = [ordered]@{
        sourceSha=$state.sourceSha; swirlExePath=$SwirlExe; swirlExeSha256=$expectedHash
        actualEngineType=$state.actualEngineType; enginePid=$started.Id
        rustDllPath=$modules[0].FileName
        rustDllSha256=(Get-FileHash -LiteralPath $modules[0].FileName -Algorithm SHA256).Hash
    }
    Save-AcceptanceProgress
    $probes = @(
        @('http_http','http://www.msftconnecttest.com/connecttest.txt','http',$false,200,'Microsoft Connect Test'),
        @('http_https','https://www.gstatic.com/generate_204','http',$false,204,''),
        @('connect_http','http://www.msftconnecttest.com/connecttest.txt','http',$true,200,'Microsoft Connect Test'),
        @('connect_https','https://www.gstatic.com/generate_204','http',$true,204,''),
        @('socks5_http','http://www.msftconnecttest.com/connecttest.txt','socks5h',$false,200,'Microsoft Connect Test'),
        @('socks5_https','https://www.gstatic.com/generate_204','socks5h',$false,204,'')
    )
    foreach ($probe in $probes) {
        $result.requests += Invoke-Probe $probe[0] $probe[1] $probe[2] $probe[3] $started.Id $probe[4] $probe[5]
        Save-AcceptanceProgress
    }
    $result.status = if (@($result.requests | Where-Object status -ne 'PASS').Count -eq 0) { 'PASS' } else { 'FAIL' }
    # A second public HTTP destination helps identify target-dependent failures.
    # These rows are diagnostics; they never change the original six-request result.
    foreach ($failed in @($result.requests | Where-Object { $_.status -ne 'PASS' -and $_.name -match '_http$' })) {
        $scheme = if ($failed.name -eq 'socks5_http') { 'socks5h' } else { 'http' }
        $tunnel = $failed.name -eq 'connect_http'
        $result.diagnostics += Invoke-Probe ('alternate_'+$failed.name) 'http://www.gstatic.com/generate_204' $scheme $tunnel $started.Id 204 '' 8
        Save-AcceptanceProgress
    }
    if ($result.pre.mihomoPids.Count -gt 0 -or $result.pre.tunAdapterCount -gt 0 -or $result.pre.tunDefaultRouteCount -gt 0 -or $result.pre.transparentDriverCount -gt 0) {
        $result.independence = '独立性未证实'
    } else { $result.independence = '未发现已知转发迹象；仍需独立出口证据' }
} catch {
    $result.reason = $_.Exception.Message
} finally {
    if ($started -and -not $started.HasExited) {
        # Only the PID returned by this invocation may receive a stop command.
        if (Test-Path -LiteralPath $commandPath) { Remove-Item -LiteralPath $commandPath -ErrorAction SilentlyContinue }
        '{"action":"stop"}' | Set-Content -LiteralPath $commandPath -Encoding ascii
        if (-not $started.WaitForExit(10000)) {
            Stop-Process -InputObject $started -Force -ErrorAction SilentlyContinue
            $result.reason += ' Test process required forced exit after its own stop command.'; $result.status='FAIL'
            if (-not $started.WaitForExit(5000)) {
                $result.reason += ' Test process remains alive; private runtime state may be rewritten until that PID exits.'
            }
        }
    }
    if ($result.pre) {
        try {
            $result.post = Get-Snapshot
            $expectedListener = if ($started) { 0 } else { $result.pre.listenerPid }
            if ($result.post.listenerPid -ne $expectedListener -or ($started -and -not $started.HasExited) -or
                $result.post.proxySettingsSha256 -ne $result.pre.proxySettingsSha256 -or
                $result.post.proxyEnvironmentSha256 -ne $result.pre.proxyEnvironmentSha256 -or
                $result.post.tunAdapterCount -ne $result.pre.tunAdapterCount -or
                $result.post.tunDefaultRouteCount -ne $result.pre.tunDefaultRouteCount -or
                $result.post.transparentDriverCount -ne $result.pre.transparentDriverCount -or
                (@($result.post.mihomoPids) -join ',') -ne (@($result.pre.mihomoPids) -join ',')) {
                $result.status='FAIL'; $result.reason += ' Post-check differs: listener, test PID, Mihomo PIDs, proxy settings, proxy environment, or transparent-route indicators.'
            }
        } catch {
            $result.status='FAIL'; $result.reason += ' Post-check could not be completed.'
        }
    }
    if ($commandPath) {
        Remove-Item -LiteralPath $commandPath,$statePath -ErrorAction SilentlyContinue
        if ($started -and -not $started.HasExited) {
            $result.status='FAIL'
            $result.reason += ' Confirm and stop only the test Swirl PID before cleaning its private directory.'
        }
    }
    Save-AcceptanceProgress
    $result | ConvertTo-Json -Depth 6
    if ($result.status -eq 'FAIL') { exit 1 }
    if ($result.status -eq 'BLOCKED') { exit 2 }
}
