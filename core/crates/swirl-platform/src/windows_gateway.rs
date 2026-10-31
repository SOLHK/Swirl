//! Dedicated-LAN control operations for the elevated native helper. This is
//! deliberately separate from WindowsNetworkBackend, which remains TUN-only.
//! A user confirmation identifies intent; Windows preflight verifies identity,
//! profile, static address, connected return route, and absence of a WAN route.
pub use crate::gateway_policy::GatewayRequest;
use crate::{
    gateway_policy::GatewayIsolationPolicy,
    network_transaction::{InterfaceIdentity, NetworkBackend, Resource, Value, validate_value},
    windows_dhcp_attachment, windows_dhcp_probe,
    windows_network::{SystemRoute, run_json},
    windows_wfp,
};
use serde::Deserialize;
use serde_json::json;
use std::{io, net::IpAddr};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Preflight {
    host_addresses: Vec<IpAddr>,
    routes: Vec<SystemRoute>,
    lan_hardware_address: String,
}

/// Read-only. No IP address, DHCP mode, route, profile or firewall state changes
/// occur here. The first release requires a preconfigured static dedicated LAN.
pub fn preflight(
    request: &GatewayRequest,
    tun: &InterfaceIdentity,
    owner: String,
) -> io::Result<GatewayIsolationPolicy> {
    request.validate()?;
    tun.validate()?;
    if !request.dedicated_lan_confirmed || request.lan.index == tun.index {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "a distinct dedicated LAN must be explicitly confirmed",
        ));
    }
    let mut captured = topology(request, tun, false)?;
    captured.host_addresses.sort();
    captured.host_addresses.dedup();
    let policy = GatewayIsolationPolicy {
        version: 1,
        owner,
        lan: request.lan.clone(),
        lan_luid: interface_luid(&request.lan)?,
        tun: tun.clone(),
        tun_luid: interface_luid(tun)?,
        subnet: request.subnet,
        gateway: request.gateway,
        allowed_sources: request.allowed_sources.clone(),
        host_addresses: captured.host_addresses,
        dhcp: request.dhcp,
    };
    policy.validate()?;
    if request.dhcp {
        windows_dhcp_probe::observe(&policy, &captured.lan_hardware_address)?;
    }
    Ok(policy)
}

/// Recheck a prepared or active gateway without changing host networking.
/// This intentionally remains separate from recovery: restoration must still
/// disable forwarding when a NIC becomes public, a DHCP process exits, or the
/// TUN disappears. A failed check never authorizes a replacement resource.
pub fn verify(policy: &GatewayIsolationPolicy, forwarding_expected: bool) -> io::Result<()> {
    policy.validate()?;
    if interface_luid(&policy.lan)? != policy.lan_luid
        || interface_luid(&policy.tun)? != policy.tun_luid
        || !windows_wfp::present(policy)?
    {
        return Err(io::Error::other(
            "gateway isolation or interface identity is no longer valid",
        ));
    }
    let request = GatewayRequest {
        lan: policy.lan.clone(),
        subnet: policy.subnet,
        gateway: policy.gateway,
        allowed_sources: policy.allowed_sources.clone(),
        dedicated_lan_confirmed: true,
        dhcp: policy.dhcp,
    };
    let mut captured = topology(&request, &policy.tun, forwarding_expected)?;
    captured.host_addresses.sort();
    captured.host_addresses.dedup();
    let mut expected = policy.host_addresses.clone();
    expected.sort();
    if captured.host_addresses != expected {
        return Err(io::Error::new(
            io::ErrorKind::AlreadyExists,
            "host address inventory changed; gateway requires a fresh preparation",
        ));
    }
    Ok(())
}

fn topology(
    request: &GatewayRequest,
    tun: &InterfaceIdentity,
    forwarding_expected: bool,
) -> io::Result<Preflight> {
    let captured: Preflight = run_json(
        PREFLIGHT,
        &json!({
            "request":request,"tun":tun,"forwarding_expected":forwarding_expected,
        }),
    )?;
    if captured.routes.len() > 8192
        || captured.routes.iter().any(|route| {
            let ipnet::IpNet::V4(destination) = route.destination else {
                return false;
            };
            destination.prefix_len() >= request.subnet.prefix_len()
                && request.subnet.contains(&destination.network())
                && route.interface_index != request.lan.index
        })
    {
        return Err(io::Error::new(
            io::ErrorKind::AlreadyExists,
            "another interface has a conflicting LAN client return route",
        ));
    }
    Ok(captured)
}

