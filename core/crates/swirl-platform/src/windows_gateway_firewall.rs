//! An owned Windows Firewall exception for the independently attested DHCP
//! socket. WFP isolation is installed first; this ordinary allow rule never
//! overrides an external block, enables a firewall profile or changes defaults.
use crate::{
    gateway_policy::{GatewayDhcpFirewallScope, GatewayIsolationPolicy},
    windows_network::run_json,
};
use serde_json::json;
use std::{io, path::PathBuf};

pub(crate) fn installed_dhcp_image() -> io::Result<PathBuf> {
    let executable = std::env::current_exe()?;
    let parent = executable
        .parent()
        .ok_or_else(|| io::Error::other("helper installation path is unavailable"))?;
    parent.join("Swirl.exe").canonicalize()
}

fn program() -> io::Result<String> {
    let image = installed_dhcp_image()?;
    let image = image
        .to_str()
        .ok_or_else(|| io::Error::other("DHCP image path is not Unicode"))?;
    Ok(image.strip_prefix(r"\\?\").unwrap_or(image).to_owned())
}

fn template(policy: &GatewayIsolationPolicy) -> GatewayDhcpFirewallScope {
    GatewayDhcpFirewallScope {
        owner: policy.owner.clone(),
        lan: policy.lan.clone(),
        interface_alias: String::new(),
        program: String::new(),
        gateway: policy.gateway,
        subnet: policy.subnet,
        allowed_sources: policy.allowed_sources.clone(),
        enabled: true,
    }
}

fn input(policy: &GatewayIsolationPolicy, mode: &str) -> serde_json::Value {
    let scope = template(policy);
    json!({"mode":mode,"policy":policy,"name":scope.name(),
        "local_addresses":scope.local_addresses(),"remote_addresses":scope.remote_addresses()})
}

/// Capture the exact image and alias before creating the durable plan. This
/// performs no firewall mutation and does not attest that DHCP has started.
pub(crate) fn scope(policy: &GatewayIsolationPolicy) -> io::Result<GatewayDhcpFirewallScope> {
    policy.validate()?;
    if !policy.dhcp {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "DHCP is not enabled for this gateway",
        ));
    }
    let mut request = input(policy, "scope");
    request["program"] = json!(program()?);
    let scope: GatewayDhcpFirewallScope = run_json(SCRIPT, &request)?;
    scope.validate()?;
    if !scope.enabled || !scope.matches_policy(policy) {
        return Err(io::Error::other(
            "DHCP firewall snapshot differs from gateway policy",
        ));
    }
    Ok(scope)
}

pub(crate) fn read(
    policy: &GatewayIsolationPolicy,
) -> io::Result<Option<GatewayDhcpFirewallScope>> {
    policy.validate()?;
    let observed: Option<GatewayDhcpFirewallScope> = run_json(SCRIPT, &input(policy, "read"))?;
    if let Some(scope) = &observed {
        scope.validate()?;
        if !scope.matches_policy(policy) {
            return Err(io::Error::other("gateway DHCP firewall ownership changed"));
        }
    }
    Ok(observed)
}

/// An installed PersistentStore rule alone is insufficient: verify the exact
/// ActiveStore rule, local-rule merging and inbound-rule policy as well.
pub(crate) fn verify(policy: &GatewayIsolationPolicy) -> io::Result<()> {
    policy.validate()?;
    let mut request = input(policy, "verify");
    request["program"] = json!(program()?);
    if !run_json::<bool>(SCRIPT, &request)? {
        return Err(io::Error::other("gateway DHCP firewall is not effective"));
    }
    Ok(())
}

pub(crate) fn compare_exchange(
    policy: &GatewayIsolationPolicy,
    expected: &Option<GatewayDhcpFirewallScope>,
    desired: &Option<GatewayDhcpFirewallScope>,
) -> io::Result<()> {
    policy.validate()?;
    for scope in expected.iter().chain(desired.iter()) {
        scope.validate()?;
        if !scope.matches_policy(policy) {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "DHCP firewall scope is outside the owned gateway",
            ));
        }
    }
    if !matches!((expected, desired), (None, Some(_)) | (Some(_), None)) {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "DHCP firewall rules cannot be adopted or replaced",
        ));
    }
    let mut request = input(policy, "compare_exchange");
    request["expected"] = json!(expected);
    request["desired"] = json!(desired);
    let observed: Option<GatewayDhcpFirewallScope> = run_json(SCRIPT, &request).map_err(|error| {
        if error.to_string().starts_with("Windows network operation failed: DHCP firewall changed after snapshot; refusing overwrite") {
            io::Error::new(io::ErrorKind::AlreadyExists, error)
        } else { error }
    })?;
    if &observed != desired {
        return Err(io::Error::other("gateway DHCP firewall readback mismatch"));
    }
    Ok(())
}

