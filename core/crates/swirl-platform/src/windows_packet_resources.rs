//! Borrow and duplicate the experimental packet worker's exact three resources.
//! Handle values and epochs are not peer authentication. The launcher must
//! authenticate its peer and provide only its two packet ends and approved file.
#![allow(unsafe_code)] // Sole Windows handle/type/identity FFI boundary.

use serde::Deserialize;
use std::{
    fs::File,
    io,
    os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle},
    ptr::null_mut,
};
use windows_sys::Win32::{
    Foundation::{CompareObjectHandles, DuplicateHandle, GetHandleInformation, HANDLE},
    Storage::FileSystem::{
        FILE_READ_ATTRIBUTES, FILE_READ_DATA, FILE_TYPE_DISK, FILE_TYPE_PIPE, FILE_WRITE_DATA,
        GetFileType, SYNCHRONIZE,
    },
    System::Threading::GetCurrentProcess,
};

#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InheritedPacketHandles {
    pub packet_input: u64,
    pub packet_output: u64,
    pub fake_ip_journal: u64,
}

pub struct PacketWorkerResources {
    pub packet_input: File,
    pub packet_output: File,
    pub fake_ip_journal: File,
}

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, message)
}

fn handles(ids: InheritedPacketHandles) -> io::Result<[HANDLE; 3]> {
    let values = [ids.packet_input, ids.packet_output, ids.fake_ip_journal];
    let mut result = [null_mut(); 3];
    for (index, value) in values.into_iter().enumerate() {
        let value = usize::try_from(value)
            .map_err(|_| invalid("resource handle does not fit process architecture"))?;
        if value == 0 || value == usize::MAX {
            return Err(invalid("null or pseudo resource handle"));
        }
        result[index] = value as HANDLE;
    }
    if result[0] == result[1] || result[0] == result[2] || result[1] == result[2] {
        return Err(invalid("resource handles must be distinct"));
    }
    Ok(result)
}

fn aliases(resources: &[HANDLE; 3], stdio: &[HANDLE; 3]) -> io::Result<()> {
    for (index, resource) in resources.iter().enumerate() {
        for other in &resources[..index] {
            // SAFETY: this query does not close or mutate either borrowed handle.
            if resource == other || unsafe { CompareObjectHandles(*resource, *other) } != 0 {
                return Err(invalid("packet resources alias one another"));
            }
        }
        for standard in stdio {
            if !standard.is_null()
                && *standard as usize != usize::MAX
                && (resource == standard
                    || unsafe { CompareObjectHandles(*resource, *standard) } != 0)
            {
                return Err(invalid("packet resource aliases a standard stream"));
            }
        }
    }
    Ok(())
}

fn kind(handle: HANDLE, expected: u32) -> io::Result<()> {
    let mut flags = 0;
    // SAFETY: read-only queries on the caller's borrowed handle value.
    if unsafe { GetHandleInformation(handle, &mut flags) } == 0 {
        return Err(io::Error::last_os_error());
    }
    if unsafe { GetFileType(handle) } != expected {
        return Err(invalid("packet resource has the wrong file type"));
    }
    Ok(())
}

fn duplicate(source: HANDLE, access: u32, expected: u32) -> io::Result<OwnedHandle> {
    kind(source, expected)?;
    let mut raw = null_mut();
    // SAFETY: borrow the original, create an independent non-inheritable owner,
    // and request only the fixed role's rights. Never close the borrowed source.
    if unsafe {
        DuplicateHandle(
            GetCurrentProcess(),
            source,
            GetCurrentProcess(),
            &mut raw,
            access,
            0,
            0,
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: successful DuplicateHandle transferred this new handle alone.
    let duplicate = unsafe { OwnedHandle::from_raw_handle(raw) };
    // Recheck the owned duplicate: an unrelated caller thread could have closed
    // and reused its original numeric handle during the preceding queries.
    kind(duplicate.as_raw_handle(), expected)?;
    Ok(duplicate)
}

/// Duplicate, do not assume ownership of, validated inherited resources. The
/// original three launch handles remain process-lifetime resources and close at
/// process exit; their count never grows per packet/flow. The returned files are
/// private non-inheritable, limited-access owners. No pathname is accepted.
pub fn clone_inherited_packet_resources(
    ids: InheritedPacketHandles,
) -> io::Result<PacketWorkerResources> {
    let originals = handles(ids)?;
    let stdio = [
        io::stdin().as_raw_handle(),
        io::stdout().as_raw_handle(),
        io::stderr().as_raw_handle(),
    ];
    aliases(&originals, &stdio)?;
    let input = duplicate(originals[0], FILE_READ_DATA | SYNCHRONIZE, FILE_TYPE_PIPE)?;
    let output = duplicate(originals[1], FILE_WRITE_DATA | SYNCHRONIZE, FILE_TYPE_PIPE)?;
    let journal = duplicate(
        originals[2],
        FILE_READ_DATA | FILE_WRITE_DATA | FILE_READ_ATTRIBUTES | SYNCHRONIZE,
        FILE_TYPE_DISK,
    )?;
    let copied = [
        input.as_raw_handle(),
        output.as_raw_handle(),
        journal.as_raw_handle(),
    ];
    aliases(&copied, &stdio)?;
    let journal = File::from(journal);
    if !journal.metadata()?.is_file() {
        return Err(invalid("fake-IP journal must be a regular disk file"));
    }
    Ok(PacketWorkerResources {
        packet_input: File::from(input),
        packet_output: File::from(output),
        fake_ip_journal: journal,
    })
}

#[cfg(test)]
#[path = "windows_packet_resources_tests.rs"]
mod tests;
