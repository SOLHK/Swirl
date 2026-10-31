//! Restricted Windows network operations for the separately elevated helper.
//!
//! Fixed PowerShell/NetTCPIP scripts receive typed JSON on stdin. No value from
//! a configuration or journal is interpolated into executable script text. All
//! mutation resources are scoped to one GUID+index pair; physical DNS settings
//! and existing default routes are never changed.
use crate::network_transaction::{InterfaceIdentity, NetworkBackend, Resource, Value};
pub use crate::windows_notify::NetworkChangeWatcher;
use ipnet::IpNet;
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::json;
use std::{
    io::{self, Read, Write},
    net::IpAddr,
    os::windows::ffi::OsStringExt,
    path::PathBuf,
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

const COMMAND_TIMEOUT: Duration = Duration::from_secs(30);
const MAX_OUTPUT: u64 = 1024 * 1024;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct NetworkAdapter {
    pub identity: InterfaceIdentity,
    pub name: String,
    pub up: bool,
    pub hardware: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct SystemRoute {
    pub interface_index: u32,
    pub destination: IpNet,
    pub next_hop: IpAddr,
    pub metric: u32,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct NetworkSnapshot {
    pub adapters: Vec<NetworkAdapter>,
    /// Default and /1 routes only, including other VPNs' captures.
    pub routes: Vec<SystemRoute>,
}

impl NetworkSnapshot {
    /// Fail closed on known default-route VPN conflicts. Per-application WFP
    /// VPNs are not discoverable from the route table and remain a test limit.
    pub fn physical_egress(&self, ipv6: bool) -> io::Result<InterfaceIdentity> {
        let family_routes = self
            .routes
            .iter()
            .filter(|r| r.destination.addr().is_ipv6() == ipv6)
            .collect::<Vec<_>>();
        if family_routes.iter().any(|r| {
            r.destination.prefix_len() == 1
                || !self
                    .adapters
                    .iter()
                    .any(|a| a.identity.index == r.interface_index && a.hardware)
        }) {
            return Err(io::Error::new(
                io::ErrorKind::AlreadyExists,
                "another VPN or non-physical default route requires explicit resolution",
            ));
        }
        family_routes
            .into_iter()
            .filter(|route| route.destination.prefix_len() == 0)
            // Disconnected hardware can retain an ActiveStore default route.
            // It is unavailable egress, not evidence of a competing VPN, and
            // must not prevent selection of an available Ethernet/Wi-Fi NIC.
            .filter(|route| {
                self.adapters
                    .iter()
                    .any(|adapter| adapter.identity.index == route.interface_index && adapter.up)
            })
            .min_by_key(|route| route.metric)
            .and_then(|route| {
                self.adapters
                    .iter()
                    .find(|adapter| adapter.identity.index == route.interface_index)
            })
            .map(|adapter| adapter.identity.clone())
            .ok_or_else(|| {
                io::Error::new(
                    io::ErrorKind::NotFound,
                    "no active physical default route for address family",
                )
            })
    }
}

pub fn snapshot() -> io::Result<NetworkSnapshot> {
    run_json(SNAPSHOT_SCRIPT, &json!({}))
}

/// Stable configuration of every enumerated adapter and every ActiveStore
/// route. This read-only acceptance snapshot excludes aging lifetimes and
/// counters; Windows does not provide an atomic snapshot across these cmdlets.
/// It is separate from the mutation journal and never authorizes a write.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NetworkConfigurationSnapshot {
    pub adapters: Vec<AdapterConfiguration>,
    pub routes: Vec<NetworkRouteConfiguration>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AdapterConfiguration {
    pub identity: InterfaceIdentity,
    pub name: String,
    pub hardware: bool,
    pub interfaces: Vec<IpInterfaceConfiguration>,
    pub addresses: Vec<IpAddressConfiguration>,
    pub dns: Vec<DnsConfiguration>,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IpInterfaceConfiguration {
    pub compartment_id: u32,
    /// Windows AF_INET / AF_INET6 values, preserved without reinterpretation.
    pub address_family: u32,
    /// Raw MSFT_NetIPInterface.NlMtu in bytes, independent of requested TUN MTU.
    pub nl_mtu_bytes: u32,
    pub dhcp: String,
    pub automatic_metric: String,
    pub interface_metric: u32,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IpAddressConfiguration {
    /// MSFT_NetIPAddress exposes this inherited field as null on real Windows
    /// adapters. Preserve that raw value without inventing an opaque identity.
    /// The JSON member remains required; only its provider value is nullable.
    #[serde(deserialize_with = "Option::deserialize")]
    pub instance_id: Option<String>,
    pub address_family: u32,
    /// Keep any IPv6 scope identifier; an IpAddr alone cannot represent it.
    pub address: String,
    pub prefix_len: u8,
    pub skip_as_source: bool,
    pub prefix_origin: String,
    pub suffix_origin: String,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DnsConfiguration {
    pub address_family: u32,
    /// Server order is resolver priority. Normalization must not sort it.
    pub servers: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NetworkRouteConfiguration {
    /// MSFT_NetRoute exposes InstanceID, not a portable CompartmentId property.
    pub instance_id: String,
    pub interface_index: u32,
    pub address_family: u32,
    pub destination: String,
    pub next_hop: String,
    pub route_metric: u32,
    pub protocol: String,
    pub publish: String,
}

impl NetworkConfigurationSnapshot {
    fn normalize(&mut self) {
        for adapter in &mut self.adapters {
            adapter.interfaces.sort();
            adapter.addresses.sort();
            // This sorts family rows, never the ordered servers inside a row.
            adapter.dns.sort();
        }
        self.adapters.sort_by(|left, right| {
            (&left.identity.guid, left.identity.index)
                .cmp(&(&right.identity.guid, right.identity.index))
        });
        self.routes.sort();
        // Preserve duplicate rows. Removing them could conceal a real change.
    }
}

pub fn snapshot_network_configuration() -> io::Result<NetworkConfigurationSnapshot> {
    let mut snapshot: NetworkConfigurationSnapshot =
        run_json(CONFIGURATION_SNAPSHOT_SCRIPT, &json!({}))?;
    if snapshot.adapters.is_empty() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Windows network configuration snapshot returned no adapters",
        ));
    }
    snapshot.normalize();
    Ok(snapshot)
}

/// Create/verify the helper's fixed state directory through the Windows known
/// CommonApplicationData location, never an inherited environment variable.
/// Existing untrusted/reparse-point directories or files are rejected rather
/// than adopted, chmodded, followed, or overwritten.
pub fn secure_state_directory() -> io::Result<PathBuf> {
    let path: String = run_json(SECURE_STATE_SCRIPT, &json!({}))?;
    let path = PathBuf::from(path);
    if !path.is_absolute() {
        return Err(io::Error::other("Windows returned a relative state path"));
    }
    Ok(path)
}

pub struct WindowsNetworkBackend {
    owned: InterfaceIdentity,
}

impl WindowsNetworkBackend {
    /// Call only with the identity returned by this session's Wintun creation.
    /// It does not elevate the current process or touch routes/DNS.
    pub fn for_owned_interface(owned: InterfaceIdentity) -> io::Result<Self> {
        owned.validate()?;
        Ok(Self { owned })
    }

    fn check_identity(&self, identity: &InterfaceIdentity) -> io::Result<()> {
        identity.validate()?;
        if identity != &self.owned {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                format!(
                    "interface ownership mismatch: expected {:?}, received {identity:?}",
                    self.owned
                ),
            ));
        }
        Ok(())
    }

    fn check_resource(&self, resource: &Resource) -> io::Result<()> {
        if matches!(resource, Resource::GatewayIsolation { .. }) {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "physical gateway isolation requires its dedicated backend",
            ));
        }
        if let Resource::DnsGuard { name } = resource {
            let prefix = format!("Swirl.NativeTun.DNS.{}.", self.owned.guid);
            let suffix = name.strip_prefix(&prefix).ok_or_else(|| {
                io::Error::new(
                    io::ErrorKind::PermissionDenied,
                    "firewall rule outside owned namespace",
                )
            })?;
            let (owner, protocol) = suffix.split_once('.').ok_or_else(|| {
                io::Error::new(io::ErrorKind::InvalidInput, "invalid firewall rule name")
            })?;
            if owner.len() != 32
                || !owner.bytes().all(|c| c.is_ascii_hexdigit())
                || !matches!(protocol, "tcp" | "udp")
            {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "invalid firewall rule owner",
                ));
            }
        }
        Ok(())
    }
}

