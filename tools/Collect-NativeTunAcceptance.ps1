#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [ValidateSet('Baseline','Sample','ScopedDriverSmoke')][string]$Mode='Baseline',
    [ValidateSet('Unknown','Physical','Virtual')][string]$MachineClass='Unknown',
    [string]$Wintun,
    [string]$SmokeExecutable,
    [switch]$DisposableNetwork,
    [ValidateRange(1,2147483647)][int]$ProcessId=1,
    [ValidateRange(1,86400)][int]$DurationSeconds=1800,
    [ValidateRange(1,60)][int]$IntervalSeconds=5,
    [ValidateRange(1,1048576)][int]$MaxRssMiB=512,
    [ValidateRange(1,10000000)][int]$MaxHandles=4096
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if (-not $IsWindows) { throw 'This collector requires Windows; no network operation was attempted.' }
if ($Mode -eq 'ScopedDriverSmoke' -and -not $DisposableNetwork) {
    throw 'ScopedDriverSmoke requires -DisposableNetwork and an authorized recoverable disposable machine.'
}
if ($Mode -eq 'Sample' -and -not $PSBoundParameters.ContainsKey('ProcessId')) {
    throw 'Sample requires an explicit -ProcessId; the collector does not choose a user process.'
}
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$source=(& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $source -notmatch '^[0-9a-f]{40}$') { throw 'Exact Git source identity is required.' }
$dirty=!!(& git -C $repo status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0) { throw 'Could not determine source working tree state.' }
if ($Mode -eq 'ScopedDriverSmoke' -and $dirty) { throw 'Scoped driver acceptance requires clean identified source.' }
$output=[IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Evidence requires a fresh output directory; existing evidence is never overwritten.' }
New-Item -ItemType Directory -Path $output | Out-Null
function Save-Json([string]$Name,$Value) {
    ConvertTo-Json -InputObject $Value -Depth 20 | Set-Content -LiteralPath (Join-Path $output $Name) -Encoding utf8NoBOM
}
function Hash-File([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Fingerprint($Value) {
    $bytes=[Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject $Value -Depth 12 -Compress))
    [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
}
function Inventory([scriptblock]$Read) {
    try { [ordered]@{status='observed';data=(& $Read)} }
    catch { [ordered]@{status='unavailable';error_type=$_.Exception.GetType().Name} }
}
function Network-Snapshot {
    # Keep names, SSIDs, addresses, endpoints, profiles and rule contents local:
    # exported evidence contains counts and whole-schema fingerprints only.
    [ordered]@{
        adapters=Inventory {
            $items=@(Get-NetAdapter -IncludeHidden | Sort-Object InterfaceIndex |
                Select-Object InterfaceIndex,InterfaceGuid,Status,HardwareInterface,Virtual)
            @{count=$items.Count;hardware=@($items|Where-Object HardwareInterface).Count;fingerprint=(Fingerprint $items)}
        }
        routes=Inventory {
            $items=@(Get-NetRoute -PolicyStore ActiveStore | Sort-Object InterfaceIndex,DestinationPrefix,NextHop |
                Select-Object InterfaceIndex,AddressFamily,DestinationPrefix,NextHop,RouteMetric,Protocol,Publish)
            @{count=$items.Count;ipv4=@($items|Where-Object AddressFamily -eq IPv4).Count;
                ipv6=@($items|Where-Object AddressFamily -eq IPv6).Count;
                default_routes=@($items|Where-Object DestinationPrefix -in @('0.0.0.0/0','::/0')).Count;
                split_defaults=@($items|Where-Object DestinationPrefix -in @('0.0.0.0/1','128.0.0.0/1','::/1','8000::/1')).Count;
                fingerprint=(Fingerprint $items)}
        }
        dns=Inventory {
            $items=@(Get-DnsClientServerAddress | Sort-Object InterfaceIndex,AddressFamily |
                Select-Object InterfaceIndex,AddressFamily,ServerAddresses)
            @{interfaces=$items.Count;configured=@($items|Where-Object {$_.ServerAddresses.Count -gt 0}).Count;
                fingerprint=(Fingerprint $items)}
        }
        firewall=Inventory {
            $profiles=@(Get-NetFirewallProfile -PolicyStore ActiveStore |
                Sort-Object Name | Select-Object Name,Enabled,AllowLocalFirewallRules,DefaultOutboundAction)
            $rules=@(Get-NetFirewallRule -PolicyStore ActiveStore | Where-Object Name -Like 'Swirl.NativeTun.DNS.*')
            $filters=@($rules | Get-NetFirewallPortFilter | Select-Object Protocol,LocalPort,RemotePort)
            @{service=[string](Get-Service mpssvc).Status;profiles=$profiles;
                owned_active_rule_count=$rules.Count;
                enabled_outbound_blocks=@($rules | Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Outbound' -and $_.Action -eq 'Block' }).Count;
                port53_filters=@($filters|Where-Object RemotePort -eq '53').Count;
                rules_fingerprint=(Fingerprint @($rules|Sort-Object Name|Select-Object Name,Enabled,Direction,Action,Profile));
                filters_fingerprint=(Fingerprint $filters)}
        }
    }
}
$os=Get-CimInstance Win32_OperatingSystem -Property Caption,Version,BuildNumber,ProductType
$computer=Get-CimInstance Win32_ComputerSystem -Property Manufacturer,Model,PCSystemType,NumberOfLogicalProcessors
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=[Security.Principal.WindowsPrincipal]::new($identity)
$elevated=$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$environment=[ordered]@{
    os=@{caption=$os.Caption;version=$os.Version;build=$os.BuildNumber;product_type=[int]$os.ProductType;
        windows_11=([int]$os.ProductType -eq 1 -and [int]$os.BuildNumber -ge 22000)};
    machine=@{manufacturer=$computer.Manufacturer;model=$computer.Model;class=$MachineClass;class_source='operator';
        logical_processors=[int]$computer.NumberOfLogicalProcessors};
    elevated=$elevated;power_shell=$PSVersionTable.PSVersion.ToString();architecture=[Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
}
$driver=$null
if ($Wintun) {
    $driverPath=(Resolve-Path -LiteralPath $Wintun).Path
    if ($driverPath -notmatch '^[A-Za-z]:[\\/]') { throw 'Driver must be an explicit local absolute path.' }
    $file=Get-Item -LiteralPath $driverPath
    $driver=@{sha256=(Hash-File $driverPath);file_version=$file.VersionInfo.FileVersion;version_expected='0.14.1'}
}
$observationTarget=$null
if ($Mode -eq 'Sample') {
    $process=Get-Process -Id $ProcessId
    $initialStart=$process.StartTime.ToUniversalTime().ToString('o')
    $observationTarget=@{process_id=$ProcessId;process_start_utc=$initialStart}
}
$plan=[ordered]@{schema=1;run_id=[guid]::NewGuid().ToString();created_utc=[DateTime]::UtcNow.ToString('o');
    source_sha=$source;source_dirty=$dirty;collector_sha256=(Hash-File $PSCommandPath);mode=$Mode;environment=$environment;driver=$driver;
    observation_target=$observationTarget;
    load=@{generator='external; not started or inferred by collector';duration_seconds=$DurationSeconds;
        interval_seconds=$IntervalSeconds;max_rss_mib=$MaxRssMiB;max_handles=$MaxHandles};
    scope='read-only inventory and optional process sampling; scoped driver smoke only with explicit authorization';
    physical_windows_11_acceptance=$false}
Save-Json 'plan.json' $plan
$started=[DateTime]::UtcNow.ToString('o')
$before=Network-Snapshot
Save-Json 'network-before.json' $before
$record=[ordered]@{schema=1;plan_sha256=(Hash-File (Join-Path $output 'plan.json'));started_utc=$started;
    finished_utc=$null;source_sha=$source;mode=$Mode;status='recorded';
    physical_windows_11_acceptance=$false;artifacts=@();command=@{collector_sha256=(Hash-File $PSCommandPath);
        arguments=@('-Mode',$Mode,'-MachineClass',$MachineClass,'-DurationSeconds',[string]$DurationSeconds,
            '-IntervalSeconds',[string]$IntervalSeconds,'-MaxRssMiB',[string]$MaxRssMiB,'-MaxHandles',[string]$MaxHandles);
        process_id=if($Mode -eq 'Sample'){$ProcessId}else{$null};exit_code=0};
    limitations=@('Counts and fingerprints are read-only observations, not a DNS/IPv6 leak test.',
        'Application DoH/DoT, packet paths and firewall effectiveness are not inferred from rule presence.',
        'Process samples do not generate load, establish throughput or certify task/socket/Wintun leak freedom.',
        'ScopedDriverSmoke uses loopback peers and exact test routes, never physical full-tunnel acceptance.')}
$failed=$false
try {
    if ($Mode -eq 'Sample') {
        $samples=[Collections.Generic.List[object]]::new()
        $timer=[Diagnostics.Stopwatch]::StartNew()
        do {
            $process.Refresh()
            if ($process.HasExited -or $process.StartTime.ToUniversalTime().ToString('o') -ne $initialStart) {
                throw 'Observed process exited or its identity changed; the resource run is incomplete.'
            }
            $sample=@{elapsed_seconds=$timer.Elapsed.TotalSeconds;rss_bytes=[long]$process.WorkingSet64;
                private_bytes=[long]$process.PrivateMemorySize64;handles=$process.HandleCount;
                cpu_seconds=$process.TotalProcessorTime.TotalSeconds;threads=$process.Threads.Count}
            $samples.Add($sample)
            if ($sample.elapsed_seconds -ge $DurationSeconds) { break }
            Start-Sleep -Seconds ([Math]::Min($IntervalSeconds,[Math]::Max(0.05,$DurationSeconds-$timer.Elapsed.TotalSeconds)))
        } while ($true)
        Save-Json 'resource-samples.json' @{process_id=$ProcessId;process_start_utc=$initialStart;samples=@($samples)}
        $record.status='recorded' # The verifier computes threshold results from samples.
    } elseif ($Mode -eq 'ScopedDriverSmoke') {
        if (-not $elevated -or -not $driver -or -not $SmokeExecutable) {
            throw 'ScopedDriverSmoke requires an elevated disposable machine, -Wintun and -SmokeExecutable.'
        }
        $smoke=(Resolve-Path -LiteralPath $SmokeExecutable).Path
        if ($smoke -notmatch '^[A-Za-z]:[\\/]') { throw 'Smoke executable must be a local absolute path.' }
        $log=Join-Path $output 'scoped-driver.log'
        # Preserve the existing smoke recovery contract. Do not terminate it with
        # a wrapper timeout while it owns a transaction; its operations have their
        # own deadlines and its finally path must perform exact restoration.
        $record.command=@{collector_sha256=(Hash-File $PSCommandPath);executable_sha256=(Hash-File $smoke);executable_name=[IO.Path]::GetFileName($smoke);
            arguments=@('--disposable-network','--wintun','<explicit locally hashed Wintun DLL>')}
        & $smoke --disposable-network --wintun $driverPath 2>&1 | Tee-Object -FilePath $log | Out-Null
        $record.command.exit_code=$LASTEXITCODE
        if ($LASTEXITCODE -ne 0) { $failed=$true;$record.status='failed' }
    }
} catch {
    $record.status='failed';$record.command.exit_code=1;$record.error_type=$_.Exception.GetType().Name;$failed=$true
} finally {
    Save-Json 'network-after.json' (Network-Snapshot)
    $record.finished_utc=[DateTime]::UtcNow.ToString('o')
    foreach ($name in @('network-before.json','network-after.json','resource-samples.json','scoped-driver.log')) {
        $path=Join-Path $output $name
        if (Test-Path -LiteralPath $path -PathType Leaf) { $record.artifacts+=@{path=$name;sha256=(Hash-File $path)} }
    }
    Save-Json 'result.json' $record
}
Write-Output $output
if ($failed) { throw 'Acceptance collection failed. Preserve the evidence and inspect owned recovery state before retrying.' }
