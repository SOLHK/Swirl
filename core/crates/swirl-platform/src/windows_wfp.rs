//! Scoped WFP transaction foundation, deliberately not a system kill switch.
//!
//! Policies are confined to one executable and explicit loopback TCP/UDP
//! endpoints. Nothing is installed on import/open/drop. Persistent objects
//! survive engine-handle closure; removal is explicit and ownership-checked.
//! No service/boot policy or existing-flow coverage is supplied here. BFE and
//! system restart behavior have not been accepted. ALE reauthorization runs on subsequent traffic,
//! not synchronously at commit. This module must not enable a product capability.
#![allow(unsafe_code)] // The private, documented Windows FFI boundary.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    io,
    net::{IpAddr, SocketAddr},
    os::windows::ffi::OsStrExt,
    path::{Component, PathBuf, Prefix},
    ptr::{null, null_mut},
};
use windows_sys::{
    Win32::{
        Foundation::{
            FWP_E_FILTER_NOT_FOUND, FWP_E_PROVIDER_NOT_FOUND, FWP_E_SUBLAYER_NOT_FOUND, HANDLE,
            LocalFree,
        },
        NetworkManagement::WindowsFilteringPlatform::*,
        Security::{
            ACCESS_ALLOWED_ACE,
            Authorization::{
                ConvertStringSecurityDescriptorToSecurityDescriptorW, SDDL_REVISION_1,
            },
            DACL_SECURITY_INFORMATION, GetAce, GetLengthSid, GetSecurityDescriptorControl,
            GetSecurityDescriptorDacl, GetSecurityDescriptorOwner, OWNER_SECURITY_INFORMATION,
            SE_DACL_PROTECTED,
        },
    },
    core::GUID,
};

const PROVIDER: GUID = GUID::from_u128(0x391ebfc1_341d_4c97_a64d_d5cd33e1bca1);
const SUBLAYER: GUID = GUID::from_u128(0x6d683252_9b58_43cf_b6f9_e6fd6e71d932);
const NAME: &str = "Swirl Native TUN scoped WFP foundation v1";
const SUBLAYER_WEIGHT: u16 = 0x100;
// Explicit WFP/standard rights avoid inheriting the mutable engine/container
// DACL. BA ownership and OWNER RIGHTS remove an unelevated creator's implicit
// WRITE_DAC; no creator-user ACE is installed. No SACL privilege is required.
const SDDL: &str = "O:BAG:BAD:P(A;;0x000f07ff;;;SY)(A;;0x000f07ff;;;BA)(A;;RC;;;OW)";

struct SecurityDescriptor(*mut std::ffi::c_void);

impl SecurityDescriptor {
    fn new() -> io::Result<Self> {
        let text = SDDL.encode_utf16().chain(Some(0)).collect::<Vec<_>>();
        let mut descriptor = null_mut();
        // SAFETY: constant terminated SDDL and valid allocation output. The
        // returned LocalAlloc buffer is exclusively owned by this wrapper.
        if unsafe {
            ConvertStringSecurityDescriptorToSecurityDescriptorW(
                text.as_ptr(),
                SDDL_REVISION_1,
                &mut descriptor,
                null_mut(),
            )
        } == 0
        {
            return Err(context(
                "ConvertStringSecurityDescriptorToSecurityDescriptorW",
                io::Error::last_os_error(),
            ));
        }
        Ok(Self(descriptor))
    }
}

impl Drop for SecurityDescriptor {
    fn drop(&mut self) {
        // SAFETY: sole LocalAlloc allocation returned by the conversion API.
        unsafe { LocalFree(self.0) };
    }
}

#[derive(Debug, PartialEq, Eq)]
struct SecurityShape {
    owner: Vec<u8>,
    protected: bool,
    grants: Vec<(u32, Vec<u8>)>,
}