/// Verify a real DHCP socket and a stable owner process, never a readiness
/// boolean supplied by the GUI. The creation receipt is canonical decimal UTC
/// FILETIME, as returned by GetProcessTimes, not wall-clock text or a PID alone.
/// The caller reuses the same receipt when polling; process restart/recycling
/// therefore closes forwarding until an explicit new activation.
pub fn verify_dhcp_attachment(
    policy: &GatewayIsolationPolicy,
    owner_pid: u32,
    owner_creation: &str,
) -> io::Result<()> {
    policy.validate()?;
    let creation = owner_creation.parse::<u64>().map_err(|_| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "invalid DHCP process creation receipt",
        )
    })?;
    if !policy.dhcp || owner_pid == 0 || creation == 0 || creation.to_string() != owner_creation {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "invalid DHCP process attachment",
        ));
    }
    let executable = std::env::current_exe()?;
    let parent = executable
        .parent()
        .ok_or_else(|| io::Error::other("helper installation path is unavailable"))?;
    let expected_image = parent.join("Swirl.exe").canonicalize()?;
    let verified: bool = run_json(
        DHCP_ATTACHMENT,
        &json!({
            "policy":policy,"owner_pid":owner_pid,"owner_creation":owner_creation,
            "expected_image":expected_image,
        }),
    )?;
    if !verified {
        return Err(io::Error::other("DHCP owner verification did not succeed"));
    }
    Ok(())
}

/// Consume a one-use WSADuplicateSocketW receipt before enabling forwarding.
/// Subsequent lifecycle checks use only PID + creation time; the opaque socket
/// token must not enter a journal, status response, error message or log.
pub fn attest_dhcp_socket(
    policy: &GatewayIsolationPolicy,
    owner_pid: u32,
    owner_creation: &str,
    target_helper_pid: u32,
    protocol_info_base64: &str,
) -> io::Result<()> {
    verify_dhcp_attachment(policy, owner_pid, owner_creation)?;
    windows_dhcp_attachment::attest(
        protocol_info_base64,
        target_helper_pid,
        policy.lan.index,
        policy.gateway,
    )?;
    verify_dhcp_attachment(policy, owner_pid, owner_creation)
}

/// Resource order is a safety property: install isolation before forwarding,
/// restore forwarding before removing isolation, retaining guards on conflict.
pub fn desired_resources(
    policy: &GatewayIsolationPolicy,
) -> io::Result<Vec<(Resource, Option<Value>)>> {
    policy.validate()?;
    Ok(vec![
        (
            Resource::GatewayIsolation {
                name: policy.name(),
            },
            Some(Value::GatewayIsolation {
                policy: policy.clone(),
            }),
        ),
        (
            Resource::Forwarding { ipv6: false },
            Some(Value::Forwarding { enabled: true }),
        ),
    ])
}

