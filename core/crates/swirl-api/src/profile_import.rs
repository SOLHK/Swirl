//! Offline profile semantics shared by all platform shells.
use crate::import_ffi::encoded_response;
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    format: String,
    configuration: Value,
}

fn response(input: &[u8], capacity: usize) -> Result<(usize, Option<Vec<u8>>), isize> {
    let result = swirl_subscription::parse_json_value(input)
        .map_err(|_| ("ProfileRequestSyntax", String::from("configuration")))
        .and_then(|value| {
            serde_json::from_value::<Request>(value)
                .map_err(|_| ("ProfileRequestSyntax", String::from("configuration")))
        })
        .and_then(|request| {
            swirl_subscription::profile::project_format(&request.format, &request.configuration)
                .map_err(|error| (error.code, error.field))
        });
    let result = match result {
        Ok(configuration) => {
            json!({"schema":1,"ok":true,"configuration":configuration,"network_verified":false})
        }
        Err((code, field)) => {
            json!({"schema":1,"ok":false,"error":code,"field":field,"network_verified":false})
        }
    };
    encoded_response(&result, capacity)
}

/// Validate and project an external complete profile without network or host
/// operations. The response never includes unrecognized fields or their values.
///
/// # Safety
/// Identical nonoverlapping caller-owned buffer contract to the node import
/// boundary. Input is bounded to 4 MiB and response to the shared output budget.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swirl_import_profile_v1(
    input: *const u8,
    input_len: usize,
    output: *mut u8,
    output_capacity: usize,
) -> isize {
    // SAFETY: the public contract is checked by the common import helper.
    unsafe {
        crate::import_ffi::call(
            input,
            input_len,
            output,
            output_capacity,
            4 * 1024 * 1024,
            response,
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn call(input: &[u8]) -> Value {
        // SAFETY: input remains live and immutable during both calls.
        let required = unsafe {
            swirl_import_profile_v1(input.as_ptr(), input.len(), std::ptr::null_mut(), 0)
        };
        assert!(required > 0);
        let mut short = vec![0xa5; required as usize];
        // SAFETY: output is independent and live; a short buffer must be untouched.
        assert_eq!(
            unsafe {
                swirl_import_profile_v1(
                    input.as_ptr(),
                    input.len(),
                    short.as_mut_ptr(),
                    short.len() - 1,
                )
            },
            required
        );
        assert!(short.iter().all(|b| *b == 0xa5));
        // SAFETY: exact caller-owned output, no overlap.
        assert_eq!(
            unsafe {
                swirl_import_profile_v1(
                    input.as_ptr(),
                    input.len(),
                    short.as_mut_ptr(),
                    short.len(),
                )
            },
            required
        );
        serde_json::from_slice(&short).unwrap()
    }

    #[test]
    fn complete_profiles_have_bounded_abi_and_explicit_failures() {
        let source = json!({"format":"clash","configuration":{"rules":["MATCH,DIRECT"],"dns":{"enable":true,"nameserver":["192.0.2.53"],"ipv6":false}}});
        let projected = call(&serde_json::to_vec(&source).unwrap());
        assert_eq!(projected["ok"], true);
        assert_eq!(
            projected["configuration"]["dns"]["queryFamily"],
            "ipv4_only"
        );
        for invalid in [br#"{"format":"clash","format":"ini","configuration":{}}"#.as_slice(),br#"{"format":"sing-box","configuration":{}}"#.as_slice(),br#"{"format":"clash","configuration":{"rules":["MATCH,DIRECT"],"dns":{"fallback":["https://private.invalid/?token=PRIVATE"]}}}"#.as_slice(),br#"{"format":"clash","configuration":{"rules":["MATCH,DIRECT"],"dns":{"nameserver":["192.0.2.53"],"nameserver":["192.0.2.54"]}}}"#.as_slice(),br#"{"format":"clash","configuration":{"rules":["MATCH,DIRECT"],"PRIVATE_TOKEN":{"value":"PRIVATE"}}}"#.as_slice(),br#"{"format":"clash","configuration":{"rules":["MATCH,DIRECT"],"dns":{"PRIVATE_TOKEN":"PRIVATE"}}}"#.as_slice()] {
            let result = call(invalid);
            assert_eq!(result["ok"],false);
            assert_eq!(result["network_verified"],false);
            assert!(!result.to_string().contains("PRIVATE"));
        }
    }
}