// All input is typed, bounded JSON on stdin through the existing 30-second
// helper boundary. Only one nonce-owned rule is queried/removed. The firewall
// cmdlets return address masks in more than one documented representation;
// compare exact IPv4 ranges, never names such as Any or LocalSubnet.
const SCRIPT: &str = r#"
$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'
[Console]::InputEncoding=New-Object Text.UTF8Encoding($false)
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$script:gatewayFirewallStage='scope'
try {
  $p=[Console]::In.ReadToEnd() | ConvertFrom-Json
  $policy=$p.policy; $name=[string]$p.name
  function Owned-Adapter {
    $script:gatewayFirewallStage='preflight-adapter'
    $adapters=@(Get-NetAdapter -IncludeHidden -ErrorAction Stop | Where-Object {([guid]$_.InterfaceGuid) -eq ([guid]$policy.lan.guid)})
    if($adapters.Count -ne 1 -or $adapters[0].ifIndex -ne $policy.lan.index -or -not $adapters[0].HardwareInterface){throw 'DHCP firewall LAN identity changed'}
    return $adapters[0]
  }
  function Check-Profile {
    $script:gatewayFirewallStage='preflight-connection-profile'
    $profiles=@(Get-NetConnectionProfile -InterfaceIndex ([uint32]$policy.lan.index) -ErrorAction Stop)
    if($profiles.Count -ne 1 -or [string]$profiles[0].NetworkCategory -ne 'Private'){throw 'DHCP firewall requires the dedicated Private LAN'}
    $script:gatewayFirewallStage='preflight-firewall-profile'
    $firewall=@(Get-NetFirewallProfile -Name Private -PolicyStore ActiveStore -ErrorAction Stop)
    if($firewall.Count -ne 1 -or [string]$firewall[0].Enabled -ne 'True' -or [string]$firewall[0].AllowLocalFirewallRules -eq 'False' -or [string]$firewall[0].AllowInboundRules -eq 'False'){throw 'Private firewall policy does not admit local inbound exceptions'}
    $script:gatewayFirewallStage='preflight-filtering-services'
    foreach($service in @('BFE','mpssvc')){if((Get-Service -Name $service -ErrorAction Stop).Status -ne 'Running'){throw 'Windows filtering services are unavailable'}}
  }
  function IPv4-Number([string]$text) {
    if($text -notmatch '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'){throw 'DHCP firewall address is not an IPv4 literal'}
    $bytes=([ipaddress]$text).GetAddressBytes()
    if($bytes.Length -ne 4){throw 'DHCP firewall address family changed'}
    return ([uint64]$bytes[0]*16777216+[uint64]$bytes[1]*65536+[uint64]$bytes[2]*256+[uint64]$bytes[3])
  }
  function Address-Key([string]$text) {
    $parts=$text.Split('/')
    if($parts.Count -eq 2){
      $start=IPv4-Number $parts[0]
      if($parts[1] -match '^[0-9]{1,2}$'){
        $bits=[int]$parts[1];if($bits -gt 32){throw 'DHCP firewall prefix length changed'}
        $mask=([uint64]4294967295 -shl (32-$bits)) -band [uint64]4294967295
      }else{
        $mask=IPv4-Number $parts[1]
        $inverse=[uint64]4294967295 -bxor $mask
        if(($inverse -band ($inverse+1)) -ne 0){throw 'DHCP firewall address mask is not contiguous'}
      }
      $start=$start -band $mask; $end=$start -bor ([uint64]4294967295 -bxor $mask)
    }elseif($parts.Count -eq 1){
      $range=$text.Split('-')
      if($range.Count -eq 1){$start=IPv4-Number $range[0];$end=$start}
      elseif($range.Count -eq 2){$start=IPv4-Number $range[0];$end=IPv4-Number $range[1];if($end -lt $start){throw 'DHCP firewall address range changed'}}
      else{throw 'DHCP firewall address range is invalid'}
    }else{throw 'DHCP firewall address scope is invalid'}
    return ([string]$start+':'+[string]$end)
  }
  function Same-Addresses($actual,$expected) {
    if(@($actual).Count -gt 65 -or @($expected).Count -gt 65){return $false}
    $a=@($actual | ForEach-Object {Address-Key ([string]$_)} | Sort-Object -Unique)
    $b=@($expected | ForEach-Object {Address-Key ([string]$_)} | Sort-Object -Unique)
    return (($a -join ',') -ceq ($b -join ','))
  }
  function Make-Scope([string]$image,[string]$alias,[bool]$enabled) {
    return @{owner=[string]$policy.owner;lan=$policy.lan;interface_alias=$alias;program=$image;gateway=[string]$policy.gateway;subnet=[string]$policy.subnet;allowed_sources=@($policy.allowed_sources);enabled=$enabled}
  }
  function Filter-Diagnostic($filter,[string]$field) {
    # Read only fixed non-path fields. Never stringify an entire CIM filter or
    # echo an arbitrary value from a foreign rule into helper/CI diagnostics.
    if($null -eq $filter){return 'not_single_filter'}
    $property=$filter.PSObject.Properties[$field]
    if($null -eq $property){return 'missing_property'}
    $value=$property.Value
    if($null -eq $value){return 'null'}
    if($value -isnot [string]){return 'non_string'}
    if($value.Length -eq 0){return 'empty_string'}
    if($value -cin @('Any','None','All','NotConfigured','NotRequired','*')){return ('keyword:'+ $value)}
    if($value.Length -le 184 -and $value -cmatch '^S-[0-9]+(-[0-9]{1,10}){1,15}$'){return ('sid:'+ $value)}
    return ('redacted_string_length:'+ [string]$value.Length)
  }
  function Read-State([string]$store) {
    $script:gatewayFirewallStage='read-rule'
    try{$rules=@(Get-NetFirewallRule -Name $name -PolicyStore $store -ErrorAction Stop)}
    catch{if($_.CategoryInfo.Category -eq [Management.Automation.ErrorCategory]::ObjectNotFound){return $null}else{throw}}
    if($rules.Count -ne 1){throw 'DHCP firewall rule identity is ambiguous'}
    $rule=$rules[0]
    if([string]$rule.Name -cne $name -or [string]$rule.DisplayName -cne $name -or [string]$rule.Group -cne 'Swirl Native Gateway DHCP' -or [string]$rule.Description -cne ('Swirl native gateway DHCP owner '+[string]$policy.owner)){throw 'DHCP firewall ownership metadata changed'}
    if([string]$rule.Direction -ne 'Inbound' -or [string]$rule.Action -ne 'Allow' -or [string]$rule.Enabled -notin @('True','False') -or [string]$rule.Profile -ne 'Private' -or [string]$rule.EdgeTraversalPolicy -ne 'Block' -or [string]$rule.LooseSourceMapping -ne 'False' -or [string]$rule.LocalOnlyMapping -ne 'False' -or -not [string]::IsNullOrEmpty([string]$rule.Owner) -or @($rule.Platform | Where-Object {-not [string]::IsNullOrEmpty([string]$_)}).Count -ne 0){throw 'DHCP firewall rule scope changed'}
    $script:gatewayFirewallStage='read-port'
    $ports=@($rule | Get-NetFirewallPortFilter -ErrorAction Stop)
    if($ports.Count -ne 1 -or [string]$ports[0].Protocol -notin @('17','UDP') -or [string]$ports[0].LocalPort -ne '67' -or [string]$ports[0].RemotePort -ne '68' -or [string]$ports[0].DynamicTarget -ne 'Any'){throw 'DHCP firewall port scope changed'}
    $script:gatewayFirewallStage='read-address'
    $addresses=@($rule | Get-NetFirewallAddressFilter -ErrorAction Stop)
    if($addresses.Count -ne 1 -or -not (Same-Addresses @($addresses[0].LocalAddress) @($p.local_addresses)) -or -not (Same-Addresses @($addresses[0].RemoteAddress) @($p.remote_addresses))){throw 'DHCP firewall address scope changed'}
    $script:gatewayFirewallStage='read-app'
    $apps=@($rule | Get-NetFirewallApplicationFilter -ErrorAction Stop)
    $script:gatewayFirewallStage='read-service'
    $services=@($rule | Get-NetFirewallServiceFilter -ErrorAction Stop)
    if($apps.Count -ne 1 -or [string]$apps[0].Package -ne 'Any' -or $services.Count -ne 1 -or [string]$services[0].Service -ne 'Any'){
      $app=if($apps.Count -eq 1){$apps[0]}else{$null}
      $service=if($services.Count -eq 1){$services[0]}else{$null}
      throw ('DHCP firewall application scope changed; application_count={0}; service_count={1}; package={2}; service={3}; service_name={4}' -f $apps.Count,$services.Count,(Filter-Diagnostic $app 'Package'),(Filter-Diagnostic $service 'Service'),(Filter-Diagnostic $service 'ServiceName'))
    }
    $script:gatewayFirewallStage='read-interface'
    $interfaces=@($rule | Get-NetFirewallInterfaceFilter -ErrorAction Stop)
    $script:gatewayFirewallStage='read-type'
    $types=@($rule | Get-NetFirewallInterfaceTypeFilter -ErrorAction Stop)
    if($interfaces.Count -ne 1 -or @($interfaces[0].InterfaceAlias).Count -ne 1 -or $types.Count -ne 1 -or [string]$types[0].InterfaceType -ne 'Wired'){throw 'DHCP firewall interface scope changed'}
    $aliases=@($interfaces[0].InterfaceAlias)
    $script:gatewayFirewallStage='read-security'
    $security=@($rule | Get-NetFirewallSecurityFilter -ErrorAction Stop)
    if($security.Count -ne 1 -or [string]$security[0].Authentication -ne 'NotRequired' -or [string]$security[0].Encryption -ne 'NotRequired' -or [string]$security[0].OverrideBlockRules -ne 'False' -or [string]$security[0].LocalUser -ne 'Any' -or [string]$security[0].RemoteUser -ne 'Any' -or [string]$security[0].RemoteMachine -ne 'Any'){throw 'DHCP firewall security scope changed'}
    return (Make-Scope ([string]$apps[0].Program) ([string]$aliases[0]) ([string]$rule.Enabled -eq 'True'))
  }
  function Same-Scope($a,$b) {
    if($null -eq $a -or $null -eq $b){return ($null -eq $a -and $null -eq $b)}
    return ($a.owner -ceq $b.owner -and $a.lan.guid -ceq $b.lan.guid -and $a.lan.index -eq $b.lan.index -and $a.interface_alias -ceq $b.interface_alias -and $a.program -ceq $b.program -and $a.enabled -eq $b.enabled -and $a.gateway -ceq $b.gateway -and $a.subnet -ceq $b.subnet -and ((@($a.allowed_sources) -join ',') -ceq (@($b.allowed_sources) -join ',')))
  }
  if($p.mode -eq 'scope'){
    $adapter=Owned-Adapter; Check-Profile
    $result=Make-Scope ([string]$p.program) ([string]$adapter.Name) $true
  }elseif($p.mode -eq 'verify'){
    $adapter=Owned-Adapter; Check-Profile
    $expected=Make-Scope ([string]$p.program) ([string]$adapter.Name) $true
    if(-not (Same-Scope (Read-State 'PersistentStore') $expected) -or -not (Same-Scope (Read-State 'ActiveStore') $expected)){throw 'DHCP firewall effective state differs from its owned scope'}
    $result=$true
  }elseif($p.mode -in @('read','compare_exchange')){
    $current=Read-State 'PersistentStore'
    if($p.mode -eq 'compare_exchange'){
      $principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
      if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'An elevated native gateway helper is required'}
      if(-not (Same-Scope $current $p.expected)){throw 'DHCP firewall changed after snapshot; refusing overwrite'}
      if($null -eq $p.desired){
        if($null -eq $current){throw 'DHCP firewall removal lacks an owned rule'}
        $script:gatewayFirewallStage='delete'
        Remove-NetFirewallRule -Name $name -PolicyStore PersistentStore -Confirm:$false -ErrorAction Stop
      }else{
        if($null -ne $current){throw 'DHCP firewall replacement is forbidden'}
        $adapter=Owned-Adapter
        if([string]$adapter.Name -cne [string]$p.desired.interface_alias){throw 'DHCP firewall interface alias changed before installation'}
        if($p.desired.enabled){Check-Profile}
        $enabled=if($p.desired.enabled){'True'}else{'False'}
        $script:gatewayFirewallStage='create'
        New-NetFirewallRule -Name $name -DisplayName $name -Group 'Swirl Native Gateway DHCP' -Description ('Swirl native gateway DHCP owner '+[string]$policy.owner) -Direction Inbound -Action Allow -Enabled $enabled -Profile Private -Protocol UDP -LocalPort 67 -RemotePort 68 -LocalAddress ([string[]]$p.local_addresses) -RemoteAddress ([string[]]$p.remote_addresses) -Program ([string]$p.desired.program) -Service Any -InterfaceAlias ([string]$p.desired.interface_alias) -InterfaceType Wired -EdgeTraversalPolicy Block -LooseSourceMapping $false -LocalOnlyMapping $false -Authentication NotRequired -Encryption NotRequired -OverrideBlockRules $false -PolicyStore PersistentStore -ErrorAction Stop | Out-Null
      }
      $current=Read-State 'PersistentStore'
      if(-not (Same-Scope $current $p.desired)){throw 'Windows rejected or altered the DHCP firewall exception'}
      if($null -ne $current -and $current.enabled -and -not (Same-Scope (Read-State 'ActiveStore') $current)){throw 'DHCP firewall exception is not active'}
    }
    $result=$current
  }else{throw 'Unsupported DHCP firewall operation'}
  if($null -eq $result){[Console]::Out.WriteLine('null')}else{ConvertTo-Json -InputObject $result -Compress -Depth 10}
}catch{[Console]::Error.WriteLine(($_.Exception.Message+'; stage='+$script:gatewayFirewallStage));exit 1}
"#;