fn normalized(mut value: Option<Value>) -> Option<Value> {
    if let Some(Value::DnsGuard { interfaces, .. }) = &mut value {
        interfaces.sort();
    }
    value
}

impl NetworkBackend for WindowsNetworkBackend {
    fn read(
        &mut self,
        interface: &InterfaceIdentity,
        resource: &Resource,
    ) -> io::Result<Option<Value>> {
        self.check_identity(interface)?;
        self.check_resource(resource)?;
        run_json(
            RESOURCE_SCRIPT,
            &json!({"mode":"read", "interface":interface, "resource":resource}),
        )
        .map(normalized)
    }

    fn compare_exchange(
        &mut self,
        interface: &InterfaceIdentity,
        resource: &Resource,
        expected: &Option<Value>,
        desired: &Option<Value>,
    ) -> io::Result<()> {
        self.check_identity(interface)?;
        self.check_resource(resource)?;
        // This primitive serves both installation and journal recovery.
        // Validate the full OS state range here: recovery's desired MTU may be
        // a captured value larger than the MTU Swirl is allowed to install.
        // Journal::prepare/validate separately constrain every after value.
        crate::network_transaction::validate_value(resource, expected).map_err(|error| {
            io::Error::new(
                error.kind(),
                format!("compare_exchange expected validation: {error}"),
            )
        })?;
        crate::network_transaction::validate_value(resource, desired).map_err(|error| {
            io::Error::new(
                error.kind(),
                format!("compare_exchange desired validation: {error}"),
            )
        })?;
        for value in [expected, desired] {
            if let (
                Resource::DnsGuard { name },
                Some(Value::DnsGuard {
                    protocol, owner, ..
                }),
            ) = (resource, value)
                && name != &crate::network_transaction::dns_guard_name(interface, owner, *protocol)
            {
                return Err(io::Error::new(
                    io::ErrorKind::PermissionDenied,
                    "DNS guard metadata does not match its owner name",
                ));
            }
        }
        let actual: Option<Value> = run_json(
            RESOURCE_SCRIPT,
            &json!({"mode":"compare_exchange", "interface":interface, "resource":resource, "expected":expected, "desired":desired}),
        ).map_err(|error| {
            if error.to_string().starts_with("Windows network operation failed: Network resource changed after snapshot; refusing overwrite") {
                io::Error::new(io::ErrorKind::AlreadyExists, error)
            } else { error }
        })?;
        if &normalized(actual) != desired {
            return Err(io::Error::other("Windows network readback mismatch"));
        }
        Ok(())
    }
}

pub(crate) fn run_json<T: DeserializeOwned>(
    script: &str,
    input: &serde_json::Value,
) -> io::Result<T> {
    run_json_with_timeout(script, input, COMMAND_TIMEOUT)
}

fn run_json_with_timeout<T: DeserializeOwned>(
    script: &str,
    input: &serde_json::Value,
    timeout: Duration,
) -> io::Result<T> {
    let bytes = serde_json::to_vec(input).map_err(io::Error::other)?;
    if bytes.len() > 64 * 1024 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "helper request too large",
        ));
    }
    let powershell = system_powershell()?;
    let modules = powershell
        .parent()
        .ok_or_else(|| io::Error::other("missing system PowerShell directory"))?
        .join("Modules");
    let mut command = Command::new(powershell);
    command
        .args([
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ])
        // Never auto-import a user-supplied NetTCPIP or NetAdapter module in a
        // privileged helper via the inherited PSModulePath.
        .env("PSModulePath", modules)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    // The command is suspended until assigned to a kill-on-close Job Object.
    // Worker death terminates this process tree, and normal exit/timeout also
    // stop descendants before pipe joins. An in-flight CIM service call still
    // requires journal readback; process exit alone is not rollback proof.
    // No unowned child fallback is permitted.
    let mut child = crate::windows_command::spawn_owned(&mut command)?;
    let mut stdin = child
        .stdin
        .take()
        .ok_or_else(|| io::Error::other("missing helper stdin"))?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| io::Error::other("missing helper stdout"))?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| io::Error::other("missing helper stderr"))?;
    // Pipe I/O belongs to a control operation, never packet I/O. Write on a
    // separate thread so a child that stops reading cannot fill the pipe and
    // block before the operation deadline is checked.
    let in_writer = thread::spawn(move || stdin.write_all(&bytes));
    let out_reader = thread::spawn(move || read_bounded(stdout));
    let err_reader = thread::spawn(move || read_bounded(stderr));
    let start = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Ok(status),
            Ok(None) => {}
            // OwnedChild has already stopped the job and reaped the child on
            // a wait error. Join every pipe owner below before returning it.
            Err(error) => break Err(error),
        }
        if start.elapsed() >= timeout {
            // kill() terminates the entire Job Object, including descendants
            // that might otherwise keep a redirected pipe open indefinitely.
            let termination = child.kill();
            let _ = child.wait();
            let message = match termination {
                Ok(()) => "Windows network operation timed out; recover its journal".into(),
                Err(error) => format!(
                    "Windows network operation timed out; job termination reported {error}; recover its journal"
                ),
            };
            break Err(io::Error::new(io::ErrorKind::TimedOut, message));
        }
        thread::sleep(Duration::from_millis(25));
    };
    // Collect all joins before propagating any I/O error: even a broken stdin
    // must not leave a reader thread detached from this control operation.
    let written = in_writer.join();
    let stdout = out_reader.join();
    let stderr = err_reader.join();
    let status = status?;
    written.map_err(|_| io::Error::other("stdin writer panicked"))??;
    let stdout = stdout.map_err(|_| io::Error::other("stdout reader panicked"))??;
    let stderr = stderr.map_err(|_| io::Error::other("stderr reader panicked"))??;
    if !status.success() {
        return Err(io::Error::other(format!(
            "Windows network operation failed: {}",
            String::from_utf8_lossy(&stderr).trim()
        )));
    }
    let stdout = stdout.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(&stdout);
    decode_json(stdout)
}