fn security_shape(descriptor: *mut std::ffi::c_void) -> io::Result<SecurityShape> {
    let mut owner = null_mut();
    let mut defaulted = 0;
    let mut control = 0;
    let mut revision = 0;
    let mut present = 0;
    let mut dacl = null_mut();
    // SAFETY: private callers lend either LocalAlloc or BFE-owned valid
    // descriptors. Windows returns borrowed SID/ACL pointers into that owner.
    unsafe {
        if GetSecurityDescriptorOwner(descriptor, &mut owner, &mut defaulted) == 0 {
            return Err(context(
                "GetSecurityDescriptorOwner",
                io::Error::last_os_error(),
            ));
        }
        if GetSecurityDescriptorControl(descriptor, &mut control, &mut revision) == 0 {
            return Err(context(
                "GetSecurityDescriptorControl",
                io::Error::last_os_error(),
            ));
        }
        if GetSecurityDescriptorDacl(descriptor, &mut present, &mut dacl, &mut defaulted) == 0 {
            return Err(context(
                "GetSecurityDescriptorDacl",
                io::Error::last_os_error(),
            ));
        }
        if owner.is_null() || present == 0 || dacl.is_null() || (*dacl).AceCount != 3 {
            let owner_label = if owner.is_null() {
                "null".into()
            } else {
                sid_label(std::slice::from_raw_parts(
                    owner.cast::<u8>(),
                    GetLengthSid(owner) as usize,
                ))
            };
            return Err(conflict_detail(format!(
                "security_shape owner={owner_label} owner_null={} dacl_present={present} dacl_null={} ace_count={:?} protected={}",
                owner.is_null(),
                dacl.is_null(),
                dacl.as_ref().map(|acl| acl.AceCount),
                control & SE_DACL_PROTECTED != 0
            )));
        }
        let owner =
            std::slice::from_raw_parts(owner.cast::<u8>(), GetLengthSid(owner) as usize).to_vec();
        let mut grants = Vec::new();
        for index in 0..u32::from((*dacl).AceCount) {
            let mut ace = null_mut();
            if GetAce(dacl, index, &mut ace) == 0 {
                return Err(context(
                    &format!("GetAce index={index}"),
                    io::Error::last_os_error(),
                ));
            }
            let ace = &*ace.cast::<ACCESS_ALLOWED_ACE>();
            if ace.Header.AceType != 0 || ace.Header.AceFlags != 0 {
                return Err(conflict_detail(format!(
                    "security_shape ACE index={index} type={} flags=0x{:02x}; expected allow type=0 flags=0",
                    ace.Header.AceType, ace.Header.AceFlags
                )));
            }
            let sid = (&ace.SidStart as *const u32).cast_mut().cast();
            let length = GetLengthSid(sid) as usize;
            if length + std::mem::offset_of!(ACCESS_ALLOWED_ACE, SidStart)
                > usize::from(ace.Header.AceSize)
            {
                return Err(conflict_detail(format!(
                    "security_shape ACE index={index} sid_length={length} ace_size={} does not contain SID",
                    ace.Header.AceSize
                )));
            }
            grants.push((
                ace.Mask,
                std::slice::from_raw_parts(sid.cast::<u8>(), length).to_vec(),
            ));
        }
        grants.sort();
        Ok(SecurityShape {
            owner,
            protected: control & SE_DACL_PROTECTED != 0,
            grants,
        })
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Protocol {
    Tcp,
    Udp,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Action {
    Block,
    /// Overridable permit in our sublayer, never CLEAR_ACTION_RIGHT.
    SoftPermit,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScopedRule {
    pub endpoint: SocketAddr,
    pub protocol: Protocol,
    pub action: Action,
}

/// Persist this exact receipt before installation if crash recovery is needed.
/// The owner is an identity, not authentication; Windows ACLs authorize writes.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScopedPolicy {
    pub schema: u32,
    pub owner: [u8; 16],
    pub application: PathBuf,
    pub rules: Vec<ScopedRule>,
}

impl ScopedPolicy {
    pub fn validate(&self) -> io::Result<()> {
        if self.schema != 1
            || self.owner == [0; 16]
            || !self.application.is_absolute()
            || !matches!(self.application.components().next(), Some(Component::Prefix(prefix))
                if matches!(prefix.kind(), Prefix::Disk(_) | Prefix::VerbatimDisk(_)))
            || self.application.as_os_str().encode_wide().any(|unit| unit == 0)
            || !(1..=16).contains(&self.rules.len())
            || self.rules.iter().any(|rule| {
                !rule.endpoint.ip().is_loopback()
                    || rule.endpoint.port() == 0
                    || matches!(rule.endpoint, SocketAddr::V6(v6) if v6.scope_id() != 0 || v6.flowinfo() != 0)
            })
        {
            return Err(io::Error::new(io::ErrorKind::InvalidInput, "invalid scoped WFP policy"));
        }
        Ok(())
    }

    fn metadata(&self) -> io::Result<Vec<u8>> {
        self.validate()?;
        let bytes = serde_json::to_vec(self).map_err(io::Error::other)?;
        if bytes.len() > 16 * 1024 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "WFP receipt too large",
            ));
        }
        Ok(bytes)
    }

    fn key(&self, index: usize) -> GUID {
        let mut hash = Sha256::new();
        hash.update(b"Swirl scoped WFP filter v1");
        hash.update(self.owner);
        hash.update((index as u64).to_be_bytes());
        let digest = hash.finalize();
        let mut bytes = [0; 16];
        bytes.copy_from_slice(&digest[..16]);
        GUID::from_u128(u128::from_be_bytes(bytes))
    }
}

fn same_guid(a: &GUID, b: &GUID) -> bool {
    (a.data1, a.data2, a.data3, a.data4) == (b.data1, b.data2, b.data3, b.data4)
}

fn status(code: u32) -> io::Result<()> {
    if code == 0 {
        Ok(())
    } else {
        Err(io::Error::from_raw_os_error(code as i32))
    }
}