#[cfg(test)]
mod tests {
    use super::*;
    use crate::network_transaction::InterfaceIdentity;
    use serde::Deserialize;

    fn fixture() -> (GatewayIsolationPolicy, GatewayDhcpFirewallScope) {
        let mut policy = crate::gateway_policy::fixture();
        policy.dhcp = true;
        let mut scope = template(&policy);
        scope.interface_alias = "Dedicated LAN".into();
        scope.program = r"C:\Swirl Firewall Fixture\Swirl.exe".into();
        scope.enabled = false;
        (policy, scope)
    }

    const MOCKS: &str = r#"
function Get-NetFirewallRule {param($Name,$PolicyStore,$ErrorAction);return $p.fixture.rule}
function Get-NetFirewallPortFilter {param([Parameter(ValueFromPipeline=$true)]$InputObject);process{return $p.fixture.ports}}
function Get-NetFirewallAddressFilter {param([Parameter(ValueFromPipeline=$true)]$InputObject);process{return $p.fixture.addresses}}
function Get-NetFirewallApplicationFilter {param([Parameter(ValueFromPipeline=$true)]$InputObject);process{return $p.fixture.application}}
function Get-NetFirewallServiceFilter {param([Parameter(ValueFromPipeline=$true)]$InputObject);process{return $p.fixture.service}}
function Get-NetFirewallInterfaceFilter {param([Parameter(ValueFromPipeline=$true)]$InputObject);process{return $p.fixture.interface}}
function Get-NetFirewallInterfaceTypeFilter {param([Parameter(ValueFromPipeline=$true)]$InputObject);process{return $p.fixture.interface_type}}
function Get-NetFirewallSecurityFilter {param([Parameter(ValueFromPipeline=$true)]$InputObject);process{return $p.fixture.security}}
function New-NetFirewallRule {throw 'Unexpected network mutation in read-only fixture'}
function Remove-NetFirewallRule {throw 'Unexpected network mutation in read-only fixture'}
"#;