fn decode_json<T: DeserializeOwned>(stdout: &[u8]) -> io::Result<T> {
    serde_json::from_slice(stdout).map_err(|error| {
        // Report exact null field locations without printing addresses, adapter
        // names or other system configuration. Keep the original strict type
        // error; missing provider values must not become invented defaults.
        let mut null_fields = Vec::new();
        if let Ok(value) = serde_json::from_slice::<serde_json::Value>(stdout) {
            let mut pending = vec![(String::new(), &value)];
            while let Some((path, value)) = pending.pop() {
                match value {
                    serde_json::Value::Null => null_fields.push(path),
                    serde_json::Value::Object(fields) => {
                        for (key, value) in fields {
                            let key = key.replace('~', "~0").replace('/', "~1");
                            pending.push((format!("{path}/{key}"), value));
                        }
                    }
                    serde_json::Value::Array(values) => {
                        for (index, value) in values.iter().enumerate() {
                            pending.push((format!("{path}/{index}"), value));
                        }
                    }
                    _ => {}
                }
                if null_fields.len() == 32 {
                    break;
                }
            }
        }
        io::Error::new(
            io::ErrorKind::InvalidData,
            format!(
                "Windows network helper returned invalid JSON ({} bytes): {error}; raw null field pointers (up to 32): {}",
                stdout.len(), json!(null_fields)
            ),
        )
    })
}

fn read_bounded(reader: impl Read) -> io::Result<Vec<u8>> {
    let mut output = Vec::new();
    reader.take(MAX_OUTPUT + 1).read_to_end(&mut output)?;
    if output.len() as u64 > MAX_OUTPUT {
        return Err(io::Error::other("network helper output exceeded limit"));
    }
    Ok(output)
}

#[allow(unsafe_code)]
fn system_powershell() -> io::Result<PathBuf> {
    let mut buffer = [0u16; 32768];
    // SAFETY: Windows receives a writable buffer of the stated size, writes a
    // bounded UTF-16 path, and does not retain its pointer.
    let length = unsafe {
        windows_sys::Win32::System::SystemInformation::GetSystemDirectoryW(
            buffer.as_mut_ptr(),
            buffer.len() as u32,
        )
    } as usize;
    if length == 0 {
        return Err(io::Error::last_os_error());
    }
    if length >= buffer.len() {
        return Err(io::Error::other("system directory exceeds path limit"));
    }
    Ok(
        PathBuf::from(std::ffi::OsString::from_wide(&buffer[..length]))
            .join("WindowsPowerShell/v1.0/powershell.exe"),
    )
}

