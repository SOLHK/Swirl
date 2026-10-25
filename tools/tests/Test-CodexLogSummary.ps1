# Offline synthetic regression: no app launch, account access or network IO.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot '../CodexLogSummary.psm1') -Force
$script:checks=0
function Assert([bool]$Value,[string]$Message) { if (!$Value) { throw $Message }; ++$script:checks }
$prefix='2026-10-24T09:17:39.458Z warning [electron-message-handler] sa_server_request_failed '
$local=ConvertFrom-CodexNetworkLogLine ($prefix+'errorMessage="Workspace routing is unavailable" errorCode=undefined routePattern=/settings/user status=432')
Assert ($local.category -eq 'workspace_routing_unavailable' -and $local.layer -eq 'local_workspace_gate') 'Synthetic 432 was treated as a server reply.'
$other=ConvertFrom-CodexNetworkLogLine ($prefix+'errorMessage="some other error" routePattern=/settings/user status=432')
Assert ($other.category -eq 'http_status_requires_correlation') 'Unrecognized 432 must stay unverified.'
$rpc=ConvertFrom-CodexNetworkLogLine ('2026-10-24T09:17:17.503Z error [electron-message-handler] Request failed error={"code":-32603,"message":"workspace routing discovery failed"} method=account/read')
Assert ($rpc.category -eq 'workspace_routing_discovery_failed') 'Discovery RPC failure was not recognized.'
foreach ($case in @(@('ERR_PROXY_CONNECTION_FAILED','proxy_connection_failed'),@('ERR_TUNNEL_CONNECTION_FAILED','proxy_tunnel_failed'),@('ERR_NAME_NOT_RESOLVED','name_resolution_failed'),@('ERR_CERT_AUTHORITY_INVALID','certificate_validation_failed'),@('ERR_CONNECTION_RESET','connection_reset'),@('ERR_TIMED_OUT','request_timed_out'))) {
    $event=ConvertFrom-CodexNetworkLogLine ($prefix+'errorCode='+$case[0]+' routePattern=/settings/user status=500')
    Assert ($event.category -eq $case[1]) 'Transport category was lost to wrapper status 500.'
}
$challenge=ConvertFrom-CodexNetworkLogLine ($prefix+'errorCode=cloudflare_challenge routePattern=/settings/user status=403')
Assert ($challenge.category -eq 'cloudflare_challenge' -and $challenge.layer -eq 'server_security_response') 'Explicit desktop Cloudflare classification was lost.'
foreach ($suffix in @('errorMessage="Cloudflare" status=403','errorCode=cloudflare_challenge status=500','errorCode=undefined status=403')) {
    $unverified=ConvertFrom-CodexNetworkLogLine ($prefix+$suffix)
    Assert ($unverified.category -eq 'http_status_requires_correlation') 'Unconfirmed server status became a Cloudflare diagnosis.'
}
$release=ConvertFrom-CodexNetworkLogLine '2026-10-24T09:17:38.341Z warning [windows-offers] Windows release marker unavailable errorMessage=net::ERR_PROXY_CONNECTION_FAILED errorName=Error'
Assert ($release.category -eq 'proxy_connection_failed') 'Electron release-marker error missed.'
$secret='private-credential-do-not-export'
$safe=ConvertFrom-CodexNetworkLogLine ($prefix+'errorCode=ERR_PROXY_CONNECTION_FAILED errorMessage="Bearer '+$secret+'" routePattern=/private/'+$secret+' status=500 url=https://example.invalid/?token='+$secret)
$json=$safe | ConvertTo-Json -Compress
Assert (!$json.Contains($secret) -and $safe.route -eq 'other') 'Private source text escaped the allowlist.'
Assert (!(ConvertFrom-CodexNetworkLogLine ('2026-10-24T09:17:39.458Z info [electron-message-handler] Reasoning summary="'+$prefix+'errorCode=ERR_PROXY_CONNECTION_FAILED"'))) 'Conversation text was mistaken for an event.'
Assert (!(ConvertFrom-CodexNetworkLogLine ($prefix+('x'*16384)))) 'Oversized line accepted.'
$temp=Join-Path ([IO.Path]::GetTempPath()) ('SwirlCodexSummary-'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($temp) | Out-Null
try {
    $file=Join-Path $temp 'codex-desktop-fixture.log'
    @(($prefix+'errorCode=ERR_PROXY_CONNECTION_FAILED routePattern=/settings/user status=500'), ($prefix+'errorMessage="Workspace routing is unavailable" routePattern=/settings/user status=432')) | Set-Content -LiteralPath $file -Encoding utf8
    # Secret-like unrelated files are ignored, even when in the chosen folder.
    Set-Content -LiteralPath (Join-Path $temp 'auth.json') -Value $secret
    $summary=Get-CodexLogSummary -LogDirectory $temp
    Assert ($summary.filesRead -eq 1 -and $summary.counts.workspace_routing_unavailable -eq 1 -and $summary.counts.proxy_connection_failed -eq 1) 'Offline file scan lost independent errors.'
    Assert (!(($summary|ConvertTo-Json -Depth 8).Contains($secret))) 'Unrelated auth file was read or disclosed.'
    $older=Join-Path $temp 'codex-desktop-older.log'
    Set-Content -LiteralPath $older -Value '2026-10-23T09:17:38.341Z warning [windows-offers] Windows release marker unavailable errorMessage=net::ERR_NAME_NOT_RESOLVED errorName=Error'
    (Get-Item -LiteralPath $older).LastWriteTimeUtc=[DateTime]::UtcNow.AddMinutes(1)
    $latest=Get-CodexLogSummary -LogDirectory $temp -MaxEvents 1
    Assert ($latest.latestEvents.Count -eq 1 -and $latest.latestEvents[0].timeUtc -eq '2026-10-24T09:17:39.458Z') 'File modification order evicted the latest event.'
    Remove-Item -LiteralPath $older
    $bounded=Get-CodexLogSummary -LogDirectory $temp -MaxFileBytes 1024
    Assert ($bounded.filesRead -eq 1) 'Small fixture unexpectedly skipped.'
    [IO.File]::AppendAllText($file,('x'*2048))
    $bounded=Get-CodexLogSummary -LogDirectory $temp -MaxFileBytes 1024
    Assert ($bounded.filesRead -eq 0 -and $bounded.filesSkipped -eq 1) 'Oversized file was read.'
    $rejected=$false
    try { Get-CodexLogSummary -LogDirectory '//example.invalid/private' | Out-Null } catch { $rejected=$true }
    Assert $rejected 'Remote log directory was inspected.'
    $empty=Get-CodexLogSummary -LogDirectory @()
    Assert ($empty.state -eq 'no_logs' -and $empty.filesRead -eq 0) 'Absent installations did not return an explicit no_logs result.'
    $appData=Join-Path $temp 'Local'
    # Local date is October 26, but the writer's current UTC folder is October
    # 25. The latest previous-day file must be found for either package type.
    $store=Join-Path $appData 'Packages/OpenAI.Codex_fixture/LocalCache/Local/Codex/Logs/2026/10/25'
    $unpacked=Join-Path $appData 'Codex/Logs/2026/10/24'
    $outsideWindow=Join-Path $appData 'Codex/Logs/2026/10/22'
    foreach ($folder in @($store,$unpacked,$outsideWindow)) { [IO.Directory]::CreateDirectory($folder) | Out-Null }
    Set-Content -LiteralPath (Join-Path $store 'codex-desktop-store.log') -Value '2026-10-25T16:10:38.066Z warning [electron-message-handler] sa_server_request_failed errorMessage="Workspace routing is unavailable" routePattern=/settings/user status=432'
    Set-Content -LiteralPath (Join-Path $unpacked 'codex-desktop-unpacked.log') -Value ($prefix+'errorCode=cloudflare_challenge routePattern=/settings/user status=403')
    Set-Content -LiteralPath (Join-Path $outsideWindow 'codex-desktop-old.log') -Value ($prefix+'errorCode=ERR_PROXY_CONNECTION_FAILED status=500')
    $directories=@(Get-CodexLogDirectories -LocalAppData $appData -Now ([DateTimeOffset]'2026-10-26T00:12:00+08:00'))
    Assert ($directories.Count -eq 2 -and $store -in $directories -and $unpacked -in $directories) 'UTC rollover or packaged log discovery omitted an installation.'
    $combined=Get-CodexLogSummary -LogDirectory $directories
    Assert ($combined.filesRead -eq 2 -and $combined.counts.workspace_routing_unavailable -eq 1 -and $combined.counts.cloudflare_challenge -eq 1) 'Multiple installation/day summaries lost independent failure classes.'
    Assert ($combined.latestEvents[0].category -eq 'workspace_routing_unavailable') 'Latest event was not ordered across UTC folders.'
    $copy=Join-Path $unpacked 'codex-desktop-store.log'
    Copy-Item -LiteralPath (Join-Path $store 'codex-desktop-store.log') -Destination $copy
    $mirrored=Get-CodexLogSummary -LogDirectory $directories
    Assert ($mirrored.filesRead -eq 2 -and $mirrored.duplicateFilesSkipped -eq 1 -and $mirrored.counts.workspace_routing_unavailable -eq 1) 'Store-virtualized duplicate logs inflated failure counts.'
    Add-Content -LiteralPath $copy -Value ($prefix+'errorCode=ERR_TIMED_OUT routePattern=/settings/user status=500')
    $distinct=Get-CodexLogSummary -LogDirectory $directories
    Assert ($distinct.filesRead -eq 3 -and $distinct.duplicateFilesSkipped -eq 0 -and $distinct.counts.request_timed_out -eq 1) 'Distinct contents with the same log name were silently omitted.'
    $boundedCombined=Get-CodexLogSummary -LogDirectory $directories -MaxFiles 1
    Assert ($boundedCombined.filesRead -eq 1) 'File bound was applied per directory instead of globally.'
    $rejected=$false
    try { Get-CodexLogDirectories -LocalAppData '//example.invalid/private' | Out-Null } catch { $rejected=$true }
    Assert $rejected 'Discovery accepted a remote profile root.'
} finally {
    # Only this exact freshly-created, resolved fixture directory is removed.
    $resolved=[IO.Path]::GetFullPath($temp)
    if ([IO.Path]::GetDirectoryName($resolved) -ne [IO.Path]::GetTempPath().TrimEnd('\','/')) { throw 'Unsafe fixture cleanup target.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Write-Output "Codex offline log summary: $script:checks assertions passed."