    fn mocked_read_with(
        policy: &GatewayIsolationPolicy,
        fixture: &serde_json::Value,
        overrides: &str,
    ) -> io::Result<Option<GatewayDhcpFirewallScope>> {
        let mut request = input(policy, "read");
        request["fixture"] = fixture.clone();
        let observed: Option<GatewayDhcpFirewallScope> =
            run_json(&(MOCKS.to_owned() + overrides + SCRIPT), &request)?;
        if let Some(scope) = &observed {
            scope.validate()?;
        }
        Ok(observed)
    }

    fn mocked_read(
        policy: &GatewayIsolationPolicy,
        fixture: &serde_json::Value,
    ) -> io::Result<Option<GatewayDhcpFirewallScope>> {
        mocked_read_with(policy, fixture, "")
    }

    fn readback_fixture(
        policy: &GatewayIsolationPolicy,
        scope: &GatewayDhcpFirewallScope,
    ) -> serde_json::Value {
        json!({
            "rule":{"Name":scope.name(),"DisplayName":scope.name(),"Group":"Swirl Native Gateway DHCP",
                "Description":format!("Swirl native gateway DHCP owner {}",policy.owner),"Direction":"Inbound","Action":"Allow",
                "Enabled":"False","Profile":"Private","EdgeTraversalPolicy":"Block","LooseSourceMapping":false,"LocalOnlyMapping":false,"Owner":"","Platform":[]},
            "ports":{"Protocol":"UDP","LocalPort":"67","RemotePort":"68","DynamicTarget":"Any"},
            "addresses":{"LocalAddress":["192.168.77.1/32","192.168.77.255","255.255.255.255"],"RemoteAddress":["0.0.0.0","192.168.77.0/255.255.255.128"]},
            "application":{"Program":scope.program,"Package":"Any"},"service":{"Service":"Any"},
            "interface":{"InterfaceAlias":[scope.interface_alias]},"interface_type":{"InterfaceType":"Wired"},
            "security":{"Authentication":"NotRequired","Encryption":"NotRequired","OverrideBlockRules":false,"LocalUser":"Any","RemoteUser":"Any","RemoteMachine":"Any"}
        })
    }