// This script never accepts a command/expression/filename supplied by callers.
// Resource values are parsed as typed IPs/prefix lengths in Rust before use.
const RESOURCE_SCRIPT: &str = r#"
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
  $p = [Console]::In.ReadToEnd() | ConvertFrom-Json
  $index = [uint32]$p.interface.index
  $expectedGuid = [guid]$p.interface.guid
  function Owned-Adapter {
    $all = @(Get-NetAdapter -IncludeHidden -ErrorAction Stop)
    $adapters = @($all | Where-Object { ([guid]$_.InterfaceGuid) -eq $expectedGuid })
    if ($adapters.Count -eq 0) { return $null }
    if ($adapters.Count -ne 1 -or $adapters[0].ifIndex -ne $index) { throw 'TUN interface ownership changed' }
    if ($adapters[0].HardwareInterface) { throw 'Refusing to mutate a physical interface' }
    return $adapters[0]
  }
  function Read-State {
    if ($p.resource.kind -ne 'dns_guard' -and $null -eq (Owned-Adapter)) { return $null }
    switch ($p.resource.kind) {
      'forwarding' {
        $family = if ($p.resource.ipv6) { 'IPv6' } else { 'IPv4' }
        $rows = @(Get-NetIPInterface -InterfaceIndex $index -AddressFamily $family -PolicyStore ActiveStore -ErrorAction Stop)
        if ($rows.Count -ne 1 -or [string]$rows[0].Forwarding -notin @('Enabled','Disabled')) { throw 'Ambiguous forwarding state' }
        return @{kind='forwarding';enabled=([string]$rows[0].Forwarding -eq 'Enabled')}
      }
      'mtu' {
        $family = if ($p.resource.ipv6) { 'IPv6' } else { 'IPv4' }
        $rows = @(Get-NetIPInterface -InterfaceIndex $index -AddressFamily $family -PolicyStore ActiveStore -ErrorAction Stop)
        if ($rows.Count -ne 1) { throw 'Ambiguous MTU ownership' }
        # NlMtuBytes is the Set-NetIPInterface parameter. Its CIM result exposes
        # NlMtu; casting a missing property to uint32 would silently invent zero.
        $mtuProperty = $rows[0].PSObject.Properties['NlMtu']
        if ($null -eq $mtuProperty -or $null -eq $mtuProperty.Value) { throw 'Windows MTU snapshot missing NlMtu property or value' }
        return @{kind='mtu';mtu=[uint32]$mtuProperty.Value}
      }
      'address' {
        $rows = @(Get-NetIPAddress -InterfaceIndex $index -PolicyStore ActiveStore -ErrorAction Stop | Where-Object { $_.IPAddress -eq $p.resource.address })
        if ($rows.Count -gt 1) { throw 'Ambiguous interface address' }
        if ($rows.Count -eq 0) { return $null }
        return @{kind='address';prefix_len=[int]$rows[0].PrefixLength;skip_as_source=[bool]$rows[0].SkipAsSource}
      }
      'route' {
        $rows = @(Get-NetRoute -InterfaceIndex $index -PolicyStore ActiveStore -ErrorAction Stop | Where-Object { $_.DestinationPrefix -eq $p.resource.destination -and $_.NextHop -eq $p.resource.next_hop })
        if ($rows.Count -gt 1) { throw 'Ambiguous route ownership' }
        if ($rows.Count -eq 0) { return $null }
        return @{kind='route';metric=[uint32]$rows[0].RouteMetric}
      }
      'dns' {
        $servers = @(Get-DnsClientServerAddress -InterfaceIndex $index -ErrorAction Stop | Sort-Object AddressFamily | ForEach-Object { $_.ServerAddresses } | ForEach-Object { ([ipaddress]$_).ToString() })
        return @{kind='dns';servers=$servers}
      }
      'dns_guard' {
        try { $rules = @(Get-NetFirewallRule -Name ([string]$p.resource.name) -PolicyStore PersistentStore -ErrorAction Stop) }
        catch { if ($_.CategoryInfo.Category -eq [System.Management.Automation.ErrorCategory]::ObjectNotFound) { return $null } else { throw } }
        if ($rules.Count -ne 1) { throw 'Ambiguous firewall rule ownership' }
        $rule = $rules[0]
        $pieces = ([string]$p.resource.name).Split('.')
        $owner = $pieces[$pieces.Length-2]
        if ([string]$rule.Name -cne [string]$p.resource.name -or [string]$rule.DisplayName -cne [string]$p.resource.name -or [string]$rule.Group -cne 'Swirl Native TUN DNS Guard' -or [string]$rule.Description -cne ('Swirl native TUN DNS guard owner ' + $owner)) { throw 'Firewall ownership metadata changed' }
        if ([string]$rule.Direction -ne 'Outbound' -or [string]$rule.Action -ne 'Block' -or [string]$rule.Enabled -ne 'True' -or [string]$rule.Profile -ne 'Any') { throw 'DNS firewall rule scope changed' }
        $port = $rule | Get-NetFirewallPortFilter -ErrorAction Stop
        $protocol = switch ([string]$port.Protocol) { 'TCP' {'tcp'} '6' {'tcp'} 'UDP' {'udp'} '17' {'udp'} default {throw 'DNS firewall protocol changed'} }
        if ([string]$port.RemotePort -ne '53' -or [string]$port.LocalPort -ne 'Any') { throw 'DNS firewall port scope changed' }
        $address = $rule | Get-NetFirewallAddressFilter -ErrorAction Stop
        if ([string]$address.LocalAddress -ne 'Any' -or [string]$address.RemoteAddress -ne 'Any') { throw 'DNS firewall address scope changed' }
        $application = $rule | Get-NetFirewallApplicationFilter -ErrorAction Stop
        $service = $rule | Get-NetFirewallServiceFilter -ErrorAction Stop
        if ([string]$application.Program -ne 'Any' -or [string]$service.Service -ne 'Any') { throw 'DNS firewall application scope changed' }
        $interfaceType = $rule | Get-NetFirewallInterfaceTypeFilter -ErrorAction Stop
        if ([string]$interfaceType.InterfaceType -ne 'Any') { throw 'DNS firewall interface type scope changed' }
        $security = $rule | Get-NetFirewallSecurityFilter -ErrorAction Stop
        if ([string]$security.Authentication -ne 'NotRequired' -or [string]$security.Encryption -ne 'NotRequired' -or [string]$security.LocalUser -ne 'Any' -or [string]$security.RemoteUser -ne 'Any' -or [string]$security.RemoteMachine -ne 'Any') { throw 'DNS firewall security scope changed' }
        $aliases = @($rule | Get-NetFirewallInterfaceFilter -ErrorAction Stop | ForEach-Object { $_.InterfaceAlias })
        return @{kind='dns_guard';protocol=$protocol;interfaces=$aliases;owner=$owner}
      }
      default { throw 'Unsupported network resource' }
    }
  }
  function Same-State($a, $b) {
    if ($null -eq $a -or $null -eq $b) { return ($null -eq $a -and $null -eq $b) }
    if ($a.kind -ne $b.kind) { return $false }
    switch ($a.kind) {
      'forwarding' { return ($a.enabled -eq $b.enabled) }
      'mtu' { return ($a.mtu -eq $b.mtu) }
      'address' { return ($a.prefix_len -eq $b.prefix_len -and $a.skip_as_source -eq $b.skip_as_source) }
      'route' { return ($a.metric -eq $b.metric) }
      'dns' { return ((@($a.servers) -join ',') -ceq (@($b.servers) -join ',')) }
      'dns_guard' {
        if ($a.protocol -ne $b.protocol -or $a.owner -cne $b.owner -or @($a.interfaces).Count -ne @($b.interfaces).Count) { return $false }
        foreach ($alias in @($a.interfaces)) { if (@($b.interfaces) -cnotcontains $alias) { return $false } }
        return $true
      }
    }
    return $false
  }
  $current = Read-State
  if ($p.mode -eq 'compare_exchange') {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'An independently elevated TUN helper is required' }
    if (-not (Same-State $current $p.expected)) { throw 'Network resource changed after snapshot; refusing overwrite' }
    $value = $p.desired
    if (($p.resource.kind -ne 'dns_guard' -or $null -ne $value) -and $null -eq (Owned-Adapter)) { throw 'Owned TUN no longer exists' }
    switch ($p.resource.kind) {
      'forwarding' {
        if ($null -eq $value) { throw 'Interface forwarding state cannot be removed' }
        $family = if ($p.resource.ipv6) { 'IPv6' } else { 'IPv4' }
        $forwarding = if ($value.enabled) { 'Enabled' } else { 'Disabled' }
        Set-NetIPInterface -InterfaceIndex $index -AddressFamily $family -Forwarding $forwarding -PolicyStore ActiveStore -ErrorAction Stop
      }
      'mtu' {
        if ($null -eq $value) { throw 'An interface MTU cannot be removed' }
        $family = if ($p.resource.ipv6) { 'IPv6' } else { 'IPv4' }
        Set-NetIPInterface -InterfaceIndex $index -AddressFamily $family -NlMtuBytes ([uint32]$value.mtu) -PolicyStore ActiveStore -ErrorAction Stop
      }
      'address' {
        if ($null -eq $value) {
          Get-NetIPAddress -InterfaceIndex $index -PolicyStore ActiveStore | Where-Object { $_.IPAddress -eq $p.resource.address } | Remove-NetIPAddress -Confirm:$false -ErrorAction Stop
        } elseif ($null -eq $current) {
          New-NetIPAddress -InterfaceIndex $index -IPAddress ([string]$p.resource.address) -PrefixLength ([byte]$value.prefix_len) -SkipAsSource ([bool]$value.skip_as_source) -PolicyStore ActiveStore -ErrorAction Stop | Out-Null
        } else {
          Get-NetIPAddress -InterfaceIndex $index -PolicyStore ActiveStore | Where-Object { $_.IPAddress -eq $p.resource.address } | Set-NetIPAddress -PrefixLength ([byte]$value.prefix_len) -SkipAsSource ([bool]$value.skip_as_source) -Confirm:$false -ErrorAction Stop | Out-Null
        }
      }
      'route' {
        if ($null -eq $value) {
          Get-NetRoute -InterfaceIndex $index -PolicyStore ActiveStore | Where-Object { $_.DestinationPrefix -eq $p.resource.destination -and $_.NextHop -eq $p.resource.next_hop } | Remove-NetRoute -Confirm:$false -ErrorAction Stop
        } elseif ($null -eq $current) {
          New-NetRoute -InterfaceIndex $index -DestinationPrefix ([string]$p.resource.destination) -NextHop ([string]$p.resource.next_hop) -RouteMetric ([uint32]$value.metric) -PolicyStore ActiveStore -ErrorAction Stop | Out-Null
        } else {
          Get-NetRoute -InterfaceIndex $index -PolicyStore ActiveStore | Where-Object { $_.DestinationPrefix -eq $p.resource.destination -and $_.NextHop -eq $p.resource.next_hop } | Set-NetRoute -RouteMetric ([uint32]$value.metric) -Confirm:$false -ErrorAction Stop | Out-Null
        }
      }
      'dns' {
        if ($null -eq $value -or @($value.servers).Count -eq 0) {
          Set-DnsClientServerAddress -InterfaceIndex $index -ResetServerAddresses -Confirm:$false -ErrorAction Stop
        } else {
          Set-DnsClientServerAddress -InterfaceIndex $index -ServerAddresses ([string[]]$value.servers) -Confirm:$false -ErrorAction Stop
        }
      }
      'dns_guard' {
        if ($null -eq $value) {
          if ($null -ne $current) { Remove-NetFirewallRule -Name ([string]$p.resource.name) -PolicyStore PersistentStore -Confirm:$false -ErrorAction Stop }
        } else {
          if ($null -ne $current) { throw 'Refusing to replace an existing firewall rule' }
          if ((Get-Service -Name mpssvc -ErrorAction Stop).Status -ne 'Running') { throw 'Windows Defender Firewall service is not running' }
          $profiles = @(Get-NetFirewallProfile -PolicyStore ActiveStore -ErrorAction Stop)
          if ($profiles.Count -ne 3 -or @($profiles | Where-Object { [string]$_.Enabled -ne 'True' -or [string]$_.AllowLocalFirewallRules -eq 'False' }).Count -ne 0) { throw 'Firewall profiles must enforce local DNS guard rules' }
          $hardware = @(Get-NetAdapter -IncludeHidden -Physical -ErrorAction Stop | ForEach-Object { [string]$_.Name })
          foreach ($alias in @($value.interfaces)) { if ($hardware -cnotcontains $alias) { throw 'DNS guard alias is not a physical adapter' } }
          if (@($hardware | Where-Object { @($value.interfaces) -cnotcontains $_ }).Count -ne 0) { throw 'DNS guard must cover every known physical adapter, including disconnected adapters' }
          $protocol = if ($value.protocol -eq 'tcp') { 'TCP' } else { 'UDP' }
          New-NetFirewallRule -Name ([string]$p.resource.name) -DisplayName ([string]$p.resource.name) -Group 'Swirl Native TUN DNS Guard' -Description ('Swirl native TUN DNS guard owner ' + [string]$value.owner) -Direction Outbound -Action Block -Enabled True -Profile Any -Protocol $protocol -RemotePort 53 -LocalPort Any -LocalAddress Any -RemoteAddress Any -Program Any -Service Any -InterfaceAlias ([string[]]$value.interfaces) -EdgeTraversalPolicy Block -PolicyStore PersistentStore -ErrorAction Stop | Out-Null
        }
      }
    }
    $current = Read-State
    if (-not (Same-State $current $value)) { throw 'Windows rejected or altered requested network state' }
  } elseif ($p.mode -ne 'read') { throw 'Unsupported helper operation' }
  # Windows PowerShell 5.1 emits nothing for ConvertTo-Json $null. Missing
  # resources are a successful typed None, so they need an explicit JSON null.
  if ($null -eq $current) { [Console]::Out.WriteLine('null') }
  else { ConvertTo-Json -InputObject $current -Compress -Depth 8 }
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
"#;

