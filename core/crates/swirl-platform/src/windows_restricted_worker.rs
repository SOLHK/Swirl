//! Restricted headless process foundation, not the product broker integration.
//!
//! Only three anonymous stdio pipe ends are inherited by `spawn`. The explicit
//! data-plane variant adds two packet-pipe ends and one approved journal file.
//! The child gets an
//! explicitly restricted low-integrity token, a private low-label desktop and
//! an owning kill-on-close job with UI restrictions. No elevation, account,
//! service, filesystem permission or host-network change happens on import.
//! This is not an AppContainer or a complete sandbox: the worker retains the
//! ordinary user's readable files/network access. Core packet IPC and signed
//! GUI/broker authentication remain separate integration work.
#![allow(unsafe_code)] // This module is the Windows token/process FFI boundary.

use serde::Serialize;
use std::{
    ffi::{OsStr, OsString, c_void},
    fs::File,
    io,
    mem::{offset_of, size_of},
    os::windows::{
        ffi::{OsStrExt, OsStringExt},
        io::{AsRawHandle, FromRawHandle, OwnedHandle},
    },
    path::{Component, Path, Prefix},
    ptr::{null, null_mut},
    time::Duration,
};
use windows_sys::{
    Win32::{
        Foundation::{
            DUPLICATE_SAME_ACCESS, DuplicateHandle, ERROR_BAD_LENGTH, ERROR_INSUFFICIENT_BUFFER,
            GENERIC_ALL, HANDLE, LocalFree, WAIT_OBJECT_0, WAIT_TIMEOUT,
        },
        Security::{
            Authorization::{
                ConvertSidToStringSidW, ConvertStringSecurityDescriptorToSecurityDescriptorW,
                SDDL_REVISION_1,
            },
            *,
        },
        Storage::FileSystem::{
            FILE_READ_ATTRIBUTES, FILE_READ_DATA, FILE_TYPE_DISK, FILE_WRITE_DATA, GetFileType,
            SYNCHRONIZE,
        },
        System::{
            JobObjects::*,
            Pipes::CreatePipe,
            Rpc::UuidCreate,
            StationsAndDesktops::*,
            SystemInformation::GetWindowsDirectoryW,
            SystemServices::{
                MAXIMUM_ALLOWED, SE_GROUP_ENABLED, SE_GROUP_INTEGRITY, SE_GROUP_LOGON_ID,
                SE_GROUP_USE_FOR_DENY_ONLY,
            },
            Threading::*,
        },
    },
    core::GUID,
};

fn success(value: i32) -> io::Result<()> {
    if value == 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(())
    }
}
fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, message)
}
fn denied(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, message)
}