    #[test]
    fn dhcp_firewall_readback_rejects_each_foreign_scope_change_without_network_writes() {
        let (policy, scope) = fixture();
        let valid = readback_fixture(&policy, &scope);
        assert_eq!(mocked_read(&policy, &valid).unwrap(), Some(scope.clone()));
        for (object, field, value) in [
            ("rule", "Description", json!("foreign owner")),
            ("rule", "Enabled", json!("True")),
            ("rule", "Profile", json!("Any")),
            ("rule", "EdgeTraversalPolicy", json!("Allow")),
            ("rule", "LooseSourceMapping", json!(true)),
            ("rule", "LocalOnlyMapping", json!(true)),
            ("rule", "Owner", json!("S-1-5-18")),
            ("rule", "Platform", json!(["6.1+"])),
            ("ports", "Protocol", json!("TCP")),
            ("ports", "LocalPort", json!("Any")),
            ("ports", "RemotePort", json!("Any")),
            ("ports", "DynamicTarget", json!("WifiDirectDevices")),
            ("addresses", "LocalAddress", json!(["Any"])),
            (
                "addresses",
                "RemoteAddress",
                json!(["0.0.0.0/0", "192.168.77.0/25"]),
            ),
            (
                "addresses",
                "RemoteAddress",
                json!(["0.0.0.0/32", "192.168.77.0/24"]),
            ),
            ("application", "Program", json!(r"C:\Other\Swirl.exe")),
            ("application", "Package", json!("S-1-15-2-1")),
            ("interface", "InterfaceAlias", json!(["WAN"])),
            (
                "interface",
                "InterfaceAlias",
                json!(["Dedicated LAN", "WAN"]),
            ),
            ("interface_type", "InterfaceType", json!("Any")),
            ("security", "OverrideBlockRules", json!(true)),
        ] {
            let mut changed = valid.clone();
            changed[object][field] = value;
            assert_ne!(
                mocked_read(&policy, &changed).ok().flatten(),
                Some(scope.clone()),
                "{object}.{field}"
            );
        }
    }

