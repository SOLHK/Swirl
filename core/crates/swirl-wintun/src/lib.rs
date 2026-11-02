//! Runtime loader for the signed Wintun 0.14 DLL.
//!
//! The driver source is GPL-2.0 and is not compiled or linked. Official
//! prebuilt `wintun.dll` builds may be placed beside a future helper under
//! WireGuard's prebuilt-binaries license; this crate only resolves the
//! documented `wintun.h` entry points. It never creates an adapter unless
//! `open_session` is called with authorization, and tests do not do that.

use std::path::Path;

#[cfg(windows)]
mod ffi;

/// Confirm the DLL exports the session API. Does not create an adapter.
pub fn probe(dll: &Path) -> Result<(), &'static str> {
    #[cfg(windows)]
    {
        ffi::probe(dll)
    }
    #[cfg(not(windows))]
    {
        let _ = dll;
        Err("WintunRequiresWindows")
    }
}

/// An open Wintun adapter session. Drop ends the session and closes the adapter.
/// Routes and DNS are not changed here.
pub struct Session {
    #[cfg(windows)]
    inner: ffi::Session,
    #[cfg(not(windows))]
    _private: (),
}

impl Session {
    pub fn receive(&mut self) -> Result<Option<Vec<u8>>, &'static str> {
        #[cfg(windows)]
        {
            self.inner.receive()
        }
        #[cfg(not(windows))]
        {
            let _ = self;
            Err("WintunRequiresWindows")
        }
    }

    pub fn transmit(&mut self, packet: &[u8]) -> Result<(), &'static str> {
        #[cfg(windows)]
        {
            self.inner.transmit(packet)
        }
        #[cfg(not(windows))]
        {
            let _ = (self, packet);
            Err("WintunRequiresWindows")
        }
    }
}

/// Open a packet session. Refused unless the caller has an explicit
/// authorization bit. This process does not change routes or DNS.
pub fn open_session(dll: &Path, name: &str, authorized: bool) -> Result<Session, &'static str> {
    if !authorized {
        return Err("AdapterCreateNotAuthorized");
    }
    if name.is_empty() || name.len() > 128 || name.chars().any(|c| c.is_control()) {
        return Err("WintunAdapterName");
    }
    #[cfg(windows)]
    {
        Ok(Session {
            inner: ffi::open_session(dll, name)?,
        })
    }
    #[cfg(not(windows))]
    {
        let _ = dll;
        Err("WintunRequiresWindows")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn probe_and_open_do_not_touch_host_routes() {
        let missing = Path::new("missing-wintun.dll");
        let probed = probe(missing).unwrap_err();
        #[cfg(windows)]
        assert_eq!(probed, "WintunLibraryMissing");
        #[cfg(not(windows))]
        assert_eq!(probed, "WintunRequiresWindows");
        assert_eq!(
            open_session(missing, "Swirl", false).err(),
            Some("AdapterCreateNotAuthorized")
        );
    }
}