fn conflict() -> io::Error {
    io::Error::new(
        io::ErrorKind::PermissionDenied,
        "scoped WFP ownership or policy differs",
    )
}

fn context(operation: &str, error: io::Error) -> io::Error {
    let code = error
        .raw_os_error()
        .map(|code| format!("0x{:08x}", code as u32));
    io::Error::new(
        error.kind(),
        format!("{operation}: sdk_code={code:?}; {error}"),
    )
}

fn conflict_detail(detail: impl std::fmt::Display) -> io::Error {
    let error = conflict();
    io::Error::new(error.kind(), format!("{error}: {detail}"))
}

fn sid_label(bytes: &[u8]) -> String {
    match bytes {
        [1, 2, 0, 0, 0, 0, 0, 5, 32, 0, 0, 0, 32, 2, 0, 0] => "BUILTIN_ADMINISTRATORS".into(),
        [1, 1, 0, 0, 0, 0, 0, 5, 18, 0, 0, 0] => "LOCAL_SYSTEM".into(),
        [1, 1, 0, 0, 0, 0, 0, 3, 4, 0, 0, 0] => "OWNER_RIGHTS".into(),
        _ => format!("sha256:{:x}", Sha256::digest(bytes)),
    }
}

fn security_summary(shape: &SecurityShape) -> serde_json::Value {
    serde_json::json!({"owner":sid_label(&shape.owner),"protected":shape.protected,
        "grants":shape.grants.iter().map(|(mask,sid)|serde_json::json!({"mask":format!("0x{mask:08x}"),"sid":sid_label(sid)})).collect::<Vec<_>>()})
}

struct Allocation<T>(*mut T);

impl<T> Allocation<T> {
    fn get(&self) -> io::Result<&T> {
        // SAFETY: only successful BFE allocation APIs populate this pointer;
        // the allocation lives until this owner drops. Null is an error.
        unsafe { self.0.as_ref() }.ok_or_else(|| io::Error::other("WFP returned null allocation"))
    }
}

impl<T> Drop for Allocation<T> {
    fn drop(&mut self) {
        // SAFETY: null or the sole allocation returned by a Fwpm* API. BFE
        // releases nested allocations too; this wrapper never copies ownership.
        unsafe { FwpmFreeMemory0((&mut self.0 as *mut *mut T).cast()) };
    }
}

fn allocated<T>(
    operation: &str,
    call: impl FnOnce(*mut *mut T) -> u32,
) -> io::Result<Allocation<T>> {
    let mut value = Allocation(null_mut());
    status(call(&mut value.0)).map_err(|error| context(operation, error))?;
    value.get().map_err(|error| context(operation, error))?;
    Ok(value)
}

fn blob(bytes: &mut [u8]) -> FWP_BYTE_BLOB {
    FWP_BYTE_BLOB {
        size: bytes.len() as u32,
        data: bytes.as_mut_ptr(),
    }
}

fn blob_matches(value: &FWP_BYTE_BLOB, bytes: &[u8]) -> bool {
    if value.size as usize != bytes.len() || value.data.is_null() {
        return false;
    }
    // SAFETY: this blob belongs to a live BFE allocation, with validated length.
    unsafe { std::slice::from_raw_parts(value.data, bytes.len()) == bytes }
}

fn app_id(policy: &ScopedPolicy) -> io::Result<Allocation<FWP_BYTE_BLOB>> {
    let wide = policy
        .application
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect::<Vec<_>>();
    // SAFETY: terminated path and writable output; BFE owns the returned blob.
    allocated("FwpmGetAppIdFromFileName0", |out| unsafe {
        FwpmGetAppIdFromFileName0(wide.as_ptr(), out)
    })
}

/// A non-dynamic engine session. Closing it never implicitly unlocks a policy.
pub struct Engine(HANDLE);

impl Engine {
    pub fn open() -> io::Result<Self> {
        let session = FWPM_SESSION0 {
            txnWaitTimeoutInMSec: 5_000,
            ..Default::default()
        };
        let mut handle = null_mut();
        // SAFETY: local authenticated RPC, no supplied credentials, valid
        // input/output pointers. The session is copied by BFE during this call.
        status(unsafe { FwpmEngineOpen0(null(), u32::MAX, null(), &session, &mut handle) })
            .map_err(|error| context("FwpmEngineOpen0", error))?;
        Ok(Self(handle))
    }