    #[test]
    fn dhcp_firewall_application_diagnostics_are_bounded_without_loosening_scope() {
        let (policy, scope) = fixture();
        let valid = readback_fixture(&policy, &scope);
        let secret = "credential-must-not-be-logged";
        let cases = [
            (json!(null), "package=null"),
            (json!(""), "package=empty_string"),
            (json!("None"), "package=keyword:None"),
            (json!("S-1-15-2-1"), "package=sid:S-1-15-2-1"),
            (json!(secret.repeat(100)), "package=redacted_string_length:"),
            (json!({"secret":secret}), "package=non_string"),
        ];
        for (package, expected) in cases {
            let mut changed = valid.clone();
            changed["application"]["Package"] = package;
            let error = mocked_read(&policy, &changed).unwrap_err().to_string();
            assert!(error.contains("application_count=1; service_count=1"));
            assert!(error.contains(expected), "{error}");
            assert!(error.contains("service=keyword:Any"));
            assert!(!error.contains(&scope.program));
            assert!(!error.contains(secret));
            assert!(error.len() < 768);
        }
        for (field, replacement, expected) in [
            (
                "application",
                json!({"Program":scope.program}),
                "package=missing_property",
            ),
            ("application", json!([]), "application_count=0"),
            (
                "application",
                json!([valid["application"], valid["application"]]),
                "application_count=2",
            ),
            (
                "service",
                json!({"ServiceName":"Any"}),
                "service=missing_property; service_name=keyword:Any",
            ),
            ("service", json!({"Service":null}), "service=null"),
            ("service", json!({"Service":""}), "service=empty_string"),
            (
                "service",
                json!({"Service":secret}),
                "service=redacted_string_length:",
            ),
            (
                "service",
                json!([valid["service"], valid["service"]]),
                "service_count=2",
            ),
        ] {
            let mut changed = valid.clone();
            changed[field] = replacement;
            let error = mocked_read(&policy, &changed).unwrap_err().to_string();
            assert!(error.contains(expected), "{error}");
            assert!(!error.contains(&scope.program));
            assert!(!error.contains(secret));
            assert!(error.len() < 768);
        }
    }