pub struct WindowsGatewayBackend {
    policy: GatewayIsolationPolicy,
}
impl WindowsGatewayBackend {
    /// A restored journal may create this backend without rerunning activation
    /// preflight. Each read/write still validates GUID+index and installed state.
    pub fn for_policy(policy: GatewayIsolationPolicy) -> io::Result<Self> {
        policy.validate()?;
        Ok(Self { policy })
    }
    fn check(&self, interface: &InterfaceIdentity, resource: &Resource) -> io::Result<()> {
        if interface != &self.policy.lan
            || !matches!(
                resource,
                Resource::Forwarding { ipv6: false } | Resource::GatewayIsolation { .. }
            )
        {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "gateway backend resource is outside its dedicated LAN",
            ));
        }
        if let Resource::GatewayIsolation { name } = resource
            && name != &self.policy.name()
        {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "gateway guard ownership mismatch",
            ));
        }
        Ok(())
    }
}
impl NetworkBackend for WindowsGatewayBackend {
    fn read(
        &mut self,
        interface: &InterfaceIdentity,
        resource: &Resource,
    ) -> io::Result<Option<Value>> {
        self.check(interface, resource)?;
        match resource {
            Resource::GatewayIsolation { .. } => Ok(windows_wfp::present(&self.policy)?.then(
                || Value::GatewayIsolation {
                    policy: self.policy.clone(),
                },
            )),
            Resource::Forwarding { .. } => {
                run_json(FORWARDING, &json!({"mode":"read","policy":self.policy}))
            }
            _ => unreachable!("checked gateway resource"),
        }
    }
    fn compare_exchange(
        &mut self,
        interface: &InterfaceIdentity,
        resource: &Resource,
        expected: &Option<Value>,
        desired: &Option<Value>,
    ) -> io::Result<()> {
        self.check(interface, resource)?;
        validate_value(resource, expected)?;
        validate_value(resource, desired)?;
        if &self.read(interface, resource)? != expected {
            return Err(io::Error::new(
                io::ErrorKind::AlreadyExists,
                "gateway state changed after snapshot",
            ));
        }
        match resource {
            Resource::GatewayIsolation { .. } => match (expected, desired) {
                (None, Some(Value::GatewayIsolation { policy })) if policy == &self.policy => {
                    windows_wfp::install(policy)?
                }
                (Some(Value::GatewayIsolation { policy }), None) if policy == &self.policy => {
                    let forwarding: Option<Value> =
                        run_json(FORWARDING, &json!({"mode":"read","policy":self.policy}))?;
                    if !matches!(
                        forwarding,
                        None | Some(Value::Forwarding { enabled: false })
                    ) {
                        // The guard is still ours. A shared flag changing is a
                        // recovery conflict, not a reason to relinquish WFP or
                        // to overwrite the actor that enabled forwarding.
                        return Err(io::Error::other(
                            "LAN forwarding is enabled; gateway isolation retained",
                        ));
                    }
                    windows_wfp::remove(policy)?;
                }
                _ => {
                    return Err(io::Error::new(
                        io::ErrorKind::PermissionDenied,
                        "gateway isolation cannot be adopted or replaced",
                    ));
                }
            },
            Resource::Forwarding { .. } => {
                let Some(Value::Forwarding { enabled }) = desired else {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidInput,
                        "forwarding state cannot be removed",
                    ));
                };
                if *enabled {
                    // Recheck LUID identity and guard immediately before the
                    // write. A missing TUN or externally removed guard denies
                    // activation; recovery can always turn forwarding off.
                    verify(&self.policy, false)?;
                }
                let actual: Option<Value> = run_json(FORWARDING, &json!({"mode":"compare_exchange","policy":self.policy,"expected":expected,"desired":desired})).map_err(|error| {
                    if error.to_string().starts_with("Windows network operation failed: Forwarding changed after snapshot; refusing overwrite") {
                        io::Error::new(io::ErrorKind::AlreadyExists, error)
                    } else { error }
                })?;
                if &actual != desired {
                    return Err(io::Error::other("gateway forwarding readback mismatch"));
                }
            }
            _ => unreachable!("checked gateway resource"),
        }
        Ok(())
    }
}

#[allow(unsafe_code)]
fn interface_luid(identity: &InterfaceIdentity) -> io::Result<u64> {
    use windows_sys::{
        Win32::NetworkManagement::{
            IpHelper::{ConvertInterfaceIndexToLuid, ConvertInterfaceLuidToGuid},
            Ndis::NET_LUID_LH,
        },
        core::GUID,
    };
    identity.validate()?;
    let mut luid = NET_LUID_LH { Value: 0 };
    // SAFETY: valid writable output and a checked, nonzero interface index.
    let result = unsafe { ConvertInterfaceIndexToLuid(identity.index, &mut luid) };
    if result != 0 {
        return Err(io::Error::from_raw_os_error(result as i32));
    }
    let mut guid = GUID::from_u128(0);
    let result = unsafe { ConvertInterfaceLuidToGuid(&luid, &mut guid) };
    if result != 0 {
        return Err(io::Error::from_raw_os_error(result as i32));
    }
    let value = ((u128::from(guid.data1)) << 96)
        | ((u128::from(guid.data2)) << 80)
        | ((u128::from(guid.data3)) << 64)
        | u128::from(u64::from_be_bytes(guid.data4));
    if InterfaceIdentity::new(identity.index, value) != *identity {
        return Err(io::Error::other("interface index has been recycled"));
    }
    // SAFETY: ConvertInterfaceIndexToLuid initialized the NET_LUID value.
    Ok(unsafe { luid.Value })
}

