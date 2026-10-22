# Offline, bounded Windows Rust networking acceptance. The user pauses and resumes
# Mihomo; this script never changes Mihomo, WinINET, WinHTTP, TUN, routes, or DNS.
param(
    [Parameter(Mandatory=$true)][string]$SwirlExe,
    [Parameter(Mandatory=$true)][string]$EncryptedStore,
    [Parameter(Mandatory=$true)][string]$WorkDirectory,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$ExpectedSourceSha,
    [ValidatePattern('^$|^[0-9a-fA-F]{64}$')][string]$ExpectedExeSha256 = '',
    [ValidatePattern('^$|^[0-9a-fA-F]{64}$')][string]$ExpectedRustDllSha256 = '',
    [Parameter(Mandatory=$true)][ValidateRange(1,2147483647)][int]$MihomoPid,
    [ValidateRange(1,65535)][int]$MihomoProxyPort = 7898,
    [ValidateRange(5,1800)][int]$WaitForPauseSeconds = 600,
    [switch]$PreflightOnly
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$publicTlsUrl = 'https://www.gstatic.com/generate_204'
$result = [ordered]@{
    schemaVersion=1; status='BLOCKED'; rustFrontEnd='NOT TESTED'
    controlledRequestIndependence='NOT TESTED'; mihomoIndependent='BLOCKED'
    reasonCode='NOT_STARTED'; startedUtc=[DateTime]::UtcNow.ToString('o'); completedUtc=$null
    pre=$null; paused=$null; post=$null; controls=$null; dns=$null; acceptance=$null; stages=$null; pauseMonitor=$null; binaryPin=$null
    outboundObserved=$false; configChanged=$false; scriptModifiedNetworkConfig=$false
}
$workReady = $false
$pauseMonitor = $null

function Get-TextSha256([string]$Value) {
    $sha=[Security.Cryptography.SHA256]::Create()
    try { return [Convert]::ToHexString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value))) }
    finally { $sha.Dispose() }
}
function Get-ListenerPid([int]$Port) {
    $rows=@(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -eq '127.0.0.1' -or $_.LocalAddress -eq '0.0.0.0' })
    $ids=@($rows | Select-Object -ExpandProperty OwningProcess -Unique)
    if($ids.Count -eq 0) { return 0 }
    if($ids.Count -ne 1) { return -1 }
    return [int]$ids[0]
}
function Get-MihomoState([int]$TargetPid) {
    $p=Get-Process -Id $TargetPid -ErrorAction SilentlyContinue
    if(-not $p) { return [ordered]@{exists=$false; startTicks=0L; threadCount=0; suspendedThreads=0; allThreadsSuspended=$false} }
    $threads=@($p.Threads)
    $suspended=0
    foreach($thread in $threads) {
        try { if([string]$thread.WaitReason -eq 'Suspended') { $suspended++ } } catch { }
    }
    return [ordered]@{
        exists=$true; startTicks=$p.StartTime.ToUniversalTime().Ticks
        threadCount=$threads.Count; suspendedThreads=$suspended
        allThreadsSuspended=($threads.Count -gt 0 -and $suspended -eq $threads.Count)
    }
}
function Get-NetworkSnapshot {
    $proxy=Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    $proxyText=@($proxy.ProxyEnable,$proxy.ProxyServer,$proxy.AutoConfigURL,$proxy.ProxyOverride) -join [char]10
    $envNames=@(Get-ChildItem Env: | Where-Object { $_.Name -match '^(?i)(http|https|all|no)_proxy$' } |
        Select-Object -ExpandProperty Name | Sort-Object -Unique)
    $envText=@($envNames | ForEach-Object { $_ + '=' + [Environment]::GetEnvironmentVariable($_,'Process') }) -join [char]10
    $adapters=@(Get-NetAdapter -ErrorAction Stop | Where-Object {
        ($_.Name+' '+$_.InterfaceDescription) -match '(?i)wintun|wireguard|\btun\b|\btap\b|mihomo|clash'
    })
    $activeTun=@($adapters | Where-Object Status -eq 'Up')
    $tunIndexes=@($adapters | Select-Object -ExpandProperty ifIndex)
    $routes=@(Get-NetRoute -ErrorAction Stop)
    $routedTun=@($routes | Where-Object { $tunIndexes -contains $_.InterfaceIndex -and
        $_.DestinationPrefix -in @('0.0.0.0/0','::/0','0.0.0.0/1','128.0.0.0/1','::/1','8000::/1','198.18.0.0/15') })
    $routeText=@($routes | Sort-Object DestinationPrefix,InterfaceIndex,NextHop |
        ForEach-Object { $_.DestinationPrefix+'|'+$_.InterfaceIndex+'|'+$_.NextHop }) -join [char]10
    $drivers=@(Get-CimInstance Win32_SystemDriver | Where-Object {
        $_.State -eq 'Running' -and $_.Name -match '(?i)windivert|wintun|wireguard'
    })
    $dns=@(Get-DnsClientServerAddress -ErrorAction Stop)
    $dnsServers=@($dns | ForEach-Object { $_.ServerAddresses } | Where-Object { $_ })
    $dnsText=@($dns | Sort-Object InterfaceIndex,AddressFamily |
        ForEach-Object { $_.InterfaceIndex.ToString()+'|'+$_.AddressFamily+'|'+(@($_.ServerAddresses) -join ',') }) -join [char]10
    $nrpt=@(Get-DnsClientNrptPolicy -ErrorAction SilentlyContinue)
    $winHttp=@(netsh winhttp show proxy)
    $mihomo=Get-MihomoState $MihomoPid
    return [ordered]@{
        listener17988Pid=(Get-ListenerPid 17988); mihomoListenerPid=(Get-ListenerPid $MihomoProxyPort)
        mihomo=$mihomo; winInetProxyEnabled=[bool]$proxy.ProxyEnable
        winInetProxyPointsToMihomo=([string]$proxy.ProxyServer -match ('(?i)(127\.0\.0\.1|localhost):'+$MihomoProxyPort+'\b'))
        winInetProxySha256=(Get-TextSha256 $proxyText)
        proxyEnvironmentNames=$envNames; proxyEnvironmentSha256=(Get-TextSha256 $envText)
        winHttpProxySha256=(Get-TextSha256 (@($winHttp) -join [char]10))
        activeTunAdapterCount=$activeTun.Count; tunRouteCount=$routedTun.Count
        transparentDriverCount=$drivers.Count; routeSha256=(Get-TextSha256 $routeText)
        dnsServerCount=$dnsServers.Count
        loopbackDnsServerCount=@($dnsServers | Where-Object { $_ -match '^(127\.|::1$)' }).Count
        dnsConfigSha256=(Get-TextSha256 $dnsText); nrptRuleCount=$nrpt.Count
    }
}
function Get-NetworkSnapshotBounded([int]$Seconds = 20) {
    # NetTCPIP/CIM/netsh are local reads, but a broken provider must not strand
    # an offline worker while the user has Mihomo suspended.
    $names=@('Get-TextSha256','Get-ListenerPid','Get-MihomoState','Get-NetworkSnapshot')
    $definitions=(@($names | ForEach-Object {
        'function '+$_+' {'+[char]10+(Get-Command $_ -CommandType Function).Definition+[char]10+'}'
    }) -join [char]10)
    $job=Start-ThreadJob -ArgumentList @($definitions,$MihomoPid,$MihomoProxyPort) -ScriptBlock {
        param($source,[int]$targetPid,[int]$targetPort)
        . ([scriptblock]::Create($source))
        $script:MihomoPid=$targetPid
        $script:MihomoProxyPort=$targetPort
        Get-NetworkSnapshot
    }
    try {
        $done=Wait-Job -Job $job -Timeout $Seconds
        if(-not $done) { throw 'NETWORK_SNAPSHOT_TIMEOUT' }
        if($job.State -ne 'Completed') { throw 'NETWORK_SNAPSHOT_FAILED' }
        $items=@(Receive-Job -Job $job -ErrorAction Stop)
        if($items.Count -ne 1) { throw 'NETWORK_SNAPSHOT_FAILED' }
        return $items[0]
    } finally {
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }
}
function Invoke-MihomoControl([int]$Seconds) {
    $proxy='http://127.0.0.1:'+$MihomoProxyPort
    $wire=& curl.exe --disable --silent --max-time $Seconds --proxy $proxy '--noproxy=' --output NUL --write-out '%{http_code}' $publicTlsUrl 2>$null
    return [ordered]@{exitCode=[int]$LASTEXITCODE; httpStatus=([string]$wire).Trim()}
}
function Write-Event([string]$Stage,[string]$State,[string]$Code) {
    if(-not $workReady) { return }
    $line=[ordered]@{utc=[DateTime]::UtcNow.ToString('o'); stage=$Stage; status=$State; code=$Code} | ConvertTo-Json -Compress
    Add-Content -LiteralPath (Join-Path $WorkDirectory 'events.jsonl') -Value $line -Encoding utf8
}
function Write-Status([string]$State,[string]$Code) {
    if(-not $workReady) { return }
    $data=[ordered]@{state=$State; code=$Code; utc=[DateTime]::UtcNow.ToString('o'); workerPid=$PID}
    $path=Join-Path $WorkDirectory 'status.json'
    $temp=Join-Path $WorkDirectory 'status.tmp'
    $data | ConvertTo-Json -Compress | Set-Content -LiteralPath $temp -Encoding utf8
    Move-Item -LiteralPath $temp -Destination $path -Force
    Write-Event 'worker' $State $Code
}
function Test-PathOutsideGit([string]$Path) {
    $dir=if(Test-Path -LiteralPath $Path -PathType Container) { $Path } else { Split-Path -Parent $Path }
    while(-not(Test-Path -LiteralPath $dir -PathType Container)) { $dir=Split-Path -Parent $dir }
    $inside=& git -C $dir rev-parse --is-inside-work-tree 2>$null
    return ($LASTEXITCODE -ne 0 -or $inside -ne 'true')
}
function Assert-Inputs {
    $driveRoot=[IO.Path]::GetFullPath('D:\Codex\')
    foreach($path in @($SwirlExe,$EncryptedStore,$WorkDirectory)) {
        if(-not([IO.Path]::GetFullPath($path).StartsWith($driveRoot,[StringComparison]::OrdinalIgnoreCase))) {
            throw 'PATH_OUTSIDE_D_CODEX'
        }
    }
    if(-not(Test-Path -LiteralPath $SwirlExe -PathType Leaf)) { throw 'EXE_MISSING' }
    $dll=Join-Path (Split-Path $SwirlExe) 'swirl_api.dll'
    if(-not(Test-Path -LiteralPath $dll -PathType Leaf)) { throw 'RUST_DLL_MISSING' }
    if($ExpectedExeSha256 -and (Get-FileHash -LiteralPath $SwirlExe -Algorithm SHA256).Hash -ne $ExpectedExeSha256) { throw 'EXE_HASH_CHANGED' }
    if($ExpectedRustDllSha256 -and (Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash -ne $ExpectedRustDllSha256) { throw 'RUST_DLL_HASH_CHANGED' }
    if(-not(Test-Path -LiteralPath $EncryptedStore -PathType Leaf)) { throw 'STORE_MISSING' }
    if(-not(Test-Path -LiteralPath ($EncryptedStore+'.selected') -PathType Leaf)) { throw 'SELECTION_SIDECAR_MISSING' }
    if(-not(Test-PathOutsideGit $EncryptedStore) -or -not(Test-PathOutsideGit $WorkDirectory)) { throw 'PRIVATE_PATH_INSIDE_GIT' }
    if(-not(Get-Command curl.exe -ErrorAction SilentlyContinue)) { throw 'CURL_MISSING' }
    if(-not(Get-Command Start-ThreadJob -ErrorAction SilentlyContinue)) { throw 'THREAD_JOB_MISSING' }
    $snap=Get-NetworkSnapshotBounded
    if(-not $snap.mihomo.exists -or $snap.mihomoListenerPid -ne $MihomoPid) { throw 'MIHOMO_IDENTITY_MISMATCH' }
    if($snap.listener17988Pid -ne 0) { throw 'RUST_PORT_ALREADY_OWNED' }
    if($snap.mihomo.allThreadsSuspended) { throw 'MIHOMO_ALREADY_SUSPENDED' }
    return $snap
}
function Invoke-SystemDnsProbe {
    $out=Join-Path $WorkDirectory 'dns.out'
    $err=Join-Path $WorkDirectory 'dns.err'
    $code=@'
try {
    $r=Resolve-DnsName -Name 'www.gstatic.com' -DnsOnly -QuickTimeout -ErrorAction Stop
    [Console]::Out.WriteLine((@($r | Where-Object { $_.Type -in @('A','AAAA') }).Count))
    exit 0
} catch { exit 1 }
'@
    $encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($code))
    $child=Start-Process -FilePath (Get-Command pwsh -ErrorAction Stop).Source -ArgumentList @('-NoProfile','-EncodedCommand',$encoded) -PassThru -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err
    $timedOut=-not $child.WaitForExit(8000)
    if($timedOut) { Stop-Process -InputObject $child -Force -ErrorAction SilentlyContinue; [void]$child.WaitForExit(2000) }
    $text=if(Test-Path -LiteralPath $out) { (Get-Content -LiteralPath $out -Raw).Trim() } else { '' }
    $count=0
    if(-not [int]::TryParse($text,[ref]$count)) { $count=0 }
    $answer=[ordered]@{kind='Windows OS resolver control, not Rust upstream DNS'; status=if(-not $timedOut -and $child.ExitCode -eq 0 -and $count -gt 0){'PASS'}else{'FAIL'}; addressCount=$count; timedOut=$timedOut}
    Remove-Item -LiteralPath $out,$err -ErrorAction SilentlyContinue
    return $answer
}
function Start-MihomoPauseMonitor([int]$TargetPid,[long]$StartTicks) {
    $stop=[Threading.ManualResetEventSlim]::new($false)
    $ready=[Threading.ManualResetEventSlim]::new($false)
    $ps=[PowerShell]::Create()
    $code=@'
param([int]$targetProcessId,[long]$expectedTicks,$stopSignal,$readySignal)
$samples=0
$resumed=$false
$status='SAMPLED'
try {
    $deadline=[DateTime]::UtcNow.AddSeconds(240)
    do {
        $p=Get-Process -Id $targetProcessId -ErrorAction Stop
        if($p.StartTime.ToUniversalTime().Ticks -ne $expectedTicks) { $resumed=$true }
        $threads=@($p.Threads)
        if($threads.Count -eq 0) { $resumed=$true }
        foreach($thread in $threads) {
            try { if([string]$thread.WaitReason -ne 'Suspended') { $resumed=$true } }
            catch { $resumed=$true }
        }
        $samples++
        $readySignal.Set()
    } while(-not $stopSignal.Wait(100) -and [DateTime]::UtcNow -lt $deadline)
    if([DateTime]::UtcNow -ge $deadline) { $status='TIMED_OUT'; $resumed=$true }
} catch {
    $status='UNAVAILABLE'; $resumed=$true; $readySignal.Set()
}
[pscustomobject]@{status=$status;samples=$samples;resumedObserved=$resumed}
'@
    try {
        $null=$ps.AddScript($code).AddArgument($TargetPid).AddArgument($StartTicks).AddArgument($stop).AddArgument($ready)
        $handle=$ps.BeginInvoke()
        $started=$ready.Wait(3000)
        if(-not $started) { $stop.Set() }
        return [pscustomobject]@{ps=$ps;handle=$handle;stop=$stop;ready=$ready;started=$started}
    } catch {
        $stop.Dispose();$ready.Dispose();$ps.Dispose()
        return $null
    }
}
function Stop-MihomoPauseMonitor($Monitor) {
    $answer=[ordered]@{status='UNAVAILABLE';samples=0;resumedObserved=$true}
    if(-not $Monitor) { return $answer }
    try {
        $Monitor.stop.Set()
        if($Monitor.handle.AsyncWaitHandle.WaitOne(3000)) {
            $items=@($Monitor.ps.EndInvoke($Monitor.handle))
            if($Monitor.started -and $items.Count -eq 1) {
                $answer.status=[string]$items[0].status
                $answer.samples=[int]$items[0].samples
                $answer.resumedObserved=[bool]$items[0].resumedObserved
            }
        } else { $null=$Monitor.ps.BeginStop($null,$null) }
    } catch { }
    finally {
        $Monitor.ps.Dispose()
        $Monitor.stop.Dispose()
        $Monitor.ready.Dispose()
    }
    return $answer
}
function Stop-OwnedTestSwirl([int]$AcceptancePid,[string]$TestWork) {
    # Only a direct child of this invocation with the exact EXE path/hash can
    # receive a stop command or be force-stopped after the child times out.
    $expectedHash=(Get-FileHash -LiteralPath $SwirlExe -Algorithm SHA256).Hash
    $children=@(Get-CimInstance Win32_Process -Filter "ParentProcessId=$AcceptancePid" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ieq 'Swirl.exe' })
    try {
        foreach($child in $children) {
            if(-not $child.ExecutablePath -or
                -not [string]::Equals([IO.Path]::GetFullPath($child.ExecutablePath),[IO.Path]::GetFullPath($SwirlExe),[StringComparison]::OrdinalIgnoreCase) -or
                (Get-FileHash -LiteralPath $child.ExecutablePath -Algorithm SHA256).Hash -ne $expectedHash) { continue }
            $ownedPid=[int]$child.ProcessId
            Set-Content -LiteralPath (Join-Path $TestWork 'runtime-command.json') -Value '{"action":"stop"}' -Encoding ascii
            $owned=Get-Process -Id $ownedPid -ErrorAction SilentlyContinue
            if($owned -and -not $owned.WaitForExit(10000)) {
                Stop-Process -Id $ownedPid -Force -ErrorAction SilentlyContinue
            }
        }
    } finally {
        Remove-Item -LiteralPath (Join-Path $TestWork 'runtime-command.json'),(Join-Path $TestWork 'runtime-state.json') -ErrorAction SilentlyContinue
    }
}
function Invoke-GuardedAcceptance([string]$Accept,[string]$Store,[string]$TestWork) {
    $out=Join-Path $WorkDirectory 'acceptance.out'
    $err=Join-Path $WorkDirectory 'acceptance.err'
    $args=@(
        '-NoProfile','-File',('"' + $Accept + '"'),
        '-SwirlExe',('"' + $SwirlExe + '"'),
        '-EncryptedStore',('"' + $Store + '"'),
        '-WorkDirectory',('"' + $TestWork + '"'),
        '-ExpectedSourceSha',$ExpectedSourceSha,
        '-ObserveRustOutbound','-WriteProgress'
    )
    $child=Start-Process -FilePath (Get-Command pwsh -ErrorAction Stop).Source -ArgumentList $args -PassThru -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err
    try {
        if(-not $child.WaitForExit(270000)) {
            Stop-Process -InputObject $child -Force -ErrorAction SilentlyContinue
            [void]$child.WaitForExit(2000)
            throw 'ACCEPTANCE_WALL_TIMEOUT'
        }
        if(-not(Test-Path -LiteralPath $out)) { throw 'ACCEPTANCE_REPORT_MISSING' }
        $text=Get-Content -LiteralPath $out -Raw
        if([string]::IsNullOrWhiteSpace($text)) { throw 'ACCEPTANCE_REPORT_MISSING' }
        return ($text | ConvertFrom-Json)
    } finally {
        try { Stop-OwnedTestSwirl $child.Id $TestWork }
        finally { Remove-Item -LiteralPath $out,$err -ErrorAction SilentlyContinue }
    }
}