    #[test]
    fn dhcp_firewall_cmdlet_failure_reports_its_fixed_stage_without_scope_data() {
        let (policy, scope) = fixture();
        let valid = readback_fixture(&policy, &scope);
        for (command, stage) in [
            ("Get-NetFirewallPortFilter", "read-port"),
            ("Get-NetFirewallAddressFilter", "read-address"),
            ("Get-NetFirewallApplicationFilter", "read-app"),
            ("Get-NetFirewallServiceFilter", "read-service"),
            ("Get-NetFirewallInterfaceFilter", "read-interface"),
            ("Get-NetFirewallInterfaceTypeFilter", "read-type"),
            ("Get-NetFirewallSecurityFilter", "read-security"),
        ] {
            let overrides = format!(
                "\nfunction {command} {{param([Parameter(ValueFromPipeline=$true)]$InputObject);process{{throw 'fixture-cmdlet-failure'}}}}\n"
            );
            let error = mocked_read_with(&policy, &valid, &overrides)
                .unwrap_err()
                .to_string();
            assert!(error.contains("fixture-cmdlet-failure"), "{error}");
            assert!(error.ends_with(&format!("stage={stage}")), "{error}");
            assert!(!error.contains(&scope.program));
            assert!(!error.contains(&scope.interface_alias));
            assert!(error.len() < 256);
        }
    }