fn owned(raw: HANDLE) -> io::Result<OwnedHandle> {
    if raw.is_null() {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: every caller transfers one newly created kernel handle.
    Ok(unsafe { OwnedHandle::from_raw_handle(raw) })
}

struct TokenBuffer {
    words: Vec<usize>,
    bytes: usize,
}
impl TokenBuffer {
    fn query(token: HANDLE, class: TOKEN_INFORMATION_CLASS) -> io::Result<Self> {
        let mut required = 0;
        // SAFETY: size query to a live token. Fixed information classes can
        // require their exact record length and report BAD_LENGTH rather than
        // INSUFFICIENT_BUFFER. Neither result provides a usable partial token.
        let first = unsafe { GetTokenInformation(token, class, null_mut(), 0, &mut required) };
        let error = io::Error::last_os_error();
        if first != 0
            || !matches!(error.raw_os_error(),Some(code) if code==ERROR_INSUFFICIENT_BUFFER as i32||code==ERROR_BAD_LENGTH as i32)
            || required == 0
            || required > 1024 * 1024
        {
            return Err(io::Error::new(
                error.kind(),
                format!("GetTokenInformation size class={class} required={required}: {error}"),
            ));
        }
        let mut result = Self {
            words: vec![0; (required as usize).div_ceil(size_of::<usize>())],
            bytes: required as usize,
        };
        // SAFETY: aligned allocation is at least the exact reported length;
        // the API receives that exact length, not allocator padding bytes.
        success(unsafe {
            GetTokenInformation(
                token,
                class,
                result.words.as_mut_ptr().cast(),
                required,
                &mut required,
            )
        })?;
        if required == 0 || required as usize > result.bytes {
            return Err(invalid("token query exceeded allocation"));
        }
        result.bytes = required as usize;
        Ok(result)
    }
    fn value<T>(&self) -> io::Result<&T> {
        if size_of::<T>() > self.bytes || align_of::<T>() > align_of::<usize>() {
            return Err(invalid("truncated token record"));
        }
        // SAFETY: private callers select the structure corresponding to the
        // query class. Storage is aligned and size checked above.
        Ok(unsafe { &*self.words.as_ptr().cast::<T>() })
    }
    fn array<T>(&self, offset: usize, length: u32) -> io::Result<&[T]> {
        let bytes = (length as usize)
            .checked_mul(size_of::<T>())
            .and_then(|n| n.checked_add(offset));
        if bytes.is_none_or(|n| n > self.bytes) || !offset.is_multiple_of(align_of::<T>()) {
            return Err(invalid("truncated token array"));
        }
        // SAFETY: private callers use the queried variable-array element type;
        // its aligned range has been checked against the allocation's length.
        Ok(unsafe {
            std::slice::from_raw_parts(
                self.words.as_ptr().cast::<u8>().add(offset).cast::<T>(),
                length as usize,
            )
        })
    }
}

struct Sid(Vec<u32>);
impl Sid {
    fn well_known(kind: WELL_KNOWN_SID_TYPE) -> io::Result<Self> {
        let mut result = Self(vec![0; 17]);
        let mut bytes = (result.0.len() * size_of::<u32>()) as u32;
        // SAFETY: aligned SECURITY_MAX_SID_SIZE buffer and writable size.
        success(unsafe {
            CreateWellKnownSid(kind, null_mut(), result.0.as_mut_ptr().cast(), &mut bytes)
        })?;
        Ok(result)
    }
    fn raw(&self) -> PSID {
        self.0.as_ptr().cast_mut().cast()
    }
}

fn open_token(process: HANDLE, rights: u32) -> io::Result<OwnedHandle> {
    let mut token = null_mut();
    // SAFETY: live process/pseudo handle and writable new-token output.
    success(unsafe { OpenProcessToken(process, rights, &mut token) })?;
    owned(token)
}

#[derive(Debug, Serialize)]
pub struct TokenProfile {
    pub elevated: bool,
    pub restricted: bool,
    pub admin_enabled: bool,
    pub admin_deny_only: bool,
    pub integrity_rid: u32,
    pub enabled_privileges: usize,
    pub unexpected_enabled_privileges: usize,
}

fn profile(token: HANDLE) -> io::Result<TokenProfile> {
    let elevation = TokenBuffer::query(token, TokenElevation)?;
    let groups = TokenBuffer::query(token, TokenGroups)?;
    let group_count = *groups.value::<u32>()?;
    let groups =
        groups.array::<SID_AND_ATTRIBUTES>(offset_of!(TOKEN_GROUPS, Groups), group_count)?;
    let admins = Sid::well_known(WinBuiltinAdministratorsSid)?;
    let mut admin_enabled = false;
    let mut admin_deny_only = false;
    for group in groups {
        // SAFETY: token/Sid own valid SID buffers throughout this comparison.
        if unsafe { EqualSid(group.Sid, admins.raw()) } != 0 {
            admin_enabled |= group.Attributes & SE_GROUP_ENABLED as u32 != 0;
            admin_deny_only |= group.Attributes & SE_GROUP_USE_FOR_DENY_ONLY as u32 != 0;
        }
    }
    let integrity = TokenBuffer::query(token, TokenIntegrityLevel)?;
    let integrity = integrity.value::<TOKEN_MANDATORY_LABEL>()?.Label.Sid;
    // SAFETY: token returned a valid integrity SID; its last subauthority is RID.
    let integrity_rid = unsafe {
        let count = *GetSidSubAuthorityCount(integrity);
        if count == 0 {
            return Err(invalid("integrity SID has no RID"));
        }
        *GetSidSubAuthority(integrity, u32::from(count - 1))
    };
    let privileges = TokenBuffer::query(token, TokenPrivileges)?;
    let count = *privileges.value::<u32>()?;
    let privileges =
        privileges.array::<LUID_AND_ATTRIBUTES>(offset_of!(TOKEN_PRIVILEGES, Privileges), count)?;
    let mut allowed = Default::default();
    let name = "SeChangeNotifyPrivilege"
        .encode_utf16()
        .chain(Some(0))
        .collect::<Vec<_>>();
    // SAFETY: constant terminated privilege name and writable LUID.
    success(unsafe { LookupPrivilegeValueW(null(), name.as_ptr(), &mut allowed) })?;
    let enabled = privileges
        .iter()
        .filter(|p| p.Attributes & SE_PRIVILEGE_ENABLED != 0)
        .collect::<Vec<_>>();
    Ok(TokenProfile {
        elevated: elevation.value::<TOKEN_ELEVATION>()?.TokenIsElevated != 0,
        // SAFETY: read-only query of the live token; no token state is changed.
        restricted: unsafe { IsTokenRestricted(token) } != 0,
        admin_enabled,
        admin_deny_only,
        integrity_rid,
        enabled_privileges: enabled.len(),
        unexpected_enabled_privileges: enabled
            .iter()
            .filter(|p| p.Luid.LowPart != allowed.LowPart || p.Luid.HighPart != allowed.HighPart)
            .count(),
    })
}

pub fn current_token_profile() -> io::Result<TokenProfile> {
    // SAFETY: GetCurrentProcess returns a pseudo handle, never closed here.
    let token = open_token(unsafe { GetCurrentProcess() }, TOKEN_QUERY)?;
    profile(token.as_raw_handle())
}

fn verify_restricted(profile: &TokenProfile) -> io::Result<()> {
    if profile.elevated
        || !profile.restricted
        || profile.admin_enabled
        || !profile.admin_deny_only
        || profile.integrity_rid != 0x1000
        || profile.unexpected_enabled_privileges != 0
    {
        return Err(denied(
            "worker token failed low-integrity/restricted/admin/privilege checks",
        ));
    }
    Ok(())
}

#[derive(Clone, Debug, Serialize)]
struct CreationProbeError {
    operation: &'static str,
    win32_error: Option<i32>,
}
impl CreationProbeError {
    fn new(operation: &'static str, error: io::Error) -> Self {
        // Never serialize arbitrary SDK error text, paths or account identity.
        Self {
            operation,
            win32_error: error.raw_os_error(),
        }
    }
}

#[derive(Debug, Serialize)]
struct CreationAccessDecision {
    requested_mask: u32,
    mapped_mask: Option<u32>,
    api_success: Option<bool>,
    allowed: Option<bool>,
    granted_mask: Option<u32>,
    error: Option<CreationProbeError>,
}
impl CreationAccessDecision {
    fn unknown(requested_mask: u32, error: CreationProbeError) -> Self {
        Self {
            requested_mask,
            mapped_mask: None,
            api_success: None,
            allowed: None,
            granted_mask: None,
            error: Some(error),
        }
    }
}

#[derive(Debug, Serialize)]
struct CreationLabel {
    integrity_rid: u32,
    mandatory_policy: u32,
}

#[derive(Debug, Serialize)]
struct CreationObjectAccess {
    object: &'static str,
    station_visible: Option<bool>,
    descriptor_error: Option<CreationProbeError>,
    explicit_label: Option<CreationLabel>,
    label_error: Option<CreationProbeError>,
    full_access: CreationAccessDecision,
    maximum_access: CreationAccessDecision,
}

fn creation_desktop_mapping() -> GENERIC_MAPPING {
    // Microsoft Desktop Security and Access Rights generic mapping. These are
    // requested rights for an observational SDK-contract check, not ACL grants.
    GENERIC_MAPPING {
        GenericRead: 0x0002_0041,
        GenericWrite: 0x0002_00be,
        GenericExecute: 0x0002_0100,
        GenericAll: 0x000f_01ff,
    }
}

fn creation_station_mapping(visible: bool) -> GENERIC_MAPPING {
    // Window Station Security and Access Rights specifies separate interactive
    // and noninteractive mappings. The latter excludes READSCREEN/EXITWINDOWS.
    GENERIC_MAPPING {
        GenericRead: if visible { 0x0002_0303 } else { 0x0002_0103 },
        GenericWrite: 0x0002_001c,
        GenericExecute: if visible { 0x0002_0060 } else { 0x0002_0020 },
        GenericAll: if visible { 0x000f_037f } else { 0x000f_013f },
    }
}

fn creation_probe_buffer(bytes: u32) -> io::Result<Vec<usize>> {
    if bytes == 0 || bytes > 1024 * 1024 {
        return Err(invalid(
            "creation access probe returned invalid buffer size",
        ));
    }
    Ok(vec![0; (bytes as usize).div_ceil(size_of::<usize>())])
}

fn creation_object_descriptor(handle: HANDLE) -> io::Result<Vec<usize>> {
    let information = OWNER_SECURITY_INFORMATION
        | GROUP_SECURITY_INFORMATION
        | DACL_SECURITY_INFORMATION
        | LABEL_SECURITY_INFORMATION;
    let mut bytes = 0;
    // SAFETY: size query on the chosen live desktop/window station only.
    let first = unsafe { GetUserObjectSecurity(handle, &information, null_mut(), 0, &mut bytes) };
    if first != 0 || io::Error::last_os_error().raw_os_error() != Some(122) {
        return Err(io::Error::last_os_error());
    }
    let mut buffer = creation_probe_buffer(bytes)?;
    let allocated = bytes;
    // SAFETY: aligned owned storage covers the exact reported length. This
    // reads owner/group/DACL and the mandatory label, never writes an ACL.
    success(unsafe {
        GetUserObjectSecurity(
            handle,
            &information,
            buffer.as_mut_ptr().cast(),
            allocated,
            &mut bytes,
        )
    })?;
    if bytes == 0 || bytes > allocated {
        return Err(invalid("creation access descriptor exceeded allocation"));
    }
    Ok(buffer)
}

fn creation_object_label(descriptor: PSECURITY_DESCRIPTOR) -> io::Result<Option<CreationLabel>> {
    let mut present = 0;
    let mut defaulted = 0;
    let mut acl = null_mut();
    // SAFETY: descriptor is the live kernel-returned binary security descriptor.
    success(unsafe {
        GetSecurityDescriptorSacl(descriptor, &mut present, &mut acl, &mut defaulted)
    })?;
    if present == 0 || acl.is_null() {
        return Ok(None);
    }
    // SAFETY: GetSecurityDescriptorSacl returned an ACL within that owner.
    for index in 0..u32::from(unsafe { (*acl).AceCount }) {
        let mut ace = null_mut();
        // SAFETY: GetAce checks the index and lends a pointer into the live ACL.
        success(unsafe { GetAce(acl, index, &mut ace) })?;
        // SAFETY: Windows returned the ACE's valid type and corresponding data.
        unsafe {
            if (*ace.cast::<ACE_HEADER>()).AceType != 0x11 {
                continue;
            }
            let label = &*ace.cast::<SYSTEM_MANDATORY_LABEL_ACE>();
            let sid = (&label.SidStart as *const u32).cast_mut().cast();
            let count = *GetSidSubAuthorityCount(sid);
            if count == 0 {
                return Err(invalid("creation access label has no RID"));
            }
            return Ok(Some(CreationLabel {
                integrity_rid: *GetSidSubAuthority(sid, u32::from(count - 1)),
                mandatory_policy: label.Mask,
            }));
        }
    }
    Ok(None)
}

fn creation_access_check(
    descriptor: PSECURITY_DESCRIPTOR,
    token: HANDLE,
    requested: u32,
    mapping: &GENERIC_MAPPING,
) -> CreationAccessDecision {
    let mut mapped = requested;
    // SAFETY: mapping and access mask are owned values; no object is changed.
    unsafe { MapGenericMask(&mut mapped, mapping) };
    let mut report = CreationAccessDecision {
        requested_mask: requested,
        mapped_mask: Some(mapped),
        api_success: Some(false),
        allowed: None,
        granted_mask: None,
        error: None,
    };
    let mut bytes = size_of::<PRIVILEGE_SET>() as u32;
    let mut privileges = vec![0usize; size_of::<PRIVILEGE_SET>().div_ceil(size_of::<usize>())];
    for attempt in 0..2 {
        let mut granted = 0;
        let mut allowed = 0;
        // SAFETY: live binary SD, query-only impersonation token, generic bits
        // already mapped, and aligned output buffer with its exact byte length.
        let result = unsafe {
            AccessCheck(
                descriptor,
                token,
                mapped,
                mapping,
                privileges.as_mut_ptr().cast(),
                &mut bytes,
                &mut granted,
                &mut allowed,
            )
        };
        if result != 0 {
            report.api_success = Some(true);
            report.allowed = Some(allowed != 0);
            report.granted_mask = Some(granted);
            return report;
        }
        let error = io::Error::last_os_error();
        if attempt == 0 && error.raw_os_error() == Some(122) {
            match creation_probe_buffer(bytes) {
                Ok(buffer) => {
                    privileges = buffer;
                    continue;
                }
                Err(error) => {
                    report.error = Some(CreationProbeError::new("AccessCheck buffer", error));
                    return report;
                }
            }
        }
        report.error = Some(CreationProbeError::new("AccessCheck", error));
        return report;
    }
    report
}

fn creation_object_access(
    object: &'static str,
    handle: HANDLE,
    token: &Result<OwnedHandle, CreationProbeError>,
    mapping: Result<GENERIC_MAPPING, CreationProbeError>,
    station_visible: Option<bool>,
) -> CreationObjectAccess {
    let mut descriptor = creation_object_descriptor(handle)
        .map_err(|error| CreationProbeError::new("GetUserObjectSecurity", error));
    let mut report = CreationObjectAccess {
        object,
        station_visible,
        descriptor_error: descriptor.as_ref().err().cloned(),
        explicit_label: None,
        label_error: None,
        full_access: CreationAccessDecision::unknown(
            GENERIC_ALL,
            CreationProbeError {
                operation: "not checked",
                win32_error: None,
            },
        ),
        maximum_access: CreationAccessDecision::unknown(
            MAXIMUM_ALLOWED,
            CreationProbeError {
                operation: "not checked",
                win32_error: None,
            },
        ),
    };
    if let Ok(buffer) = &mut descriptor {
        match creation_object_label(buffer.as_mut_ptr().cast()) {
            Ok(label) => report.explicit_label = label,
            Err(error) => {
                report.label_error = Some(CreationProbeError::new("mandatory label", error))
            }
        }
    }
    let error = match (descriptor, token, mapping) {
        (Ok(mut descriptor), Ok(token), Ok(mapping)) => {
            report.full_access = creation_access_check(
                descriptor.as_mut_ptr().cast(),
                token.as_raw_handle(),
                GENERIC_ALL,
                &mapping,
            );
            report.maximum_access = creation_access_check(
                descriptor.as_mut_ptr().cast(),
                token.as_raw_handle(),
                MAXIMUM_ALLOWED,
                &mapping,
            );
            return report;
        }
        (Err(error), _, _) | (_, _, Err(error)) => error,
        (_, Err(error), _) => error.clone(),
    };
    report.full_access = CreationAccessDecision::unknown(GENERIC_ALL, error.clone());
    report.maximum_access = CreationAccessDecision::unknown(MAXIMUM_ALLOWED, error);
    report
}

/// Observational SDK-contract checks only. AccessCheck does not reveal the
/// loader's actual requested rights or prove MIC/Job/loader initialization.
/// Called only from an already-authorized restricted launch, never on import
/// or from the pure/read-only test suite. No ACL or token policy is modified.
fn creation_access_preflight(primary: HANDLE, desktop: HDESK) -> serde_json::Value {
    let policy = TokenBuffer::query(primary, TokenMandatoryPolicy).and_then(|buffer| {
        buffer
            .value::<TOKEN_MANDATORY_POLICY>()
            .map(|value| value.Policy)
    });
    let token = (|| {
        let mut raw = null_mut();
        // SAFETY: clone only this verified restricted token for AccessCheck.
        // It is never assigned to a thread, child, or inherited handle list.
        success(unsafe {
            DuplicateTokenEx(
                primary,
                TOKEN_QUERY,
                null(),
                SecurityIdentification,
                TokenImpersonation,
                &mut raw,
            )
        })?;
        owned(raw)
    })()
    .map_err(|error| CreationProbeError::new("DuplicateTokenEx query-only", error));
    // SAFETY: borrowed current-process window station, never switched or closed.
    let station = unsafe { GetProcessWindowStation() };
    let visibility = (|| {
        let mut flags = USEROBJECTFLAGS::default();
        let mut bytes = 0;
        // SAFETY: read-only flags query into the correctly sized owned record.
        success(unsafe {
            GetUserObjectInformationW(
                station,
                UOI_FLAGS,
                (&mut flags as *mut USEROBJECTFLAGS).cast(),
                size_of::<USEROBJECTFLAGS>() as u32,
                &mut bytes,
            )
        })?;
        Ok::<_, io::Error>(flags.dwFlags & 1 != 0) // SDK WSF_VISIBLE.
    })()
    .map_err(|error| CreationProbeError::new("window station UOI_FLAGS", error));
    serde_json::json!({
        "scope":"SDK full-access preflight only; not actual loader requests or startup proof",
        "token_mandatory_policy": policy.as_ref().ok(),
        "token_policy_error": policy.err().map(|error| CreationProbeError::new("TokenMandatoryPolicy", error)),
        "private_desktop":creation_object_access("private_desktop", desktop, &token, Ok(creation_desktop_mapping()), None),
        "current_window_station":creation_object_access("current_window_station", station, &token, visibility.as_ref().map(|visible| creation_station_mapping(*visible)).map_err(Clone::clone), visibility.ok()),
    })
}

fn restricted_token() -> io::Result<OwnedHandle> {
    // SAFETY: current process pseudo handle is valid for token query.
    let source = open_token(
        unsafe { GetCurrentProcess() },
        TOKEN_QUERY | TOKEN_DUPLICATE | TOKEN_ASSIGN_PRIMARY | TOKEN_ADJUST_DEFAULT,
    )?;
    let source_profile = profile(source.as_raw_handle())?;
    if !source_profile.elevated || !source_profile.admin_enabled {
        return Err(denied(
            "restricted worker launcher requires an independently elevated broker",
        ));
    }
    let user = TokenBuffer::query(source.as_raw_handle(), TokenUser)?;
    // SAFETY: valid kernel-returned user SID. A SYSTEM token must not retain
    // its user SID's administrative grants merely because BA is deny-only.
    if unsafe { IsWellKnownSid(user.value::<TOKEN_USER>()?.User.Sid, WinLocalSystemSid) } != 0 {
        return Err(denied(
            "SYSTEM broker must supply an authenticated user token; restricting SYSTEM in place is unsupported",
        ));
    }
    let groups = TokenBuffer::query(source.as_raw_handle(), TokenGroups)?;
    let admins = Sid::well_known(WinBuiltinAdministratorsSid)?;
    let basics = [
        Sid::well_known(WinWorldSid)?,
        Sid::well_known(WinBuiltinUsersSid)?,
        Sid::well_known(WinAuthenticatedUserSid)?,
    ];
    let disabled = SID_AND_ATTRIBUTES {
        Sid: admins.raw(),
        Attributes: 0,
    };
    let mut restricted = basics
        .iter()
        .map(|sid| SID_AND_ATTRIBUTES {
            Sid: sid.raw(),
            Attributes: 0,
        })
        .collect::<Vec<_>>();
    restricted.push(SID_AND_ATTRIBUTES {
        Sid: user.value::<TOKEN_USER>()?.User.Sid,
        Attributes: 0,
    });
    for group in groups
        .array::<SID_AND_ATTRIBUTES>(offset_of!(TOKEN_GROUPS, Groups), *groups.value::<u32>()?)?
    {
        if group.Attributes & SE_GROUP_LOGON_ID as u32 == SE_GROUP_LOGON_ID as u32 {
            restricted.push(SID_AND_ATTRIBUTES {
                Sid: group.Sid,
                Attributes: 0,
            });
        }
    }
    let mut raw = null_mut();
    // SAFETY: all SID buffers and arrays are live; Windows copies them. No
    // SANDBOX_INERT/AppLocker bypass or maximum-allowed privilege fallback.
    success(unsafe {
        CreateRestrictedToken(
            source.as_raw_handle(),
            DISABLE_MAX_PRIVILEGE | LUA_TOKEN,
            1,
            &disabled,
            0,
            null(),
            restricted.len() as u32,
            restricted.as_ptr(),
            &mut raw,
        )
    })?;
    let token = owned(raw)?;
    let low = Sid::well_known(WinLowLabelSid)?;
    let label = TOKEN_MANDATORY_LABEL {
        Label: SID_AND_ATTRIBUTES {
            Sid: low.raw(),
            Attributes: SE_GROUP_INTEGRITY as u32,
        },
    };
    // SAFETY: valid label/SID live throughout the synchronous token copy.
    success(unsafe {
        SetTokenInformation(
            token.as_raw_handle(),
            TokenIntegrityLevel,
            (&label as *const TOKEN_MANDATORY_LABEL).cast(),
            (size_of::<TOKEN_MANDATORY_LABEL>() as u32) + GetLengthSid(low.raw()),
        )
    })?;
    verify_restricted(&profile(token.as_raw_handle())?)?;
    Ok(token)
}

fn object_name(handle: HANDLE) -> io::Result<String> {
    let mut bytes = 0;
    // SAFETY: size-only query on a live USER object handle.
    unsafe { GetUserObjectInformationW(handle, UOI_NAME, null_mut(), 0, &mut bytes) };
    if bytes == 0 || bytes > 4096 || !bytes.is_multiple_of(2) {
        return Err(invalid("invalid desktop name size"));
    }
    let mut buffer = vec![0u16; bytes as usize / 2];
    // SAFETY: writable UTF-16 buffer covers the returned size.
    success(unsafe {
        GetUserObjectInformationW(
            handle,
            UOI_NAME,
            buffer.as_mut_ptr().cast(),
            bytes,
            &mut bytes,
        )
    })?;
    let end = buffer
        .iter()
        .position(|c| *c == 0)
        .ok_or_else(|| invalid("desktop name is not terminated"))?;
    String::from_utf16(&buffer[..end]).map_err(io::Error::other)
}

pub fn current_desktop_name() -> io::Result<String> {
    object_name(current_thread_desktop()?)
}

fn current_thread_desktop() -> io::Result<HDESK> {
    // SAFETY: read-only borrowed desktop associated with this live thread. The
    // returned handle must never be closed by this adapter.
    let desktop = unsafe { GetThreadDesktop(GetCurrentThreadId()) };
    if desktop.is_null() {
        return Err(io::Error::last_os_error());
    }
    Ok(desktop)
}

fn restore_desktop_binding(
    previous: HDESK,
    mut current: impl FnMut() -> io::Result<HDESK>,
    mut restore: impl FnMut(HDESK) -> io::Result<()>,
) -> io::Result<()> {
    if current()? != previous {
        restore(previous)?;
        if current()? != previous {
            return Err(denied(
                "creator thread desktop restoration did not take effect",
            ));
        }
    }
    Ok(())
}

fn checked_cleanup<T>(primary: io::Result<T>, cleanup: io::Result<()>) -> io::Result<T> {
    match (primary, cleanup) {
        (Err(primary), Err(cleanup)) => Err(io::Error::new(
            primary.kind(),
            format!("{primary}; cleanup failed: {cleanup}"),
        )),
        (Err(error), _) | (_, Err(error)) => Err(error),
        (Ok(value), Ok(())) => Ok(value),
    }
}

struct LocalDescriptor(*mut c_void);
impl LocalDescriptor {
    fn new(sddl: &str) -> io::Result<Self> {
        let text = sddl.encode_utf16().chain(Some(0)).collect::<Vec<_>>();
        let mut raw = null_mut();
        // SAFETY: terminated, internally constructed SDDL and new allocation output.
        success(unsafe {
            ConvertStringSecurityDescriptorToSecurityDescriptorW(
                text.as_ptr(),
                SDDL_REVISION_1,
                &mut raw,
                null_mut(),
            )
        })?;
        Ok(Self(raw))
    }
}
impl Drop for LocalDescriptor {
    fn drop(&mut self) {
        // SAFETY: sole LocalAlloc allocation returned by SDDL conversion.
        unsafe { LocalFree(self.0) };
    }
}

fn private_desktop_descriptor(user_sid: &str) -> io::Result<LocalDescriptor> {
    // The caller obtains this canonical SID from the verified worker token.
    // This descriptor is used only when creating our own private desktop.
    // CreateProcessAsUserW requires full access to its selected desktop for
    // startup. Grant that only on this isolated Low desktop; the default
    // desktop/window station, restricted token and Job limits are unchanged.
    LocalDescriptor::new(&format!(
        "O:BAG:BAD:P(A;;0x000f01ff;;;SY)(A;;0x000f01ff;;;BA)(A;;0x000f01ff;;;{user_sid})(A;;RC;;;OW)S:(ML;;NW;;;LW)"
    ))
}

struct Desktop {
    handle: HDESK,
    name: String,
    qualified: Vec<u16>,
}

// SAFETY: HDESK is a process-wide USER object handle, not a thread-owned Rust
// pointer. This sole owner is transferred only after its creator thread has
// joined, so that thread can no longer be attached when another thread closes
// it. No shared access or Sync implementation is provided.
unsafe impl Send for Desktop {}

impl Desktop {
    fn create(token: &OwnedHandle) -> io::Result<Self> {
        let parent_desktop = current_thread_desktop()?;
        let token = token.try_clone()?;
        // CreateDesktop may bind its calling thread. Keep that operation away
        // from the broker/GUI thread, including failed restoration paths.
        let creator = std::thread::Builder::new()
            .name("swirl-desktop-creator".into())
            .spawn(move || Self::create_on_thread(token.as_raw_handle()))?;
        let outcome = creator
            .join()
            .map_err(|_| io::Error::other("private desktop creator panicked"))
            .and_then(|result| result);
        let parent_unchanged = current_thread_desktop().and_then(|current| {
            if current == parent_desktop {
                Ok(())
            } else {
                Err(denied(
                    "private desktop creation changed parent thread desktop",
                ))
            }
        });
        match outcome {
            Ok((mut desktop, ready)) => {
                if let Err(error) = checked_cleanup(ready, parent_unchanged) {
                    // The creator is already joined/detached, even if its
                    // explicit restoration failed. Closing is now safe here.
                    return checked_cleanup(Err(error), desktop.close());
                }
                Ok(desktop)
            }
            Err(error) => checked_cleanup(Err(error), parent_unchanged),
        }
    }

    fn create_on_thread(token: HANDLE) -> io::Result<(Self, io::Result<()>)> {
        let previous = current_thread_desktop()?;
        let user = TokenBuffer::query(token, TokenUser)?;
        let mut text = null_mut();
        // SAFETY: valid kernel-returned user SID, writable LocalAlloc string output.
        success(unsafe {
            ConvertSidToStringSidW(user.value::<TOKEN_USER>()?.User.Sid, &mut text)
        })?;
        // SAFETY: conversion returns a terminated UTF-16 SID string.
        let user_text = unsafe {
            let mut n = 0;
            while *text.add(n) != 0 {
                n += 1;
            }
            let value =
                String::from_utf16(std::slice::from_raw_parts(text, n)).map_err(io::Error::other);
            LocalFree(text.cast());
            value?
        };
        let security = private_desktop_descriptor(&user_text)?;
        let mut id = GUID::from_u128(0);
        // SAFETY: writable GUID; no external input or global network change.
        let status = unsafe { UuidCreate(&mut id) };
        if status != 0 {
            return Err(io::Error::from_raw_os_error(status));
        }
        let name = format!(
            "SwirlRestricted-{:08x}{:04x}{:04x}{:016x}",
            id.data1,
            id.data2,
            id.data3,
            u64::from_be_bytes(id.data4)
        );
        let wide = name.encode_utf16().chain(Some(0)).collect::<Vec<_>>();
        let attributes = SECURITY_ATTRIBUTES {
            nLength: size_of::<SECURITY_ATTRIBUTES>() as u32,
            lpSecurityDescriptor: security.0,
            bInheritHandle: 0,
        };
        // SAFETY: valid constant/owned inputs on the dedicated creator thread.
        // No SwitchDesktop or window-station change is performed.
        let handle = unsafe {
            CreateDesktopW(
                wide.as_ptr(),
                null(),
                null(),
                0,
                DESKTOP_CREATEWINDOW
                    | DESKTOP_READOBJECTS
                    | DESKTOP_WRITEOBJECTS
                    | DESKTOP_READ_CONTROL,
                &attributes,
            )
        };
        if handle.is_null() {
            return Err(io::Error::last_os_error());
        }
        let mut desktop = Self {
            handle,
            name,
            qualified: Vec::new(),
        };
        let ready = (|| {
            restore_desktop_binding(previous, current_thread_desktop, |original| {
                // SAFETY: borrowed original desktop of this same creator
                // thread, still on the same process window station.
                success(unsafe { SetThreadDesktop(original) })
            })?;
            if object_name(desktop.handle)? != desktop.name {
                return Err(denied("private desktop identity mismatch"));
            }
            // SAFETY: borrowed current-process window station, never closed here.
            let station = object_name(unsafe { GetProcessWindowStation() })?;
            desktop.qualified = format!("{station}\\{}", desktop.name)
                .encode_utf16()
                .chain(Some(0))
                .collect();
            Ok(())
        })();
        // Pass both the handle and any failure to the parent. The parent joins
        // this thread before closing, rather than leaking a still-bound HDESK.
        Ok((desktop, ready))
    }

    fn close(&mut self) -> io::Result<()> {
        if !self.handle.is_null() {
            // SAFETY: sole owned handle; creator joined and child reaped first.
            success(unsafe { CloseDesktop(self.handle) })
                .map_err(|error| io::Error::new(error.kind(), format!("CloseDesktop: {error}")))?;
            self.handle = null_mut();
        }
        Ok(())
    }
}
impl Drop for Desktop {
    fn drop(&mut self) {
        if let Err(error) = self.close() {
            eprintln!("private desktop cleanup failed: {error}");
        }
    }
}

fn quote_argument(argument: &OsStr) -> io::Result<Vec<u16>> {
    let mut result = vec![b'"' as u16];
    let mut slashes = 0;
    for unit in argument.encode_wide() {
        if unit == 0 {
            return Err(invalid("worker argument contains NUL"));
        }
        if unit == b'\\' as u16 {
            slashes += 1;
            continue;
        }
        result.extend(std::iter::repeat_n(
            b'\\' as u16,
            slashes * if unit == b'"' as u16 { 2 } else { 1 },
        ));
        if unit == b'"' as u16 {
            result.push(b'\\' as u16);
        }
        result.push(unit);
        slashes = 0;
    }
    result.extend(std::iter::repeat_n(b'\\' as u16, slashes * 2));
    result.push(b'"' as u16);
    Ok(result)
}

fn command_line(executable: &Path, arguments: &[OsString]) -> io::Result<Vec<u16>> {
    let mut line = quote_argument(executable.as_os_str())?;
    for argument in arguments {
        line.push(b' ' as u16);
        line.extend(quote_argument(argument)?);
    }
    line.push(0);
    if line.len() > 32_767 {
        return Err(invalid("worker command line exceeds Windows limit"));
    }
    Ok(line)
}

fn environment(system_root: &Path) -> Vec<u16> {
    let mut result = Vec::new();
    for (name, value) in [
        ("PATH", system_root.join("System32")),
        ("SystemRoot", system_root.to_path_buf()),
        ("WINDIR", system_root.to_path_buf()),
    ] {
        result.extend(OsString::from(format!("{name}=")).encode_wide());
        result.extend(value.as_os_str().encode_wide());
        result.push(0);
    }
    result.push(0);
    result
}

fn pipe() -> io::Result<(OwnedHandle, OwnedHandle)> {
    let mut read = null_mut();
    let mut write = null_mut();
    // SAFETY: writable outputs; null attributes make both ends non-inheritable.
    success(unsafe { CreatePipe(&mut read, &mut write, null(), 0) })?;
    Ok((owned(read)?, owned(write)?))
}

fn inheritable(handle: &OwnedHandle) -> io::Result<OwnedHandle> {
    let mut duplicate = null_mut();
    // SAFETY: broker duplicates only an anonymous pipe end it just created;
    // the explicit child handle list excludes all other broker handles.
    success(unsafe {
        DuplicateHandle(
            GetCurrentProcess(),
            handle.as_raw_handle(),
            GetCurrentProcess(),
            &mut duplicate,
            0,
            1,
            DUPLICATE_SAME_ACCESS,
        )
    })?;
    owned(duplicate)
}

const JOURNAL_ACCESS: u32 = FILE_READ_DATA | FILE_WRITE_DATA | FILE_READ_ATTRIBUTES | SYNCHRONIZE;

fn inherited_fake_ip_journal(journal: &File) -> io::Result<OwnedHandle> {
    // SAFETY: borrowed caller-approved file handle, queried without changing it.
    if unsafe { GetFileType(journal.as_raw_handle()) } != FILE_TYPE_DISK
        || !journal.metadata()?.is_file()
    {
        return Err(invalid("fake-IP delegation requires a regular disk file"));
    }
    let mut duplicate = null_mut();
    // SAFETY: delegate this one already-opened approved file, with no DELETE,
    // WRITE_DAC, WRITE_OWNER, attribute-write, or directory-traversal access.
    // No pathname or mutable broker handle list is accepted from the worker.
    success(unsafe {
        DuplicateHandle(
            GetCurrentProcess(),
            journal.as_raw_handle(),
            GetCurrentProcess(),
            &mut duplicate,
            JOURNAL_ACCESS,
            1,
            0,
        )
    })?;
    owned(duplicate)
}

struct DataPlaneInheritance {
    packet_input: OwnedHandle,
    packet_output: OwnedHandle,
    fake_ip_journal: OwnedHandle,
}

/// Child-local handle values, delivered only over its private control pipe.
/// These identify the launcher's explicit inherited resources; they are not
/// authentication credentials or a way to request arbitrary broker handles.
#[derive(Clone, Copy, Debug, Serialize)]
pub struct DataPlaneHandles {
    pub packet_input: usize,
    pub packet_output: usize,
    pub fake_ip_journal: usize,
}

pub struct DataPlaneChild {
    pub worker: RestrictedChild,
    /// Broker writes packets here; only the read end is inherited by the worker.
    pub packet_input: File,
    /// Broker reads packets here; only the write end is inherited by the worker.
    pub packet_output: File,
    pub inherited: DataPlaneHandles,
}

/// Launch the data-plane worker with exactly six purpose-limited resources:
/// stdio, two internally-created directional packet pipes, and the approved
/// fake-IP journal. Caller must establish the file's provenance and must not use
/// its shared cursor or acquire the allocator's lock while the worker owns it.
pub fn spawn_data_plane(
    executable: &Path,
    arguments: &[OsString],
    fake_ip_journal: &File,
) -> io::Result<DataPlaneChild> {
    spawn_data_plane_inner(executable, arguments, fake_ip_journal, false)
}

fn spawn_data_plane_inner(
    executable: &Path,
    arguments: &[OsString],
    fake_ip_journal: &File,
    diagnostic: bool,
) -> io::Result<DataPlaneChild> {
    let journal = inherited_fake_ip_journal(fake_ip_journal)?;
    let (packet_input, broker_input) = pipe()?;
    let (broker_output, packet_output) = pipe()?;
    let inheritance = DataPlaneInheritance {
        packet_input: inheritable(&packet_input)?,
        packet_output: inheritable(&packet_output)?,
        fake_ip_journal: journal,
    };
    let inherited = DataPlaneHandles {
        packet_input: inheritance.packet_input.as_raw_handle() as usize,
        packet_output: inheritance.packet_output.as_raw_handle() as usize,
        fake_ip_journal: inheritance.fake_ip_journal.as_raw_handle() as usize,
    };
    let worker = spawn_inner(executable, arguments, Some(&inheritance), diagnostic)?;
    Ok(DataPlaneChild {
        worker,
        packet_input: File::from(broker_input),
        packet_output: File::from(broker_output),
        inherited,
    })
}

struct Attributes {
    memory: Vec<usize>,
    list: LPPROC_THREAD_ATTRIBUTE_LIST,
}
impl Attributes {
    fn new(handles: &[HANDLE]) -> io::Result<Self> {
        let mut bytes = 0;
        // SAFETY: documented first size query for one process attribute.
        unsafe { InitializeProcThreadAttributeList(null_mut(), 1, 0, &mut bytes) };
        if bytes == 0 {
            return Err(io::Error::last_os_error());
        }
        let mut memory = vec![0usize; bytes.div_ceil(size_of::<usize>())];
        let list = memory.as_mut_ptr().cast();
        // SAFETY: aligned storage sized by the preceding API query.
        success(unsafe { InitializeProcThreadAttributeList(list, 1, 0, &mut bytes) })?;
        let result = Self { memory, list };
        // SAFETY: the private three/six-handle array lives through
        // CreateProcessAsUser; all entries were made inheritable above.
        success(unsafe {
            UpdateProcThreadAttribute(
                result.list,
                0,
                PROC_THREAD_ATTRIBUTE_HANDLE_LIST as usize,
                handles.as_ptr().cast(),
                size_of_val(handles),
                null_mut(),
                null(),
            )
        })?;
        Ok(result)
    }
}
impl Drop for Attributes {
    fn drop(&mut self) {
        // SAFETY: initialized list still backed by memory until after this call.
        unsafe { DeleteProcThreadAttributeList(self.list) };
        let _ = &self.memory;
    }
}

pub struct RestrictedChild {
    pub stdin: Option<File>,
    pub stdout: Option<File>,
    pub stderr: Option<File>,
    process: OwnedHandle,
    job: Option<OwnedHandle>,
    desktop: Desktop,
    assigned: bool,
    // Only the explicit loader diagnostic sets this. Debug events must be
    // continued by the creating thread before the exited process can be reaped.
    debug_thread: Option<u32>,
    pub id: u32,
}

impl RestrictedChild {
    pub fn desktop_name(&self) -> &str {
        &self.desktop.name
    }

    fn terminate(&mut self) -> io::Result<()> {
        let mut error = None;
        if let Some(job) = self.job.take() {
            // SAFETY: private non-inheritable kill-on-close job; Drop closes it
            // even when explicit termination fails. No breakaway is permitted.
            if unsafe { TerminateJobObject(job.as_raw_handle(), 1) } == 0 {
                error = Some(io::Error::last_os_error());
            }
            drop(job);
        }
        if !self.assigned {
            // SAFETY: assignment failure left this child suspended/unexecuted.
            if unsafe { TerminateProcess(self.process.as_raw_handle(), 1) } == 0 {
                error.get_or_insert_with(io::Error::last_os_error);
            }
        }
        if let Some(creator) = self.debug_thread {
            loader_diagnostic::drain_terminated(creator, self.id, self.process.as_raw_handle())?;
        }
        // SAFETY: live process handle supports SYNCHRONIZE; bound cleanup wait.
        let status = unsafe { WaitForSingleObject(self.process.as_raw_handle(), 5_000) };
        if status != WAIT_OBJECT_0 {
            return Err(io::Error::other(
                "restricted worker termination did not reap the child",
            ));
        }
        checked_cleanup(error.map_or(Ok(()), Err), self.desktop.close())
    }

    pub fn kill(&mut self) -> io::Result<()> {
        self.terminate()
    }

    pub fn try_wait(&mut self) -> io::Result<Option<u32>> {
        // SAFETY: live process handle; zero timeout never blocks.
        match unsafe { WaitForSingleObject(self.process.as_raw_handle(), 0) } {
            WAIT_TIMEOUT => Ok(None),
            WAIT_OBJECT_0 => {
                let mut exit = 0;
                // SAFETY: completed live process handle and writable exit code.
                success(unsafe { GetExitCodeProcess(self.process.as_raw_handle(), &mut exit) })?;
                self.terminate()?;
                Ok(Some(exit))
            }
            _ => {
                let error = io::Error::last_os_error();
                let _ = self.terminate();
                Err(error)
            }
        }
    }

    pub fn wait(&mut self, timeout: Duration) -> io::Result<u32> {
        let timeout = u32::try_from(timeout.as_millis())
            .map_err(|_| invalid("worker wait deadline too large"))?;
        if timeout == u32::MAX {
            return Err(invalid("infinite worker wait is unsupported"));
        }
        // SAFETY: live process handle and finite deadline.
        let status = unsafe { WaitForSingleObject(self.process.as_raw_handle(), timeout) };
        if status == WAIT_TIMEOUT {
            self.terminate()?;
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "restricted worker wait timed out",
            ));
        }
        self.try_wait()?
            .ok_or_else(|| io::Error::other("worker wait returned without exit"))
    }
}
impl Drop for RestrictedChild {
    fn drop(&mut self) {
        if let Err(error) = self.terminate() {
            eprintln!("restricted worker cleanup failed: {error}");
        }
    }
}