const PREFLIGHT: &str = r#"
$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'
[Console]::InputEncoding=New-Object Text.UTF8Encoding($false)
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
try {
  $p=[Console]::In.ReadToEnd() | ConvertFrom-Json
  $r=$p.request; $index=[uint32]$r.lan.index
  $all=@(Get-NetAdapter -IncludeHidden -ErrorAction Stop)
  $lan=@($all | Where-Object {([guid]$_.InterfaceGuid) -eq ([guid]$r.lan.guid)})
  $tun=@($all | Where-Object {([guid]$_.InterfaceGuid) -eq ([guid]$p.tun.guid)})
  if($lan.Count -ne 1 -or $lan[0].ifIndex -ne $index -or -not $lan[0].HardwareInterface -or [string]$lan[0].Status -ne 'Up'){throw 'Dedicated LAN identity is unavailable or is not physical hardware'}
  if([uint32]$lan[0].InterfaceType -ne 6 -or [uint32]$lan[0].NdisPhysicalMedium -in @(1,8,9)){throw 'Gateway requires a dedicated wired Ethernet LAN; Wi-Fi and WWAN are not accepted'}
  if($tun.Count -ne 1 -or $tun[0].ifIndex -ne $p.tun.index -or $tun[0].HardwareInterface){throw 'Owned TUN identity changed'}
  $bindings=@(Get-NetAdapterBinding -Name $lan[0].Name -IncludeHidden -AllBindings -ErrorAction Stop | Where-Object {$_.Name -eq $lan[0].Name -and $_.ComponentID -eq 'ms_bridge' -and $_.Enabled})
  if($bindings.Count -ne 0){throw 'Bridged LAN interfaces are not supported by the IP forwarding guard'}
  foreach($service in @('SharedAccess','RemoteAccess')){if((Get-Service -Name $service -ErrorAction Stop).Status -eq 'Running'){throw 'Existing ICS or RRAS router must not be adopted by Swirl'}}
  $profiles=@(Get-NetConnectionProfile -InterfaceIndex $index -ErrorAction Stop)
  if($profiles.Count -ne 1 -or [string]$profiles[0].NetworkCategory -ne 'Private'){throw 'Gateway LAN must have a verified Private network profile'}
  foreach($service in @('BFE','mpssvc')){if((Get-Service -Name $service -ErrorAction Stop).Status -ne 'Running'){throw 'Windows filtering and firewall services must be running'}}
  $firewall=Get-NetFirewallProfile -Name Private -PolicyStore ActiveStore -ErrorAction Stop
  if([string]$firewall.Enabled -ne 'True'){throw 'Private firewall profile must be enabled'}
  $routes=@(Get-NetRoute -PolicyStore ActiveStore -ErrorAction Stop)
  if(@($routes | Where-Object {$_.InterfaceIndex -eq $index -and $_.DestinationPrefix -in @('0.0.0.0/0','::/0','0.0.0.0/1','128.0.0.0/1','::/1','8000::/1')}).Count -ne 0){throw 'WAN/default-route interfaces cannot be used as a dedicated gateway LAN'}
  if(@($routes | Where-Object {$_.InterfaceIndex -eq $index -and $_.NextHop -notin @('0.0.0.0','::')}).Count -ne 0){throw 'A dedicated LAN cannot carry a routed physical uplink'}
  $ipif=@(Get-NetIPInterface -InterfaceIndex $index -AddressFamily IPv4 -PolicyStore ActiveStore -ErrorAction Stop)
  if($ipif.Count -ne 1 -or [string]$ipif[0].Dhcp -ne 'Disabled'){throw 'Dedicated LAN must already have a static IPv4 configuration'}
  $expectedForwarding=if($p.forwarding_expected){'Enabled'}else{'Disabled'}
  if([string]$ipif[0].Forwarding -ne $expectedForwarding){throw 'Dedicated LAN forwarding changed or an existing router is active'}
  $addresses=@(Get-NetIPAddress -PolicyStore ActiveStore -ErrorAction Stop)
  $gateway=@($addresses | Where-Object {$_.InterfaceIndex -eq $index -and $_.IPAddress -eq [string]$r.gateway})
  $prefix=[int](([string]$r.subnet).Split('/')[1])
  if($gateway.Count -ne 1 -or $gateway[0].PrefixLength -ne $prefix -or [string]$gateway[0].PrefixOrigin -ne 'Manual' -or [string]$gateway[0].AddressState -ne 'Preferred' -or $gateway[0].SkipAsSource){throw 'Configured static LAN gateway address does not match Windows'}
  $connected=@($routes | Where-Object {$_.DestinationPrefix -eq [string]$r.subnet -and $_.NextHop -eq '0.0.0.0'})
  if($connected.Count -ne 1 -or $connected[0].InterfaceIndex -ne $index){throw 'LAN return route is absent or ambiguous'}
  $hostAddresses=@($addresses | Where-Object {$_.InterfaceIndex -ne $p.tun.index} | ForEach-Object {([ipaddress](([string]$_.IPAddress).Split('%')[0])).ToString()} | Sort-Object -Unique)
  $routeRows=@($routes | ForEach-Object {@{interface_index=[uint32]$_.InterfaceIndex;destination=[string]$_.DestinationPrefix;next_hop=[string]$_.NextHop;metric=[uint32]$_.RouteMetric}})
  ConvertTo-Json -InputObject @{host_addresses=$hostAddresses;routes=$routeRows;lan_hardware_address=[string]$lan[0].MacAddress} -Compress -Depth 8
} catch {[Console]::Error.WriteLine($_.Exception.Message); exit 1}
"#;

