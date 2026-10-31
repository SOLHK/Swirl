//! The private WFP FFI boundary. Persistent, administrator-owned filters survive
//! helper death while LAN Forwarding may still be enabled. No callout driver,
//! second tunnel, packet injection, hard permit, or global firewall reset.
#![allow(unsafe_code)]
use crate::gateway_policy::GatewayIsolationPolicy;
use ipnet::Ipv4Net;
use sha2::{Digest, Sha256};
use std::{ffi::c_void, io, net::IpAddr, ptr::{null, null_mut}};
use windows_sys::{core::GUID, Win32::{
    Foundation::{FWP_E_FILTER_NOT_FOUND, FWP_E_SUBLAYER_NOT_FOUND, HANDLE, LocalFree},
    NetworkManagement::WindowsFilteringPlatform::*,
    Security::Authorization::{ConvertStringSecurityDescriptorToSecurityDescriptorW, SDDL_REVISION_1},
    System::Rpc::RPC_C_AUTHN_WINNT,
}};

const SUBLAYER_WEIGHT: u16 = 0x7000;
// FWPS run-time profile identifiers are Public=1, Private=2, Domain=3.
// NLM_NETWORK_CATEGORY uses a different numbering (0/1/2). In particular,
// copying NLM's Private=1 here would allow packets after a Public transition.
// See Microsoft FWPS_FIELDS_IPFORWARD_V4 and FWPS_FIELDS_INBOUND_TRANSPORT_V4.
const PRIVATE_PROFILE_ID: u32 = 2;

fn api(code: u32, operation: &str) -> io::Result<()> {
    if code == 0 { Ok(()) } else {
        Err(io::Error::other(format!("{operation} failed with Windows WFP code 0x{code:08x}")))
    }
}
fn ownership() -> io::Error { io::Error::other("gateway WFP object changed; isolation retained for explicit recovery") }
fn same_guid(a: &GUID, b: &GUID) -> bool {
    a.data1 == b.data1 && a.data2 == b.data2 && a.data3 == b.data3 && a.data4 == b.data4
}
fn key(policy: &GatewayIsolationPolicy, tag: &str) -> GUID {
    let mut hash = Sha256::new();
    hash.update(b"Swirl.NativeGateway.WFP.v1\0");
    hash.update(policy.owner.as_bytes()); hash.update(policy.lan.guid.as_bytes()); hash.update(tag.as_bytes());
    let digest = hash.finalize();
    let mut bytes = [0; 16]; bytes.copy_from_slice(&digest[..16]);
    GUID::from_u128(u128::from_be_bytes(bytes))
}
fn fingerprint(policy: &GatewayIsolationPolicy) -> io::Result<Vec<u8>> {
    Ok(Sha256::digest(serde_json::to_vec(policy).map_err(io::Error::other)?).to_vec())
}

struct Engine(HANDLE);
impl Engine {
    fn open() -> io::Result<Self> {
        let mut handle = null_mut();
        let session = FWPM_SESSION0 { txnWaitTimeoutInMSec: 5000, ..Default::default() };
        // SAFETY: local engine, default credentials, no retained borrowed data.
        // Deliberately not FWPM_SESSION_FLAG_DYNAMIC: crash must not open WAN.
        api(unsafe { FwpmEngineOpen0(null(), RPC_C_AUTHN_WINNT, null(), &session, &mut handle) }, "FwpmEngineOpen0")?;
        Ok(Self(handle))
    }
    fn transaction<T>(&self, read_only: bool, operation: impl FnOnce() -> io::Result<T>) -> io::Result<T> {
        // SAFETY: this module exclusively owns the live engine handle.
        api(unsafe { FwpmTransactionBegin0(self.0, if read_only { FWPM_TXN_READ_ONLY } else { 0 }) }, "FwpmTransactionBegin0")?;
        let result = operation();
        match result {
            Ok(value) => {
                let committed = api(unsafe { FwpmTransactionCommit0(self.0) }, "FwpmTransactionCommit0");
                if committed.is_err() { unsafe { FwpmTransactionAbort0(self.0) }; }
                committed.map(|()| value)
            }
            Err(error) => { unsafe { FwpmTransactionAbort0(self.0) }; Err(error) }
        }
    }
}
impl Drop for Engine {
    fn drop(&mut self) { unsafe { FwpmEngineClose0(self.0) }; }
}

