#![allow(unsafe_code)]
use std::{ffi::c_void, os::windows::ffi::OsStrExt, path::Path};

#[link(name = "kernel32")]
unsafe extern "system" {
    fn LoadLibraryW(name: *const u16) -> *mut c_void;
    fn GetProcAddress(module: *mut c_void, name: *const u8) -> *mut c_void;
    fn FreeLibrary(module: *mut c_void) -> i32;
    fn GetLastError() -> u32;
}

const ERROR_NO_MORE_ITEMS: u32 = 259;
const RING_CAPACITY: u32 = 0x40_0000;

struct Library(*mut c_void);

impl Drop for Library {
    fn drop(&mut self) {
        if !self.0.is_null() {
            unsafe { FreeLibrary(self.0) };
        }
    }
}

fn load(path: &Path) -> Result<Library, &'static str> {
    let wide: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    // SAFETY: `wide` is a NUL-terminated path owned for this call.
    let module = unsafe { LoadLibraryW(wide.as_ptr()) };
    if module.is_null() {
        Err("WintunLibraryMissing")
    } else {
        Ok(Library(module))
    }
}

fn export(library: &Library, name: &str) -> Result<*mut c_void, &'static str> {
    let mut bytes = name.as_bytes().to_vec();
    bytes.push(0);
    // SAFETY: `library` owns a loaded module and `bytes` is a NUL-terminated name.
    let symbol = unsafe { GetProcAddress(library.0, bytes.as_ptr()) };
    if symbol.is_null() {
        Err("WintunExportMissing")
    } else {
        Ok(symbol)
    }
}

pub fn probe(path: &Path) -> Result<(), &'static str> {
    let library = load(path)?;
    for name in EXPORTS {
        export(&library, name)?;
    }
    Ok(())
}

const EXPORTS: [&str; 8] = [
    "WintunCreateAdapter",
    "WintunCloseAdapter",
    "WintunStartSession",
    "WintunEndSession",
    "WintunReceivePacket",
    "WintunReleaseReceivePacket",
    "WintunAllocateSendPacket",
    "WintunSendPacket",
];

type CreateAdapter = unsafe extern "system" fn(*const u16, *const u16, *const u8) -> *mut c_void;
type CloseAdapter = unsafe extern "system" fn(*mut c_void);
type StartSession = unsafe extern "system" fn(*mut c_void, u32) -> *mut c_void;
type EndSession = unsafe extern "system" fn(*mut c_void);
type ReceivePacket = unsafe extern "system" fn(*mut c_void, *mut u32) -> *mut u8;
type ReleaseReceive = unsafe extern "system" fn(*mut c_void, *const u8);
type AllocateSend = unsafe extern "system" fn(*mut c_void, u32) -> *mut u8;
type SendPacket = unsafe extern "system" fn(*mut c_void, *const u8);

/// Owns one Wintun adapter and its packet session. Drop ends the session
/// before the DLL is unloaded.
pub struct Session {
    library: Library,
    adapter: *mut c_void,
    session: *mut c_void,
    end: EndSession,
    close: CloseAdapter,
    receive: ReceivePacket,
    release: ReleaseReceive,
    allocate: AllocateSend,
    send: SendPacket,
}

// SAFETY: the adapter and session pointers are owned exclusively and only moved.
unsafe impl Send for Session {}

impl Session {
    pub fn receive(&mut self) -> Result<Option<Vec<u8>>, &'static str> {
        let mut size = 0u32;
        // SAFETY: `session` is the live Wintun session owned by this value.
        let packet = unsafe { (self.receive)(self.session, &mut size) };
        if packet.is_null() {
            return if unsafe { GetLastError() } == ERROR_NO_MORE_ITEMS {
                Ok(None)
            } else {
                Err("WintunReceive")
            };
        }
        let len = usize::try_from(size).map_err(|_| "WintunReceive")?;
        // SAFETY: Wintun owns `len` initialized bytes until release.
        let copy = unsafe { std::slice::from_raw_parts(packet, len) }.to_vec();
        unsafe { (self.release)(self.session, packet) };
        Ok(Some(copy))
    }

    pub fn transmit(&mut self, packet: &[u8]) -> Result<(), &'static str> {
        let len = u32::try_from(packet.len()).map_err(|_| "WintunSendLength")?;
        if len == 0 || packet.len() > 1500 {
            return Err("WintunSendLength");
        }
        // SAFETY: `session` is live and `len` is the requested allocation.
        let buffer = unsafe { (self.allocate)(self.session, len) };
        if buffer.is_null() {
            return Err("WintunSendFull");
        }
        // SAFETY: the allocation is exactly `packet.len()` writable bytes.
        unsafe { std::ptr::copy_nonoverlapping(packet.as_ptr(), buffer, packet.len()) };
        unsafe { (self.send)(self.session, buffer) };
        Ok(())
    }
}

impl Drop for Session {
    fn drop(&mut self) {
        // Keep the DLL mapped until the session and adapter handles are released.
        let _library = &self.library;
        if !self.session.is_null() {
            unsafe { (self.end)(self.session) };
            self.session = std::ptr::null_mut();
        }
        if !self.adapter.is_null() {
            unsafe { (self.close)(self.adapter) };
            self.adapter = std::ptr::null_mut();
        }
    }
}

pub fn open_session(path: &Path, name: &str) -> Result<Session, &'static str> {
    let library = load(path)?;
    let create = cast::<CreateAdapter>(export(&library, "WintunCreateAdapter")?)?;
    let close = cast::<CloseAdapter>(export(&library, "WintunCloseAdapter")?)?;
    let start = cast::<StartSession>(export(&library, "WintunStartSession")?)?;
    let end = cast::<EndSession>(export(&library, "WintunEndSession")?)?;
    let receive = cast::<ReceivePacket>(export(&library, "WintunReceivePacket")?)?;
    let release = cast::<ReleaseReceive>(export(&library, "WintunReleaseReceivePacket")?)?;
    let allocate = cast::<AllocateSend>(export(&library, "WintunAllocateSendPacket")?)?;
    let send = cast::<SendPacket>(export(&library, "WintunSendPacket")?)?;
    let adapter_name: Vec<u16> = name.encode_utf16().chain(Some(0)).collect();
    let tunnel_type: Vec<u16> = "Swirl".encode_utf16().chain(Some(0)).collect();
    // SAFETY: both names are NUL-terminated UTF-16. A null GUID lets Wintun assign one.
    let adapter = unsafe {
        create(
            adapter_name.as_ptr(),
            tunnel_type.as_ptr(),
            std::ptr::null(),
        )
    };
    if adapter.is_null() {
        return Err("WintunAdapterCreate");
    }
    // SAFETY: `adapter` is the handle just created and is closed if start fails.
    let session = unsafe { start(adapter, RING_CAPACITY) };
    if session.is_null() {
        unsafe { close(adapter) };
        return Err("WintunSessionStart");
    }
    Ok(Session {
        library,
        adapter,
        session,
        end,
        close,
        receive,
        release,
        allocate,
        send,
    })
}

fn cast<T>(ptr: *mut c_void) -> Result<T, &'static str> {
    if ptr.is_null() {
        return Err("WintunExportMissing");
    }
    // SAFETY: `T` is an `extern "system"` function pointer and `ptr` is that export.
    Ok(unsafe { std::mem::transmute_copy(&ptr) })
}
