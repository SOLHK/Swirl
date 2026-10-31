//! Host integration shared by the portable core through a platform-neutral API.
//! Mobile applications supply hosts through configuration. Desktop TUN adapters
//! require an explicitly invoked privileged helper; importing this crate never
//! changes network settings or loads a driver.
use std::path::PathBuf;

#[cfg(any(windows, test))]
mod dhcp_probe;
pub mod gateway_policy;
pub mod network_transaction;
#[cfg(windows)]
mod windows_dhcp_attachment;
#[cfg(windows)]
mod windows_dhcp_probe;

#[cfg(windows)]
mod socket_pin;
#[cfg(windows)]
mod windows_command;
#[cfg(windows)]
pub mod windows_gateway;
#[cfg(windows)]
mod windows_gateway_firewall;
#[cfg(windows)]
pub mod windows_network;
#[cfg(windows)]
mod windows_notify;
#[cfg(windows)]
mod windows_wfp;
#[cfg(windows)]
pub mod wintun_device;
#[cfg(windows)]
pub use socket_pin::pin_outbound_socket;

/// File creation policy for private append journals. Unix creation is 0600;
/// Windows callers must use their protected journal directory and inherited
/// ACL. Read/write, truncation and locking remain explicit at the call site.
pub fn owner_private_open_options() -> std::fs::OpenOptions {
    let mut options = std::fs::OpenOptions::new();
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
