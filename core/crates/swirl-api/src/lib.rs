//! Versioned JSON control plane. The only unsafe code copies caller-owned buffers
//! at the C ABI boundary; forwarding never calls a C++/third-party proxy core.
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::HashMap,
    sync::{Mutex, OnceLock},
};
use swirl_core::Core;
use swirl_subscription::Config;

mod control_v2;
pub mod native_tun;
#[cfg(test)]
mod native_tun_tests;
mod import_ffi;
mod node_import;
pub use node_import::swirl_import_node_v1;
mod profile_import;
pub use profile_import::swirl_import_profile_v1;
mod xray_import;
pub use xray_import::swirl_import_xray_v1;

const MAX_COMMAND: usize = 1024 * 1024;
pub const OUTPUT_CAPACITY: usize = 1024 * 1024;
#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
enum Command {
    Start {
        config: Config,
    },
    Configure {
        handle: u64,
        config: Config,
    },
    Select {
        handle: u64,
        id: String,
    },
    SelectGroup {
        handle: u64,
        id: String,
        member: String,
    },
    Snapshot {
        handle: u64,
    },
    ProbeStart {
        handle: u64,
        url: String,
        timeout_ms: Option<u64>,
        expected_status: Option<u16>,
    },
    ProbeStatus {
        handle: u64,
    },
    ProbeCancel {
        handle: u64,
    },
    Stop {
        handle: u64,
    },
}
#[derive(Default)]
pub struct Controller {
    next: u64,
    cores: HashMap<u64, Core>,
    cores_v2: HashMap<u64, swirl_core::v2::Core>,
}
impl Controller {
    pub fn dispatch(&mut self, input: &[u8]) -> Value {
        if input.is_empty() || input.len() > MAX_COMMAND {
            return json!({"ok":false,"error":"CommandSize"});
        }
        let parsed = match swirl_subscription::parse_json_value(input) {
            Ok(value) => value,
            Err(_) => return json!({"ok":false,"error":"CommandInvalidOrUnsupported"}),
        };
        if parsed.get("control_schema").is_some() {
            return control_v2::dispatch(self, input);
        }
        match self.execute(input) {
            Ok(v) => v,
            Err(code) => json!({"ok":false,"error":code}),
        }
    }
    fn execute(&mut self, input: &[u8]) -> Result<Value, &'static str> {
        if input.is_empty() || input.len() > MAX_COMMAND {
            return Err("CommandSize");
        }
        let command: Command =
            serde_json::from_slice(input).map_err(|_| "CommandInvalidOrUnsupported")?;
        match command {
            Command::Start { config } => {
                if self.cores.len() + self.cores_v2.len() >= 4 {
                    return Err("CoreLimit");
                }
                let core = Core::start(config)?;
                self.next = self.next.checked_add(1).ok_or("HandleLimit")?;
                let handle = self.next;
                let status = core.snapshot()?;
                self.cores.insert(handle, core);
                Ok(json!({"ok":true,"handle":handle,"status":status}))
            }
            Command::Configure { handle, config } => {
                if self.cores_v2.contains_key(&handle) {
                    return Err("V2MutationRequiresTransaction");
                }
                self.cores
                    .get(&handle)
                    .ok_or("UnknownHandle")?
                    .configure(config)?;
                Ok(json!({"ok":true}))
            }
            Command::Select { handle, id } => {
                if self.cores_v2.contains_key(&handle) {
                    return Err("V2MutationRequiresTransaction");
                }
                self.cores
                    .get(&handle)
                    .ok_or("UnknownHandle")?
                    .select_node(&id)?;
                Ok(json!({"ok":true}))
            }
            Command::Snapshot { handle } => {
                if let Some(core) = self.cores_v2.get(&handle) {
                    return Ok(json!({"ok":true,"status":core.snapshot()?}));
                }
                Ok(
                    json!({"ok":true,"status":self.cores.get(&handle).ok_or("UnknownHandle")?.snapshot()?}),
                )
            }
            Command::ProbeStart {
                handle,
                url,
                timeout_ms,
                expected_status,
            } => {
                if let Some(core) = self.cores_v2.get(&handle) {
                    return Ok(
                        json!({"ok":true,"probe":core.probe_start(url,timeout_ms,expected_status)?}),
                    );
                }
                Ok(json!({
                    "ok": true,
                    "probe": self.cores.get(&handle).ok_or("UnknownHandle")?
                        .probe_start(url, timeout_ms, expected_status)?
                }))
            }
            Command::ProbeStatus { handle } => {
                if let Some(core) = self.cores_v2.get(&handle) {
                    return Ok(json!({"ok":true,"probe":core.probe_status()?}));
                }
                Ok(json!({
                    "ok": true,
                    "probe": self.cores.get(&handle).ok_or("UnknownHandle")?.probe_status()?
                }))
            }
            Command::ProbeCancel { handle } => {
                if let Some(core) = self.cores_v2.get(&handle) {
                    return Ok(json!({"ok":true,"probe":core.probe_cancel()?}));
                }
                Ok(json!({
                    "ok": true,
                    "probe": self.cores.get(&handle).ok_or("UnknownHandle")?.probe_cancel()?
                }))
            }
            Command::SelectGroup { handle, id, member } => {
                if self.cores_v2.contains_key(&handle) {
                    return Err("V2MutationRequiresTransaction");
                }
                self.cores
                    .get(&handle)
                    .ok_or("UnknownHandle")?
                    .select_group(&id, &member)?;
                Ok(json!({"ok":true}))
            }
            Command::Stop { handle } => {
                if let Some(mut core) = self.cores_v2.remove(&handle) {
                    core.stop();
                    return Ok(json!({"ok":true}));
                }
                let mut core = self.cores.remove(&handle).ok_or("UnknownHandle")?;
                core.stop();
                Ok(json!({"ok":true}))
            }
        }
    }
}
static CONTROLLER: OnceLock<Mutex<Controller>> = OnceLock::new();

