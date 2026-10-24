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
foreach ($case in @(@('ERR_PROXY_CONNECTION_FAILED','proxy_connection_failed'),@('ERR_TUNNEL_CONNECTION_FAILED','proxy_tunnel_failed'),@('ERR_NAME_NOT_RESOLVED','name_resolution_failed'),@('ERR_CERT_AUTHORITY_INVALID','certificate_validation_failed'),@('ERR_CONNECTION_RESET','connection_reset'))) {
    $event=ConvertFrom-CodexNetworkLogLine ($prefix+'errorCode='+$case[0]+' routePattern=/settings/user status=500')
    Assert ($event.category -eq $case[1]) 'Transport category was lost to wrapper status 500.'
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
} finally {
    # Only this exact freshly-created, resolved fixture directory is removed.
    $resolved=[IO.Path]::GetFullPath($temp)
    if ([IO.Path]::GetDirectoryName($resolved) -ne [IO.Path]::GetTempPath().TrimEnd('\','/')) { throw 'Unsafe fixture cleanup target.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Write-Output "Codex offline log summary: $script:checks assertions passed."
