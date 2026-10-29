//! Host integration shared by the portable core through a platform-neutral API.
//! Mobile applications supply hosts through configuration. Desktop TUN adapters
//! require an explicitly invoked privileged helper; importing this crate never
//! changes network settings or loads a driver.
use std::path::PathBuf;

pub mod network_transaction;

#[cfg(windows)]
mod socket_pin;
#[cfg(windows)]
pub mod windows_network;
#[cfg(windows)]
mod windows_notify;
#[cfg(windows)]
pub mod wintun_device;
#[cfg(windows)]
pub use socket_pin::pin_outbound_socket;

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