#[unsafe(no_mangle)]
pub extern "C" fn swirl_core_abi_version() -> u32 {
    1
}

/// Read immutable, non-secret build identity before invoking runtime commands.
/// Returns the UTF-8 byte count (without a NUL terminator), -1 for a null/short
/// output buffer, or -2 for a panic. A 4096-byte caller buffer is sufficient.
///
/// # Safety
/// output must point to output_capacity writable bytes, valid for this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swirl_core_build_info(output: *mut u8, output_capacity: usize) -> isize {
    if output.is_null() {
        return -1;
    }
    std::panic::catch_unwind(|| {
        let metadata = json!({
            "abi_version": swirl_core_abi_version(),
            "build_id": env!("SWIRL_BUILD_ID"),
            "source_sha": env!("SWIRL_SOURCE_SHA"),
            "package_version": env!("CARGO_PKG_VERSION"),
            "target": env!("SWIRL_BUILD_TARGET"),
            "control_schemas": [1,2],
            "config_schemas": [1,2],
            "capabilities": control_v2::capabilities(),
            "limits": {"command_bytes":MAX_COMMAND,"response_bytes":OUTPUT_CAPACITY,"runtime_nodes":512,"policy_groups":128,"policy_edges":4096,"admission_waiters":64,"admission_timeout_ms":2000},
        });
        let bytes = metadata.to_string().into_bytes();
        if bytes.len() > output_capacity {
            return -1;
        }
        // SAFETY: the caller owns a writable region and the size was checked.
        unsafe { std::ptr::copy_nonoverlapping(bytes.as_ptr(), output, bytes.len()) };
        bytes.len() as isize
    })
    .unwrap_or(-2)
}

