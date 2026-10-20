# User-facing, offline-capable check for the Windows Rust acceptance preview.
# The package never changes Mihomo or Windows proxy, DNS, TUN, or routes.
param(
    [ValidateRange(60,600)][int]$WallSeconds = 270
)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$EncryptedStore='D:\Codex\Swirl-acceptance-private-20261020\nodes.dpapi'
$ResultsRoot='D:\Codex\Swirl-acceptance-private-20261020\portable-runs'
$packageDir=Split-Path $PSScriptRoot -Parent
$manifestPath=Join-Path $packageDir 'PACKAGE.json'
$exe=Join-Path $packageDir 'Swirl.exe'
$dll=Join-Path $packageDir 'swirl_api.dll'
$accept=Join-Path $PSScriptRoot 'Invoke-WindowsRustAcceptance.ps1'
$launcher=Join-Path $packageDir 'TEST-SWIRL-NETWORK.cmd'
$bundledPwsh=Join-Path $packageDir 'runtime\powershell\pwsh.exe'
$runDir=$null
$child=$null
$childTimedOut=$false
$ownedTestStillAlive=$false
$report=$null
$summary=[ordered]@{
    schemaVersion=1; status='BLOCKED'; reasonCode='NOT_STARTED'
    startedUtc=[DateTime]::UtcNow.ToString('o'); completedUtc=$null
    sourceSha=$null; exeSha256=$null; rustDllSha256=$null
    systemProxyControl=[ordered]@{status='NOT TESTED';winInetPointsToMihomo=$false;mihomoListenerPid=0;httpStatus=0;curlExitCode=$null}
    swirlRustExplicit=[ordered]@{status='NOT TESTED';passed=0;total=6;enginePid=0;requests=@()}
    fullMihomoIndependence='BLOCKED'; userSettingsChangedByScript=$false
    resultDirectory=$null; privateRuntimeStateMayPersist=$false
}

