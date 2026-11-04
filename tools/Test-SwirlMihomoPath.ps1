# Observe real HTTPS traffic through the active Swirl listener without stopping
# Mihomo or changing WinINET, WinHTTP, routes, DNS, TUN, or firewall settings.
param(
    [ValidateRange(1,65535)][int]$Port = 7898,
    [ValidateRange(3,12)][int]$RequestCount = 8
)

$ErrorActionPreference = 'Stop'
$result = [ordered]@{
    schemaVersion = 1
    status = 'INCONCLUSIVE'
    reason = ''
    swirlPid = $null
    sourceSha = $null
    mihomoProcessCount = 0
    mihomoListenerCount = 0
    requestsPassed = 0
    requestsAttempted = 0
    testTarget = 'https://www.gstatic.com/generate_204'
    observation = $null
    knownTransparentIndicators = 'UNKNOWN'
    systemProxyUnchanged = $null
    mihomoPidsUnchanged = $null
    swirlListenerUnchanged = $null
    publicEgressIndependence = 'UNPROVEN'
    changedNetworkSettings = $false
}

function Get-ListenerPid([int]$LocalPort) {
    $rows = @(Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -in @('127.0.0.1','0.0.0.0') })
    $ids = @($rows | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($ids.Count -ne 1) { throw "Expected one IPv4 listener on port $LocalPort; found $($ids.Count)." }
    return [int]$ids[0]
}

function Get-SystemProxyFingerprint {
    $p = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    $value = @($p.ProxyEnable,$p.ProxyServer,$p.AutoConfigURL,$p.ProxyOverride) -join "`n"
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [Convert]::ToBase64String($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($value))) }
    finally { $sha.Dispose() }
}

function Get-MihomoPids {
    return @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '(?i)mihomo|clash' } |
        Select-Object -ExpandProperty ProcessId | Sort-Object -Unique)
}

function Get-TransparentIndicators {
    try {
        $adapters = @(Get-NetAdapter -ErrorAction Stop | Where-Object {
            $_.Status -eq 'Up' -and ($_.Name + ' ' + $_.InterfaceDescription) -match '(?i)wintun|wireguard|\btun\b|\btap\b|mihomo|clash'
        })
        $indices = @($adapters | Select-Object -ExpandProperty ifIndex)
        $routes = @(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction Stop |
            Where-Object { $indices -contains $_.InterfaceIndex })
        $drivers = @(Get-CimInstance Win32_SystemDriver -ErrorAction Stop | Where-Object {
            $_.State -eq 'Running' -and $_.Name -match '(?i)windivert|wintun|wireguard'
        })
        if ($adapters.Count -gt 0 -or $routes.Count -gt 0 -or $drivers.Count -gt 0) { return 'PRESENT' }
        return 'NONE_FOUND'
    } catch { return 'UNKNOWN' }
}