/// Execute one bounded UTF-8 JSON command. Returns response length, or -1 for
/// invalid buffers, -2 for panic, -3 for unavailable state. Never unwinds into Qt.
///
/// # Safety
/// input must point to input_len initialized bytes; output must point to
/// output_capacity writable bytes. Buffers must not overlap. Both remain valid
/// for this call. Output capacity must be at least OUTPUT_CAPACITY. Serialize
/// lifecycle calls; clients must stop every handle before unloading the DLL.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swirl_core_command(
    input: *const u8,
    input_len: usize,
    output: *mut u8,
    output_capacity: usize,
) -> isize {
    if input.is_null()
        || output.is_null()
        || input_len == 0
        || input_len > MAX_COMMAND
        || output_capacity < OUTPUT_CAPACITY
    {
        return -1;
    }
    let outcome = std::panic::catch_unwind(|| {
        // SAFETY: the public ABI contract requires a readable input region.
        let command = unsafe { std::slice::from_raw_parts(input, input_len) };
        let Ok(mut controller) = CONTROLLER
            .get_or_init(|| Mutex::new(Controller::default()))
            .lock()
        else {
            return -3;
        };
        let value = controller.dispatch(command);
        let Ok(bytes) = serde_json::to_vec(&value) else {
            return -3;
        };
        if bytes.len() > output_capacity {
            return -1;
        }
        // SAFETY: caller provides nonoverlapping output of sufficient capacity.
        unsafe {
            std::ptr::copy_nonoverlapping(bytes.as_ptr(), output, bytes.len());
        }
        bytes.len() as isize
    });
    outcome.unwrap_or(-2)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_unknown_and_redacts_secrets() {
        let mut c = Controller::default();
        let value = c.dispatch(br#"{"op":"start","password":"PRIVATE_FIXTURE"}"#);
        assert_eq!(value["ok"], false);
        assert!(!value.to_string().contains("PRIVATE_FIXTURE"));
        assert_eq!(
            c.dispatch(br#"{"op":"snapshot","handle":999}"#)["error"],
            "UnknownHandle"
        );
    }

    #[test]
    fn build_identity_is_bounded_and_matches_compiled_inputs() {
        let mut output = [0xa5; 4096];
        // SAFETY: output is a writable local array of the declared size.
        let count = unsafe { swirl_core_build_info(output.as_mut_ptr(), output.len()) };
        assert!(count > 0 && count < 1024);
        let count = count as usize;
        assert!(output[count..].iter().all(|b| *b == 0xa5));
        let metadata: Value = serde_json::from_slice(&output[..count]).unwrap();
        assert_eq!(metadata["abi_version"], swirl_core_abi_version());
        assert_eq!(metadata["build_id"], env!("SWIRL_BUILD_ID"));
        assert_eq!(metadata["source_sha"], env!("SWIRL_SOURCE_SHA"));
        assert_eq!(metadata["package_version"], env!("CARGO_PKG_VERSION"));
        assert_eq!(metadata["target"], env!("SWIRL_BUILD_TARGET"));
        assert_eq!(metadata.as_object().unwrap().len(), 9);
        assert_eq!(metadata["control_schemas"], json!([1, 2]));
        assert_eq!(metadata["capabilities"]["optional"]["tun"], false);

        let mut short = [0xa5; 1];
        // SAFETY: short is a writable local array of the declared size.
        assert_eq!(unsafe { swirl_core_build_info(short.as_mut_ptr(), 1) }, -1);
        assert_eq!(short, [0xa5]);
        // SAFETY: a null pointer is explicitly rejected before dereferencing.
        assert_eq!(
            unsafe { swirl_core_build_info(std::ptr::null_mut(), 4096) },
            -1
        );
        let mut exact = vec![0; count];
        // SAFETY: exact has count writable bytes.
        assert_eq!(
            unsafe { swirl_core_build_info(exact.as_mut_ptr(), exact.len()) },
            count as isize
        );
        assert_eq!(exact, output[..count]);
    }
}

#[cfg(test)]
#[path = "probe_tests.rs"]
mod probe_tests;