    pub fn begin(&mut self) -> io::Result<Transaction<'_>> {
        self.transaction(0)
    }

    pub fn close(mut self) -> io::Result<()> {
        // SAFETY: uniquely owned live handle with no borrowed transaction.
        status(unsafe { FwpmEngineClose0(self.0) })
            .map_err(|error| context("FwpmEngineClose0", error))?;
        self.0 = null_mut();
        Ok(())
    }

    fn transaction(&mut self, flags: u32) -> io::Result<Transaction<'_>> {
        // SAFETY: live engine, exclusive borrow prevents nested transactions.
        status(unsafe { FwpmTransactionBegin0(self.0, flags) })
            .map_err(|error| context("FwpmTransactionBegin0", error))?;
        Ok(Transaction {
            engine: self,
            active: true,
            failed: false,
        })
    }

    pub fn verify(&mut self, policy: &ScopedPolicy) -> io::Result<()> {
        let mut transaction = self.transaction(FWPM_TXN_READ_ONLY)?;
        transaction.verify(policy)?;
        transaction.commit()
    }

    /// Check every owned key; a partially removed policy is a conflict.
    pub fn absent(&mut self, policy: &ScopedPolicy) -> io::Result<bool> {
        policy.validate()?;
        let transaction = self.transaction(FWPM_TXN_READ_ONLY)?;
        let result = transaction.absent(policy);
        drop(transaction);
        result
    }
}

impl Drop for Engine {
    fn drop(&mut self) {
        // SAFETY: this type uniquely owns a live engine handle; closing also
        // aborts any uncommitted transaction. Persistent policies are retained.
        if !self.0.is_null() {
            // SAFETY: the handle is still uniquely owned; explicit close has
            // not already succeeded and cleared it.
            unsafe { FwpmEngineClose0(self.0) };
        }
    }
}

pub struct Transaction<'a> {
    engine: &'a mut Engine,
    active: bool,
    failed: bool,
}