function Start-ConnectionSampler([int]$SwirlPid,[int]$ProxyPort,[int[]]$MihomoPids,[int[]]$MihomoPorts,[string[]]$Baseline) {
    $stop = [Threading.ManualResetEventSlim]::new($false)
    $ready = [Threading.ManualResetEventSlim]::new($false)
    $ps = [PowerShell]::Create()
    $code = @'
param([int]$swirlPid,[int]$proxyPort,[int[]]$mihomoPids,[int[]]$mihomoPorts,[string[]]$baseline,$stop,$ready)
$samples = 0
$newSwirl = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$newMihomo = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$swirlToMihomo = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$initial = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($item in $baseline) { [void]$initial.Add($item) }
$swirlNonLoopbackSamples = 0
$mihomoNonLoopbackSamples = 0
try {
    $deadline = [DateTime]::UtcNow.AddSeconds(240)
    do {
        $connections = @(Get-NetTCPConnection -ErrorAction Stop)
        foreach ($c in $connections) {
            $owner = [int]$c.OwningProcess
            if ($owner -ne $swirlPid -and $mihomoPids -notcontains $owner) { continue }
            if ($c.State -eq 'Listen' -or $c.State -eq 'Bound' -or
                ($owner -eq $swirlPid -and [int]$c.LocalPort -eq $proxyPort)) { continue }
            $ip = $null
            if (-not [Net.IPAddress]::TryParse([string]$c.RemoteAddress,[ref]$ip)) { continue }
            if ($ip.IsIPv4MappedToIPv6) { $ip = $ip.MapToIPv4() }
            if ($ip.Equals([Net.IPAddress]::Any) -or $ip.Equals([Net.IPAddress]::IPv6Any)) { continue }
            $key = @($owner,$c.LocalAddress,$c.LocalPort,$c.RemoteAddress,$c.RemotePort) -join '|'
            if ($initial.Contains($key)) { continue }
            if ($owner -eq $swirlPid) {
                if ([Net.IPAddress]::IsLoopback($ip)) {
                    if ($mihomoPorts -contains [int]$c.RemotePort) { [void]$swirlToMihomo.Add($key) }
                } else {
                    [void]$newSwirl.Add($key)
                    $swirlNonLoopbackSamples++
                }
            } elseif (-not [Net.IPAddress]::IsLoopback($ip)) {
                [void]$newMihomo.Add($key)
                $mihomoNonLoopbackSamples++
            }
        }
        $samples++
        $ready.Set()
    } while (-not $stop.Wait(80) -and [DateTime]::UtcNow -lt $deadline)
    [pscustomobject]@{
        status='SAMPLED'; samples=$samples
        newSwirlNonLoopbackConnections=$newSwirl.Count
        swirlNonLoopbackSamples=$swirlNonLoopbackSamples
        swirlToMihomoLocalConnections=$swirlToMihomo.Count
        newMihomoNonLoopbackConnections=$newMihomo.Count
        mihomoNonLoopbackSamples=$mihomoNonLoopbackSamples
    }
} catch {
    $ready.Set()
    [pscustomobject]@{ status='UNAVAILABLE'; samples=$samples
        newSwirlNonLoopbackConnections=0; swirlNonLoopbackSamples=0
        swirlToMihomoLocalConnections=0; newMihomoNonLoopbackConnections=0
        mihomoNonLoopbackSamples=0 }
}
'@
    try {
        $null = $ps.AddScript($code).AddArgument($SwirlPid).AddArgument($ProxyPort).AddArgument($MihomoPids).AddArgument($MihomoPorts).AddArgument($Baseline).AddArgument($stop).AddArgument($ready)
        $handle = $ps.BeginInvoke()
        $started = $ready.Wait(5000)
        return [pscustomobject]@{ powershell=$ps; handle=$handle; stop=$stop; ready=$ready; started=$started }
    } catch {
        $ps.Dispose(); $stop.Dispose(); $ready.Dispose()
        return $null
    }
}

function Stop-ConnectionSampler($Sampler) {
    $unavailable = [ordered]@{ status='UNAVAILABLE'; samples=0
        newSwirlNonLoopbackConnections=0; swirlNonLoopbackSamples=0
        swirlToMihomoLocalConnections=0; newMihomoNonLoopbackConnections=0
        mihomoNonLoopbackSamples=0 }
    if (-not $Sampler) { return $unavailable }
    try {
        $Sampler.stop.Set()
        if ($Sampler.handle.AsyncWaitHandle.WaitOne(5000)) {
            $items = @($Sampler.powershell.EndInvoke($Sampler.handle))
            if ($Sampler.started -and $items.Count -eq 1) { return $items[0] }
        } else { $null = $Sampler.powershell.BeginStop($null,$null) }
        return $unavailable
    } catch { return $unavailable }
    finally {
        $Sampler.powershell.Dispose()
        $Sampler.stop.Dispose()
        $Sampler.ready.Dispose()
    }
}

