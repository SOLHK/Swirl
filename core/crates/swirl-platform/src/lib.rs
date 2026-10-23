//! Host integration shared by the portable core through a platform-neutral API.
//! Mobile applications supply hosts through configuration; compiling a target
//! does not grant VPN permissions or implement a system tunnel adapter.
use std::path::PathBuf;

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
