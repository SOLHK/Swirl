//! Wintun L3 packet I/O. This module never adds an IP address, route, or DNS
//! setting; those belong to the separately journaled network controller.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs::{File, OpenOptions},
    io::{self, Read},
    os::windows::fs::OpenOptionsExt,
    path::{Component, Path, PathBuf, Prefix},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WintunConfig {
    pub driver_path: PathBuf,
    /// Must match both the file and the compiled-in official release hash.
    pub expected_sha256: String,
    pub adapter_name: String,
    pub adapter_guid: u128,
    /// Power of two, 128 KiB..64 MiB. A moderate 4 MiB ring is sufficient for
    /// bounded experiments; it is not an unmeasured throughput guarantee.
    pub ring_capacity: u32,
}

/// SHA-256 of the unmodified official Wintun 0.14.1 DLL for this target.
/// Source ZIP hash: 07c256185d6ee3652e09fa55c0b673e2624b565e02c4b9091c79ca7d2f24ef51.
pub fn official_driver_sha256() -> io::Result<&'static str> {
    match std::env::consts::ARCH {
        "x86_64" => Ok("e5da8447dc2c320edc0fc52fa01885c103de8c118481f683643cacc3220dafce"),
        "x86" => Ok("d694fa46ab4cfebcb2632d094c7aa97278eef2f8052438621766d863ae98a931"),
        "aarch64" => Ok("f7ba89005544be9d85231a9e0d5f23b2d15b3311667e2dad0debd344918a3f80"),
        "arm" => Ok("daad267411ecdc70a0535e274d2c3e9da3d0084bdac7662cb8424dd4a031b4d9"),
        _ => Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "Wintun release has no DLL for this architecture",
        )),
    }
}

pub struct WintunDevice {
    session: Arc<wintun::Session>,
    adapter: Arc<wintun::Adapter>,
    closed: AtomicBool,
    // Prevent writes/deletion between verification and loading, and retain the
    // lock for the device's lifetime. The DLL directory must also be trusted.
    _driver_file: File,
}

impl WintunDevice {
    /// Creates a dedicated adapter. Existing adapters are never automatically
    /// opened, renamed, deleted, or adopted, even if their name is "Swirl".
    pub fn create(config: &WintunConfig) -> io::Result<Self> {
        if config.adapter_name.is_empty()
            || config.adapter_name.encode_utf16().count() > 127
            || config.adapter_name.contains('\0')
            || config.adapter_guid == 0
            || !(wintun::MIN_RING_CAPACITY..=wintun::MAX_RING_CAPACITY)
                .contains(&config.ring_capacity)
            || !config.ring_capacity.is_power_of_two()
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "invalid Wintun adapter configuration",
            ));
        }
        let (path, driver_file) = verify_driver(config)?;
        let library = load_verified_library(&path)?;
        if wintun::Adapter::open(&library, &config.adapter_name).is_ok() {
            return Err(io::Error::new(
                io::ErrorKind::AlreadyExists,
                "adapter name already exists; recover the previous owner before starting",
            ));
        }
        let adapter = wintun::Adapter::create(
            &library,
            &config.adapter_name,
            "Swirl Native TUN",
            Some(config.adapter_guid),
        )
        .map_err(driver_error)?;
        let session = Arc::new(
            adapter
                .start_session(config.ring_capacity)
                .map_err(driver_error)?,
        );
        Ok(Self {
            session,
            adapter,
            closed: AtomicBool::new(false),
            _driver_file: driver_file,
        })
    }

    pub fn interface_index(&self) -> io::Result<u32> {
        self.adapter.get_adapter_index().map_err(driver_error)
    }

    pub fn adapter_guid(&self) -> u128 {
        self.adapter.get_guid()
    }

    /// Copy one L3 packet into a reusable caller buffer, releasing its Wintun
    /// ring slot immediately. Call only from one dedicated blocking reader.
    pub fn receive_blocking(&self, buffer: &mut Vec<u8>) -> io::Result<()> {
        self.check_open()?;
        let packet = self.session.receive_blocking().map_err(driver_error)?;
        buffer.clear();
        buffer.extend_from_slice(packet.bytes());
        Ok(())
    }

    /// Drain a bounded batch after `receive_blocking`, checking the shutdown
    /// flag between packets even under sustained incoming traffic.
    pub fn try_receive(&self, buffer: &mut Vec<u8>) -> io::Result<bool> {
        self.check_open()?;
        let Some(packet) = self.session.try_receive().map_err(driver_error)? else {
            return Ok(false);
        };
        buffer.clear();
        buffer.extend_from_slice(packet.bytes());
        Ok(true)
    }

    /// Deliver one complete IP packet to Windows. Allocation failure propagates
    /// as an error; callers must apply bounded backpressure/drop accounting.
    pub fn send(&self, bytes: &[u8]) -> io::Result<()> {
        self.check_open()?;
        let size = u16::try_from(bytes.len()).map_err(|_| {
            io::Error::new(
                io::ErrorKind::InvalidInput,
                "Wintun packet exceeds 65535 bytes",
            )
        })?;
        if size == 0 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "empty IP packet",
            ));
        }
        let mut packet = self
            .session
            .allocate_send_packet(size)
            .map_err(driver_error)?;
        // No fallible operation is allowed between allocate and send: dropping
        // an unsent Wintun packet would stall later packets in the send ring.
        packet.bytes_mut().copy_from_slice(bytes);
        self.session.send_packet(packet);
        Ok(())
    }

    /// Wake a blocking reader before joining its thread. No route/DNS changes
    /// happen here; the caller must recover its journal before dropping us.
    pub fn shutdown(&self) -> io::Result<()> {
        self.closed.store(true, Ordering::Release);
        self.session.shutdown().map_err(driver_error)
    }

    fn check_open(&self) -> io::Result<()> {
        if self.closed.load(Ordering::Acquire) {
            return Err(io::Error::new(
                io::ErrorKind::Interrupted,
                "Wintun session is stopping",
            ));
        }
        Ok(())
    }
}

