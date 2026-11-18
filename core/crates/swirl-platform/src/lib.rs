//! Host integration shared by the portable core through a platform-neutral API.
//! Mobile applications supply hosts through configuration. Desktop TUN adapters
//! require an explicitly invoked privileged helper; importing this crate never
//! changes network settings or loads a driver.
use std::{
    fs::{File, OpenOptions},
    io,
    path::{Path, PathBuf},
};

#[cfg(any(windows, test))]
mod dhcp_probe;
pub mod gateway_policy;
pub mod network_transaction;
#[cfg(windows)]
mod windows_dhcp_attachment;
#[cfg(windows)]
mod windows_dhcp_probe;

#[cfg(windows)]
pub mod physical_network;
#[cfg(windows)]
mod socket_pin;
#[cfg(windows)]
mod windows_command;
#[cfg(windows)]
pub mod windows_gateway;
#[cfg(windows)]
mod windows_gateway_firewall;
#[cfg(windows)]
mod windows_gateway_wfp;
#[cfg(windows)]
pub mod windows_network;
#[cfg(windows)]
mod windows_network_session;
#[cfg(windows)]
mod windows_notify;
#[cfg(windows)]
pub mod windows_packet_resources;
#[cfg(windows)]
pub mod windows_restricted_worker;
#[cfg(windows)]
pub mod windows_tun_broker;
#[cfg(windows)]
pub mod windows_wfp;
#[cfg(windows)]
pub mod wintun_device;
#[cfg(windows)]
pub use socket_pin::pin_outbound_socket;

/// Open a repairable journal without truncating existing records. New Unix
/// files request owner read/write permissions only (further limited by umask).
/// Windows inherits the parent ACL; the caller must establish trusted storage
/// and acquire its exclusive journal lock before reading or writing records.
pub fn open_private_journal(path: &Path) -> io::Result<File> {
    // Append-only Windows handles cannot truncate a torn final record.
    owner_private_open_options()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)
}

/// File creation policy for private append journals. Unix creation is 0600;
/// Windows callers must use their protected journal directory and inherited
/// ACL. Read/write, truncation and locking remain explicit at the call site.
pub fn owner_private_open_options() -> OpenOptions {
    let mut options = OpenOptions::new();
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    // `mut` is needed only on Unix, but this signature has one portable body.
    let _ = &mut options;
    options
}

/// Location of a desktop hosts file, when this adapter supports one.
/// `None` means no platform file integration, not a resolver/network failure.
pub fn system_hosts_path() -> Option<PathBuf> {
    #[cfg(target_os = "windows")]
    {
        Some(
            PathBuf::from(std::env::var_os("SystemRoot").unwrap_or_else(|| "C:\\Windows".into()))
                .join("System32/drivers/etc/hosts"),
        )
    }
    #[cfg(any(target_os = "macos", target_os = "linux"))]
    {
        Some(PathBuf::from("/etc/hosts"))
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos", target_os = "linux")))]
    {
        None
    }
}

#[cfg(test)]
#[path = "journal_file_tests.rs"]
mod journal_file_tests;