struct Descriptor(*mut c_void);
impl Descriptor {
    fn administrators() -> io::Result<Self> {
        let sddl = "O:BAG:BAD:P(A;;GA;;;SY)(A;;GA;;;BA)\0".encode_utf16().collect::<Vec<_>>();
        let mut descriptor = null_mut();
        // SAFETY: NUL-terminated input; returned LocalAlloc allocation is owned.
        if unsafe { ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.as_ptr(), SDDL_REVISION_1, &mut descriptor, null_mut()) } == 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(Self(descriptor))
    }
}
impl Drop for Descriptor {
    fn drop(&mut self) { unsafe { LocalFree(self.0) }; }
}
struct WfpAllocation<T>(*mut T);
impl<T> Drop for WfpAllocation<T> {
    fn drop(&mut self) {
        let mut pointer = self.0.cast::<c_void>();
        // SAFETY: allocation came from the matching WFP GetByKey API.
        unsafe { FwpmFreeMemory0(&mut pointer) };
    }
}

#[derive(Clone, Copy)]
enum ConditionValue { U8(u8), U16(u16), U32(u32), U64(u64), V4(Ipv4Net) }
#[derive(Clone)]
struct Condition { field: GUID, value: ConditionValue }
struct Rule { tag: String, layer: GUID, weight: u8, permit: bool, conditions: Vec<Condition> }