impl Transaction<'_> {
    /// Adds only absent keys. Any failure poisons the transaction: even a
    /// caller that mistakenly tries to commit cannot publish a partial policy.
    pub fn install(&mut self, policy: &ScopedPolicy) -> io::Result<()> {
        let result = self.install_inner(policy);
        self.failed |= result.is_err();
        result
    }

    fn install_inner(&mut self, policy: &ScopedPolicy) -> io::Result<()> {
        let mut metadata = policy.metadata()?;
        let app = app_id(policy)?;
        let security = SecurityDescriptor::new()?;
        let mut name = NAME.encode_utf16().chain(Some(0)).collect::<Vec<_>>();
        let mut provider_key = PROVIDER;
        let provider = FWPM_PROVIDER0 {
            providerKey: PROVIDER,
            displayData: FWPM_DISPLAY_DATA0 {
                name: name.as_mut_ptr(),
                description: null_mut(),
            },
            flags: FWPM_PROVIDER_FLAG_PERSISTENT,
            providerData: blob(&mut metadata),
            ..Default::default()
        };
        let sublayer = FWPM_SUBLAYER0 {
            subLayerKey: SUBLAYER,
            displayData: provider.displayData,
            flags: FWPM_SUBLAYER_FLAG_PERSISTENT,
            providerKey: &mut provider_key,
            providerData: blob(&mut metadata),
            weight: SUBLAYER_WEIGHT,
        };
        // SAFETY: all nested buffers/pointers are live through these copying
        // BFE calls. Existing objects are rejected, never adopted or overwritten.
        status(unsafe { FwpmProviderAdd0(self.engine.0, &provider, security.0) })
            .map_err(|error| context("FwpmProviderAdd0", error))?;
        // SAFETY: same ownership and buffer lifetime as the provider above.
        status(unsafe { FwpmSubLayerAdd0(self.engine.0, &sublayer, security.0) })
            .map_err(|error| context("FwpmSubLayerAdd0", error))?;
        for (index, rule) in policy.rules.iter().enumerate() {
            with_filter(policy, index, rule, app.get()?, &mut metadata, |filter| {
                // SAFETY: with_filter keeps every nested buffer alive while
                // BFE copies the filter; no user pointer is retained by BFE.
                status(unsafe { FwpmFilterAdd0(self.engine.0, filter, security.0, null_mut()) })
                    .map_err(|error| context(&format!("FwpmFilterAdd0 index={index}"), error))
            })?;
        }
        self.verify_inner(policy)
    }

    pub fn verify(&mut self, policy: &ScopedPolicy) -> io::Result<()> {
        let result = self.verify_inner(policy);
        self.failed |= result.is_err();
        result
    }

    fn verify_inner(&self, policy: &ScopedPolicy) -> io::Result<()> {
        let mut metadata = policy.metadata()?;
        let app = app_id(policy)?;
        let security = SecurityDescriptor::new()?;
        let security = security_shape(security.0)?;
        self.verify_security(&PROVIDER, Object::Provider, &security)?;
        self.verify_security(&SUBLAYER, Object::Sublayer, &security)?;
        // SAFETY: live engine/key/output; returned structures stay owned below.
        let provider = allocated("FwpmProviderGetByKey0", |out| unsafe {
            FwpmProviderGetByKey0(self.engine.0, &PROVIDER, out)
        })?;
        // SAFETY: as above, distinct BFE allocation owned by this wrapper.
        let sublayer = allocated("FwpmSubLayerGetByKey0", |out| unsafe {
            FwpmSubLayerGetByKey0(self.engine.0, &SUBLAYER, out)
        })?;
        let provider = provider.get()?;
        let sublayer = sublayer.get()?;
        // SAFETY: optional providerKey is part of the live BFE allocation.
        let linked_provider = unsafe { sublayer.providerKey.as_ref() };
        if provider.flags != FWPM_PROVIDER_FLAG_PERSISTENT
            || !provider.serviceName.is_null()
            || !blob_matches(&provider.providerData, &metadata)
            || sublayer.flags != FWPM_SUBLAYER_FLAG_PERSISTENT
            || sublayer.weight != SUBLAYER_WEIGHT
            || !linked_provider.is_some_and(|key| same_guid(key, &PROVIDER))
            || !blob_matches(&sublayer.providerData, &metadata)
        {
            return Err(conflict_detail(
                serde_json::json!({"phase":"verify provider/sublayer",
                "provider_flags":{"actual":provider.flags,"expected":FWPM_PROVIDER_FLAG_PERSISTENT},
                "provider_service_name_is_null":provider.serviceName.is_null(),
                "provider_metadata_equal":blob_matches(&provider.providerData,&metadata),
                "sublayer_flags":{"actual":sublayer.flags,"expected":FWPM_SUBLAYER_FLAG_PERSISTENT},
                "sublayer_weight":{"actual":sublayer.weight,"expected":SUBLAYER_WEIGHT},
                "sublayer_provider_equal":linked_provider.is_some_and(|key|same_guid(key,&PROVIDER)),
                "sublayer_metadata_equal":blob_matches(&sublayer.providerData,&metadata)}),
            ));
        }
        for (index, rule) in policy.rules.iter().enumerate() {
            let key = policy.key(index);
            self.verify_security(&key, Object::Filter(index), &security)?;
            // SAFETY: live engine/key/output; returned filter is uniquely owned.
            let actual = allocated(
                &format!("FwpmFilterGetByKey0 index={index}"),
                |out| unsafe { FwpmFilterGetByKey0(self.engine.0, &key, out) },
            )?;
            with_filter(policy, index, rule, app.get()?, &mut metadata, |expected| {
                if filter_matches(actual.get()?, expected) {
                    Ok(())
                } else {
                    Err(conflict_detail(format!(
                        "verify filter index={index}: {}",
                        filter_summary(actual.get()?, expected)
                    )))
                }
            })?;
        }
        Ok(())
    }

    fn verify_security(
        &self,
        key: &GUID,
        object: Object,
        expected: &SecurityShape,
    ) -> io::Result<()> {
        let mut descriptor = Allocation::<u8>(null_mut());
        // SAFETY: live engine/key/output; BFE returns a descriptor containing
        // owner/DACL. Optional separate outputs are omitted; the descriptor
        // owns every nested pointer until after the comparison below.
        let code = unsafe {
            let information = OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION;
            let out = (&mut descriptor.0 as *mut *mut u8).cast();
            match object {
                Object::Provider => FwpmProviderGetSecurityInfoByKey0(
                    self.engine.0,
                    key,
                    information,
                    null_mut(),
                    null_mut(),
                    null_mut(),
                    null_mut(),
                    out,
                ),
                Object::Sublayer => FwpmSubLayerGetSecurityInfoByKey0(
                    self.engine.0,
                    key,
                    information,
                    null_mut(),
                    null_mut(),
                    null_mut(),
                    null_mut(),
                    out,
                ),
                Object::Filter(_) => FwpmFilterGetSecurityInfoByKey0(
                    self.engine.0,
                    key,
                    information,
                    null_mut(),
                    null_mut(),
                    null_mut(),
                    null_mut(),
                    out,
                ),
            }
        };
        status(code).map_err(|error| context(object.operation(), error))?;
        if descriptor.0.is_null() {
            return Err(conflict_detail(format!(
                "verify_security {} returned null descriptor",
                object.label()
            )));
        }
        let actual = security_shape(descriptor.0.cast())
            .map_err(|error| context(&format!("verify_security {}", object.label()), error))?;
        if actual != *expected {
            return Err(conflict_detail(format!(
                "verify_security {} actual={} expected={}",
                object.label(),
                security_summary(&actual),
                security_summary(expected)
            )));
        }
        Ok(())
    }

    fn absent(&self, policy: &ScopedPolicy) -> io::Result<bool> {
        // SAFETY: outputs owned locally even when an API reports absence.
        let mut provider = Allocation(null_mut());
        let provider_status =
            unsafe { FwpmProviderGetByKey0(self.engine.0, &PROVIDER, &mut provider.0) };
        if provider_status == 0 {
            return Ok(false);
        }
        if provider_status != FWP_E_PROVIDER_NOT_FOUND as u32 {
            status(provider_status)
                .map_err(|error| context("FwpmProviderGetByKey0 absent", error))?;
        }
        let mut sublayer = Allocation(null_mut());
        // SAFETY: live engine and valid output for owned BFE allocation.
        let sublayer_status =
            unsafe { FwpmSubLayerGetByKey0(self.engine.0, &SUBLAYER, &mut sublayer.0) };
        if sublayer_status != FWP_E_SUBLAYER_NOT_FOUND as u32 {
            return Err(conflict_detail(format!(
                "absent sublayer expected_not_found=true sdk_code=0x{sublayer_status:08x}"
            )));
        }
        for index in 0..policy.rules.len() {
            let mut filter = Allocation(null_mut());
            // SAFETY: live engine/key/output, allocation freed before iteration.
            let code =
                unsafe { FwpmFilterGetByKey0(self.engine.0, &policy.key(index), &mut filter.0) };
            if code != FWP_E_FILTER_NOT_FOUND as u32 {
                return Err(conflict_detail(format!(
                    "absent filter index={index} expected_not_found=true sdk_code=0x{code:08x}"
                )));
            }
        }
        Ok(true)
    }

    /// Compare every owned value before deleting anything. Extra foreign
    /// children cause BFE deletion to fail and the entire transaction to abort.
    pub fn remove(&mut self, policy: &ScopedPolicy) -> io::Result<()> {
        let result = (|| {
            policy.validate()?;
            if self.absent(policy)? {
                return Ok(());
            }
            self.verify_inner(policy)?;
            for index in 0..policy.rules.len() {
                // SAFETY: exact filter key was verified in this transaction.
                status(unsafe { FwpmFilterDeleteByKey0(self.engine.0, &policy.key(index)) })
                    .map_err(|error| {
                        context(&format!("FwpmFilterDeleteByKey0 index={index}"), error)
                    })?;
            }
            // SAFETY: owned child filters are deleted; BFE refuses unlisted
            // children rather than allowing removal of another owner's objects.
            status(unsafe { FwpmSubLayerDeleteByKey0(self.engine.0, &SUBLAYER) })
                .map_err(|error| context("FwpmSubLayerDeleteByKey0", error))?;
            // SAFETY: exact owned provider was verified; foreign links block deletion.
            status(unsafe { FwpmProviderDeleteByKey0(self.engine.0, &PROVIDER) })
                .map_err(|error| context("FwpmProviderDeleteByKey0", error))?;
            if !self.absent(policy)? {
                return Err(conflict_detail(
                    "remove completed but owned keys are not all absent",
                ));
            }
            Ok(())
        })();
        self.failed |= result.is_err();
        result
    }

    pub fn commit(mut self) -> io::Result<()> {
        if self.failed {
            return Err(io::Error::other("failed WFP transaction cannot commit"));
        }
        // SAFETY: this uniquely borrowed engine has a live explicit transaction.
        status(unsafe { FwpmTransactionCommit0(self.engine.0) })
            .map_err(|error| context("FwpmTransactionCommit0", error))?;
        self.active = false;
        Ok(())
    }
}

