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
}
impl Controller {
    pub fn dispatch(&mut self, input: &[u8]) -> Value {
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
                if self.cores.len() >= 4 {
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
                self.cores
                    .get(&handle)
                    .ok_or("UnknownHandle")?
                    .configure(config)?;
                Ok(json!({"ok":true}))
            }
            Command::Select { handle, id } => {
                self.cores
                    .get(&handle)
                    .ok_or("UnknownHandle")?
                    .select_node(&id)?;
                Ok(json!({"ok":true}))
            }
            Command::Snapshot { handle } => Ok(
                json!({"ok":true,"status":self.cores.get(&handle).ok_or("UnknownHandle")?.snapshot()?}),
            ),
            Command::ProbeStart {
                handle,
                url,
                timeout_ms,
                expected_status,
            } => Ok(json!({
                "ok": true,
                "probe": self.cores.get(&handle).ok_or("UnknownHandle")?
                    .probe_start(url, timeout_ms, expected_status)?
            })),
            Command::ProbeStatus { handle } => Ok(json!({
                "ok": true,
                "probe": self.cores.get(&handle).ok_or("UnknownHandle")?.probe_status()?
            })),
            Command::ProbeCancel { handle } => Ok(json!({
                "ok": true,
                "probe": self.cores.get(&handle).ok_or("UnknownHandle")?.probe_cancel()?
            })),
            Command::SelectGroup { handle, id, member } => {
                self.cores
                    .get(&handle)
                    .ok_or("UnknownHandle")?
                    .select_group(&id, &member)?;
                Ok(json!({"ok":true}))
            }
            Command::Stop { handle } => {
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
}

#[cfg(test)]
#[path = "probe_tests.rs"]
mod probe_tests;
