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
        });
    let result = match result {
        Ok(request) => match swirl_subscription::profile::project_format(
            &request.format,
            &request.configuration,
        ) {
            Ok(configuration) => json!({"schema":1,"ok":true,"configuration":configuration,
                "safe_node_fallback":swirl_subscription::profile::node_only_fallback_allowed(&request.format,&request.configuration),
                "has_profile_semantics":swirl_subscription::profile::has_profile_semantics(&request.format,&request.configuration),
                "network_verified":false}),
            Err(error) => json!({"schema":1,"ok":false,"error":error.code,"field":error.field,
                "safe_node_fallback":swirl_subscription::profile::node_only_fallback_allowed(&request.format,&request.configuration),
                "network_verified":false}),
        },
        Err((code, field)) => {
            json!({"schema":1,"ok":false,"error":code,"field":field,"safe_node_fallback":false,"network_verified":false})
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

    #[test]
    fn complete_ini_document_is_validated_in_portable_rust_including_rejected_sections() {
        let document = "[General]\ndns-server=192.0.2.53\nipv6=false\n[Proxy]\nA=socks5,proxy.invalid,1080\n[Proxy Group]\nroute=select,A,DIRECT\n[Rule]\nFINAL,route\n";
        let request = json!({"format":"ini","configuration":{"document":document}});
        let result = call(&serde_json::to_vec(&request).unwrap());
        assert_eq!(result["ok"], true);
        assert_eq!(result["configuration"]["rules"], json!(["MATCH,route"]));
        assert_eq!(result["configuration"]["dns"]["queryFamily"], "ipv4_only");
        assert_eq!(result["network_verified"], false);
        for suffix in [
            "[Script]\nrequest=PRIVATE",
            "[Remote Proxy]\nProvider=https://private.invalid?token=PRIVATE",
        ] {
            let request =
                json!({"format":"ini","configuration":{"document":format!("{document}{suffix}")}});
            let result = call(&serde_json::to_vec(&request).unwrap());
            assert_eq!(result["ok"], false);
            assert!(result.get("configuration").is_none());
            assert!(!result.to_string().contains("PRIVATE"));
            assert!(!result.to_string().contains("https://"));
        }
    }

    #[test]
    fn data_only_extraction_does_not_authorize_foreign_profile_execution() {
        let basic = "[Proxy]\nA=socks5,proxy.invalid,1080\n";
        let node_only = call(
            &serde_json::to_vec(&json!({"format":"ini","configuration":{"document":basic}}))
                .unwrap(),
        );
        assert_eq!(node_only["ok"], true);
        assert_eq!(node_only["has_profile_semantics"], false);
        let incompatible = "[General]\nloglevel=notify\n[Proxy]\nA=socks5,proxy.invalid,1080\n[Proxy Group]\nroute=url-test,A,url=https://example.invalid/check\n[Rule]\nFINAL,route\n";
        let recoverable = call(
            &serde_json::to_vec(&json!({"format":"ini","configuration":{"document":incompatible}}))
                .unwrap(),
        );
        assert_eq!(recoverable["ok"], false);
        assert_eq!(recoverable["safe_node_fallback"], true);
        for suffix in [
            "[Script]\nrequest=https://private.invalid/PRIVATE_TOKEN\n",
            "[MITM]\nenable=true\n",
            "[Unknown Metadata]\nfile=C:\\PRIVATE_TOKEN\n",
        ] {
            let dangerous = call(&serde_json::to_vec(&json!({"format":"ini","configuration":{"document":format!("{incompatible}{suffix}")}})).unwrap());
            assert_eq!(dangerous["ok"], false);
            assert_eq!(dangerous["safe_node_fallback"], true);
            assert_eq!(dangerous["network_verified"], false);
            assert!(!dangerous.to_string().contains("PRIVATE_TOKEN"));
            assert!(dangerous.get("configuration").is_none());
        }
        let malformed =
            call(br#"{"format":"ini","configuration":{"document":"[Proxy]"},"format":"clash"}"#);
        assert_eq!(malformed["safe_node_fallback"], false);
    }

    #[test]
    fn foreign_global_data_grants_only_node_extraction_never_native_configuration() {
        for (format, configuration) in [
            (
                "ini",
                json!({"document":"[General]\nbypass-system=true\nhttp-listen=0.0.0.0:6152\n[Proxy]\nA=socks5,proxy.invalid,1080\n[Unknown Metadata]\nprivate-value=PRIVATE_TOKEN\n"}),
            ),
            (
                "clash",
                json!({"mixed-port":7890,"allow-lan":true,"tun":{"enable":true,"auto-route":true},"script":{"code":"PRIVATE_TOKEN"},"unknown-global":{"value":"PRIVATE_TOKEN","file":"C:\\PRIVATE_TOKEN"},"rules":["MATCH,DIRECT"]}),
            ),
        ] {
            let result = call(
                &serde_json::to_vec(&json!({"format":format,"configuration":configuration}))
                    .unwrap(),
            );
            assert_eq!(result["schema"], 1);
            assert_eq!(result["ok"], false);
            assert_eq!(result["safe_node_fallback"], true);
            assert_eq!(result["network_verified"], false);
            assert!(result.get("configuration").is_none());
            assert!(!result.to_string().contains("PRIVATE_TOKEN"));
            assert!(!result.to_string().contains("0.0.0.0"));
        }
    }
}