const FORWARDING: &str = r#"
$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'
[Console]::InputEncoding=New-Object Text.UTF8Encoding($false)
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
try {
  $p=[Console]::In.ReadToEnd() | ConvertFrom-Json; $policy=$p.policy
  $index=[uint32]$policy.lan.index
  function Read-Forwarding {
    $adapters=@(Get-NetAdapter -IncludeHidden -ErrorAction Stop | Where-Object {([guid]$_.InterfaceGuid) -eq ([guid]$policy.lan.guid)})
    if($adapters.Count -eq 0){return $null}
    if($adapters.Count -ne 1 -or $adapters[0].ifIndex -ne $index -or -not $adapters[0].HardwareInterface){throw 'Physical LAN interface ownership changed'}
    $rows=@(Get-NetIPInterface -InterfaceIndex $index -AddressFamily IPv4 -PolicyStore ActiveStore -ErrorAction Stop)
    if($rows.Count -ne 1 -or [string]$rows[0].Forwarding -notin @('Enabled','Disabled')){throw 'Ambiguous physical LAN forwarding state'}
    return @{kind='forwarding';enabled=([string]$rows[0].Forwarding -eq 'Enabled')}
  }
  $current=Read-Forwarding
  if($p.mode -eq 'compare_exchange'){
    $principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'An elevated native gateway helper is required'}
    if($null -eq $current -or $null -eq $p.expected -or $current.kind -ne $p.expected.kind -or $current.enabled -ne $p.expected.enabled){throw 'Forwarding changed after snapshot; refusing overwrite'}
    if($p.desired.enabled){
      $profiles=@(Get-NetConnectionProfile -InterfaceIndex $index -ErrorAction Stop)
      if($profiles.Count -ne 1 -or [string]$profiles[0].NetworkCategory -ne 'Private'){throw 'Dedicated LAN profile changed'}
      if(@(Get-NetRoute -InterfaceIndex $index -PolicyStore ActiveStore -ErrorAction Stop | Where-Object {$_.DestinationPrefix -in @('0.0.0.0/0','::/0','0.0.0.0/1','128.0.0.0/1','::/1','8000::/1')}).Count -ne 0){throw 'Dedicated LAN acquired a WAN route'}
      $addresses=@(Get-NetIPAddress -InterfaceIndex $index -AddressFamily IPv4 -PolicyStore ActiveStore -ErrorAction Stop | Where-Object {$_.IPAddress -eq [string]$policy.gateway})
      if($addresses.Count -ne 1 -or $addresses[0].PrefixLength -ne [int](([string]$policy.subnet).Split('/')[1])){throw 'Dedicated LAN gateway address changed'}
    }
    $value=if($p.desired.enabled){'Enabled'}else{'Disabled'}
    Set-NetIPInterface -InterfaceIndex $index -AddressFamily IPv4 -Forwarding $value -PolicyStore ActiveStore -ErrorAction Stop
    $current=Read-Forwarding
    if($null -eq $current -or $current.enabled -ne $p.desired.enabled){throw 'Windows rejected gateway forwarding state'}
  } elseif($p.mode -ne 'read'){throw 'Unsupported gateway helper operation'}
  if($null -eq $current){[Console]::Out.WriteLine('null')}else{ConvertTo-Json -InputObject $current -Compress}
} catch {[Console]::Error.WriteLine($_.Exception.Message); exit 1}
"#;

