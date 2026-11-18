//! IP Helper notification boundary. Callbacks only coalesce an atomic signal;
//! they never allocate, wait on a mutex, invoke PowerShell, or mutate networks.
use std::{
    ffi::c_void,
    io, ptr,
    sync::atomic::{AtomicBool, Ordering},
};
use windows_sys::Win32::{
    Foundation::HANDLE,
    NetworkManagement::IpHelper::{
        CancelMibChangeNotify2, MIB_IPFORWARD_ROW2, MIB_IPINTERFACE_ROW, MIB_NOTIFICATION_TYPE,
        MIB_UNICASTIPADDRESS_ROW, NotifyIpInterfaceChange, NotifyRouteChange2,
        NotifyUnicastIpAddressChange,
    },
    Networking::WinSock::AF_UNSPEC,
};

struct Signal {
    owned_index: u32,
    changed: AtomicBool,
}

/// Registers for both address families without a polling thread. The caller
/// checks `take_changed` from its existing lifecycle task, then obtains a fresh
/// snapshot outside the notification callback.
pub struct NetworkChangeWatcher {
    // Numeric handle storage keeps this safe wrapper Send+Sync without custom
    // unsafe trait impls; ownership remains exclusive to this instance.
    handles: Vec<usize>,
    signal: Option<Box<Signal>>,
}

impl NetworkChangeWatcher {
    #[allow(unsafe_code)]
    pub fn new(owned_tun_index: u32) -> io::Result<Self> {
        if owned_tun_index == 0 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "TUN interface index must be nonzero",
            ));
        }
        let mut watcher = Self {
            handles: Vec::with_capacity(3),
            signal: Some(Box::new(Signal {
                owned_index: owned_tun_index,
                changed: AtomicBool::new(false),
            })),
        };
        let context = (&mut **watcher.signal.as_mut().expect("signal just allocated")
            as *mut Signal)
            .cast::<c_void>();
        let mut handle: HANDLE = ptr::null_mut();
        // SAFETY: callbacks match the documented ABI. Box allocation is stable
        // until every notification is cancelled; initial notifications are off.
        let result = unsafe {
            NotifyIpInterfaceChange(
                AF_UNSPEC,
                Some(interface_changed),
                context,
                false,
                &mut handle,
            )
        };
        if result != 0 {
            return Err(io::Error::from_raw_os_error(result as i32));
        }
        watcher.handles.push(handle as usize);
        handle = ptr::null_mut();
        // SAFETY: same context lifetime and callback contract as above.
        let result = unsafe {
            NotifyRouteChange2(AF_UNSPEC, Some(route_changed), context, false, &mut handle)
        };
        if result != 0 {
            return Err(io::Error::from_raw_os_error(result as i32));
        }
        watcher.handles.push(handle as usize);
        handle = ptr::null_mut();
        // SAFETY: same context lifetime and callback contract as above.
        let result = unsafe {
            NotifyUnicastIpAddressChange(
                AF_UNSPEC,
                Some(address_changed),
                context,
                false,
                &mut handle,
            )
        };
        if result != 0 {
            return Err(io::Error::from_raw_os_error(result as i32));
        }
        watcher.handles.push(handle as usize);
        Ok(watcher)
    }

    pub fn take_changed(&self) -> bool {
        self.signal
            .as_ref()
            .is_some_and(|signal| signal.changed.swap(false, Ordering::AcqRel))
    }

    #[allow(unsafe_code)]
    pub fn close(&mut self) -> io::Result<()> {
        let mut failure = None;
        self.handles.retain(|handle| {
            // SAFETY: handles came from successful Notify* registrations and
            // are not otherwise exposed. Cancellation waits for callbacks; no
            // callback waits on this thread or calls cancellation itself.
            let result = unsafe { CancelMibChangeNotify2(*handle as HANDLE) };
            if result == 0 {
                false
            } else {
                failure.get_or_insert(result);
                true
            }
        });
        if let Some(error) = failure {
            Err(io::Error::from_raw_os_error(error as i32))
        } else {
            Ok(())
        }
    }
}

impl Drop for NetworkChangeWatcher {
    fn drop(&mut self) {
        if self.close().is_err() {
            // An OS cancellation error means a callback might still retain the
            // context. Retain its tiny allocation rather than risk use-after-
            // free. The helper process owns this code for its entire lifetime.
            if let Some(signal) = self.signal.take() {
                let _ = Box::leak(signal);
            }
        }
    }
}

fn mark(signal: &Signal, index: Option<u32>) {
    if index != Some(signal.owned_index) {
        signal.changed.store(true, Ordering::Release);
    }
}

#[allow(unsafe_code)]
unsafe extern "system" fn interface_changed(
    context: *const c_void,
    row: *const MIB_IPINTERFACE_ROW,
    _: MIB_NOTIFICATION_TYPE,
) {
    // SAFETY: IP Helper invokes us only while the registered Box is alive. Row
    // is optional OS-owned memory valid for this callback; only its index is read.
    let signal = unsafe { &*context.cast::<Signal>() };
    let index = if row.is_null() {
        None
    } else {
        Some(unsafe { (*row).InterfaceIndex })
    };
    mark(signal, index);
}

#[allow(unsafe_code)]
unsafe extern "system" fn route_changed(
    context: *const c_void,
    row: *const MIB_IPFORWARD_ROW2,
    _: MIB_NOTIFICATION_TYPE,
) {
    // SAFETY: same registered context/optional-row lifetime as interface_changed.
    let signal = unsafe { &*context.cast::<Signal>() };
    let index = if row.is_null() {
        None
    } else {
        Some(unsafe { (*row).InterfaceIndex })
    };
    mark(signal, index);
}

#[allow(unsafe_code)]
unsafe extern "system" fn address_changed(
    context: *const c_void,
    row: *const MIB_UNICASTIPADDRESS_ROW,
    _: MIB_NOTIFICATION_TYPE,
) {
    // SAFETY: same registered context/optional-row lifetime as interface_changed.
    let signal = unsafe { &*context.cast::<Signal>() };
    let index = if row.is_null() {
        None
    } else {
        Some(unsafe { (*row).InterfaceIndex })
    };
    mark(signal, index);
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn notifications_coalesce_and_ignore_owned_tun_changes() {
        let signal = Signal {
            owned_index: 71,
            changed: AtomicBool::new(false),
        };
        mark(&signal, Some(71));
        assert!(!signal.changed.swap(false, Ordering::AcqRel));
        mark(&signal, Some(7));
        mark(&signal, Some(8));
        assert!(signal.changed.swap(false, Ordering::AcqRel));
        assert!(!signal.changed.swap(false, Ordering::AcqRel));
    }
    #[test]
    fn registering_and_cancelling_does_not_modify_windows_network() {
        let mut watcher = NetworkChangeWatcher::new(71).unwrap();
        watcher.close().unwrap();
        watcher.close().unwrap();
    }
    #[test]
    fn watcher_is_send_sync_without_custom_unsafe_impls() {
        fn require_send_sync<T: Send + Sync>() {}
        require_send_sync::<NetworkChangeWatcher>();
    }
}