    /// This test never creates an enabled rule or transmits DHCP. It exercises
    /// the actual Windows Firewall stores and exact ownership restoration only.
    #[test]
    #[ignore = "creates one disabled firewall exception; run explicitly on a disposable elevated Windows runner"]
    fn disabled_dhcp_firewall_fixture_verifies_scope_and_preserves_foreign_edits() {
        #[derive(Deserialize)]
        struct Adapter {
            identity: InterfaceIdentity,
            alias: String,
        }
        let adapter: Adapter = run_json(r#"
$ErrorActionPreference='Stop';[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
try{$a=@(Get-NetAdapter -IncludeHidden -ErrorAction Stop | Where-Object {$_.HardwareInterface -and [uint32]$_.InterfaceType -eq 6} | Select-Object -First 1)
if($a.Count -ne 1){throw 'A physical Ethernet adapter is required for this disabled-rule fixture'}
ConvertTo-Json -InputObject @{identity=@{index=[uint32]$a[0].ifIndex;guid=([guid]$a[0].InterfaceGuid).ToString('D').ToLowerInvariant()};alias=[string]$a[0].Name} -Compress -Depth 4
}catch{[Console]::Error.WriteLine($_.Exception.Message);exit 1}
"#,&json!({})).unwrap();
        // Safe selection evidence for a real NetSecurity failure: retain no
        // program path or adapter alias in CI, but make the bound NIC and alias
        // identity distinguishable across runner images.
        let alias_digest = <sha2::Sha256 as sha2::Digest>::digest(adapter.alias.as_bytes());
        eprintln!(
            "Gateway DHCP firewall fixture selected interface {}",
            json!({
                "interface_index":adapter.identity.index,
                "interface_guid":adapter.identity.guid,
                "alias_utf16_length":adapter.alias.encode_utf16().count(),
                "alias_sha256_utf8":format!("{alias_digest:x}"),
            })
        );
        let (mut policy, mut scope) = fixture();
        policy.lan = adapter.identity;
        policy.tun = InterfaceIdentity::new(u32::MAX, u128::MAX);
        policy.owner = format!(
            "{:032x}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
                ^ (u128::from(std::process::id()) << 64)
        );
        scope.lan = policy.lan.clone();
        scope.owner = policy.owner.clone();
        scope.interface_alias = adapter.alias;
        policy.validate().unwrap();
        scope.validate().unwrap();
        assert!(!scope.enabled);
        assert_eq!(read(&policy).unwrap(), None);
        struct Cleanup {
            policy: GatewayIsolationPolicy,
            scope: GatewayDhcpFirewallScope,
        }
        impl Drop for Cleanup {
            fn drop(&mut self) {
                if read(&self.policy).ok().flatten().as_ref() == Some(&self.scope) {
                    let _ = compare_exchange(&self.policy, &Some(self.scope.clone()), &None);
                }
            }
        }
        let cleanup = Cleanup {
            policy: policy.clone(),
            scope: scope.clone(),
        };
        compare_exchange(&policy, &None, &Some(scope.clone())).unwrap();
        assert_eq!(read(&policy).unwrap(), Some(scope.clone()));
        let mut foreign = scope.clone();
        foreign.program = r"C:\Swirl Firewall Fixture Foreign\Swirl.exe".into();
        let edit = |before: &GatewayDhcpFirewallScope, after: &GatewayDhcpFirewallScope| {
            let changed:bool=run_json(r#"
$ErrorActionPreference='Stop';[Console]::InputEncoding=New-Object Text.UTF8Encoding($false);[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
try{$p=[Console]::In.ReadToEnd()|ConvertFrom-Json
$rules=@(Get-NetFirewallRule -Name ([string]$p.name) -PolicyStore PersistentStore -ErrorAction Stop)
if($rules.Count -ne 1 -or [string]$rules[0].Name -cne [string]$p.name -or [string]$rules[0].Group -cne 'Swirl Native Gateway DHCP' -or [string]$rules[0].Description -cne ('Swirl native gateway DHCP owner '+[string]$p.owner) -or [string]$rules[0].Enabled -ne 'False'){throw 'Disabled fixture ownership changed'}
$app=@($rules[0]|Get-NetFirewallApplicationFilter -ErrorAction Stop)
if($app.Count -ne 1 -or [string]$app[0].Program -cne [string]$p.before){throw 'Disabled fixture image changed'}
$app[0]|Set-NetFirewallApplicationFilter -Program ([string]$p.after) -ErrorAction Stop|Out-Null
[Console]::Out.WriteLine('true')
}catch{[Console]::Error.WriteLine($_.Exception.Message);exit 1}
"#,&json!({"name":scope.name(),"owner":policy.owner,"before":before.program,"after":after.program})).unwrap();
            assert!(changed);
        };
        edit(&scope, &foreign);
        assert_eq!(read(&policy).unwrap(), Some(foreign.clone()));
        assert_eq!(
            compare_exchange(&policy, &Some(scope.clone()), &None)
                .unwrap_err()
                .kind(),
            io::ErrorKind::AlreadyExists
        );
        assert_eq!(
            read(&policy).unwrap(),
            Some(foreign.clone()),
            "foreign edits must survive refused recovery"
        );
        // This explicit fixture mutation is reverted only if its exact known
        // disabled object remains. Production recovery never makes this edit.
        edit(&foreign, &scope);
        assert_eq!(read(&policy).unwrap(), Some(scope.clone()));
        compare_exchange(&policy, &Some(scope), &None).unwrap();
        assert_eq!(read(&policy).unwrap(), None);
        drop(cleanup);
    }
}