/// Launch an approved worker. Caller owns executable provenance/authentication;
/// this API accepts no arbitrary inherited handle or parent environment block.
pub fn spawn(executable: &Path, arguments: &[OsString]) -> io::Result<RestrictedChild> {
    spawn_inner(executable, arguments, None, false)
}

fn spawn_inner(
    executable: &Path,
    arguments: &[OsString],
    data_plane: Option<&DataPlaneInheritance>,
    diagnostic: bool,
) -> io::Result<RestrictedChild> {
    if !executable.is_absolute()
        || !matches!(executable.components().next(), Some(Component::Prefix(prefix))
        if matches!(prefix.kind(), Prefix::Disk(_) | Prefix::VerbatimDisk(_)))
    {
        return Err(invalid("worker executable must be a local absolute path"));
    }
    let executable = std::fs::canonicalize(executable)?;
    if !matches!(executable.components().next(), Some(Component::Prefix(prefix))
        if matches!(prefix.kind(), Prefix::Disk(_) | Prefix::VerbatimDisk(_)))
    {
        return Err(invalid("worker executable resolved outside a local drive"));
    }
    let application = executable
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect::<Vec<_>>();
    let mut line = command_line(&executable, arguments)?;
    let directory = executable
        .parent()
        .ok_or_else(|| invalid("worker executable has no parent"))?
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect::<Vec<_>>();
    let token = restricted_token()?;
    let mut desktop = Desktop::create(&token)?;
    let mut root = vec![0u16; 32_768];
    // SAFETY: writable buffer sized to Windows' maximum local path length.
    let length = unsafe { GetWindowsDirectoryW(root.as_mut_ptr(), root.len() as u32) } as usize;
    if length == 0 || length >= root.len() {
        return Err(io::Error::last_os_error());
    }
    let root = Path::new(&OsString::from_wide(&root[..length])).to_path_buf();
    let environment = environment(&root);
    let (input_read, input_write) = pipe()?;
    let (output_read, output_write) = pipe()?;
    let (error_read, error_write) = pipe()?;
    let child_input = inheritable(&input_read)?;
    let child_output = inheritable(&output_write)?;
    let child_error = inheritable(&error_write)?;
    let mut handles = [
        child_input.as_raw_handle(),
        child_output.as_raw_handle(),
        child_error.as_raw_handle(),
        null_mut(),
        null_mut(),
        null_mut(),
    ];
    let count = if let Some(resources) = data_plane {
        handles[3] = resources.packet_input.as_raw_handle();
        handles[4] = resources.packet_output.as_raw_handle();
        handles[5] = resources.fake_ip_journal.as_raw_handle();
        6
    } else {
        3
    };
    let attributes = Attributes::new(&handles[..count])?;
    let mut startup = STARTUPINFOEXW::default();
    startup.StartupInfo.cb = size_of::<STARTUPINFOEXW>() as u32;
    startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
    startup.StartupInfo.hStdInput = handles[0];
    startup.StartupInfo.hStdOutput = handles[1];
    startup.StartupInfo.hStdError = handles[2];
    startup.StartupInfo.lpDesktop = desktop.qualified.as_mut_ptr();
    startup.lpAttributeList = attributes.list;
    // SAFETY: unnamed/non-inheritable job, owned by this launch operation.
    let job = owned(unsafe { CreateJobObjectW(null(), null()) })?;
    let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    // SAFETY: correctly sized initialized job-limit structure.
    success(unsafe {
        SetInformationJobObject(
            job.as_raw_handle(),
            JobObjectExtendedLimitInformation,
            (&limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
            size_of_val(&limits) as u32,
        )
    })?;
    let ui = JOBOBJECT_BASIC_UI_RESTRICTIONS {
        UIRestrictionsClass: JOB_OBJECT_UILIMIT_DESKTOP
            | JOB_OBJECT_UILIMIT_HANDLES
            | JOB_OBJECT_UILIMIT_READCLIPBOARD
            | JOB_OBJECT_UILIMIT_WRITECLIPBOARD
            | JOB_OBJECT_UILIMIT_GLOBALATOMS
            | JOB_OBJECT_UILIMIT_EXITWINDOWS
            | JOB_OBJECT_UILIMIT_SYSTEMPARAMETERS
            | JOB_OBJECT_UILIMIT_DISPLAYSETTINGS,
    };
    // SAFETY: correctly sized UI restrictions; worker is headless and cannot
    // access USER handles belonging to applications outside its private job.
    success(unsafe {
        SetInformationJobObject(
            job.as_raw_handle(),
            JobObjectBasicUIRestrictions,
            (&ui as *const JOBOBJECT_BASIC_UI_RESTRICTIONS).cast(),
            size_of_val(&ui) as u32,
        )
    })?;
    let mut process = PROCESS_INFORMATION::default();
    eprintln!(
        "restricted worker creation access preflight: {}",
        creation_access_preflight(token.as_raw_handle(), desktop.handle)
    );
    // SAFETY: live restricted token, fixed local exe, mutable quoted command,
    // explicit environment/desktop and exactly the three/six listed handles.
    // The primary thread cannot execute before the job assignment below.
    success(unsafe {
        CreateProcessAsUserW(
            token.as_raw_handle(),
            application.as_ptr(),
            line.as_mut_ptr(),
            null(),
            null(),
            1,
            CREATE_NO_WINDOW
                | CREATE_SUSPENDED
                | CREATE_UNICODE_ENVIRONMENT
                | EXTENDED_STARTUPINFO_PRESENT
                | if diagnostic {
                    DEBUG_ONLY_THIS_PROCESS
                } else {
                    0
                },
            environment.as_ptr().cast(),
            directory.as_ptr(),
            &startup.StartupInfo,
            &mut process,
        )
    })?;
    let thread = owned(process.hThread)?;
    let mut child = RestrictedChild {
        stdin: Some(File::from(input_write)),
        stdout: Some(File::from(output_read)),
        stderr: Some(File::from(error_read)),
        process: owned(process.hProcess)?,
        job: Some(job),
        desktop,
        assigned: false,
        debug_thread: diagnostic.then(|| unsafe { GetCurrentThreadId() }),
        id: process.dwProcessId,
    };
    if diagnostic {
        // PROCESS_INFORMATION handles are caller-owned (CloseHandle required),
        // unlike the separately supplied debug-event process/thread handles.
        // Keep an explicitly independent non-inheritable owner for token,
        // memory and post-Continue exit queries. Never own an event hProcess.
        child.process = child.process.try_clone()?;
    }
    // SAFETY: suspended child is uniquely owned and has not run user code.
    success(unsafe {
        AssignProcessToJobObject(
            child.job.as_ref().expect("new job").as_raw_handle(),
            child.process.as_raw_handle(),
        )
    })?;
    child.assigned = true;
    let actual_token = open_token(child.process.as_raw_handle(), TOKEN_QUERY)?;
    verify_restricted(&profile(actual_token.as_raw_handle())?)?;
    // SAFETY: exactly one initial suspension, after job/token verification.
    match unsafe { ResumeThread(thread.as_raw_handle()) } {
        1 => Ok(child),
        u32::MAX => Err(io::Error::last_os_error()),
        _ => Err(io::Error::other(
            "worker was not initially suspended exactly once",
        )),
    }
}

#[path = "windows_loader_diagnostic.rs"]
mod loader_diagnostic;
pub use loader_diagnostic::trace_headless_startup;

#[cfg(test)]
#[path = "windows_restricted_worker_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "windows_creation_access_tests.rs"]
mod creation_access_tests;