const SNAPSHOT_SCRIPT: &str = r#"
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
  $adapters = @(Get-NetAdapter -IncludeHidden -ErrorAction Stop | ForEach-Object {
    @{identity=@{index=[uint32]$_.ifIndex;guid=([guid]$_.InterfaceGuid).ToString('D').ToLowerInvariant()};name=[string]$_.Name;up=($_.Status -eq 'Up');hardware=[bool]$_.HardwareInterface}
  })
  $routes = @(Get-NetRoute -PolicyStore ActiveStore -ErrorAction Stop | Where-Object { $_.DestinationPrefix -in @('0.0.0.0/0','::/0','0.0.0.0/1','128.0.0.0/1','::/1','8000::/1') } | ForEach-Object {
    $ipif = Get-NetIPInterface -InterfaceIndex $_.InterfaceIndex -AddressFamily $_.AddressFamily -ErrorAction Stop
    @{interface_index=[uint32]$_.InterfaceIndex;destination=[string]$_.DestinationPrefix;next_hop=[string]$_.NextHop;metric=([uint32]$_.RouteMetric + [uint32]$ipif.InterfaceMetric)}
  })
  ConvertTo-Json -InputObject @{adapters=$adapters;routes=$routes} -Compress -Depth 8
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
"#;

// Enumerate globally before filtering by adapter index: a disabled address
// family is represented by an actually empty list, while a cmdlet failure must
// fail the snapshot. No per-interface ObjectNotFound error is suppressed.
const CONFIGURATION_SNAPSHOT_SCRIPT: &str = r#"
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
  $adapters = @(Get-NetAdapter -IncludeHidden -ErrorAction Stop)
  $interfaces = @(Get-NetIPInterface -PolicyStore ActiveStore -IncludeAllCompartments -ErrorAction Stop)
  $addresses = @(Get-NetIPAddress -PolicyStore ActiveStore -IncludeAllCompartments -ErrorAction Stop)
  $dns = @(Get-DnsClientServerAddress -ErrorAction Stop)
  $routes = @(Get-NetRoute -PolicyStore ActiveStore -IncludeAllCompartments -ErrorAction Stop | ForEach-Object {
    @{instance_id=$_.InstanceID;interface_index=$_.InterfaceIndex;address_family=$_.AddressFamily;destination=$_.DestinationPrefix;next_hop=$_.NextHop;route_metric=$_.RouteMetric;protocol=$_.Protocol.ToString();publish=$_.Publish.ToString()}
  })
  $configuration = @($adapters | ForEach-Object {
    $adapter = $_
    $index = $adapter.ifIndex
    $ip = @($interfaces | Where-Object { $_.InterfaceIndex -eq $index } | ForEach-Object {
      $mtuProperty = $_.PSObject.Properties['NlMtu']
      if ($null -eq $mtuProperty -or $null -eq $mtuProperty.Value) { throw 'Windows configuration snapshot missing NlMtu property or value' }
      @{compartment_id=$_.CompartmentId;address_family=$_.AddressFamily;nl_mtu_bytes=$mtuProperty.Value;dhcp=$_.Dhcp.ToString();automatic_metric=$_.AutomaticMetric.ToString();interface_metric=$_.InterfaceMetric}
    })
    $address = @($addresses | Where-Object { $_.InterfaceIndex -eq $index } | ForEach-Object {
      @{instance_id=$_.InstanceID;address_family=$_.AddressFamily;address=$_.IPAddress;prefix_len=$_.PrefixLength;skip_as_source=$_.SkipAsSource;prefix_origin=$_.PrefixOrigin.ToString();suffix_origin=$_.SuffixOrigin.ToString()}
    })
    $servers = @($dns | Where-Object { $_.InterfaceIndex -eq $index } | ForEach-Object {
      # A present DNS row with null ServerAddresses has no configured servers.
      # Keep null entries inside a non-null array visible to the typed decoder.
      $serverAddresses = @()
      if ($null -ne $_.ServerAddresses) { $serverAddresses = @($_.ServerAddresses) }
      @{address_family=$_.AddressFamily;servers=$serverAddresses}
    })
    @{identity=@{index=$index;guid=([guid]$adapter.InterfaceGuid).ToString('D').ToLowerInvariant()};name=$adapter.Name;hardware=$adapter.HardwareInterface;interfaces=$ip;addresses=$address;dns=$servers}
  })
  ConvertTo-Json -InputObject @{adapters=$configuration;routes=$routes} -Compress -Depth 12
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
"#;