impl Drop for Transaction<'_> {
    fn drop(&mut self) {
        if self.active {
            // SAFETY: this scope owns the only active transaction on the handle.
            // Closing Engine is an additional abort backstop if RPC abort fails.
            unsafe { FwpmTransactionAbort0(self.engine.0) };
        }
    }
}

#[derive(Clone, Copy)]
enum Object {
    Provider,
    Sublayer,
    Filter(usize),
}

impl Object {
    fn label(self) -> String {
        match self {
            Self::Provider => "provider".into(),
            Self::Sublayer => "sublayer".into(),
            Self::Filter(index) => format!("filter[index={index}]"),
        }
    }
    fn operation(self) -> &'static str {
        match self {
            Self::Provider => "FwpmProviderGetSecurityInfoByKey0",
            Self::Sublayer => "FwpmSubLayerGetSecurityInfoByKey0",
            Self::Filter(_) => "FwpmFilterGetSecurityInfoByKey0",
        }
    }
}

fn with_filter<T>(
    policy: &ScopedPolicy,
    index: usize,
    rule: &ScopedRule,
    app: &FWP_BYTE_BLOB,
    metadata: &mut [u8],
    use_filter: impl FnOnce(&FWPM_FILTER0) -> io::Result<T>,
) -> io::Result<T> {
    let mut app = *app;
    let mut address = FWP_BYTE_ARRAY16::default();
    let remote = match rule.endpoint.ip() {
        IpAddr::V4(ip) => FWP_CONDITION_VALUE0 {
            r#type: FWP_UINT32,
            Anonymous: FWP_CONDITION_VALUE0_0 {
                uint32: u32::from(ip),
            },
        },
        IpAddr::V6(ip) => {
            address.byteArray16 = ip.octets();
            FWP_CONDITION_VALUE0 {
                r#type: FWP_BYTE_ARRAY16_TYPE,
                Anonymous: FWP_CONDITION_VALUE0_0 {
                    byteArray16: &mut address,
                },
            }
        }
    };
    let mut conditions = [
        FWPM_FILTER_CONDITION0 {
            fieldKey: FWPM_CONDITION_ALE_APP_ID,
            matchType: FWP_MATCH_EQUAL,
            conditionValue: FWP_CONDITION_VALUE0 {
                r#type: FWP_BYTE_BLOB_TYPE,
                Anonymous: FWP_CONDITION_VALUE0_0 { byteBlob: &mut app },
            },
        },
        FWPM_FILTER_CONDITION0 {
            fieldKey: FWPM_CONDITION_IP_REMOTE_ADDRESS,
            matchType: FWP_MATCH_EQUAL,
            conditionValue: remote,
        },
        FWPM_FILTER_CONDITION0 {
            fieldKey: FWPM_CONDITION_IP_REMOTE_PORT,
            matchType: FWP_MATCH_EQUAL,
            conditionValue: FWP_CONDITION_VALUE0 {
                r#type: FWP_UINT16,
                Anonymous: FWP_CONDITION_VALUE0_0 {
                    uint16: rule.endpoint.port(),
                },
            },
        },
        FWPM_FILTER_CONDITION0 {
            fieldKey: FWPM_CONDITION_IP_PROTOCOL,
            matchType: FWP_MATCH_EQUAL,
            conditionValue: FWP_CONDITION_VALUE0 {
                r#type: FWP_UINT8,
                Anonymous: FWP_CONDITION_VALUE0_0 {
                    uint8: match rule.protocol {
                        Protocol::Tcp => 6,
                        Protocol::Udp => 17,
                    },
                },
            },
        },
    ];
    let mut name = NAME.encode_utf16().chain(Some(0)).collect::<Vec<_>>();
    let mut provider = PROVIDER;
    let mut weight = match rule.action {
        Action::Block => 100u64,
        Action::SoftPermit => 200u64,
    };
    let filter = FWPM_FILTER0 {
        filterKey: policy.key(index),
        displayData: FWPM_DISPLAY_DATA0 {
            name: name.as_mut_ptr(),
            description: null_mut(),
        },
        // Do not set CLEAR_ACTION_RIGHT: permits remain overridable by other
        // sublayers/providers. This scoped API cannot issue a hard permit.
        flags: FWPM_FILTER_FLAG_PERSISTENT,
        providerKey: &mut provider,
        providerData: blob(metadata),
        layerKey: if rule.endpoint.is_ipv6() {
            FWPM_LAYER_ALE_AUTH_CONNECT_V6
        } else {
            FWPM_LAYER_ALE_AUTH_CONNECT_V4
        },
        subLayerKey: SUBLAYER,
        weight: FWP_VALUE0 {
            r#type: FWP_UINT64,
            Anonymous: FWP_VALUE0_0 {
                uint64: &mut weight,
            },
        },
        numFilterConditions: conditions.len() as u32,
        filterCondition: conditions.as_mut_ptr(),
        action: FWPM_ACTION0 {
            r#type: match rule.action {
                Action::Block => FWP_ACTION_BLOCK,
                Action::SoftPermit => FWP_ACTION_PERMIT,
            },
            ..Default::default()
        },
        ..Default::default()
    };
    use_filter(&filter)
}

