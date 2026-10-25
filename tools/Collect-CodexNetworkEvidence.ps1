param([Parameter(Mandatory=$true)][string]$OutputPath,[string]$CodexLogDirectory)
$ErrorActionPreference='Stop'
# Read-only inventory. Never dumps command lines, environment blocks, tokens,
# browser storage or request bodies. No Set-* network calls or cache flushes.
function EndpointSummary([string]$Value) {
    if([string]::IsNullOrWhiteSpace($Value)){return $null}
    try{$uri=[uri]$Value;if($uri.IsAbsoluteUri){return @{scheme=$uri.Scheme;host=$uri.Host;port=$uri.Port;credentialsPresent=!!$uri.UserInfo}}}catch{}
    return @{configured=$true;format='not a URI; value omitted'}
}
$processes=Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId,Name,ExecutablePath,CreationDate
$selected=@($processes | Where-Object {
    $_.Name -match '^(codex|Swirl.*|.*mihomo.*|msedge|chrome)\.exe$' -or
    $_.ExecutablePath -match '\\OpenAI\.Codex_[^\\]+\\app\\'
})
$ids=@($selected.ProcessId)
$inventory=@($selected | ForEach-Object {
    [pscustomobject]@{pid=$_.ProcessId;parent=$_.ParentProcessId;name=$_.Name;path=$_.ExecutablePath;created=$_.CreationDate;
        role=if($_.ExecutablePath -match '\\OpenAI\\Codex\\bin\\'){'Codex CLI or app-server; launch mode uninspected'}elseif($_.ExecutablePath -match '\\OpenAI\.Codex_'){'Codex desktop process'}elseif($_.Name -match '^(msedge|chrome)\.exe$'){'browser process'}else{'proxy or helper'}}
})
$tcp=@(Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object OwningProcess -in $ids | Select-Object OwningProcess,State,LocalAddress,LocalPort,RemoteAddress,RemotePort)
$settings=Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
$proxy=@{enabled=$settings.ProxyEnable;server=$settings.ProxyServer;pacConfigured=!!$settings.AutoConfigURL}
$environment=@(foreach($scope in @('Process','User','Machine')){foreach($name in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY')){
    $value=[Environment]::GetEnvironmentVariable($name,$scope)
    [pscustomobject]@{scope=$scope;name=$name;configured=!!$value;endpoint=if($name -ne 'NO_PROXY'){EndpointSummary $value}else{$null}}
}})
$certificates=@(foreach($scope in @('Process','User','Machine')){foreach($name in @('SSL_CERT_FILE','SSL_CERT_DIR','CODEX_CA_CERTIFICATE','NODE_EXTRA_CA_CERTS')){
    $value=[Environment]::GetEnvironmentVariable($name,$scope)
    # Report only presence and local existence. Do not open certificates or
    # touch UNC/device paths, and never export the full environment block.
    $local=!!$value -and $value -match '\A[A-Za-z]:[\\/]' -and $value -notmatch '\A[\\/]{2}'
    [pscustomobject]@{scope=$scope;name=$name;configured=!!$value;localPath=$local;exists=if($local){Test-Path -LiteralPath $value}else{$null}}
}})
$interfaces=@(Get-NetIPInterface -ErrorAction SilentlyContinue | Where-Object InterfaceAlias -match 'Swirl|Clash|TUN|Wintun' | Select-Object InterfaceAlias,InterfaceIndex,AddressFamily,ConnectionState,InterfaceMetric)
$dns=@(Get-DnsClientCache -ErrorAction SilentlyContinue | Where-Object Entry -match '(^|\.)(chatgpt|openai|oaistatic|oaiusercontent)\.com$' | Select-Object Entry,@{Name='RecordType';Expression={$_.Type}},Data,TimeToLive)
$codexLogSummary=$null
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'CodexLogSummary.psm1')) {
    Import-Module (Join-Path $PSScriptRoot 'CodexLogSummary.psm1') -Force
    $logDirectories=if ($CodexLogDirectory) { @($CodexLogDirectory) } else { @(Get-CodexLogDirectories) }
    $codexLogSummary=Get-CodexLogSummary -LogDirectory $logDirectories
}
$report=@{timestamp=(Get-Date).ToString('o');processes=$inventory;tcp=$tcp;windowsProxy=$proxy;winHttp=(netsh winhttp show proxy | Out-String).Trim();environment=$environment;certificateEnvironment=$certificates;tunCandidates=$interfaces;dnsCache=$dns;codexExistingLogSummary=$codexLogSummary;
    limitations=@('Process environment is the collector environment, not an inspection of already-running Codex processes.','TCP endpoints do not reveal encrypted WebSocket or SSE contents.','A TUN adapter name is a candidate, not proof of effective routing.','A loopback proxy connection and a TUN interface can coexist without proving a loop.')}
$destination=[IO.Path]::GetFullPath($OutputPath)
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))|Out-Null
$report|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $destination -Encoding utf8
Write-Output $destination