const SECURE_STATE_SCRIPT: &str = r#"
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
  $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
  if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'State setup requires the independently elevated helper' }
  $known = [Environment]::GetFolderPath([Environment+SpecialFolder]::CommonApplicationData)
  if ([string]::IsNullOrWhiteSpace($known) -or [IO.Path]::GetPathRoot($known) -notmatch '^[A-Za-z]:\\$') { throw 'Windows CommonApplicationData is unavailable' }
  $base = [IO.Path]::GetFullPath($known)
  if ([IO.Path]::GetPathRoot($base) -notmatch '^[A-Za-z]:\\$') { throw 'Helper state must reside on a local Windows drive' }
  $parent = [IO.DirectoryInfo]::new($base)
  while ($null -ne $parent) {
    if (-not $parent.Exists -or ($parent.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Untrusted state ancestor or reparse point' }
    $parent = $parent.Parent
  }
  $admins = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
  $system = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
  $ownerRights = [Security.Principal.SecurityIdentifier]::new('S-1-3-4')
  $inherit = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
  $propagate = [Security.AccessControl.PropagationFlags]::None
  $allow = [Security.AccessControl.AccessControlType]::Allow
  $full = [Security.AccessControl.FileSystemRights]::FullControl
  $readAcl = [Security.AccessControl.FileSystemRights]::ReadPermissions
  $acl = [Security.AccessControl.DirectorySecurity]::new()
  $acl.SetOwner($admins)
  $acl.SetAccessRuleProtection($true,$false)
  $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($admins,$full,$inherit,$propagate,$allow))
  $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($system,$full,$inherit,$propagate,$allow))
  # OWNER RIGHTS suppresses the implicit owner WRITE_DAC grant. A file whose
  # default owner is the elevated user's SID cannot then be rewritten later
  # by the same user's unelevated token through an owner/DACL takeover.
  $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($ownerRights,$readAcl,$inherit,$propagate,$allow))
  function Verify-StateItem($item, $directory) {
    $item.Refresh()
    if (-not $item.Exists -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Reparse point or missing helper state item' }
    $actual = $item.GetAccessControl()
    if ($directory -and (-not $actual.AreAccessRulesProtected -or $actual.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-32-544','S-1-5-18'))) { throw 'Existing state directory has untrusted ownership or inherited ACLs' }
    $trusted = @{}
    $ownerRestricted = $false
    foreach ($rule in $actual.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
      if ($rule.AccessControlType -ne $allow) { throw 'Unexpected helper state access denial' }
      $sid = $rule.IdentityReference.Value
      if ($sid -eq 'S-1-3-4') {
        $safeOwner = [int]$readAcl -bor [int][Security.AccessControl.FileSystemRights]::Synchronize
        if (([int]$rule.FileSystemRights -band (-bnot $safeOwner)) -ne 0 -or ([int]$rule.FileSystemRights -band [int]$readAcl) -ne [int]$readAcl) { throw 'State owner has unsafe implicit access' }
        $ownerRestricted = $true
      } elseif ($sid -in @('S-1-5-32-544','S-1-5-18')) {
        if (($rule.FileSystemRights -band $full) -eq $full) { $trusted[$sid] = $true }
      } else { throw 'State ACL grants access outside Administrators and SYSTEM' }
    }
    if (-not $ownerRestricted -or -not $trusted['S-1-5-32-544'] -or -not $trusted['S-1-5-18']) { throw 'State ACL is missing required protection' }
  }
  $path = $base
  foreach ($component in @('Swirl','NativeTun')) {
    $path = [IO.Path]::Combine($path,$component)
    # DirectorySecurity is applied at creation, eliminating a public-write
    # interval. Existing directories are only inspected, never taken over.
    $directory = [IO.Directory]::CreateDirectory($path,$acl)
    Verify-StateItem $directory $true
  }
  foreach ($entry in $directory.EnumerateFileSystemInfos()) {
    if (($entry.Attributes -band [IO.FileAttributes]::Directory)) { throw 'Unexpected nested directory in helper state' }
    Verify-StateItem $entry $false
  }
  ConvertTo-Json -InputObject $path -Compress
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
"#;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn different_interface_guid_or_index_is_rejected_before_network_commands() {
        let owned = InterfaceIdentity::new(71, 1);
        let mut backend = WindowsNetworkBackend::for_owned_interface(owned).unwrap();
        // These valid but unowned identities must fail in Rust before a
        // PowerShell child can query or mutate any actual network adapter.
        for unowned in [InterfaceIdentity::new(71, 2), InterfaceIdentity::new(72, 1)] {
            for ipv6 in [false, true] {
                let resource = Resource::Mtu { ipv6 };
                let error = backend.read(&unowned, &resource).unwrap_err();
                assert_eq!(error.kind(), io::ErrorKind::PermissionDenied);
                assert!(error.to_string().contains("interface ownership mismatch"));
                let error = backend
                    .compare_exchange(
                        &unowned,
                        &resource,
                        &Some(Value::Mtu { mtu: 1500 }),
                        &Some(Value::Mtu { mtu: u32::MAX }),
                    )
                    .unwrap_err();
                assert_eq!(error.kind(), io::ErrorKind::PermissionDenied);
                assert!(error.to_string().contains("interface ownership mismatch"));
            }
        }
    }

    #[test]
    fn unread_stdin_cannot_block_the_control_deadline() {
        // A 60 KiB request exceeds the redirected pipe capacity. This actual
        // PowerShell child intentionally never reads it and would otherwise
        // keep both the writer and the output readers blocked for two minutes.
        // No network state changes or administrative access are used.
        const BLOCKED: &str = "Start-Sleep -Seconds 120; [Console]::Out.WriteLine('true')";
        let start = Instant::now();
        let error = run_json_with_timeout::<bool>(
            BLOCKED,
            &json!({"blocked_input": "x".repeat(60 * 1024)}),
            Duration::from_secs(2),
        )
        .unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::TimedOut);
        assert!(
            start.elapsed() < Duration::from_secs(15),
            "control timeout did not close the blocked pipes"
        );
    }

    fn read_mtu_from_mock_cim_row(row: &str, ipv6: bool) -> io::Result<Option<Value>> {
        // Only test code provides this prefix. Execute the complete production
        // RESOURCE_SCRIPT and its normal JSON input/output on system PowerShell.
        let mocks = format!(
            r#"
function Get-NetAdapter {{
  [CmdletBinding()]
  param([switch]$IncludeHidden)
  [pscustomobject]@{{InterfaceGuid=[guid]'00000000-0000-0000-0000-000000000001';ifIndex=71;HardwareInterface=$false}}
}}
function Get-NetIPInterface {{
  [CmdletBinding()]
  param([uint32]$InterfaceIndex,[string]$AddressFamily,[string]$PolicyStore)
  if ($InterfaceIndex -ne 71 -or $AddressFamily -notin @('IPv4','IPv6') -or $PolicyStore -ne 'ActiveStore') {{ throw 'Wrong MTU query scope' }}
  [pscustomobject]@{{{row}}}
}}
"#
        );
        run_json(
            &format!("{mocks}\n{RESOURCE_SCRIPT}"),
            &json!({
                "mode":"read",
                "interface":InterfaceIdentity::new(71, 1),
                "resource":Resource::Mtu { ipv6 },
            }),
        )
    }

    #[test]
    fn mtu_snapshot_reads_cim_nlmtu_instead_of_cmdlet_parameter_name() {
        for (ipv6, mtu) in [(false, 1500), (true, 65535), (true, u32::MAX)] {
            let actual = read_mtu_from_mock_cim_row(
                &format!("NlMtu=[uint32]{mtu};NlMtuBytes=[uint32]0"),
                ipv6,
            )
            .unwrap();
            assert_eq!(actual, Some(Value::Mtu { mtu }));
        }
    }

    #[test]
    fn mtu_snapshot_rejects_missing_or_null_cim_property_without_inventing_zero() {
        for row in [
            "NlMtuBytes=[uint32]1500",
            "NlMtu=$null;NlMtuBytes=[uint32]1500",
        ] {
            let error = read_mtu_from_mock_cim_row(row, false).unwrap_err();
            assert!(
                error
                    .to_string()
                    .contains("Windows MTU snapshot missing NlMtu property or value"),
                "{error}"
            );
        }
    }

    #[test]
    fn real_net_ip_interface_exposes_non_null_cim_nlmtu_read_only() {
        // Verify the actual Windows provider schema, without changing any
        // adapter, route or MTU. Missing fields must fail, never cast to zero.
        const READ_SCHEMA: &str = r#"
$ErrorActionPreference='Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$rows = @(Get-NetIPInterface -PolicyStore ActiveStore -ErrorAction Stop)
if ($rows.Count -eq 0) { throw 'No real IP interfaces to verify' }
$values = @($rows | ForEach-Object {
  $property = $_.PSObject.Properties['NlMtu']
  if ($null -eq $property -or $null -eq $property.Value) { throw 'Windows provider did not expose NlMtu' }
  [uint32]$property.Value
})
ConvertTo-Json -InputObject $values -Compress
"#;
        let values: Vec<u32> = run_json(READ_SCHEMA, &json!({})).unwrap();
        assert!(!values.is_empty());
    }

    #[test]
    fn missing_owned_resource_is_json_null_on_system_powershell() {
        // Read-only: use an absent test identity and never create an adapter.
        // Exercise the real system PowerShell version, including 5.1's null
        // serialization behavior, without creating any network resources.
        let identity = InterfaceIdentity::new(u32::MAX, 0x72b3267d68984af3a5b41e3152d2a3d9);
        let mut backend = WindowsNetworkBackend::for_owned_interface(identity.clone()).unwrap();
        assert_eq!(
            backend
                .read(
                    &identity,
                    &Resource::Address {
                        address: "198.18.0.1".parse().unwrap(),
                    },
                )
                .unwrap(),
            None
        );
    }

    #[test]
    fn fixed_helper_scripts_parse_without_executing_network_commands() {
        const PARSE: &str = r#"
$ErrorActionPreference='Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$p = [Console]::In.ReadToEnd() | ConvertFrom-Json
$tokens=$null
$errors=$null
$null = [System.Management.Automation.Language.Parser]::ParseInput([string]$p.script,[ref]$tokens,[ref]$errors)
if (@($errors).Count -ne 0) { [Console]::Error.WriteLine(($errors | Out-String)); exit 1 }
ConvertTo-Json -InputObject $true
"#;
        for script in [
            RESOURCE_SCRIPT,
            SNAPSHOT_SCRIPT,
            CONFIGURATION_SNAPSHOT_SCRIPT,
            SECURE_STATE_SCRIPT,
        ] {
            assert!(run_json::<bool>(PARSE, &json!({"script":script})).unwrap());
        }
    }

    #[test]
    fn configuration_snapshot_reads_system_state_without_network_writes() {
        let snapshot = snapshot_network_configuration().unwrap();
        assert!(!snapshot.adapters.is_empty());
        let bytes = serde_json::to_vec(&snapshot).unwrap();
        let decoded: NetworkConfigurationSnapshot = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(snapshot, decoded);
    }

    #[test]
    fn invalid_json_reports_raw_null_location_without_network_values() {
        let input = br#"{"private/~field":["do-not-log-this-value",null]}"#;
        let error =
            decode_json::<std::collections::BTreeMap<String, Vec<String>>>(input).unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        let message = error.to_string();
        assert!(message.contains("expected a string"));
        assert!(message.contains("/private~1~0field/1"));
        assert!(!message.contains("do-not-log-this-value"));
    }

    #[test]
    fn address_snapshot_preserves_raw_nullable_instance_id_without_defaults() {
        let raw = json!({
            "instance_id":null,"address_family":23,"address":"fe80::1%71",
            "prefix_len":64,"skip_as_source":false,
            "prefix_origin":"WellKnown","suffix_origin":"Link"
        });
        let absent_id: IpAddressConfiguration = serde_json::from_value(raw.clone()).unwrap();
        assert_eq!(absent_id.instance_id, None);
        assert_eq!(serde_json::to_value(&absent_id).unwrap(), raw);

        let mut identified = raw.clone();
        identified["instance_id"] = json!("provider supplied identity");
        let present: IpAddressConfiguration = serde_json::from_value(identified.clone()).unwrap();
        assert_eq!(
            present.instance_id.as_deref(),
            Some("provider supplied identity")
        );
        assert_eq!(serde_json::to_value(&present).unwrap(), identified);
        assert_ne!(
            absent_id, present,
            "a changed provider value must remain visible"
        );

        let mut missing = raw.clone();
        missing.as_object_mut().unwrap().remove("instance_id");
        assert!(serde_json::from_value::<IpAddressConfiguration>(missing).is_err());
        for invalid in [json!(0), json!(false), json!([]), json!({})] {
            let mut malformed = raw.clone();
            malformed["instance_id"] = invalid;
            assert!(serde_json::from_value::<IpAddressConfiguration>(malformed).is_err());
        }
    }

    #[test]
    fn configuration_normalization_preserves_raw_mtu_dns_priority_scope_and_duplicates() {
        let adapter = AdapterConfiguration {
            identity: InterfaceIdentity::new(71, 1),
            name: "test adapter".into(),
            hardware: false,
            interfaces: vec![IpInterfaceConfiguration {
                compartment_id: 1,
                address_family: 23,
                nl_mtu_bytes: u32::MAX,
                dhcp: "Disabled".into(),
                automatic_metric: "Enabled".into(),
                interface_metric: 75,
            }],
            addresses: vec![],
            dns: vec![DnsConfiguration {
                address_family: 23,
                servers: vec!["fe80::2%71".into(), "fe80::1%71".into()],
            }],
        };
        let route = NetworkRouteConfiguration {
            instance_id: "test-route".into(),
            interface_index: 71,
            address_family: 23,
            destination: "::/0".into(),
            next_hop: "fe80::1%71".into(),
            route_metric: 256,
            protocol: "NetMgmt".into(),
            publish: "No".into(),
        };
        let mut another = adapter.clone();
        another.identity = InterfaceIdentity::new(72, 2);
        let mut snapshot = NetworkConfigurationSnapshot {
            adapters: vec![another.clone(), adapter.clone()],
            routes: vec![route.clone(), route.clone()],
        };
        snapshot.normalize();
        assert_eq!(snapshot.adapters, vec![adapter.clone(), another]);
        assert_eq!(snapshot.adapters[0].interfaces[0].nl_mtu_bytes, u32::MAX);
        assert_eq!(snapshot.adapters[0].dns[0].servers, adapter.dns[0].servers);
        assert_eq!(snapshot.routes, vec![route.clone(), route]);
        let mut reversed_dns = snapshot.clone();
        reversed_dns.adapters[0].dns[0].servers.reverse();
        reversed_dns.normalize();
        assert_ne!(
            snapshot, reversed_dns,
            "DNS priority changes must remain visible"
        );
    }

    #[test]
    fn physical_egress_rejects_existing_vpn_capture() {
        let identity = InterfaceIdentity::new(7, 1);
        let mut snapshot = NetworkSnapshot {
            adapters: vec![NetworkAdapter {
                identity: identity.clone(),
                name: "test".into(),
                up: true,
                hardware: true,
            }],
            routes: vec![SystemRoute {
                interface_index: 7,
                destination: "0.0.0.0/0".parse().unwrap(),
                next_hop: "192.0.2.1".parse().unwrap(),
                metric: 10,
            }],
        };
        assert_eq!(snapshot.physical_egress(false).unwrap(), identity);
        snapshot.routes.push(SystemRoute {
            interface_index: 12,
            destination: "0.0.0.0/1".parse().unwrap(),
            next_hop: "0.0.0.0".parse().unwrap(),
            metric: 1,
        });
        assert_eq!(
            snapshot.physical_egress(false).unwrap_err().kind(),
            io::ErrorKind::AlreadyExists
        );
    }

    #[test]
    fn physical_egress_ignores_disconnected_hardware_default_routes() {
        let connected = InterfaceIdentity::new(7, 1);
        let disconnected = InterfaceIdentity::new(8, 2);
        let mut snapshot = NetworkSnapshot {
            adapters: vec![
                NetworkAdapter {
                    identity: connected.clone(),
                    name: "Ethernet".into(),
                    up: true,
                    hardware: true,
                },
                NetworkAdapter {
                    identity: disconnected,
                    name: "Wi-Fi".into(),
                    up: false,
                    hardware: true,
                },
            ],
            routes: vec![
                SystemRoute {
                    interface_index: 7,
                    destination: "0.0.0.0/0".parse().unwrap(),
                    next_hop: "192.0.2.1".parse().unwrap(),
                    metric: 50,
                },
                SystemRoute {
                    interface_index: 8,
                    destination: "0.0.0.0/0".parse().unwrap(),
                    next_hop: "192.0.2.2".parse().unwrap(),
                    metric: 1,
                },
            ],
        };
        assert_eq!(snapshot.physical_egress(false).unwrap(), connected);
        snapshot.adapters[0].up = false;
        assert_eq!(
            snapshot.physical_egress(false).unwrap_err().kind(),
            io::ErrorKind::NotFound
        );
    }

    #[test]
    fn socket_interface_options_roundtrip_on_windows_loopback() {
        const LOOPBACK: &str = r#"
$ErrorActionPreference='Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$p = [Console]::In.ReadToEnd() | ConvertFrom-Json
$rows = @(Get-NetIPAddress -IPAddress ([string]$p.address) -ErrorAction Stop)
if ($rows.Count -ne 1) { throw 'Expected one loopback interface' }
ConvertTo-Json -InputObject ([uint32]$rows[0].InterfaceIndex)
"#;
        for (address, ipv6) in [("127.0.0.1", false), ("::1", true)] {
            let index: u32 = run_json(LOOPBACK, &json!({"address":address})).unwrap();
            let socket =
                std::net::UdpSocket::bind(std::net::SocketAddr::new(address.parse().unwrap(), 0))
                    .unwrap();
            crate::pin_outbound_socket(&socket, ipv6, index).unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(2)))
                .unwrap();
            socket
                .send_to(b"interface-bound-loopback", socket.local_addr().unwrap())
                .unwrap();
            let mut buffer = [0u8; 64];
            let received = socket.recv(&mut buffer).unwrap();
            assert_eq!(&buffer[..received], b"interface-bound-loopback");
        }
    }
}
