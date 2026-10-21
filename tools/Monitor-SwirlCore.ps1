# Continuous, privacy-minimal monitoring of the existing Swirl Windows session.
# Active probes are bounded and use the already selected node; no settings change.
param(
    [string]$DataDirectory = 'D:\Codex\SwirlCoreMonitorData',
    [switch]$Once,
    [switch]$PassiveOnly
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Get-Configuration {
    $path = Join-Path $DataDirectory 'config.json'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'SwirlCoreMonitor.config.json') -Destination $path
    }
    $config = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    if ($config.schemaVersion -ne 1 -or [int]$config.proxyPort -lt 1 -or [int]$config.proxyPort -gt 65535 -or
        [int]$config.passiveIntervalSeconds -lt 30 -or [int]$config.passiveIntervalSeconds -gt 3600 -or
        [int]$config.activeIntervalMinutes -lt 5 -or [int]$config.activeIntervalMinutes -gt 1440 -or
        [int]$config.activeRequestCount -lt 3 -or [int]$config.activeRequestCount -gt 12) {
        throw 'Monitor configuration is invalid; existing config was not replaced.'
    }
    return $config
}

function Get-PassiveSnapshot([int]$Port) {
    $listenerPid = 0
    $name = ''
    try {
        $ids = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalAddress -in @('127.0.0.1','0.0.0.0') } |
            Select-Object -ExpandProperty OwningProcess -Unique)
        if ($ids.Count -eq 1) {
            $listenerPid = [int]$ids[0]
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$listenerPid" -ErrorAction Stop
            $name = [string]$process.Name
        }
    } catch { $listenerPid = 0 }
    $proxy = 'UNKNOWN'
    try {
        $p = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop
        if ($p.ProxyEnable -eq 1 -and -not $p.AutoConfigURL) {
            $entries = @([string]$p.ProxyServer -split ';' | ForEach-Object { ($_ -split '=',2)[-1].Trim() })
            $proxy = if ($entries -contains "127.0.0.1:$Port") { 'SWIRL' } else { 'OTHER' }
        } elseif ($p.ProxyEnable -eq 0) { $proxy='OFF' }
    } catch { }
    $mode = 'UNKNOWN'
    try { $mode = [string](Get-ItemProperty 'HKCU:\Software\SOLHK\Swirl\Proxy' -ErrorAction Stop).routingMode } catch { }
    $mihomoCount = -1
    $swirlToMihomo=0; $swirlOutbound=0; $mihomoOutbound=0; $connectionSample='UNAVAILABLE'
    try {
        $mihomoPids=@(Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object { $_.Name -match '(?i)mihomo|clash' } |
            Select-Object -ExpandProperty ProcessId -Unique)
        $mihomoCount=$mihomoPids.Count
        $connections=@(Get-NetTCPConnection -ErrorAction Stop)
        $mihomoPorts=@($connections | Where-Object {
            $_.State -eq 'Listen' -and $mihomoPids -contains [int]$_.OwningProcess -and
            $_.LocalAddress -in @('127.0.0.1','0.0.0.0','::1','::')
        } | Select-Object -ExpandProperty LocalPort -Unique)
        foreach($c in $connections) {
            $owner=[int]$c.OwningProcess
            if([string]$c.State -notin @('Established','SynSent','SynReceived')) { continue }
            if($owner -ne $listenerPid -and $mihomoPids -notcontains $owner) { continue }
            if($owner -eq $listenerPid -and [int]$c.LocalPort -eq $Port) { continue }
            $ip=$null
            if(-not [Net.IPAddress]::TryParse([string]$c.RemoteAddress,[ref]$ip)) { continue }
            if($ip.IsIPv4MappedToIPv6) { $ip=$ip.MapToIPv4() }
            if($ip.Equals([Net.IPAddress]::Any) -or $ip.Equals([Net.IPAddress]::IPv6Any)) { continue }
            if($owner -eq $listenerPid) {
                if([Net.IPAddress]::IsLoopback($ip)) {
                    if($mihomoPorts -contains [int]$c.RemotePort) { $swirlToMihomo++ }
                } else { $swirlOutbound++ }
            } elseif(-not [Net.IPAddress]::IsLoopback($ip)) { $mihomoOutbound++ }
        }
        $connectionSample='SAMPLED'
    } catch { }
    return [ordered]@{
        listenerPid=$listenerPid; listenerIsSwirl=($listenerPid -gt 0 -and $name -ieq 'Swirl.exe')
        systemProxy=$proxy; routingMode=$mode; mihomoProcessCount=$mihomoCount
        connectionSample=$connectionSample; swirlToMihomoActive=$swirlToMihomo
        swirlOutboundActive=$swirlOutbound; mihomoOutboundActive=$mihomoOutbound
    }
}