if($PreflightOnly) {
    try {
        $snapshot=Assert-Inputs
        $control=Invoke-MihomoControl 8
        $status=if($control.exitCode -eq 0 -and $control.httpStatus -eq '204') { 'PASS' } else { 'BLOCKED' }
        [ordered]@{
            status=$status; reasonCode=if($status -eq 'PASS'){'READY'}else{'MIHOMO_BASELINE_CONTROL_FAILED'}
            sourceShaExpected=$ExpectedSourceSha
            swirlExeSha256=(Get-FileHash -LiteralPath $SwirlExe -Algorithm SHA256).Hash
            rustDllSha256=(Get-FileHash -LiteralPath (Join-Path (Split-Path $SwirlExe) 'swirl_api.dll') -Algorithm SHA256).Hash
            mihomoPid=$MihomoPid; mihomoStartTicks=$snapshot.mihomo.startTicks
            mihomoListenerPid=$snapshot.mihomoListenerPid; listener17988Pid=$snapshot.listener17988Pid
            mihomoControl=$control
            network=$snapshot
            note='Mihomo is running; no independent networking request was attempted.'
        } | ConvertTo-Json -Depth 7
    } catch {
        $code=if($_.Exception.Message -match '^[A-Z0-9_]+$'){$_.Exception.Message}else{'PREFLIGHT_'+$_.Exception.GetType().Name}
        [ordered]@{status='BLOCKED';reasonCode=$code;note='No independent networking request was attempted.'} | ConvertTo-Json
    }
    return
}