impl Drop for WintunDevice {
    fn drop(&mut self) {
        let _ = self.shutdown();
    }
}

fn verify_driver(config: &WintunConfig) -> io::Result<(PathBuf, File)> {
    if !config.driver_path.is_absolute() || config.expected_sha256 != official_driver_sha256()? {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "Wintun requires an absolute path and the pinned official architecture hash",
        ));
    }
    let path = std::fs::canonicalize(&config.driver_path)?;
    match path.components().next() {
        Some(Component::Prefix(prefix))
            if matches!(prefix.kind(), Prefix::Disk(_) | Prefix::VerbatimDisk(_)) => {}
        _ => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "Wintun driver must be on a local drive, not a network share or device path",
            ));
        }
    }
    // FILE_SHARE_READ only: disallow modifying/replacing a verified driver.
    let mut file = OpenOptions::new()
        .read(true)
        .share_mode(0x0000_0001)
        .open(&path)?;
    let length = file.metadata()?.len();
    if !(1..=16 * 1024 * 1024).contains(&length) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid Wintun DLL length",
        ));
    }
    let mut hash = Sha256::new();
    let mut bytes = [0u8; 64 * 1024];
    loop {
        let read = file.read(&mut bytes)?;
        if read == 0 {
            break;
        }
        hash.update(&bytes[..read]);
    }
    if format!("{:x}", hash.finalize()) != config.expected_sha256 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Wintun DLL digest does not match the official release",
        ));
    }
    Ok((path, file))
}

#[allow(unsafe_code)]
fn load_verified_library(path: &Path) -> io::Result<wintun::Wintun> {
    // SAFETY: the only caller first locks and hashes the official unmodified
    // DLL for this target. The path is absolute/local. Dependent DLL resolution
    // is restricted to System32; PATH/current-directory searches are disabled.
    let library = unsafe {
        libloading::os::windows::Library::load_with_flags(
            path,
            libloading::os::windows::LOAD_LIBRARY_SEARCH_SYSTEM32,
        )
    }
    .map_err(io::Error::other)?;
    // SAFETY: the verified Wintun 0.14.1 DLL implements the documented API
    // expected by wintun 0.5.1; the binding retains the library's lifetime.
    unsafe { wintun::load_from_library(library) }.map_err(driver_error)
}

fn driver_error(error: wintun::Error) -> io::Error {
    match error {
        wintun::Error::ShuttingDown => {
            io::Error::new(io::ErrorKind::Interrupted, "Wintun session is stopping")
        }
        // WintunAllocateSendPacket uses ERROR_BUFFER_OVERFLOW when its bounded
        // ring is full. Let the packet pump apply its backpressure policy.
        wintun::Error::Io(error) if error.raw_os_error() == Some(111) => {
            io::Error::new(io::ErrorKind::WouldBlock, error)
        }
        wintun::Error::Io(error) => error,
        other => io::Error::other(other),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_arbitrary_library_before_loading_or_creating_adapter() {
        let config = WintunConfig {
            driver_path: "wintun.dll".into(),
            expected_sha256: "0".repeat(64),
            adapter_name: "Swirl Test".into(),
            adapter_guid: 1,
            ring_capacity: 4 * 1024 * 1024,
        };
        assert_eq!(
            WintunDevice::create(&config).err().unwrap().kind(),
            io::ErrorKind::InvalidInput
        );
    }

    #[test]
    fn rejects_unbounded_ring_before_driver_access() {
        let config = WintunConfig {
            driver_path: "C:\\missing\\wintun.dll".into(),
            expected_sha256: official_driver_sha256().unwrap().into(),
            adapter_name: "Swirl Test".into(),
            adapter_guid: 1,
            ring_capacity: u32::MAX,
        };
        assert_eq!(
            WintunDevice::create(&config).err().unwrap().kind(),
            io::ErrorKind::InvalidInput
        );
    }

    #[test]
    fn device_can_cross_threads_without_custom_unsafe_impls() {
        fn require_send_sync<T: Send + Sync>() {}
        require_send_sync::<WintunDevice>();
    }
}