fn rules(policy: &GatewayIsolationPolicy) -> Vec<Rule> {
    let source = vec![
        Condition { field: FWPM_CONDITION_IP_PHYSICAL_ARRIVAL_INTERFACE, value: ConditionValue::U64(policy.lan_luid) },
    ];
    let host = vec![
        Condition { field: FWPM_CONDITION_INTERFACE_INDEX, value: ConditionValue::U32(policy.lan.index) },
        Condition { field: FWPM_CONDITION_IP_LOCAL_INTERFACE, value: ConditionValue::U64(policy.lan_luid) },
    ];
    let mut rules = Vec::new();
    let mut deny_sources = policy.host_addresses.iter().filter_map(|ip| match ip { IpAddr::V4(ip) => Some(*ip), _ => None }).collect::<Vec<_>>();
    deny_sources.extend([policy.subnet.network(), policy.subnet.broadcast()]);
    deny_sources.sort(); deny_sources.dedup();
    for (index, address) in deny_sources.into_iter().enumerate() {
        let mut conditions = source.clone();
        conditions.push(Condition { field: FWPM_CONDITION_IP_SOURCE_ADDRESS, value: ConditionValue::V4(Ipv4Net::new(address, 32).expect("IPv4 host prefix")) });
        rules.push(Rule { tag: format!("spoof-{index}"), layer: FWPM_LAYER_IPFORWARD_V4, weight: 14, permit: false, conditions });
        rules.push(Rule { tag: format!("return-spoof-{index}"), layer: FWPM_LAYER_IPFORWARD_V4, weight: 14, permit: false, conditions: vec![
            Condition { field: FWPM_CONDITION_IP_FORWARD_INTERFACE, value: ConditionValue::U64(policy.lan_luid) },
            Condition { field: FWPM_CONDITION_IP_DESTINATION_ADDRESS, value: ConditionValue::V4(Ipv4Net::new(address, 32).expect("IPv4 host prefix")) },
        ] });
    }
    for (index, subnet) in policy.allowed_sources.iter().enumerate() {
        let mut conditions = source.clone();
        conditions.push(Condition { field: FWPM_CONDITION_SOURCE_INTERFACE_INDEX, value: ConditionValue::U32(policy.lan.index) });
        conditions.push(Condition { field: FWPM_CONDITION_ARRIVAL_INTERFACE_PROFILE_ID, value: ConditionValue::U32(PRIVATE_PROFILE_ID) });
        conditions.push(Condition { field: FWPM_CONDITION_IP_SOURCE_ADDRESS, value: ConditionValue::V4(*subnet) });
        conditions.push(Condition { field: FWPM_CONDITION_IP_FORWARD_INTERFACE, value: ConditionValue::U64(policy.tun_luid) });
        rules.push(Rule { tag: format!("admit-{index}"), layer: FWPM_LAYER_IPFORWARD_V4, weight: 10, permit: true, conditions });
        rules.push(Rule { tag: format!("return-{index}"), layer: FWPM_LAYER_IPFORWARD_V4, weight: 10, permit: true, conditions: vec![
            Condition { field: FWPM_CONDITION_IP_PHYSICAL_ARRIVAL_INTERFACE, value: ConditionValue::U64(policy.tun_luid) },
            Condition { field: FWPM_CONDITION_SOURCE_INTERFACE_INDEX, value: ConditionValue::U32(policy.tun.index) },
            Condition { field: FWPM_CONDITION_IP_FORWARD_INTERFACE, value: ConditionValue::U64(policy.lan_luid) },
            Condition { field: FWPM_CONDITION_NEXTHOP_INTERFACE_PROFILE_ID, value: ConditionValue::U32(PRIVATE_PROFILE_ID) },
            Condition { field: FWPM_CONDITION_IP_DESTINATION_ADDRESS, value: ConditionValue::V4(*subnet) },
        ] });
    }
    for (tag, layer) in [("forward-v4", FWPM_LAYER_IPFORWARD_V4), ("forward-v6", FWPM_LAYER_IPFORWARD_V6)] {
        rules.push(Rule { tag: tag.into(), layer, weight: 1, permit: false, conditions: source.clone() });
        // No other physical interface may spoof a host/client source and enter
        // this gateway TUN. Local host output does not traverse IPFORWARD.
        rules.push(Rule { tag: format!("{tag}-to-tun"), layer, weight: 1, permit: false, conditions: vec![
            Condition { field: FWPM_CONDITION_IP_FORWARD_INTERFACE, value: ConditionValue::U64(policy.tun_luid) },
        ] });
        // Return traffic cannot be injected directly from another physical
        // interface; IPv6 has no return permit in this IPv4-only release.
        rules.push(Rule { tag: format!("{tag}-to-lan"), layer, weight: 1, permit: false, conditions: vec![
            Condition { field: FWPM_CONDITION_IP_FORWARD_INTERFACE, value: ConditionValue::U64(policy.lan_luid) },
        ] });
    }
    // IP_LOCAL_INTERFACE identifies the destination address's interface. It
    // alone is insufficient under Windows weak-host receive. ALE admission
    // checks the original arrival LUID as well. During outbound-response
    // reauthorization arrival metadata may be empty, so cover next-hop too.
    let scopes = [
        ("host-transport", FWPM_LAYER_INBOUND_TRANSPORT_V4, FWPM_LAYER_INBOUND_TRANSPORT_V6, host),
        ("host-arrival", FWPM_LAYER_ALE_AUTH_RECV_ACCEPT_V4, FWPM_LAYER_ALE_AUTH_RECV_ACCEPT_V6, vec![
            Condition { field: FWPM_CONDITION_IP_ARRIVAL_INTERFACE, value: ConditionValue::U64(policy.lan_luid) },
        ]),
        ("host-reauthorize", FWPM_LAYER_ALE_AUTH_RECV_ACCEPT_V4, FWPM_LAYER_ALE_AUTH_RECV_ACCEPT_V6, vec![
            Condition { field: FWPM_CONDITION_IP_NEXTHOP_INTERFACE, value: ConditionValue::U64(policy.lan_luid) },
        ]),
    ];
    for (tag, v4, v6, conditions) in scopes {
        if policy.dhcp {
            let mut permit = conditions.clone();
            permit.extend([
                Condition { field: FWPM_CONDITION_IP_PROTOCOL, value: ConditionValue::U8(17) },
                Condition { field: FWPM_CONDITION_IP_LOCAL_PORT, value: ConditionValue::U16(67) },
                Condition { field: FWPM_CONDITION_IP_REMOTE_PORT, value: ConditionValue::U16(68) },
                Condition { field: FWPM_CONDITION_CURRENT_PROFILE_ID, value: ConditionValue::U32(PRIVATE_PROFILE_ID) },
            ]);
            rules.push(Rule { tag: format!("{tag}-dhcp"), layer: v4, weight: 10, permit: true, conditions: permit });
        }
        for (suffix, layer) in [("v4", v4), ("v6", v6)] {
            rules.push(Rule { tag: format!("{tag}-{suffix}"), layer, weight: 1, permit: false, conditions: conditions.clone() });
        }
    }
    rules
}