function Get-ListenerPid([int]$Port) {
    $ids=@(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -in @('127.0.0.1','0.0.0.0') } |
        Select-Object -ExpandProperty OwningProcess -Unique)
    if($ids.Count -eq 1) { return [int]$ids[0] }
    return 0
}
function Test-DPathOutsidePackage([string]$Path) {
    $full=[IO.Path]::GetFullPath($Path)
    $dRoot=[IO.Path]::GetFullPath('D:\Codex\')
    $packageFull=[IO.Path]::GetFullPath($packageDir)
    return ($full.StartsWith($dRoot,[StringComparison]::OrdinalIgnoreCase) -and
        -not [string]::Equals($full.TrimEnd('\'),$packageFull.TrimEnd('\'),[StringComparison]::OrdinalIgnoreCase) -and
        -not $full.StartsWith($packageFull.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase))
}
function Stop-ExactOwnedSwirl([int]$ParentPid,[string]$ExpectedHash) {
    $survivors=0
    $children=@(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ParentPid" -ErrorAction SilentlyContinue)
    foreach($process in $children) {
        if($process.Name -ine 'Swirl.exe' -or -not $process.ExecutablePath) { continue }
        if(-not [string]::Equals([IO.Path]::GetFullPath($process.ExecutablePath),
            [IO.Path]::GetFullPath($exe),[StringComparison]::OrdinalIgnoreCase)) { continue }
        if((Get-FileHash -LiteralPath $process.ExecutablePath -Algorithm SHA256).Hash -ne $ExpectedHash) { continue }
        $owned=Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
        if(-not $owned) { continue }
        '{"action":"stop"}' | Set-Content -LiteralPath (Join-Path $runDir 'runtime-command.json') -Encoding ascii
        if(-not $owned.WaitForExit(10000)) {
            Stop-Process -InputObject $owned -Force -ErrorAction SilentlyContinue
            [void]$owned.WaitForExit(5000)
        }
        if(-not $owned.HasExited) { $survivors++ }
    }
    return $survivors
}
function Show-Result {
    $daily=$summary.systemProxyControl.status
    $rust=$summary.swirlRustExplicit.status
    $dailyLabel=if($daily -eq 'PASS'){'可用'}elseif($daily -eq 'FAIL'){'未通过'}else{'未测试'}
    $rustLabel=if($rust -eq 'PASS'){'可用'}elseif($rust -eq 'FAIL' -and $summary.swirlRustExplicit.passed -gt 0){'部分可用'}elseif($rust -eq 'FAIL'){'未通过'}else{'未完成'}
    $lines=[Collections.Generic.List[string]]::new()
    $lines.Add('====== Swirl Rust 联网测试 ======')
    $lines.Add("电脑当前代理控制请求：$dailyLabel（$daily）")
    $lines.Add("Swirl Rust 显式代理：$rustLabel（$($summary.swirlRustExplicit.passed)/6，判定 $rust）")
    if($rust -eq 'PASS') {
        $lines.Add('六项请求均进入测试版 Swirl Rust，并有出站收发。')
    } elseif($rust -eq 'FAIL') {
        $rows=@($summary.swirlRustExplicit.requests)
        $plain=@($rows | Where-Object { $_.name -match '_http$' })
        $https=@($rows | Where-Object { $_.name -match '_https$' })
        $lines.Add("明文 HTTP：$(@($plain | Where-Object status -eq 'PASS').Count)/3；HTTPS：$(@($https | Where-Object status -eq 'PASS').Count)/3。")
        $names=@{http_http='HTTP 代理到明文网页';http_https='HTTP 代理到 HTTPS';connect_http='CONNECT 到明文网页';connect_https='CONNECT 到 HTTPS';socks5_http='SOCKS5 到明文网页';socks5_https='SOCKS5 到 HTTPS'}
        foreach($row in @($rows | Where-Object status -ne 'PASS')) {
            $label=if($names.ContainsKey([string]$row.name)){$names[[string]$row.name]}else{'未知请求'}
            $lines.Add("失败：$label；curl 退出码 $($row.curlExitCode)。")
        }
        $lines.Add('有些请求已成功，但本轮不稳定；失败记录已经保存。')
    } else {
        $lines.Add("尚不能判断 Swirl 联网：$($summary.reasonCode)")
    }
    $lines.Add('完整摆脱 Mihomo 依赖：未证明。普通应用仍按 Windows 系统代理走。')
    if($runDir) { $lines.Add("本机结果：$runDir") }
    $lines.Add('脚本没有暂停或关闭 Mihomo，也没有修改系统代理、TUN、路由或 DNS。')
    if($runDir) { $lines | Set-Content -LiteralPath (Join-Path $runDir '结果-直接看.txt') -Encoding utf8 }
    Write-Host ''
    foreach($line in $lines) { Write-Host $line }
}

try {
    if(-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $exe -PathType Leaf) -or
        -not (Test-Path -LiteralPath $dll -PathType Leaf) -or
        -not (Test-Path -LiteralPath $accept -PathType Leaf) -or
        -not (Test-Path -LiteralPath $bundledPwsh -PathType Leaf) -or
        -not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw 'PACKAGE_INCOMPLETE' }
    $manifest=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if($manifest.kind -ne 'windows-rust-acceptance-preview' -or
        $manifest.sourceSha -notmatch '^[0-9a-fA-F]{40}$') { throw 'PACKAGE_MANIFEST_INVALID' }
    $summary.sourceSha=$manifest.sourceSha
    $summary.exeSha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
    $summary.rustDllSha256=(Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash
    if($summary.exeSha256 -ne $manifest.exeSha256 -or
        $summary.rustDllSha256 -ne $manifest.rustDllSha256 -or
        (Get-FileHash -LiteralPath $accept -Algorithm SHA256).Hash -ne $manifest.acceptanceScriptSha256 -or
        (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash -ne $manifest.portableRunnerSha256 -or
        (Get-FileHash -LiteralPath $bundledPwsh -Algorithm SHA256).Hash -ne $manifest.bundledPowerShellSha256 -or
        (Get-FileHash -LiteralPath $launcher -Algorithm SHA256).Hash -ne $manifest.launcherCmdSha256) {
        throw 'PACKAGE_HASH_MISMATCH'
    }
    if(-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) { throw 'WINDOWS_CURL_MISSING' }
    if(-not (Test-DPathOutsidePackage $EncryptedStore) -or
        -not (Test-DPathOutsidePackage $ResultsRoot)) { throw 'PRIVATE_PATH_MUST_BE_D_CODEX_OUTSIDE_PACKAGE' }
    if(-not (Test-Path -LiteralPath $EncryptedStore -PathType Leaf) -or
        -not (Test-Path -LiteralPath ($EncryptedStore+'.selected') -PathType Leaf)) { throw 'ENCRYPTED_STORE_COPY_MISSING' }
    if((Get-ListenerPid 17988) -ne 0) { throw 'SWIRL_TEST_PORT_BUSY' }
    if(-not (Test-Path -LiteralPath $ResultsRoot -PathType Container)) {
        New-Item -ItemType Directory -Path $ResultsRoot -ErrorAction Stop | Out-Null
    }
    $runDir=Join-Path $ResultsRoot ('run-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8))
    New-Item -ItemType Directory -Path $runDir -ErrorAction Stop | Out-Null
    $summary.resultDirectory=$runDir
    $copy=Join-Path $runDir 'nodes.dpapi'
    Copy-Item -LiteralPath $EncryptedStore -Destination $copy -ErrorAction Stop
    Copy-Item -LiteralPath ($EncryptedStore+'.selected') -Destination ($copy+'.selected') -ErrorAction Stop
    if((Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash -ne
        (Get-FileHash -LiteralPath $EncryptedStore -Algorithm SHA256).Hash -or
        (Get-FileHash -LiteralPath ($copy+'.selected') -Algorithm SHA256).Hash -ne
        (Get-FileHash -LiteralPath ($EncryptedStore+'.selected') -Algorithm SHA256).Hash) {
        throw 'ENCRYPTED_COPY_HASH_MISMATCH'
    }

    # This row checks the current Windows proxy route only when it points to the
    # known local Mihomo port. It is separate from the Swirl Rust test below.
    $proxy=Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    $summary.systemProxyControl.winInetPointsToMihomo=([bool]$proxy.ProxyEnable -and
        [string]$proxy.ProxyServer -match '(?i)(127\.0\.0\.1|localhost):7898\b')
    $summary.systemProxyControl.mihomoListenerPid=Get-ListenerPid 7898
    if($summary.systemProxyControl.winInetPointsToMihomo) {
        $wire=& curl.exe --disable --silent --max-time 6 --proxy 'http://127.0.0.1:7898' '--noproxy=' --output NUL --write-out '%{http_code}' 'https://www.gstatic.com/generate_204' 2>$null
        $summary.systemProxyControl.curlExitCode=[int]$LASTEXITCODE
        $summary.systemProxyControl.httpStatus=([string]$wire).Trim()
        $summary.systemProxyControl.status=if($LASTEXITCODE -eq 0 -and ([string]$wire).Trim() -eq '204'){'PASS'}else{'FAIL'}
    }

    $storage=Join-Path $runDir 'storage'
    New-Item -ItemType Directory -Path $storage -ErrorAction Stop | Out-Null
    $out=Join-Path $runDir 'acceptance.out'
    $err=Join-Path $runDir 'acceptance.err'
    $args=@('-NoProfile','-File',('"'+$accept+'"'),'-SwirlExe',('"'+$exe+'"'),
        '-EncryptedStore',('"'+$copy+'"'),'-WorkDirectory',('"'+$runDir+'"'),
        '-ExpectedSourceSha',$manifest.sourceSha,'-ObserveRustOutbound','-WriteProgress')
    $previousRoot=[Environment]::GetEnvironmentVariable('SWIRL_TEST_ROOT','Process')
    try {
        [Environment]::SetEnvironmentVariable('SWIRL_TEST_ROOT',$storage,'Process')
        $child=Start-Process -FilePath $bundledPwsh -ArgumentList $args -PassThru -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err
    } finally {
        [Environment]::SetEnvironmentVariable('SWIRL_TEST_ROOT',$previousRoot,'Process')
    }
    Write-Host '正在测试 Swirl Rust，请等候；每项请求有超时，整轮最多约 5 分钟。'
    if(-not $child.WaitForExit($WallSeconds*1000)) {
        $childTimedOut=$true
        Stop-Process -InputObject $child -Force -ErrorAction SilentlyContinue
        [void]$child.WaitForExit(2000)
        throw 'ACCEPTANCE_WALL_TIMEOUT'
    }
    if(-not (Test-Path -LiteralPath $out -PathType Leaf)) { throw 'ACCEPTANCE_REPORT_MISSING' }
    $text=Get-Content -LiteralPath $out -Raw
    if([string]::IsNullOrWhiteSpace($text)) { throw 'ACCEPTANCE_REPORT_MISSING' }
    $report=$text | ConvertFrom-Json
    $rows=@($report.requests)
    $summary.swirlRustExplicit.enginePid=[int]$report.identity.enginePid
    $summary.swirlRustExplicit.passed=@($rows | Where-Object status -eq 'PASS').Count
    $summary.swirlRustExplicit.requests=@($rows | ForEach-Object {
        [ordered]@{name=$_.name;status=$_.status;curlExitCode=$_.exitCode
            httpStatus=$_.httpStatus;httpConnectStatus=$_.httpConnectStatus
            tlsCertificateVerified=$_.tlsCertificateVerified
            rustTransferObserved=$_.rustTransferObserved
            rustOutboundPidObserved=$_.rustOutboundObservation.observed}
    })
    $allObserved=($rows.Count -eq 6 -and @($rows | Where-Object {
        $_.status -ne 'PASS' -or -not $_.rustTransferObserved -or
        -not $_.rustOutboundObservation.observed
    }).Count -eq 0)
    if($report.status -eq 'PASS' -and $allObserved -and
        $report.identity.sourceSha -eq $manifest.sourceSha -and
        $report.identity.actualEngineType -eq 'rust' -and
        $report.identity.swirlExeSha256 -eq $summary.exeSha256 -and
        $report.identity.rustDllSha256 -eq $summary.rustDllSha256 -and
        $report.post.listenerPid -eq 0) {
        $summary.swirlRustExplicit.status='PASS'
        $summary.status='PASS'
        $summary.reasonCode='SIX_EXPLICIT_RUST_REQUESTS_PASS'
    } elseif($report.status -eq 'FAIL' -or @($rows | Where-Object status -eq 'FAIL').Count -gt 0) {
        $summary.swirlRustExplicit.status='FAIL'
        $summary.status='FAIL'
        $summary.reasonCode='ONE_OR_MORE_SWIRL_REQUESTS_FAILED'
    } else {
        $summary.reasonCode='RUST_IDENTITY_OR_OUTBOUND_EVIDENCE_INCOMPLETE'
    }
} catch {
    $code=$_.Exception.Message
    $summary.reasonCode=if($code -match '^[A-Z0-9_]+$'){$code}else{'PORTABLE_CHECK_ERROR'}
    if($summary.reasonCode -eq 'ACCEPTANCE_WALL_TIMEOUT') { $summary.status='FAIL' }
} finally {
    if($child) {
        try {
            $ownedTestStillAlive=(Stop-ExactOwnedSwirl $child.Id $summary.exeSha256) -gt 0
        } catch { $ownedTestStillAlive=$true }
    }
    if($runDir) {
        $summary.privateRuntimeStateMayPersist=$ownedTestStillAlive
        if($ownedTestStillAlive) {
            $summary.status='FAIL';$summary.reasonCode='TEST_SWIRL_PROCESS_STILL_ALIVE'
        } else {
            Remove-Item -LiteralPath (Join-Path $runDir 'runtime-command.json'),(Join-Path $runDir 'runtime-state.json') -ErrorAction SilentlyContinue
            $storage=Join-Path $runDir 'storage'
            if((Test-Path -LiteralPath $storage -PathType Container) -and
                [IO.Path]::GetFullPath($storage).StartsWith([IO.Path]::GetFullPath($runDir).TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) {
                Remove-Item -LiteralPath $storage -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        Remove-Item -LiteralPath (Join-Path $runDir 'nodes.dpapi'),(Join-Path $runDir 'nodes.dpapi.selected'),(Join-Path $runDir 'acceptance.out'),(Join-Path $runDir 'acceptance.err') -ErrorAction SilentlyContinue
        $summary.completedUtc=[DateTime]::UtcNow.ToString('o')
        $summary | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $runDir 'summary.json') -Encoding utf8
    }
    Show-Result
}
if($summary.status -eq 'PASS') { exit 0 }
if($summary.status -eq 'FAIL') { exit 1 }
exit 2
