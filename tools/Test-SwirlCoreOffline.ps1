# Read-only, localhost-only check of the currently running Windows Swirl proxy.
# This script does not send a SOCKS CONNECT request or contact a public target.
param(
    [ValidateRange(1,65535)][int]$Port = 7898,
    [ValidateRange(1,30)][int]$TimeoutSeconds = 3,
    [string]$ExpectedSourceSha = ''
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'SwirlCoreIdentity.ps1')
$result = [ordered]@{
    schemaVersion = 1
    status = 'BLOCKED'
    reason = ''
    listenerPort = $Port
    listenerPid = $null
    processName = $null
    sourceSha = $null
    productIdentityFormat = $null
    rustBuildId = $null
    rulesHashesVerified = $false
    publisherAuthenticity = 'NOT_VERIFIED'
    executableHashMatchesManifest = $false
    rustDllHashMatchesManifest = $false
    rustDllLoadedInListener = $false
    rustBuildFlagEnabled = $false
    productDeclaresRustCore = $false
    otherCoreModuleLoaded = $false
    socks5LocalGreeting = 'NOT_TESTED'
    systemProxyPointsToListener = 'UNKNOWN'
    publicEgressIndependence = 'NOT_TESTED'
    changedNetworkSettings = $false
}

if (-not [Environment]::Is64BitProcess) {
    $result.reason = '64-bit Windows PowerShell is required to inspect the Swirl Rust DLL.'
    $result | ConvertTo-Json -Depth 3
    exit 2
}

function Get-ListenerPid([int]$LocalPort) {
    $rows = @(Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -in @('127.0.0.1','0.0.0.0') })
    $ids = @($rows | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($ids.Count -ne 1) { throw "Expected exactly one IPv4 listener on port $LocalPort; found $($ids.Count)." }
    return [int]$ids[0]
}

function Read-Exactly([System.IO.Stream]$Stream, [int]$Count) {
    $bytes = New-Object byte[] $Count
    $offset = 0
    while ($offset -lt $Count) {
        $n = $Stream.Read($bytes, $offset, $Count - $offset)
        if ($n -eq 0) { throw 'Local proxy closed during SOCKS5 greeting.' }
        $offset += $n
    }
    return $bytes
}

try {
    $pidBefore = Get-ListenerPid $Port
    $result.listenerPid = $pidBefore
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$pidBefore"
    if (-not $process) { throw 'The listener process could not be inspected.' }
    $result.processName = $process.Name
    if ($process.Name -ine 'Swirl.exe') {
        $result.status = 'FAIL'
        throw 'The listener belongs to a process other than Swirl.exe.'
    }
    if (-not $process.ExecutablePath) { throw 'Swirl.exe path is unavailable to this user.' }
    $exe = [System.IO.Path]::GetFullPath($process.ExecutablePath)
    $folder = Split-Path -Parent $exe
    $dllPath = Join-Path $folder 'swirl_api.dll'
    $identity = Get-SwirlInstalledIdentity -Directory $folder -ExpectedSourceSha $ExpectedSourceSha
    $result.sourceSha = $identity.sourceSha
    $result.productIdentityFormat = $identity.format
    $result.rustBuildId = $identity.buildId
    $result.rulesHashesVerified = $identity.rulesHashesVerified
    $result.productDeclaresRustCore = $identity.productDeclaresRustCore
    $result.rustBuildFlagEnabled = $identity.rustBuildFlagEnabled
    $result.executableHashMatchesManifest = $identity.executableHashMatchesManifest
    $result.rustDllHashMatchesManifest = $identity.rustDllHashMatchesManifest

    $live = Get-Process -Id $pidBefore -ErrorAction Stop
    $start = $live.StartTime.ToUniversalTime()
    if ((Get-Item -LiteralPath $exe).LastWriteTimeUtc -gt $start -or
        (Get-Item -LiteralPath $dllPath).LastWriteTimeUtc -gt $start) {
        throw 'Executable or Rust DLL changed on disk after this process started; loaded image identity is uncertain.'
    }
    $modules = @($live.Modules)
    $rustModules = @($modules | Where-Object { $_.ModuleName -ieq 'swirl_api.dll' })
    $result.rustDllLoadedInListener = ($rustModules.Count -eq 1 -and
        [System.IO.Path]::GetFullPath($rustModules[0].FileName) -ieq [System.IO.Path]::GetFullPath($dllPath))
    $result.otherCoreModuleLoaded = (@($modules | Where-Object {
        $_.ModuleName -match '(?i)mihomo|clash|sing-box|xray|v2ray'
    }).Count -gt 0)

    # Read WinINET's static proxy value only. Do not evaluate a PAC URL.
    $inet = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    if ($inet.ProxyEnable -eq 1 -and -not $inet.AutoConfigURL) {
        $entries = @([string]$inet.ProxyServer -split ';' | ForEach-Object { $_.Trim() })
        $addresses = @($entries | ForEach-Object { ($_ -split '=',2)[-1] })
        $result.systemProxyPointsToListener = if ($addresses -contains "127.0.0.1:$Port") { 'YES' } else { 'NO' }
    }

    if (-not ($result.productDeclaresRustCore -and $result.rustBuildFlagEnabled -and
        $result.executableHashMatchesManifest -and $result.rustDllHashMatchesManifest -and
        $result.rustDllLoadedInListener) -or $result.otherCoreModuleLoaded) {
        $result.status = 'FAIL'
        throw 'Rust build identity, module ownership, or file integrity check failed.'
    }

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync('127.0.0.1', $Port)
        if (-not $task.Wait($TimeoutSeconds * 1000)) { throw 'Local proxy connection timed out.' }
        $client.ReceiveTimeout = $TimeoutSeconds * 1000
        $client.SendTimeout = $TimeoutSeconds * 1000
        $stream = $client.GetStream()
        # Advertise no-auth and username/password; do not send credentials or CONNECT.
        $stream.Write([byte[]]@(5,2,0,2), 0, 4)
        $reply = Read-Exactly $stream 2
        if ($reply[0] -ne 5 -or $reply[1] -notin @(0,2)) {
            $result.status = 'FAIL'
            throw 'The local listener did not return a valid SOCKS5 method selection.'
        }
        $result.socks5LocalGreeting = 'PASS'
    } finally {
        $client.Dispose()
    }
    if ((Get-ListenerPid $Port) -ne $pidBefore) { throw 'Listener PID changed during the local challenge.' }
    $result.status = 'PASS'
    $result.reason = 'Active listener matches the reported Rust package and answered a local SOCKS5 greeting; public routing and publisher authenticity were not verified.'
} catch {
    if ($result.status -ne 'FAIL') {
        $result.status = if ($result.socks5LocalGreeting -eq 'PASS') { 'FAIL' } else { 'BLOCKED' }
    }
    $result.reason = $_.Exception.Message
}

$result | ConvertTo-Json -Depth 3
if ($result.status -eq 'PASS') { exit 0 }
if ($result.status -eq 'BLOCKED') { exit 2 }
exit 1