// Boxes keep pointer-valued WFP conditions stable while vectors grow. All
// buffers live through the synchronous Add/Get comparison; WFP copies Add data.
enum Storage { U64 { _value: Box<u64> }, V4 { _value: Box<FWP_V4_ADDR_AND_MASK> } }
struct NativeRule {
    _storage: Vec<Storage>, _name: Vec<u16>, _fingerprint: Vec<u8>,
    _conditions: Vec<FWPM_FILTER_CONDITION0>, raw: FWPM_FILTER0,
}
impl NativeRule {
    fn new(policy: &GatewayIsolationPolicy, rule: &Rule) -> io::Result<Self> {
        let mut storage = Vec::new();
        let mut conditions = Vec::new();
        for condition in &rule.conditions {
            let value = match condition.value {
                ConditionValue::U8(value) => FWP_CONDITION_VALUE0 { r#type: FWP_UINT8, Anonymous: FWP_CONDITION_VALUE0_0 { uint8: value } },
                ConditionValue::U16(value) => FWP_CONDITION_VALUE0 { r#type: FWP_UINT16, Anonymous: FWP_CONDITION_VALUE0_0 { uint16: value } },
                ConditionValue::U32(value) => FWP_CONDITION_VALUE0 { r#type: FWP_UINT32, Anonymous: FWP_CONDITION_VALUE0_0 { uint32: value } },
                ConditionValue::U64(value) => {
                    let mut value = Box::new(value);
                    let raw = FWP_CONDITION_VALUE0 { r#type: FWP_UINT64, Anonymous: FWP_CONDITION_VALUE0_0 { uint64: &mut *value } };
                    storage.push(Storage::U64 { _value: value }); raw
                }
                ConditionValue::V4(net) => {
                    let mut value = Box::new(FWP_V4_ADDR_AND_MASK { addr: u32::from(net.network()), mask: u32::from(net.netmask()) });
                    let raw = FWP_CONDITION_VALUE0 { r#type: FWP_V4_ADDR_MASK, Anonymous: FWP_CONDITION_VALUE0_0 { v4AddrMask: &mut *value } };
                    storage.push(Storage::V4 { _value: value }); raw
                }
            };
            conditions.push(FWPM_FILTER_CONDITION0 { fieldKey: condition.field, matchType: FWP_MATCH_EQUAL, conditionValue: value });
        }
        let mut name = format!("{}.{}\0", policy.name(), rule.tag).encode_utf16().collect::<Vec<_>>();
        let mut fingerprint = fingerprint(policy)?;
        let raw = FWPM_FILTER0 {
            filterKey: key(policy, &rule.tag),
            displayData: FWPM_DISPLAY_DATA0 { name: name.as_mut_ptr(), description: null_mut() },
            // Ordinary permits do not override another provider's firewall block.
            flags: FWPM_FILTER_FLAG_PERSISTENT,
            providerData: FWP_BYTE_BLOB { size: fingerprint.len() as u32, data: fingerprint.as_mut_ptr() },
            layerKey: rule.layer, subLayerKey: key(policy, "sublayer"),
            weight: FWP_VALUE0 { r#type: FWP_UINT8, Anonymous: FWP_VALUE0_0 { uint8: rule.weight } },
            numFilterConditions: conditions.len() as u32, filterCondition: conditions.as_mut_ptr(),
            action: FWPM_ACTION0 { r#type: if rule.permit { FWP_ACTION_PERMIT } else { FWP_ACTION_BLOCK }, ..Default::default() },
            ..Default::default()
        };
        Ok(Self { _storage: storage, _name: name, _fingerprint: fingerprint, _conditions: conditions, raw })
    }
}

fn same_blob(a: &FWP_BYTE_BLOB, b: &FWP_BYTE_BLOB) -> bool {
    if a.size != b.size || a.size != 32 || a.data.is_null() || b.data.is_null() { return false; }
    // SAFETY: WFP-provided data has the declared length; our digest is 32 bytes.
    unsafe { std::slice::from_raw_parts(a.data, 32) == std::slice::from_raw_parts(b.data, 32) }
}
fn same_condition(a: &FWPM_FILTER_CONDITION0, b: &FWPM_FILTER_CONDITION0) -> bool {
    if !same_guid(&a.fieldKey, &b.fieldKey) || a.matchType != b.matchType || a.conditionValue.r#type != b.conditionValue.r#type { return false; }
    // SAFETY: the discriminants were compared above; pointer arms are checked.
    unsafe {
        let left = a.conditionValue.Anonymous; let right = b.conditionValue.Anonymous;
        match a.conditionValue.r#type {
            FWP_UINT8 => left.uint8 == right.uint8,
            FWP_UINT16 => left.uint16 == right.uint16,
            FWP_UINT32 => left.uint32 == right.uint32,
            FWP_UINT64 => !left.uint64.is_null() && !right.uint64.is_null() && *left.uint64 == *right.uint64,
            FWP_V4_ADDR_MASK => !left.v4AddrMask.is_null() && !right.v4AddrMask.is_null()
                && (*left.v4AddrMask).addr == (*right.v4AddrMask).addr && (*left.v4AddrMask).mask == (*right.v4AddrMask).mask,
            _ => false,
        }
    }
}
fn same_filter(actual: &FWPM_FILTER0, expected: &FWPM_FILTER0) -> bool {
    if !same_guid(&actual.filterKey, &expected.filterKey) || !same_guid(&actual.layerKey, &expected.layerKey)
        || !same_guid(&actual.subLayerKey, &expected.subLayerKey) || actual.flags != expected.flags
        || !actual.providerKey.is_null() || !same_blob(&actual.providerData, &expected.providerData)
        || actual.action.r#type != expected.action.r#type || actual.weight.r#type != FWP_UINT8
        || actual.numFilterConditions != expected.numFilterConditions || actual.filterCondition.is_null() {
        return false;
    }
    // SAFETY: discriminants/counts checked; both arrays have their declared size.
    unsafe {
        if actual.weight.Anonymous.uint8 != expected.weight.Anonymous.uint8 { return false; }
        let actual = std::slice::from_raw_parts(actual.filterCondition, actual.numFilterConditions as usize);
        let expected = std::slice::from_raw_parts(expected.filterCondition, expected.numFilterConditions as usize);
        // WFP may reorder conditions; field keys are unique in each rule.
        expected.iter().all(|condition| actual.iter().any(|value| same_condition(value, condition)))
    }
}

fn inspect(engine: &Engine, policy: &GatewayIsolationPolicy) -> io::Result<bool> {
    let mut layer = null_mut();
    let code = unsafe { FwpmSubLayerGetByKey0(engine.0, &key(policy, "sublayer"), &mut layer) };
    if code == FWP_E_SUBLAYER_NOT_FOUND as u32 { return Ok(false); }
    api(code, "FwpmSubLayerGetByKey0")?;
    let layer = WfpAllocation(layer);
    if layer.0.is_null() { return Err(ownership()); }
    let mut digest = fingerprint(policy)?;
    let expected_blob = FWP_BYTE_BLOB { size: digest.len() as u32, data: digest.as_mut_ptr() };
    let raw = unsafe { &*layer.0 };
    if raw.flags != FWPM_SUBLAYER_FLAG_PERSISTENT || raw.weight != SUBLAYER_WEIGHT
        || !raw.providerKey.is_null() || !same_blob(&raw.providerData, &expected_blob) { return Err(ownership()); }
    for rule in rules(policy) {
        let expected = NativeRule::new(policy, &rule)?;
        let mut actual = null_mut();
        let code = unsafe { FwpmFilterGetByKey0(engine.0, &expected.raw.filterKey, &mut actual) };
        if code == FWP_E_FILTER_NOT_FOUND as u32 { return Err(ownership()); }
        api(code, "FwpmFilterGetByKey0")?;
        let actual = WfpAllocation(actual);
        if actual.0.is_null() || !same_filter(unsafe { &*actual.0 }, &expected.raw) { return Err(ownership()); }
    }
    Ok(true)
}

pub(crate) fn present(policy: &GatewayIsolationPolicy) -> io::Result<bool> {
    policy.validate()?;
    let engine = Engine::open()?;
    engine.transaction(true, || inspect(&engine, policy))
}

pub(crate) fn install(policy: &GatewayIsolationPolicy) -> io::Result<()> {
    policy.validate()?;
    let engine = Engine::open()?;
    let descriptor = Descriptor::administrators()?;
    engine.transaction(false, || {
        if inspect(&engine, policy)? { return Err(io::Error::new(io::ErrorKind::AlreadyExists, "gateway isolation already exists")); }
        let mut name = format!("{}\0", policy.name()).encode_utf16().collect::<Vec<_>>();
        let mut digest = fingerprint(policy)?;
        let layer = FWPM_SUBLAYER0 {
            subLayerKey: key(policy, "sublayer"),
            displayData: FWPM_DISPLAY_DATA0 { name: name.as_mut_ptr(), description: null_mut() },
            flags: FWPM_SUBLAYER_FLAG_PERSISTENT,
            providerData: FWP_BYTE_BLOB { size: digest.len() as u32, data: digest.as_mut_ptr() },
            weight: SUBLAYER_WEIGHT, ..Default::default()
        };
        api(unsafe { FwpmSubLayerAdd0(engine.0, &layer, descriptor.0) }, "FwpmSubLayerAdd0")?;
        for rule in rules(policy) {
            let native = NativeRule::new(policy, &rule)?;
            api(unsafe { FwpmFilterAdd0(engine.0, &native.raw, descriptor.0, null_mut()) }, "FwpmFilterAdd0")?;
        }
        if !inspect(&engine, policy)? { return Err(io::Error::other("gateway isolation installation readback failed")); }
        Ok(())
    })
}

pub(crate) fn remove(policy: &GatewayIsolationPolicy) -> io::Result<()> {
    policy.validate()?;
    let engine = Engine::open()?;
    engine.transaction(false, || {
        if !inspect(&engine, policy)? { return Ok(()); }
        for rule in rules(policy) {
            api(unsafe { FwpmFilterDeleteByKey0(engine.0, &key(policy, &rule.tag)) }, "FwpmFilterDeleteByKey0")?;
        }
        api(unsafe { FwpmSubLayerDeleteByKey0(engine.0, &key(policy, "sublayer")) }, "FwpmSubLayerDeleteByKey0")
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn compiled_forward(policy: &GatewayIsolationPolicy, source: IpAddr, destination: IpAddr, arrival: u64, outgoing: u64, private: bool) -> bool {
        let layer = if source.is_ipv4() { FWPM_LAYER_IPFORWARD_V4 } else { FWPM_LAYER_IPFORWARD_V6 };
        let index = if arrival == policy.lan_luid { policy.lan.index }
            else if arrival == policy.tun_luid { policy.tun.index } else { 999 };
        let mut matching = rules(policy).into_iter().filter(|rule| same_guid(&rule.layer, &layer)
            && rule.conditions.iter().all(|condition| match condition.value {
                ConditionValue::U64(value) if same_guid(&condition.field, &FWPM_CONDITION_IP_PHYSICAL_ARRIVAL_INTERFACE) => value == arrival,
                ConditionValue::U64(value) if same_guid(&condition.field, &FWPM_CONDITION_IP_FORWARD_INTERFACE) => value == outgoing,
                ConditionValue::U32(value) if same_guid(&condition.field, &FWPM_CONDITION_SOURCE_INTERFACE_INDEX) => value == index,
                ConditionValue::U32(value) if same_guid(&condition.field, &FWPM_CONDITION_ARRIVAL_INTERFACE_PROFILE_ID)
                    || same_guid(&condition.field, &FWPM_CONDITION_NEXTHOP_INTERFACE_PROFILE_ID) => value == if private { 2 } else { 1 },
                ConditionValue::V4(net) if same_guid(&condition.field, &FWPM_CONDITION_IP_SOURCE_ADDRESS) => matches!(source, IpAddr::V4(address) if net.contains(&address)),
                ConditionValue::V4(net) if same_guid(&condition.field, &FWPM_CONDITION_IP_DESTINATION_ADDRESS) => matches!(destination, IpAddr::V4(address) if net.contains(&address)),
                _ => panic!("unmodeled forwarding condition"),
            })).collect::<Vec<_>>();
        matching.sort_by_key(|rule| std::cmp::Reverse(rule.weight));
        matching.first().is_none_or(|rule| rule.permit)
    }

    #[test]
    fn compiled_forwarding_matches_independent_client_return_and_ipv6_policy() {
        let policy = crate::gateway_policy::fixture();
        for (source, destination) in [
            ("192.168.77.10", "203.0.113.5"), ("192.168.77.1", "203.0.113.5"),
            ("192.168.77.0", "203.0.113.5"), ("192.168.77.255", "203.0.113.5"),
            ("192.168.77.200", "203.0.113.5"), ("203.0.113.5", "192.168.77.10"),
            ("203.0.113.5", "192.168.77.1"), ("203.0.113.5", "192.168.77.0"),
            ("203.0.113.5", "192.168.77.255"), ("203.0.113.5", "192.168.77.200"),
            ("fd00::1", "fd00::2"),
        ] {
            let source = source.parse().unwrap();
            let destination = destination.parse().unwrap();
            for arrival in [110, 120, 130] {
                for outgoing in [110, 120, 140] {
                    for private in [true, false] {
                        assert_eq!(compiled_forward(&policy, source, destination, arrival, outgoing, private),
                            policy.permits_forward(source, destination, arrival, outgoing, private),
                            "{source} -> {destination}, arrival {arrival}, outgoing {outgoing}, private {private}");
                    }
                }
            }
        }
    }

    #[test]
    fn compiler_has_no_public_egress_or_hard_permit() {
        let mut policy = crate::gateway_policy::fixture(); policy.dhcp = true;
        for rule in rules(&policy) {
            let native = NativeRule::new(&policy, &rule).unwrap();
            assert_eq!(native.raw.flags, FWPM_FILTER_FLAG_PERSISTENT);
            assert!(same_filter(&native.raw, &native.raw));
            if rule.permit && same_guid(&rule.layer, &FWPM_LAYER_IPFORWARD_V4) {
                assert!(rule.conditions.iter().any(|condition| same_guid(&condition.field, &FWPM_CONDITION_IP_FORWARD_INTERFACE)));
                assert!(rule.conditions.iter().any(|condition| (same_guid(&condition.field, &FWPM_CONDITION_ARRIVAL_INTERFACE_PROFILE_ID) || same_guid(&condition.field, &FWPM_CONDITION_NEXTHOP_INTERFACE_PROFILE_ID))
                    && matches!(condition.value, ConditionValue::U32(PRIVATE_PROFILE_ID))));
            }
        }
        let rules = rules(&policy);
        assert!(rules.iter().any(|rule| !rule.permit && rule.conditions.iter().any(|condition| same_guid(&condition.field, &FWPM_CONDITION_IP_ARRIVAL_INTERFACE))));
        assert!(rules.iter().any(|rule| !rule.permit && rule.conditions.iter().any(|condition| same_guid(&condition.field, &FWPM_CONDITION_IP_NEXTHOP_INTERFACE))));
    }

    #[test]
    #[ignore = "requires elevation; explicitly run on a disposable Windows validation runner"]
    fn persistent_wfp_fixture_installs_verifies_ownership_and_removes_exact_objects() {
        // Neither index nor LUID can match any installed adapter. This tests
        // actual BFE API acceptance and readback without affecting host traffic.
        let mut policy = crate::gateway_policy::fixture();
        policy.lan.index = 0xffff_fffe;
        policy.tun.index = 0xffff_fffd;
        policy.lan_luid = 0x0006_ffff_fe00_0000;
        policy.tun_luid = 0x0006_ffff_fd00_0000;
        policy.owner = format!("{:032x}", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos());
        policy.dhcp = true;
        let adapters = crate::windows_network::snapshot().unwrap().adapters;
        assert!(adapters.iter().all(|adapter| adapter.identity.index != policy.lan.index && adapter.identity.index != policy.tun.index));
        assert!(!present(&policy).unwrap());
        install(&policy).unwrap();
        struct Cleanup(GatewayIsolationPolicy);
        impl Drop for Cleanup { fn drop(&mut self) { let _ = remove(&self.0); } }
        let cleanup = Cleanup(policy.clone());
        // Each call opens a fresh non-dynamic engine session. Closing the
        // installing session must retain persistent guards.
        assert!(present(&policy).unwrap());
        let mut changed = policy.clone();
        changed.allowed_sources = vec!["192.168.77.0/26".parse().unwrap()];
        assert!(present(&changed).is_err());
        assert!(remove(&changed).is_err());
        assert!(present(&policy).unwrap());
        remove(&policy).unwrap();
        assert!(!present(&policy).unwrap());
        drop(cleanup);
    }
}
