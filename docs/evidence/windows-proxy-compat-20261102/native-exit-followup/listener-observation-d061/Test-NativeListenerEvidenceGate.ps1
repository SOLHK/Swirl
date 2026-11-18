param([Parameter(Mandatory)][string]$CriticalScript,[Parameter(Mandatory)][string]$OriginalControlReceipt)
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($CriticalScript,[ref]$tokens,[ref]$errors)
if($errors.Count){$errors|ForEach-Object {Write-Error $_.Message};exit 1}
foreach($name in @('Assert-NativeTcpState','Assert-ExclusivePortOccupied','Assert-NativeListenerReleased')){
    $function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
    if($null -eq $function){throw "Missing actual CI function: $name"}
    . ([scriptblock]::Create($function.Extent.Text))
}
$actual=Get-Content -LiteralPath $OriginalControlReceipt -Raw|ConvertFrom-Json
$connection=$actual.current.closed
if($connection.connected -or $connection.outcome -ne 'deadline'){throw 'Expected the preserved native known-closed deadline observation'}
$valid=[pscustomobject]@{
    connection=$connection
    tcp=[pscustomobject]@{
        ipv4=[pscustomobject]@{family=2;win32_error=0;rows=@([pscustomobject]@{state=12;pid=0})}
        ipv6=[pscustomobject]@{family=23;win32_error=0;rows=@()}
    }
    exclusive=[pscustomobject]@{exclusive_option=$true;bound=$true;listening=$true;stage='listening';win32_error=0}
}
$validJson=$valid|ConvertTo-Json -Depth 10
function Invoke-Receipt($receipt){Assert-NativeListenerReleased $receipt.connection $receipt.tcp $receipt.exclusive 'contract fixture'}
Invoke-Receipt $valid
$deadlineOnlyRejected=$false
try{Assert-NativeListenerReleased $connection $null $null 'preserved real deadline only'}catch{$deadlineOnlyRejected=$true}
if(-not $deadlineOnlyRejected){throw 'An actual deadline without positive release evidence was accepted'}
$cases=@(
    @{name='missing table';mutate={param($r) $r.tcp.ipv6=$null}},
    @{name='unreadable table';mutate={param($r) $r.tcp.ipv4.win32_error=5}},
    @{name='wrong family';mutate={param($r) $r.tcp.ipv6.family=2}},
    @{name='missing rows';mutate={param($r) $r.tcp.ipv4.rows=$null}},
    @{name='listener remains';mutate={param($r) $r.tcp.ipv4.rows=@([pscustomobject]@{state=2;pid=123})}},
    @{name='invalid native state';mutate={param($r) $r.tcp.ipv4.rows=@([pscustomobject]@{state=0;pid=0})}},
    @{name='not exclusive';mutate={param($r) $r.exclusive.exclusive_option=$false}},
    @{name='not bound';mutate={param($r) $r.exclusive.bound=$false}},
    @{name='not listening';mutate={param($r) $r.exclusive.listening=$false}},
    @{name='wrong stage';mutate={param($r) $r.exclusive.stage='bind'}},
    @{name='native bind error';mutate={param($r) $r.exclusive.win32_error=10048}},
    @{name='actual connection';mutate={param($r) $r.connection.connected=$true}},
    @{name='missing connection observation';mutate={param($r) $r.connection=$null}},
    @{name='string instead of bool';mutate={param($r) $r.exclusive.listening='true'}}
)
$rejected=@()
foreach($case in $cases){
    $candidate=$validJson|ConvertFrom-Json
    & $case.mutate $candidate
    $rejectedCase=$false
    try{Invoke-Receipt $candidate}catch{$rejectedCase=$true}
    if(-not $rejectedCase){throw "Unsafe or incomplete release evidence accepted: $($case.name)"}
    $rejected+=$case.name
}
$liveTcp=$validJson|ConvertFrom-Json
$liveTcp.tcp.ipv4.rows=@([pscustomobject]@{state=2;pid=123})
Assert-NativeTcpState $liveTcp.tcp $true 'live fixture'
$occupied=[pscustomobject]@{exclusive_option=$true;bound=$false;listening=$false;stage='bind';win32_error=10048}
Assert-ExclusivePortOccupied $occupied 'live fixture'
$falseLiveRejected=$false
try{Assert-ExclusivePortOccupied $valid.exclusive 'falsely accepted live port'}catch{$falseLiveRejected=$true}
if(-not $falseLiveRejected){throw 'A successful live-port exclusive bind was accepted as an occupied-port control'}
[ordered]@{
    scope='Local validation of actual CI PowerShell functions with recorded deadline and synthetic ownership receipts; not native Windows execution'
    parse_errors=$errors.Count
    critical_script_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $CriticalScript).Hash.ToLowerInvariant()
    original_control_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $OriginalControlReceipt).Hash.ToLowerInvariant()
    deadline_without_positive_evidence_rejected=$deadlineOnlyRejected
    synthetic_complete_release_with_time_wait_accepted=$true
    invalid_receipts_rejected=$rejected
    live_tcp_listener_detected=$true
    live_exclusive_rejection_accepted=$true
    incorrect_live_exclusive_success_rejected=$falseLiveRejected
}|ConvertTo-Json -Depth 5
