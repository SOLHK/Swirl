# Offline, allowlisted summaries only. Never export arbitrary log text, account
# identifiers, header values, URLs, query strings, stack traces or token files.
Set-StrictMode -Version Latest

function ConvertFrom-CodexNetworkLogLine {
    param([Parameter(Mandatory)][string]$Line, [int]$FileIndex, [int]$LineNumber)
    if ($Line.Length -gt 16384 -or $Line -notmatch '\A(?<stamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z) (warning|error) \[') { return }
    $stamp = $Matches.stamp
    $isRequest = $Line.Contains('[electron-message-handler] sa_server_request_failed ')
    $isRpc = $Line.Contains('[electron-message-handler] Request failed ')
    $isRelease = $Line.Contains('[windows-offers] Windows release marker unavailable ')
    if (!$isRequest -and !$isRpc -and !$isRelease) { return }
    $category = $null; $layer = $null; $status = $null
    $code = $null; $route = $null
    if ($Line -match '(?:\A| )errorCode=(ERR_[A-Z_]+|cloudflare_challenge)(?: |\z)') { $code = $Matches[1] }
    if ($Line -match '(?:\A| )status=([1-5][0-9]{2})(?: |\z)') { $status = [int]$Matches[1] }
    $routes = @('/settings/user','/accounts/check/{version}','/accounts/optimized/check','/wham/usage','/profiles/me','/wham/statsig/bootstrap')
    if ($isRequest -and $Line -match '(?:\A| )routePattern=([^ ]+)(?: |\z)') {
        $route = if ($Matches[1] -cin $routes) { $Matches[1] } else { 'other' }
    }
    if ($isRpc -and $Line -match '(?:\A| )method=account/read(?: |\z)' -and $Line.Contains('"message":"workspace routing discovery failed"')) {
        $category = 'workspace_routing_discovery_failed'; $layer = 'local_app_server_rpc'
    } elseif ($isRequest -and $status -eq 432 -and $Line.Contains('errorMessage="Workspace routing is unavailable"')) {
        # The installed desktop wraps getBackendRequestAuth failure with this
        # synthetic status BEFORE fetch; 432 here is not an OpenAI HTTP reply.
        $category = 'workspace_routing_unavailable'; $layer = 'local_workspace_gate'
    } elseif ($isRequest -and $status -eq 403 -and $code -ceq 'cloudflare_challenge') {
        # Require the desktop's explicit classification AND HTTP status. A
        # generic 403 or text mentioning Cloudflare does not establish this.
        $category = 'cloudflare_challenge'; $layer = 'server_security_response'
    } else {
        if (!$code -and $Line -match '(?:\A| )errorMessage=net::(ERR_[A-Z_]+)(?: |\z)') { $code = $Matches[1] }
        switch ($code) {
            'ERR_PROXY_CONNECTION_FAILED' { $category = 'proxy_connection_failed'; $layer = 'proxy_connection' }
            'ERR_TUNNEL_CONNECTION_FAILED' { $category = 'proxy_tunnel_failed'; $layer = 'proxy_tunnel' }
            'ERR_PROXY_AUTH_REQUESTED' { $category = 'proxy_authentication_required'; $layer = 'proxy_authentication' }
            'ERR_NAME_NOT_RESOLVED' { $category = 'name_resolution_failed'; $layer = 'name_resolution' }
            'ERR_CERT_AUTHORITY_INVALID' { $category = 'certificate_validation_failed'; $layer = 'tls' }
            'ERR_CERT_COMMON_NAME_INVALID' { $category = 'certificate_validation_failed'; $layer = 'tls' }
            'ERR_CERT_DATE_INVALID' { $category = 'certificate_validation_failed'; $layer = 'tls' }
            'ERR_SSL_PROTOCOL_ERROR' { $category = 'tls_protocol_failed'; $layer = 'tls' }
            'ERR_CONNECTION_CLOSED' { $category = 'connection_closed'; $layer = 'transport' }
            'ERR_CONNECTION_RESET' { $category = 'connection_reset'; $layer = 'transport' }
            'ERR_CONNECTION_TIMED_OUT' { $category = 'connection_timed_out'; $layer = 'transport' }
            'ERR_TIMED_OUT' { $category = 'request_timed_out'; $layer = 'transport' }
            default { if ($isRequest -and $status) { $category = 'http_status_requires_correlation'; $layer = 'unverified_http_or_local_wrapper' } }
        }
    }
    if (!$category) { return }
    [pscustomobject][ordered]@{timeUtc=$stamp;fileIndex=$FileIndex;line=$LineNumber;category=$category;layer=$layer;status=$status;route=$route}
}

function Test-CodexLocalDirectory {
    param([Parameter(Mandatory)][string]$Path)
    if ($Path -notmatch '\A[A-Za-z]:[\\/]') { throw 'Codex log directory must be a local absolute drive path.' }
    # Inspect each ancestor: an ordinary leaf below a junction must not route
    # this offline collector into browser storage or a remote share.
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        $item = Get-Item -LiteralPath $current -ErrorAction SilentlyContinue
        if (!$item -or !$item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { return $false }
        $parent = [IO.Directory]::GetParent($current)
        $current = if ($parent) { $parent.FullName } else { $null }
    }
    return $true
}