fn filter_matches(actual: &FWPM_FILTER0, expected: &FWPM_FILTER0) -> bool {
    // SAFETY: both structures come from live BFE allocations or with_filter's
    // stack frame. Check discriminants, nulls and lengths before union/pointer use.
    unsafe {
        if actual.flags != expected.flags
            || !same_guid(&actual.filterKey, &expected.filterKey)
            || !same_guid(&actual.layerKey, &expected.layerKey)
            || !same_guid(&actual.subLayerKey, &SUBLAYER)
            || !actual
                .providerKey
                .as_ref()
                .is_some_and(|key| same_guid(key, &PROVIDER))
            || !blob_matches(
                &actual.providerData,
                std::slice::from_raw_parts(
                    expected.providerData.data,
                    expected.providerData.size as usize,
                ),
            )
            || actual.action.r#type != expected.action.r#type
            || actual.weight.r#type != FWP_UINT64
            || actual.weight.Anonymous.uint64.is_null()
            || *actual.weight.Anonymous.uint64 != *expected.weight.Anonymous.uint64
            || actual.numFilterConditions != 4
            || actual.filterCondition.is_null()
        {
            return false;
        }
        let actual_conditions = std::slice::from_raw_parts(actual.filterCondition, 4);
        let expected_conditions = std::slice::from_raw_parts(expected.filterCondition, 4);
        expected_conditions.iter().all(|condition| {
            actual_conditions
                .iter()
                .filter(|other| {
                    same_guid(&other.fieldKey, &condition.fieldKey)
                        && other.matchType == condition.matchType
                        && condition_value_matches(&other.conditionValue, &condition.conditionValue)
                })
                .count()
                == 1
        })
    }
}