function Read-ProbeJson([string]$Script,[string[]]$Arguments) {
    try {
        $exe=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $wire = & $exe -NoProfile -ExecutionPolicy Bypass -File $Script @Arguments 2>$null
        if(-not $wire) { return $null }
        return ($wire -join "`n") | ConvertFrom-Json
    } catch { return $null }
}

function Get-ActiveSnapshot([int]$Port,[int]$Requests,[string]$Mode) {
    $path = Read-ProbeJson (Join-Path $PSScriptRoot 'Test-SwirlMihomoPath.ps1') @('-Port',"$Port",'-RequestCount',"$Requests")
    $private = Read-ProbeJson (Join-Path $PSScriptRoot 'Test-SwirlPrivateDirect.ps1') @('-ProxyPort',"$Port")
    $pathStatus = if ($path) { [string]$path.status } else { 'INCONCLUSIVE' }
    $pathReasonCode = if(-not $path) { 'NO_PROBE_JSON' }
        elseif($pathStatus -eq 'MIHOMO_PATH_OBSERVED') { 'MIHOMO_CHAIN' }
        elseif($pathStatus -eq 'SWIRL_NATIVE_EGRESS_OBSERVED') { 'NONE' }
        elseif([int]$path.requestsAttempted -eq 0) { 'PREFLIGHT_BLOCKED' }
        elseif([int]$path.requestsPassed -lt [int]$path.requestsAttempted) { 'REQUEST_FAILED' }
        else { 'OBSERVATION_INCONCLUSIVE' }
    $private4 = if ($private) { [string]$private.ipv4 } else { 'INCONCLUSIVE' }
    $private6 = if ($private) { [string]$private.ipv6 } else { 'INCONCLUSIVE' }
    return [ordered]@{
        checkedAt=(Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
        pathStatus=$pathStatus
        pathReasonCode=$pathReasonCode
        requestsPassed=if ($path) { [int]$path.requestsPassed } else { 0 }
        requestsAttempted=if ($path) { [int]$path.requestsAttempted } else { 0 }
        newSwirlOutbound=if ($path -and $path.observation) { [int]$path.observation.newSwirlNonLoopbackConnections } else { 0 }
        swirlToMihomo=if ($path -and $path.observation) { [int]$path.observation.swirlToMihomoLocalConnections } else { 0 }
        transparentIndicators=if ($path) { [string]$path.knownTransparentIndicators } else { 'UNKNOWN' }
        privateIpv4=$private4
        privateIpv6=$private6
        categories=[ordered]@{
            '内核身份'=if ($pathStatus -eq 'SWIRL_NATIVE_EGRESS_OBSERVED') { 'PASS' } else { 'INCONCLUSIVE' }
            '系统代理'=if ($path -and $path.systemProxyUnchanged) { 'PASS' } else { 'INCONCLUSIVE' }
            'Mihomo后续路径'=if ($pathStatus -eq 'MIHOMO_PATH_OBSERVED') { 'OBSERVED' }
                elseif ($pathStatus -eq 'SWIRL_NATIVE_EGRESS_OBSERVED') { 'NO_LOCAL_CHAIN_OBSERVED' } else { 'INCONCLUSIVE' }
            '规则模式'=if ($Mode -eq 'rule') { 'ON' } else { 'OFF' }
            '内网DIRECT IPv4'=$private4
            '内网DIRECT IPv6'=$private6
            '默认PROXY'=if ($pathStatus -eq 'SWIRL_NATIVE_EGRESS_OBSERVED') { 'EGRESS_OBSERVED' } else { 'INCONCLUSIVE' }
            '国内DIRECT'=if ($Mode -eq 'rule') { 'NOT_CONFIGURED' } else { 'RULE_MODE_OFF' }
            '海外PROXY'=if ($Mode -eq 'rule') { 'RULE_NOT_VERIFIED' } else { 'RULE_MODE_OFF' }
            'REJECT域名'=if ($Mode -eq 'rule') { 'NOT_CONFIGURED' } else { 'RULE_MODE_OFF' }
            'REJECT规则名'=if ($Mode -eq 'rule') { 'NOT_OBSERVABLE' } else { 'RULE_MODE_OFF' }
            'DNS与HTTPS'=if ($path -and $path.requestsPassed -eq $Requests) { 'HTTPS_PASS_DNS_PATH_UNKNOWN' } else { 'INCONCLUSIVE' }
        }
    }
}

function Write-Event($Snapshot) {
    $date = Get-Date -Format 'yyyyMMdd'
    $path = Join-Path $DataDirectory "events-$date.jsonl"
    $line = $Snapshot | ConvertTo-Json -Depth 7 -Compress
    [IO.File]::AppendAllText($path,$line+"`n",[Text.UTF8Encoding]::new($false))
    $latest = Join-Path $DataDirectory 'latest.json'
    $temp = $latest+'.tmp'
    [IO.File]::WriteAllText($temp,($Snapshot | ConvertTo-Json -Depth 7),[Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temp -Destination $latest -Force
}

function Remove-OldEvents {
    $cutoff=(Get-Date).AddDays(-30)
    foreach($file in @(Get-ChildItem -LiteralPath $DataDirectory -File -Filter 'events-*.jsonl' -ErrorAction SilentlyContinue)) {
        if($file.Name -match '^events-[0-9]{8}\.jsonl$' -and $file.LastWriteTime -lt $cutoff) {
            Remove-Item -LiteralPath $file.FullName -ErrorAction SilentlyContinue
        }
    }
}

function Write-Report($Snapshot) {
    $labels=@{
        PASS='通过'; OFF='未启用'; ON='已启用'; RULE_MODE_OFF='规则模式未启用'
        NOT_TESTED='未测试'; NOT_CONFIGURED='未配置目标'; NOT_OBSERVABLE='当前版本无法读取规则名'
        RULE_NOT_VERIFIED='尚无具体规则命中证据'; EGRESS_OBSERVED='观察到 Swirl 出站'
        NO_LOCAL_CHAIN_OBSERVED='未观察到本地 Mihomo 链路'; OBSERVED='观察到本地 Mihomo 链路'
        INCONCLUSIVE='证据不足'; HTTPS_PASS_DNS_PATH_UNKNOWN='HTTPS 通过；DNS 路径未单独确认'
        SWIRL_NATIVE_EGRESS_OBSERVED='观察到 Swirl 自有出站'
        MIHOMO_PATH_OBSERVED='观察到 Swirl 连向 Mihomo'
        MONITOR_ERROR='监控周期出错'; ERROR='出错，等待下次重试'
        NO_PROBE_JSON='探测脚本没有可解析结果'; PREFLIGHT_BLOCKED='身份或环境预检未通过'
        MIHOMO_CHAIN='发现 Mihomo 本地链路'; REQUEST_FAILED='受控请求失败'
        OBSERVATION_INCONCLUSIVE='连接采样证据不足'; NONE='无'
    }
    $rows = [Collections.Generic.List[string]]::new()
    foreach ($entry in $Snapshot.active.categories.GetEnumerator()) {
        $label = [Net.WebUtility]::HtmlEncode([string]$entry.Key)
        $value = [string]$entry.Value
        $state = [Net.WebUtility]::HtmlEncode($(if($labels.ContainsKey($value)){$labels[$value]}else{$value}))
        $rows.Add("<tr><th scope='row'>$label</th><td>$state</td></tr>")
    }
    $time = [Net.WebUtility]::HtmlEncode([string]$Snapshot.localTime)
    $mode = if($Snapshot.passive.routingMode -eq 'global'){'全局代理（规则未启用）'}
        elseif($Snapshot.passive.routingMode -eq 'rule'){'规则模式'}else{[string]$Snapshot.passive.routingMode}
    $mode = [Net.WebUtility]::HtmlEncode($mode)
    $rawPath=[string]$Snapshot.active.pathStatus
    $path = [Net.WebUtility]::HtmlEncode($(if($labels.ContainsKey($rawPath)){$labels[$rawPath]}else{$rawPath}))
    $checked=[Net.WebUtility]::HtmlEncode([string]$Snapshot.active.checkedAt)
    $reasonCode=[string]$Snapshot.active.pathReasonCode
    $reason=[Net.WebUtility]::HtmlEncode($(if($labels.ContainsKey($reasonCode)){$labels[$reasonCode]}else{$reasonCode}))
    $summary = "请求 $($Snapshot.active.requestsPassed)/$($Snapshot.active.requestsAttempted)；Swirl 新出站 $($Snapshot.active.newSwirlOutbound)；Swirl→Mihomo 本地连接 $($Snapshot.active.swirlToMihomo)"
    $summary = [Net.WebUtility]::HtmlEncode($summary)
    $passiveSummary = "定时连接快照：Swirl→Mihomo $($Snapshot.passive.swirlToMihomoActive)，Swirl 非回环 $($Snapshot.passive.swirlOutboundActive)，Mihomo 非回环 $($Snapshot.passive.mihomoOutboundActive)；采样 $($Snapshot.passive.connectionSample)"
    $passiveSummary = [Net.WebUtility]::HtmlEncode($passiveSummary)
    $html = @"
<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta http-equiv='refresh' content='60'>
<meta name='viewport' content='width=device-width, initial-scale=1'><title>Swirl Core 全天候验收</title>
<style>body{font:16px/1.55 system-ui,'Microsoft YaHei',sans-serif;margin:0;background:#111827;color:#f9fafb}
main{max-width:900px;margin:auto;padding:32px 20px}h1{font-size:26px;margin:0 0 8px}p{color:#d1d5db}
.card{background:#1f2937;border:1px solid #374151;border-radius:14px;padding:18px;margin:18px 0}
table{border-collapse:collapse;width:100%}th,td{text-align:left;border-bottom:1px solid #374151;padding:12px 8px}
th{font-weight:600;width:50%}td{overflow-wrap:anywhere}small{color:#d1d5db}a{color:#93c5fd}
</style></head><body><main><h1>Swirl Core 全天候验收</h1><p>最近更新：$time · 保存的路由模式：$mode</p>
<section class='card' aria-label='联网路径'><h2>最近一次主动验收</h2><p>时间：$checked · $path</p><p>诊断：$reason</p><p>$summary</p><p>$passiveSummary</p>
<small>没有观察到 Mihomo 本地链路，不等于排除所有 WFP/TUN 透明转发。</small></section>
<section class='card' aria-label='项目状态'><h2>检测项目</h2><table><tbody>$($rows -join '')</tbody></table></section>
<p>详细脱敏记录在同目录 events-YYYYMMDD.jsonl。规则名、用户目标与正文不写入报告。状态“未配置/无法观察”不计为通过。</p>
</main></body></html>
"@
    $out = Join-Path $DataDirectory 'report.html'
    $temp = $out+'.tmp'
    [IO.File]::WriteAllText($temp,$html,[Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temp -Destination $out -Force
}

if (-not (Test-Path -LiteralPath $DataDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $DataDirectory -Force | Out-Null
}
$config = Get-Configuration
$mutex = [Threading.Mutex]::new($false,'Local\SwirlCoreMonitor')
$owned = $false
try {
    $owned = $mutex.WaitOne(0)
    if (-not $owned) { throw 'Swirl Core monitor is already running.' }
    $stopPath = Join-Path $DataDirectory 'stop.request'
    if (Test-Path -LiteralPath $stopPath) { Remove-Item -LiteralPath $stopPath -Force }
    [IO.File]::WriteAllText((Join-Path $DataDirectory 'monitor.pid'),"$PID",[Text.Encoding]::ASCII)
    $nextActive = [DateTime]::MinValue
    $latestActive = $null
    $previousSignature = ''
    while ($true) {
        try {
        $now = [DateTime]::UtcNow
        $passive = Get-PassiveSnapshot ([int]$config.proxyPort)
        $signature=@($passive.listenerPid,$passive.routingMode,$passive.systemProxy) -join '|'
        if($previousSignature -and $signature -cne $previousSignature) { $nextActive=[DateTime]::MinValue }
        $previousSignature=$signature
        $activeDue = -not $PassiveOnly -and $now -ge $nextActive
        if ($activeDue) {
            $latestActive = Get-ActiveSnapshot ([int]$config.proxyPort) ([int]$config.activeRequestCount) $passive.routingMode
            $nextActive = [DateTime]::UtcNow.AddMinutes([int]$config.activeIntervalMinutes)
        }
        if (-not $latestActive) { $latestActive = [ordered]@{
            pathStatus='NOT_TESTED'; requestsPassed=0; requestsAttempted=0; newSwirlOutbound=0; swirlToMihomo=0
            categories=[ordered]@{'规则模式'=if($passive.routingMode -eq 'rule'){'ON'}else{'OFF'}; '主动联网'='NOT_TESTED'}
        } }
        $snapshot = [ordered]@{
            schemaVersion=1; utcTime=[DateTime]::UtcNow.ToString('o'); localTime=(Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            activeCycle=[bool]$activeDue; passive=$passive; active=$latestActive
        }
        Write-Event $snapshot
        Write-Report $snapshot
        if($activeDue) { Remove-OldEvents }
        } catch {
            if($Once) { throw }
            $nextActive=[DateTime]::UtcNow.AddMinutes(1)
            $latestActive=[ordered]@{
                checkedAt=(Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
                pathStatus='MONITOR_ERROR'; requestsPassed=0; requestsAttempted=0
                newSwirlOutbound=0; swirlToMihomo=0
                categories=[ordered]@{'监控状态'='ERROR';'规则验收'='NOT_TESTED'}
            }
            $snapshot=[ordered]@{
                schemaVersion=1; utcTime=[DateTime]::UtcNow.ToString('o')
                localTime=(Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
                activeCycle=$false; passive=[ordered]@{routingMode='UNKNOWN'}; active=$latestActive
            }
            try { Write-Event $snapshot; Write-Report $snapshot } catch { }
        }
        if ($Once -or (Test-Path -LiteralPath $stopPath)) { break }
        for ($i=0; $i -lt [int]$config.passiveIntervalSeconds; $i++) {
            if (Test-Path -LiteralPath $stopPath) { break }
            Start-Sleep -Seconds 1
        }
        if (Test-Path -LiteralPath $stopPath) { break }
    }
    if ($Once) { $snapshot | ConvertTo-Json -Depth 7 }
} finally {
    if ($owned) {
        Remove-Item -LiteralPath (Join-Path $DataDirectory 'monitor.pid') -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath (Join-Path $DataDirectory 'stop.request')) {
            Remove-Item -LiteralPath (Join-Path $DataDirectory 'stop.request') -Force -ErrorAction SilentlyContinue
        }
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
