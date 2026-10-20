# Read-only network acceptance around an isolated, encrypted NodeStore copy.
# Never pass a production store or write the generated private runtime state to Git.
param(
    [Parameter(Mandatory=$true)][string]$SwirlExe,
    [Parameter(Mandatory=$true)][string]$EncryptedStore,
    [Parameter(Mandatory=$true)][string]$WorkDirectory,
    [string]$ExpectedSourceSha = ''
)
$ErrorActionPreference = 'Stop'
$proxyPort = 17988
$result = [ordered]@{ status='BLOCKED'; identity=$null; requests=@(); independence='独立性未证实'; pre=$null; post=$null; reason='' }
$started = $null

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
function Invoke-Probe([string]$name,[string]$url,[string]$scheme,[bool]$tunnel,[int]$testPid) {
    if ((Get-ListenerPid) -ne $testPid) { throw '17988 listener ownership changed during request.' }
    $bodyPath = Join-Path $WorkDirectory ($name + '.body')
    $proxy = if ($scheme -eq 'socks5h') { 'socks5h://127.0.0.1:17988' } else { 'http://127.0.0.1:17988' }
    $args = @('--disable','--silent','--max-time','20','--proxy',$proxy,
        '--noproxy=','--output',$bodyPath,'--write-out',
        '{"http_code":%{http_code},"time_total":%{time_total},"proxy_used":%{proxy_used},"ssl_verify_result":%{ssl_verify_result}}')
    if ($tunnel) { $args += '--proxytunnel' }
    $args += $url
    $saved = @{}
    # Windows environment names are case-insensitive; enumerate each real key
    # once so restoring it cannot be overwritten by its lower-case alias.
    foreach ($key in @(Get-ChildItem Env: | Where-Object { $_.Name -match '^(?i)(http|https|all|no)_proxy$' } | Select-Object -ExpandProperty Name)) {
        $saved[$key] = [Environment]::GetEnvironmentVariable($key,'Process')
        [Environment]::SetEnvironmentVariable($key,$null,'Process')
    }
    try {
        $wire = & curl.exe @args 2>$null
        $code = $LASTEXITCODE
    } finally {
        foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key,$saved[$key],'Process') }
    }
    $data = try { $wire | ConvertFrom-Json } catch { $null }
    $bodyValid = $false
    if ($null -ne $data -and (Test-Path -LiteralPath $bodyPath)) {
        $bytes = [IO.File]::ReadAllBytes($bodyPath)
        if ($url.StartsWith('http://')) { $bodyValid = [Text.Encoding]::UTF8.GetString($bytes).Trim() -ceq 'Microsoft Connect Test' }
        else { $bodyValid = $bytes.Length -eq 0 }
    }
    Remove-Item -LiteralPath $bodyPath -ErrorAction SilentlyContinue
    $expectedHttp = if ($url.StartsWith('http://')) { 200 } else { 204 }
    return [ordered]@{
        name=$name; proxy_used=if ($data) { [int]$data.proxy_used } else { 0 }
        listenerPid=(Get-ListenerPid); exitCode=$code
        httpStatus=if ($data) { [int]$data.http_code } else { 0 }
        durationMs=if ($data) { [int][Math]::Round(1000*$data.time_total) } else { 0 }
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
    $started = Start-Process -FilePath $SwirlExe -ArgumentList @("--runtime-store=`"$EncryptedStore`"","--runtime-commands=`"$commandPath`"","--runtime-state=`"$statePath`"") -PassThru -WindowStyle Hidden
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
    $probes = @(
        @('http_http','http://www.msftconnecttest.com/connecttest.txt','http',$false),
        @('http_https','https://www.gstatic.com/generate_204','http',$false),
        @('connect_http','http://www.msftconnecttest.com/connecttest.txt','http',$true),
        @('connect_https','https://www.gstatic.com/generate_204','http',$true),
        @('socks5_http','http://www.msftconnecttest.com/connecttest.txt','socks5h',$false),
        @('socks5_https','https://www.gstatic.com/generate_204','socks5h',$false)
    )
    foreach ($probe in $probes) { $result.requests += Invoke-Probe $probe[0] $probe[1] $probe[2] $probe[3] $started.Id }
    $result.status = if (@($result.requests | Where-Object status -ne 'PASS').Count -eq 0) { 'PASS' } else { 'FAIL' }
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
    if ($commandPath) { Remove-Item -LiteralPath $commandPath,$statePath -ErrorAction SilentlyContinue }
    $result | ConvertTo-Json -Depth 6
    if ($result.status -eq 'FAIL') { exit 1 }
    if ($result.status -eq 'BLOCKED') { exit 2 }
}