$sampler = $null
try {
    $offlineScript = Join-Path $PSScriptRoot 'Test-SwirlCoreOffline.ps1'
    if (-not (Test-Path -LiteralPath $offlineScript -PathType Leaf)) { throw 'Offline identity checker is missing beside this script.' }
    $identityText = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $offlineScript -Port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Offline Swirl Rust identity check did not pass.' }
    $identity = $identityText | ConvertFrom-Json
    if ($identity.status -ne 'PASS' -or $identity.systemProxyPointsToListener -ne 'YES') {
        throw 'The current system proxy does not point to a verified Swirl Rust listener.'
    }
    $result.swirlPid = [int]$identity.listenerPid
    $result.sourceSha = [string]$identity.sourceSha
    $swirlStartTicks = (Get-Process -Id $result.swirlPid -ErrorAction Stop).StartTime.ToUniversalTime().Ticks
    $preProxy = Get-SystemProxyFingerprint
    $mihomoPids = @(Get-MihomoPids)
    $result.mihomoProcessCount = $mihomoPids.Count
    $mihomoPorts = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object {
        $mihomoPids -contains [int]$_.OwningProcess
    } | Select-Object -ExpandProperty LocalPort -Unique)
    $result.mihomoListenerCount = $mihomoPorts.Count
    $result.knownTransparentIndicators = Get-TransparentIndicators
    $baseline = @(Get-NetTCPConnection -ErrorAction Stop | Where-Object {
        [int]$_.OwningProcess -eq $result.swirlPid -or $mihomoPids -contains [int]$_.OwningProcess
    } | ForEach-Object {
        @($_.OwningProcess,$_.LocalAddress,$_.LocalPort,$_.RemoteAddress,$_.RemotePort) -join '|'
    })
    $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
    if (-not (Test-Path -LiteralPath $curl -PathType Leaf)) { throw 'Windows curl.exe is unavailable.' }

    $sampler = Start-ConnectionSampler $result.swirlPid $Port $mihomoPids $mihomoPorts $baseline
    $args = @('--disable','--silent','--show-error','--http1.1','--max-time','20',
        '--connect-timeout','8','--proxy',"http://127.0.0.1:$Port",'--noproxy=',
        '--output','NUL','--write-out',
        '{"proxy_used":%{proxy_used},"http_code":%{http_code},"ssl_verify_result":%{ssl_verify_result}}',
        'https://www.gstatic.com/generate_204')
    for ($i=0; $i -lt $RequestCount; $i++) {
        if ((Get-ListenerPid $Port) -ne $result.swirlPid) { throw 'Swirl listener PID changed during the test.' }
        $wire = & $curl @args 2>$null
        $exitCode = $LASTEXITCODE
        $result.requestsAttempted++
        $data = try { $wire | ConvertFrom-Json } catch { $null }
        if ($exitCode -eq 0 -and $data -and [int]$data.proxy_used -eq 1 -and
            [int]$data.http_code -eq 204 -and [int]$data.ssl_verify_result -eq 0) {
            $result.requestsPassed++
        }
    }
    $result.observation = Stop-ConnectionSampler $sampler
    $sampler = $null
    $result.systemProxyUnchanged = ((Get-SystemProxyFingerprint) -eq $preProxy)
    $result.mihomoPidsUnchanged = ((@(Get-MihomoPids) -join ',') -ceq ($mihomoPids -join ','))
    $result.swirlListenerUnchanged = ((Get-ListenerPid $Port) -eq $result.swirlPid -and
        (Get-Process -Id $result.swirlPid -ErrorAction Stop).StartTime.ToUniversalTime().Ticks -eq $swirlStartTicks)

    if ($result.observation.status -ne 'SAMPLED') { throw 'Windows TCP connection sampling was unavailable.' }
    if ($result.observation.swirlToMihomoLocalConnections -gt 0) {
        $result.status = 'MIHOMO_PATH_OBSERVED'
        $result.reason = 'A new Swirl TCP connection to a Mihomo-owned local listening port was observed during the test.'
    } elseif ($result.requestsPassed -ne $RequestCount) {
        $result.reason = 'One or more verified HTTPS requests through Swirl failed.'
    } elseif ($result.observation.newSwirlNonLoopbackConnections -lt 1) {
        $result.reason = 'No new non-loopback TCP connection owned by Swirl was captured.'
    } elseif ($result.knownTransparentIndicators -ne 'NONE_FOUND') {
        $result.reason = 'A known TUN/transparent-route indicator exists or could not be inspected.'
    } elseif (-not ($result.systemProxyUnchanged -and $result.mihomoPidsUnchanged -and $result.swirlListenerUnchanged)) {
        $result.reason = 'Listener, Mihomo process IDs, or system proxy changed during the observation.'
    } else {
        $result.status = 'SWIRL_NATIVE_EGRESS_OBSERVED'
        $result.reason = 'Verified HTTPS responses and new Swirl-owned non-loopback TCP sockets; no Swirl-to-Mihomo local chain was observed.'
    }
} catch {
    if ($result.status -eq 'INCONCLUSIVE') { $result.reason = $_.Exception.Message }
} finally {
    if ($sampler) { $result.observation = Stop-ConnectionSampler $sampler }
}

$result | ConvertTo-Json -Depth 4
if ($result.status -eq 'SWIRL_NATIVE_EGRESS_OBSERVED') { exit 0 }
if ($result.status -eq 'MIHOMO_PATH_OBSERVED') { exit 1 }
exit 2