function Get-CodexLogDirectories {
    [CmdletBinding()]
    param([string]$LocalAppData=$env:LOCALAPPDATA,
          [DateTimeOffset]$Now=[DateTimeOffset]::UtcNow)
    if (!(Test-CodexLocalDirectory $LocalAppData)) { return }
    $roots = [Collections.Generic.List[string]]::new()
    $roots.Add((Join-Path $LocalAppData 'Codex/Logs'))
    $packages = Join-Path $LocalAppData 'Packages'
    if (Test-CodexLocalDirectory $packages) {
        # Both unpackaged and Store installations are supported. Never recurse
        # through the package profile, which also contains authentication data.
        foreach ($package in @(Get-ChildItem -LiteralPath $packages -Directory -Filter 'OpenAI.Codex_*' -ErrorAction SilentlyContinue | Select-Object -First 8)) {
            if ($package.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
            $roots.Add((Join-Path $package.FullName 'LocalCache/Local/Codex/Logs'))
        }
    }
    foreach ($root in $roots) {
        # Desktop uses UTC folders. Include the previous two days so a quiet
        # current session or a local-midnight rollover cannot hide prior errors.
        foreach ($offset in 0..2) {
            $directory=Join-Path $root $Now.UtcDateTime.AddDays(-$offset).ToString('yyyy/MM/dd')
            if (Test-CodexLocalDirectory $directory) { $directory }
        }
    }
}

function Get-CodexLogSummary {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()][string[]]$LogDirectory,
          [ValidateRange(1,24)][int]$MaxFiles=12,
          [ValidateRange(1,512)][int]$MaxEvents=128,
          [ValidateRange(1024,67108864)][long]$MaxFileBytes=33554432)
    $events = [Collections.Generic.List[object]]::new()
    $counts = @{}; $filesRead=0; $filesSkipped=0; $linesSkipped=0; $unreadable=0; $duplicates=0
    $state = 'no_logs'
    # Reject remote/device paths BEFORE filesystem access. This collector must
    # not contact shares or read arbitrary per-account browser/auth storage.
    $directories=@($LogDirectory | ForEach-Object {
        if (Test-CodexLocalDirectory $_) { [IO.Path]::GetFullPath($_) }
    } | Select-Object -Unique)
    if ($directories.Count) {
        $files = @(foreach ($directory in $directories) {
            Get-ChildItem -LiteralPath $directory -Filter 'codex-desktop-*.log' -File -ErrorAction SilentlyContinue
        }) | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First $MaxFiles
        $duplicateNames=@{}; $seenCopies=@{}
        foreach ($group in @($files | Group-Object Name | Where-Object Count -gt 1)) { $duplicateNames[$group.Name]=$true }
        $index=0
        foreach ($file in $files) {
            ++$index
            if ($file.Length -gt $MaxFileBytes -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) { ++$filesSkipped; continue }
            $reader=$null; $stream=$null
            try {
                $stream=[IO.File]::Open($file.FullName,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
                if ($duplicateNames.ContainsKey($file.Name)) {
                    # Store path virtualization may expose the same session at
                    # both roots. Equal names alone are insufficient: dedupe
                    # only byte-identical bounded files, retaining distinct logs.
                    $hasher=[Security.Cryptography.SHA256]::Create()
                    try { $fingerprint=$file.Name+':'+[Convert]::ToBase64String($hasher.ComputeHash($stream)) }
                    finally { $hasher.Dispose() }
                    if ($seenCopies.ContainsKey($fingerprint)) { ++$duplicates; continue }
                    $seenCopies[$fingerprint]=$true
                    $stream.Position=0
                }
                $reader=[IO.StreamReader]::new($stream)
                ++$filesRead; $number=0
                while (!$reader.EndOfStream) {
                    $text=$reader.ReadLine(); ++$number
                    if ($text.Length -gt 16384) { ++$linesSkipped; continue }
                    $event=ConvertFrom-CodexNetworkLogLine -Line $text -FileIndex $index -LineNumber $number
                    if (!$event) { continue }
                    $key=$event.category
                    if (!$counts.ContainsKey($key)) { $counts[$key]=0 }
                    ++$counts[$key]
                    $events.Add($event)
                    if ($events.Count -gt $MaxEvents) {
                        # Files are visited by modification time; keep events
                        # by their own timestamps so old files cannot evict
                        # the latest failure from a more recent startup.
                        $oldest=0
                        for ($j=1;$j -lt $events.Count;++$j) { if ([string]::CompareOrdinal($events[$j].timeUtc,$events[$oldest].timeUtc) -lt 0) { $oldest=$j } }
                        $events.RemoveAt($oldest)
                    }
                }
            } catch { ++$unreadable } finally { if ($reader) { $reader.Dispose() } elseif ($stream) { $stream.Dispose() } }
        }
        if ($filesRead) { $state='read_existing_logs' }
    }
    $latest=@($events | Sort-Object timeUtc -Descending | Select-Object -First 24)
    [pscustomobject][ordered]@{schemaVersion=1;mode='offline_existing_logs';state=$state;filesRead=$filesRead;filesSkipped=$filesSkipped;duplicateFilesSkipped=$duplicates;unreadableFiles=$unreadable;oversizedLinesSkipped=$linesSkipped;counts=$counts;latestEvents=$latest;
        interpretation=@('workspace_routing_unavailable with the exact 432 message is a local Codex workspace gate, not an OpenAI HTTP 432 response.','workspace_routing_discovery_failed does not establish why discovery failed: correlate proxy state, transport logs and user retest.','cloudflare_challenge requires the desktop classification and status 403; it establishes a security response, not its trigger or a Swirl defect.','HTTP status without a recognized transport error needs correlation; this summary does not prove server authentication or workspace health.','Only fixed categories and allowlisted route patterns are exported. No requests, account tokens, browser storage or system settings are changed.')}
}

Export-ModuleMember -Function Get-CodexLogDirectories,Get-CodexLogSummary,ConvertFrom-CodexNetworkLogLine