// Fixed script receives data on stdin. Paths and PIDs are never executed or
// spliced into command text. Holding the Process object through both endpoint
// reads detects exit/replacement while inspecting its owned socket.
const DHCP_ATTACHMENT: &str = r#"
$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'
[Console]::InputEncoding=New-Object Text.UTF8Encoding($false)
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
try {
  $p=[Console]::In.ReadToEnd() | ConvertFrom-Json
  $owner=Get-Process -Id ([uint32]$p.owner_pid) -ErrorAction Stop
  try {
    if($owner.HasExited -or [string]$owner.StartTime.ToUniversalTime().ToFileTimeUtc() -ne [string]$p.owner_creation){throw 'DHCP owner process exited or its PID was recycled'}
    $image=[IO.Path]::GetFullPath([string]$owner.MainModule.FileName)
    $expected=[IO.Path]::GetFullPath([string]$p.expected_image)
    # canonicalize() can add the Windows extended-length path prefix.
    if($expected.StartsWith('\\?\')){$expected=$expected.Substring(4)}
    if($image.StartsWith('\\?\')){$image=$image.Substring(4)}
    if(-not [string]::Equals($image,$expected,[StringComparison]::OrdinalIgnoreCase)){throw 'DHCP owner image is not the installed sibling Swirl.exe'}
    $endpoints=@(Get-NetUDPEndpoint -LocalPort 67 -ErrorAction Stop | Where-Object {$_.OwningProcess -eq [uint32]$p.owner_pid})
    if($endpoints.Count -ne 1 -or [string]$endpoints[0].LocalAddress -notin @('0.0.0.0',[string]$p.policy.gateway)){throw 'Swirl DHCP must own exactly one IPv4 UDP67 listener'}
    $owner.Refresh()
    if($owner.HasExited -or [string]$owner.StartTime.ToUniversalTime().ToFileTimeUtc() -ne [string]$p.owner_creation){throw 'DHCP owner process changed during endpoint verification'}
    [Console]::Out.WriteLine('true')
  } finally {$owner.Dispose()}
} catch {[Console]::Error.WriteLine($_.Exception.Message); exit 1}
"#;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixed_gateway_scripts_parse_without_network_operations() {
        let parser = r#"
$ErrorActionPreference='Stop'
[Console]::InputEncoding=New-Object Text.UTF8Encoding($false)
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$p=[Console]::In.ReadToEnd() | ConvertFrom-Json
$tokens=$null; $errors=$null
[Management.Automation.Language.Parser]::ParseInput([string]$p.script,[ref]$tokens,[ref]$errors) | Out-Null
if($errors.Count -ne 0){[Console]::Error.WriteLine(($errors | Out-String)); exit 1}
[Console]::Out.WriteLine('true')
"#;
        for script in [PREFLIGHT, FORWARDING, DHCP_ATTACHMENT] {
            assert!(run_json::<bool>(parser, &json!({"script":script})).unwrap());
        }
    }

    #[test]
    fn forwarding_read_rejects_recycled_index_without_a_write() {
        let policy = crate::gateway_policy::fixture();
        let mocks = format!(
            r#"
function Get-NetAdapter {{
  param([switch]$IncludeHidden,$ErrorAction)
  [pscustomobject]@{{InterfaceGuid='{}';ifIndex=999;HardwareInterface=$true}}
}}
function Get-NetIPInterface {{throw 'Unexpected interface read after identity mismatch'}}
function Set-NetIPInterface {{throw 'Unexpected network mutation in read-only fixture'}}
"#,
            policy.lan.guid
        );
        let error = run_json::<Option<Value>>(
            &(mocks + FORWARDING),
            &json!({"mode":"read","policy":policy}),
        )
        .unwrap_err();
        assert!(
            error
                .to_string()
                .contains("Physical LAN interface ownership changed")
        );
    }
}
