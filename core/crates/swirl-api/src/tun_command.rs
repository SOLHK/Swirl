//! Separate from `swirl_core_command` so the existing control schema stays stable.
//! Qt can call this once it grows a TUN page. The helper still refuses host mutation.
use std::sync::{Mutex, OnceLock};

use swirl_tun::Control;

static TUN: OnceLock<Mutex<Control>> = OnceLock::new();

pub fn dispatch(input: &[u8]) -> Vec<u8> {
    let Ok(mut control) = TUN.get_or_init(|| Mutex::new(Control::new())).lock() else {
        return br#"{"ok":false,"error":"TunState"}"#.to_vec();
    };
    swirl_tun::command(&mut control, input)
}

/// JSON lifecycle for the in-memory TUN controller.
///
/// Returns the response length, -1 for a bad buffer, or -2 after a panic.
/// Host routes are never changed.
///
/// # Safety
/// `input` must address `input_len` initialized bytes and `output` must address
/// `output_capacity` writable bytes. The regions must not overlap and must stay
/// valid for this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swirl_tun_command(
    input: *const u8,
    input_len: usize,
    output: *mut u8,
    output_capacity: usize,
) -> isize {
    if input.is_null() || output.is_null() || input_len == 0 || input_len > 64 * 1024 {
        return -1;
    }
    std::panic::catch_unwind(|| {
        // SAFETY: the caller owns the readable input region for this call.
        let command = unsafe { std::slice::from_raw_parts(input, input_len) };
        let bytes = dispatch(command);
        if bytes.len() > output_capacity {
            return -1;
        }
        // SAFETY: the caller owns the writable output region and the length was checked.
        unsafe { std::ptr::copy_nonoverlapping(bytes.as_ptr(), output, bytes.len()) };
        bytes.len() as isize
    })
    .unwrap_or(-2)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn abi_start_reports_running_and_still_refuses_host_changes() {
        let input = br#"{"op":"start","owner":"tun-owner-1","physical":"Ethernet","proxies":[]}"#;
        let mut output = [0u8; 1024];
        // SAFETY: both buffers are local and nonoverlapping.
        let count = unsafe {
            swirl_tun_command(
                input.as_ptr(),
                input.len(),
                output.as_mut_ptr(),
                output.len(),
            )
        };
        assert!(count > 0);
        let value: serde_json::Value = serde_json::from_slice(&output[..count as usize]).unwrap();
        assert_eq!(value["phase"], "running");
        let refused = dispatch(br#"{"op":"execute"}"#);
        let refused: serde_json::Value = serde_json::from_slice(&refused).unwrap();
        assert_eq!(refused["error"], "HostMutationNotAuthorized");
        let _ = dispatch(br#"{"op":"stop"}"#);
    }
}