/// Failure-only diagnostics. Keep the acceptance predicate above unchanged;
/// never print raw application IDs, paths, receipt blobs or endpoint values.
fn filter_summary(actual: &FWPM_FILTER0, expected: &FWPM_FILTER0) -> serde_json::Value {
    // SAFETY: the same BFE/local structures used by filter_matches are live.
    // Check every discriminant, count and nullable pointer before access.
    unsafe {
        let weight = if actual.weight.r#type == FWP_UINT64 {
            actual.weight.Anonymous.uint64.as_ref().copied()
        } else {
            None
        };
        let mut conditions = Vec::new();
        if actual.numFilterConditions == 4 && !actual.filterCondition.is_null() {
            let actual_conditions = std::slice::from_raw_parts(actual.filterCondition, 4);
            for (index, condition) in std::slice::from_raw_parts(expected.filterCondition, 4)
                .iter()
                .enumerate()
            {
                let name = if same_guid(&condition.fieldKey, &FWPM_CONDITION_ALE_APP_ID) {
                    "ALE_APP_ID"
                } else if same_guid(&condition.fieldKey, &FWPM_CONDITION_IP_REMOTE_ADDRESS) {
                    "IP_REMOTE_ADDRESS"
                } else if same_guid(&condition.fieldKey, &FWPM_CONDITION_IP_REMOTE_PORT) {
                    "IP_REMOTE_PORT"
                } else if same_guid(&condition.fieldKey, &FWPM_CONDITION_IP_PROTOCOL) {
                    "IP_PROTOCOL"
                } else {
                    "unknown"
                };
                let candidates = actual_conditions
                    .iter()
                    .filter(|other| same_guid(&other.fieldKey, &condition.fieldKey))
                    .collect::<Vec<_>>();
                conditions.push(serde_json::json!({"index":index,"name":name,"field_occurrences":candidates.len(),
                    "expected_type":condition.conditionValue.r#type,"expected_match":condition.matchType,
                    "actual_types":candidates.iter().map(|other|other.conditionValue.r#type).collect::<Vec<_>>(),
                    "actual_matches":candidates.iter().map(|other|other.matchType).collect::<Vec<_>>(),
                    "matching_conditions":candidates.iter().filter(|other|other.matchType==condition.matchType && condition_value_matches(&other.conditionValue,&condition.conditionValue)).count()}));
            }
        }
        serde_json::json!({"filter_key_equal":same_guid(&actual.filterKey,&expected.filterKey),
            "flags":{"actual":actual.flags,"expected":expected.flags},
            "layer_key_equal":same_guid(&actual.layerKey,&expected.layerKey),
            "sublayer_key_equal":same_guid(&actual.subLayerKey,&SUBLAYER),
            "provider_key_equal":actual.providerKey.as_ref().is_some_and(|key|same_guid(key,&PROVIDER)),
            "metadata_equal":blob_matches(&actual.providerData,std::slice::from_raw_parts(expected.providerData.data,expected.providerData.size as usize)),
            "metadata_size":{"actual":actual.providerData.size,"expected":expected.providerData.size},
            "action":{"actual":actual.action.r#type,"expected":expected.action.r#type},
            "weight":{"actual_type":actual.weight.r#type,"expected_type":FWP_UINT64,"actual_value":weight,"expected_value":*expected.weight.Anonymous.uint64},
            "condition_count":{"actual":actual.numFilterConditions,"expected":4},"condition_pointer_null":actual.filterCondition.is_null(),"conditions":conditions})
    }
}

fn condition_value_matches(actual: &FWP_CONDITION_VALUE0, expected: &FWP_CONDITION_VALUE0) -> bool {
    if actual.r#type != expected.r#type {
        return false;
    }
    // SAFETY: private caller lends live BFE/local values, matched type controls
    // union member access; nested pointers are checked before dereferencing.
    unsafe {
        match actual.r#type {
            FWP_UINT8 => actual.Anonymous.uint8 == expected.Anonymous.uint8,
            FWP_UINT16 => actual.Anonymous.uint16 == expected.Anonymous.uint16,
            FWP_UINT32 => actual.Anonymous.uint32 == expected.Anonymous.uint32,
            FWP_BYTE_ARRAY16_TYPE => actual.Anonymous.byteArray16.as_ref().is_some_and(|array| {
                array.byteArray16 == (*expected.Anonymous.byteArray16).byteArray16
            }),
            FWP_BYTE_BLOB_TYPE => actual
                .Anonymous
                .byteBlob
                .as_ref()
                .is_some_and(|actual_blob| {
                    let expected_blob = &*expected.Anonymous.byteBlob;
                    !expected_blob.data.is_null()
                        && blob_matches(
                            actual_blob,
                            std::slice::from_raw_parts(
                                expected_blob.data,
                                expected_blob.size as usize,
                            ),
                        )
                }),
            _ => false,
        }
    }
}

#[cfg(test)]
#[path = "windows_wfp_tests.rs"]
mod tests;