try {
    # WorkDirectory is deliberately fresh and outside Git. Only encrypted copies
    # and allowlisted summaries survive. The production NodeStore is never opened.
    $pre=Assert-Inputs
    if(Test-Path -LiteralPath $WorkDirectory) {
        if(@(Get-ChildItem -LiteralPath $WorkDirectory -Force).Count -ne 0) { throw 'WORK_DIRECTORY_NOT_EMPTY' }
    } else {
        New-Item -ItemType Directory -Path $WorkDirectory -ErrorAction Stop | Out-Null
    }
    $WorkDirectory=(Resolve-Path -LiteralPath $WorkDirectory).Path
    $workReady=$true
    Write-Status 'PREFLIGHT' 'CHECKING'
    $result.pre=$pre
    $result.binaryPin=[ordered]@{
        exeSha256=(Get-FileHash -LiteralPath $SwirlExe -Algorithm SHA256).Hash
        rustDllSha256=(Get-FileHash -LiteralPath (Join-Path (Split-Path $SwirlExe) 'swirl_api.dll') -Algorithm SHA256).Hash
        sourceShaExpected=$ExpectedSourceSha
    }
    $baseline=Invoke-MihomoControl 8
    $result.controls=[ordered]@{before=$baseline;during=$null;after=$null}
    if($baseline.exitCode -ne 0 -or $baseline.httpStatus -ne '204') { throw 'MIHOMO_BASELINE_CONTROL_FAILED' }
    $sourceHash=(Get-FileHash -LiteralPath $EncryptedStore -Algorithm SHA256).Hash
    $sidecarHash=(Get-FileHash -LiteralPath ($EncryptedStore+'.selected') -Algorithm SHA256).Hash
    $copy=Join-Path $WorkDirectory 'nodes.dpapi'
    Copy-Item -LiteralPath $EncryptedStore -Destination $copy -ErrorAction Stop
    Copy-Item -LiteralPath ($EncryptedStore+'.selected') -Destination ($copy+'.selected') -ErrorAction Stop
    if((Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash -ne $sourceHash -or
       (Get-FileHash -LiteralPath ($copy+'.selected') -Algorithm SHA256).Hash -ne $sidecarHash) {
        throw 'ENCRYPTED_COPY_HASH_MISMATCH'
    }
    $testWork=Join-Path $WorkDirectory 'rust-work'
    New-Item -ItemType Directory -Path $testWork -ErrorAction Stop | Out-Null
    Write-Status 'WAITING_FOR_MIHOMO_SUSPEND' 'USER_ACTION_PENDING'
    $deadline=[DateTime]::UtcNow.AddSeconds($WaitForPauseSeconds)
    $pausedState=$null
    while([DateTime]::UtcNow -lt $deadline) {
        $state=Get-MihomoState $MihomoPid
        if(-not $state.exists -or $state.startTicks -ne $pre.mihomo.startTicks) { throw 'MIHOMO_PROCESS_REPLACED_OR_TERMINATED' }
        if((Get-ListenerPid 17988) -ne 0) { throw 'RUST_PORT_TAKEN_WHILE_WAITING' }
        if($state.allThreadsSuspended) {
            $control=Invoke-MihomoControl 3
            if($control.exitCode -eq 28 -and $control.httpStatus -eq '000') {
                $pausedState=$state
                $result.controls.during=$control
                break
            }
        }
        Start-Sleep -Seconds 1
    }
    if(-not $pausedState) { throw 'MIHOMO_PAUSE_GATE_TIMEOUT' }
    $result.paused=Get-NetworkSnapshotBounded
    if(-not $result.paused.mihomo.allThreadsSuspended -or
       $result.paused.mihomo.startTicks -ne $pre.mihomo.startTicks -or
       $result.paused.mihomoListenerPid -ne $MihomoPid) {
        throw 'MIHOMO_PAUSE_IDENTITY_CHANGED'
    }
    Write-Status 'RUNNING' 'MIHOMO_SUSPENDED_CONTROL_BLOCKED'
    $pauseMonitor=Start-MihomoPauseMonitor $MihomoPid $pre.mihomo.startTicks
    $result.dns=Invoke-SystemDnsProbe
    Write-Event 'system-dns-control' $result.dns.status 'OS_RESOLVER_NOT_RUST_UPSTREAM'
    # The existing guarded script starts only its own Swirl, checks the in-process
    # Rust DLL and 17988 PID, runs six explicit-proxy requests, then stops it.
    $accept=Join-Path $PSScriptRoot 'Invoke-WindowsRustAcceptance.ps1'
    try {
        $report=Invoke-GuardedAcceptance $accept $copy $testWork
    } catch {
        $progressPath=Join-Path $testWork 'acceptance-progress.json'
        if(Test-Path -LiteralPath $progressPath) {
            try { $result.acceptance=Get-Content -LiteralPath $progressPath -Raw | ConvertFrom-Json }
            catch { Write-Event 'acceptance-progress' 'BLOCKED' 'PARTIAL_REPORT_UNREADABLE' }
        }
        throw
    }
    $result.acceptance=$report
    $result.rustFrontEnd=if($report.status -eq 'PASS'){'PASS'}elseif($report.status -eq 'FAIL'){'FAIL'}else{'BLOCKED'}
    if($report.status -eq 'FAIL') { $result.status='FAIL'; $result.reasonCode='ONE_OR_MORE_REQUESTS_FAILED' }
    $result.outboundObserved=@($report.requests | Where-Object { $_.rustOutboundObservation.observed -eq $true }).Count -gt 0
    $requests=@($report.requests)
    $connect=@($requests | Where-Object { $_.name -in @('connect_http','connect_https') })
    $socks=@($requests | Where-Object { $_.name -in @('socks5_http','socks5_https') })
    $https=@($requests | Where-Object { $_.name -in @('http_https','connect_https','socks5_https') })
    $tcpFrontend=if($report.identity.enginePid -gt 0 -and
        @($requests | Where-Object { $_.listenerPid -ne $report.identity.enginePid }).Count -eq 0) {'PASS'} else {'FAIL'}
    $proxyHandshake=if($connect.Count -eq 2 -and $socks.Count -eq 2 -and
        @($connect | Where-Object { $_.httpConnectStatus -ne 200 -or $_.status -ne 'PASS' }).Count -eq 0 -and
        @($socks | Where-Object status -ne 'PASS').Count -eq 0) {'PASS'} else {'FAIL'}
    $tls=if($https.Count -eq 3 -and
        @($https | Where-Object { $_.status -ne 'PASS' -or -not $_.tlsCertificateVerified }).Count -eq 0) {'PASS'} else {'FAIL'}
    $http=if($requests.Count -eq 6 -and @($requests | Where-Object status -ne 'PASS').Count -eq 0) {'PASS'} else {'FAIL'}
    $allRustTransfers=($requests.Count -eq 6 -and
        @($requests | Where-Object {
            -not $_.rustOutboundObservation.observed -or
            -not $_.rustTransferObserved -or
            $_.rustUploadDelta -le 0 -or $_.rustDownloadDelta -le 0
        }).Count -eq 0)
    $result.stages=[ordered]@{
        systemDns=$result.dns.status
        rustUpstreamDns='NOT TESTED'
        tcpFrontend=$tcpFrontend
        tcpOutboundPid=if($allRustTransfers){'PASS'}else{'BLOCKED'}
        proxyHandshake=$proxyHandshake
        tlsTargetCertificate=$tls
        http=$http
        proxyHandshakeNote='CONNECT 200 is explicit; SOCKS5 success is inferred from completed requests.'
    }
    Write-Event 'tcp-front-end' $tcpFrontend 'LISTENER_PID_AND_REQUESTS'
    Write-Event 'proxy-handshake' $proxyHandshake 'CONNECT_200_SOCKS_REQUEST_SUCCESS'
    Write-Event 'target-tls' $tls 'CERTIFICATE_VERIFIED'
    Write-Event 'http' $http 'SIX_STATUS_AND_BODY_CHECKS'
    Write-Event 'rust-front-end' $result.rustFrontEnd 'SIX_EXPLICIT_PROXY_REQUESTS'
    Write-Event 'rust-outbound-pid' $(if($result.outboundObserved){'PASS'}else{'BLOCKED'}) 'NON_LOOPBACK_TCP_OWNERSHIP'
    $afterControl=Invoke-MihomoControl 3
    $result.controls.after=$afterControl
    $result.post=Get-NetworkSnapshotBounded
    $result.pauseMonitor=Stop-MihomoPauseMonitor $pauseMonitor
    $pauseMonitor=$null
    $sameConfig=($result.post.winInetProxySha256 -eq $pre.winInetProxySha256 -and
        $result.post.proxyEnvironmentSha256 -eq $pre.proxyEnvironmentSha256 -and
        $result.post.winHttpProxySha256 -eq $pre.winHttpProxySha256 -and
        $result.post.routeSha256 -eq $pre.routeSha256 -and
        $result.post.dnsConfigSha256 -eq $pre.dnsConfigSha256)
    $result.configChanged=-not $sameConfig
    $mihomoStayedSuspended=($result.post.mihomo.exists -and
        $result.post.mihomo.startTicks -eq $pre.mihomo.startTicks -and
        $result.post.mihomo.allThreadsSuspended -and
        $afterControl.exitCode -eq 28 -and $afterControl.httpStatus -eq '000')
    $noKnownTransparentPath=($result.paused.activeTunAdapterCount -eq 0 -and
        $result.paused.tunRouteCount -eq 0 -and
        $result.paused.transparentDriverCount -eq 0 -and
        $result.post.activeTunAdapterCount -eq 0 -and
        $result.post.tunRouteCount -eq 0 -and
        $result.post.transparentDriverCount -eq 0)
    $identityValid=($report.identity.sourceSha -eq $ExpectedSourceSha -and
        $report.identity.actualEngineType -eq 'rust' -and
        $report.identity.swirlExeSha256 -eq $result.binaryPin.exeSha256 -and
        $report.identity.rustDllSha256 -eq $result.binaryPin.rustDllSha256 -and
        (Get-FileHash -LiteralPath $SwirlExe -Algorithm SHA256).Hash -eq $result.binaryPin.exeSha256 -and
        (Get-FileHash -LiteralPath (Join-Path (Split-Path $SwirlExe) 'swirl_api.dll') -Algorithm SHA256).Hash -eq $result.binaryPin.rustDllSha256 -and
        $report.post.listenerPid -eq 0 -and
        $report.pre.proxySettingsSha256 -eq $report.post.proxySettingsSha256 -and
        $report.pre.proxyEnvironmentSha256 -eq $report.post.proxyEnvironmentSha256)
    $storeUnchanged=((Get-FileHash -LiteralPath $EncryptedStore -Algorithm SHA256).Hash -eq $sourceHash -and
        (Get-FileHash -LiteralPath ($EncryptedStore+'.selected') -Algorithm SHA256).Hash -eq $sidecarHash)
    $controlledPass=($report.status -eq 'PASS' -and $identityValid -and $allRustTransfers -and
        $mihomoStayedSuspended -and $noKnownTransparentPath -and $sameConfig -and $storeUnchanged -and
        $result.dns.status -eq 'PASS' -and $result.paused.loopbackDnsServerCount -eq 0 -and
        $result.pauseMonitor.status -eq 'SAMPLED' -and $result.pauseMonitor.samples -gt 0 -and
        -not $result.pauseMonitor.resumedObserved)
    if($controlledPass) {
        $result.controlledRequestIndependence='PASS'
        # A Windows resolver control and PID socket counters do not trace every
        # Rust DNS decision or every WFP path. Keep the stronger claim BLOCKED.
        $result.status='BLOCKED'
        $result.reasonCode='CONTROLLED_REQUEST_PASS_FULL_DEPENDENCY_UNPROVEN'
    } elseif($report.status -eq 'FAIL') {
        $result.status='FAIL'; $result.reasonCode='ONE_OR_MORE_REQUESTS_FAILED'
    } else {
        $result.status='BLOCKED'; $result.reasonCode='INDEPENDENCE_EVIDENCE_INCOMPLETE'
    }
    Write-Event 'controlled-request-independence' $result.controlledRequestIndependence $result.reasonCode
    Write-Event 'full-independence' $result.mihomoIndependent 'RUST_DNS_AND_WFP_PATH_NOT_FULLY_TRACED'
} catch {
    $code=if($_.Exception.Message -match '^[A-Z0-9_]+$'){$_.Exception.Message}else{'WORKER_'+$_.Exception.GetType().Name}
    $result.reasonCode=$code
    Write-Event 'worker' 'BLOCKED' $code
} finally {
    if($pauseMonitor) {
        $result.pauseMonitor=Stop-MihomoPauseMonitor $pauseMonitor
        $pauseMonitor=$null
    }
    if($workReady) {
        if(-not $result.post) {
            try { $result.post=Get-NetworkSnapshotBounded } catch { Write-Event 'post' 'FAIL' 'SNAPSHOT_UNAVAILABLE' }
        }
        $result.completedUtc=[DateTime]::UtcNow.ToString('o')
        $reportPath=Join-Path $WorkDirectory 'result.json'
        $tempPath=Join-Path $WorkDirectory 'result.tmp'
        $result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $tempPath -Encoding utf8
        Move-Item -LiteralPath $tempPath -Destination $reportPath -Force
        Write-Status 'COMPLETE' $result.reasonCode
        Set-Content -LiteralPath (Join-Path $WorkDirectory 'complete.marker') -Value $result.status -Encoding ascii
    }
}
